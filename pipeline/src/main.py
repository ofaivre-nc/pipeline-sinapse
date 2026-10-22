#!/usr/bin/env python3
"""
Point d'entree du pipeline — chaine minimale : ADF locaux -> faits de page -> graphe.

VERSION : 1.0 — collecte des faits (contracts/faits.md), mode incremental, graphe

Usage :
    python pipeline/src/main.py --adf <dossier des ADF> --pages <metadonnees> --sortie <faits>
                                [--complet] [--config <faits_types.json>]

  --adf     dossier contenant les ADF bruts `{page_id}.json`, cherches recursivement
            (sortie de recense_adf.py --pages --out, ou fixtures par type).
  --pages   metadonnees des pages : `pages.json` des fixtures (cle `pages`) ou rapport
            `*_pages.json` de recense_adf.py (cle `pages_analysees`).
  --sortie  dossier des faits : `{page_id}.json`, `graphe.json`, `rapport_collecte.json`.
  --complet relit toutes les pages, sans tenir compte des faits existants.

L'export depuis Confluence reste a recense_adf.py (lance par l'utilisateur, jeton dans
l'environnement) ; ce module ne joint jamais le reseau. Le rendu `.md` sera branche ici
avec l'inventaire (`md_path`), a l'etape suivante.

MODE INCREMENTAL : une page n'est relue que si sa version Confluence, la version du
collecteur ou celle de sa configuration a change. S'y ajoutent les pages qui INCLUENT
un extrait d'une page relue : le statut de leurs inclusions peut avoir change sans
qu'elles-memes aient bouge. Le graphe est toujours reconstruit en entier.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import re

import faits as fx
import graphe as gr
import multiexcerpt as mx
import resolver as rs
from inventory import (build_inventory, chaine_ascendance, module_par_titre, normalize_title,
                       type_par_titre)

VERSION = "1.1"
RE_QUARTIER = re.compile(r"^Q-[A-Z0-9_.\-]+", re.I)


# ==========================================================================
# Entrees
# ==========================================================================

def charge_metadonnees(chemin):
    """Liste de {id, titre, type?, version, parent_id?} depuis l'un des deux formats."""
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if "pages" in donnees:
        return [{"id": str(p["id"]), "titre": p["titre"], "type": p.get("type"),
                 "version": p.get("version"), "parent_id": p.get("parent_id")}
                for p in donnees["pages"]]
    if "pages_analysees" in donnees:
        # spec_type de recense_adf.py classe les SA en AUTRE : le type est retire du titre.
        return [{"id": str(p["id"]), "titre": p["title"], "type": None,
                 "version": p.get("version"), "parent_id": p.get("parent_id")}
                for p in donnees["pages_analysees"]]
    raise SystemExit(f"format de metadonnees non reconnu : {chemin}")


def index_adf(dossier):
    """page_id -> chemin du fichier ADF, cherche recursivement."""
    fichiers = {}
    for chemin in Path(dossier).rglob("*.json"):
        if chemin.stem.isdigit():
            fichiers.setdefault(chemin.stem, chemin)
    return fichiers


class FournisseurLocal:
    """Fournisseur du resolver adosse aux ADF du disque : aucun appel reseau."""

    def __init__(self, pages, fichiers):
        self.pages = {p["id"]: p for p in pages}
        self.fichiers = fichiers
        self.par_titre_ = {mx.clean_page_title(p["titre"]): p["id"] for p in pages}
        self._cache = {}

    def adf(self, page_id):
        if page_id not in self._cache:
            self._cache[page_id] = json.loads(self.fichiers[page_id].read_text(encoding="utf-8"))
        return self._cache[page_id]

    def par_identifiant(self, page_id):
        page_id = str(page_id)
        if page_id not in self.pages or page_id not in self.fichiers:
            return None
        return page_id, self.pages[page_id]["titre"], self.adf(page_id)

    def par_titre(self, titre):
        page_id = self.par_titre_.get(mx.clean_page_title(titre))
        return self.par_identifiant(page_id) if page_id else None


def type_de(page, classement=None):
    if page.get("type"):
        return page["type"]
    if classement and classement.get("type"):
        return classement["type"]
    return type_par_titre(normalize_title(page["titre"])) or "AUTRE"


def classe(pages):
    """Classement de l'inventaire (type, module par l'arborescence, exclusions) et quartiers.

    Le quartier est la page parente de la page chapeau du SF (decision du 2026-10-22) :
    on remonte l'arborescence jusqu'a la page de type MODULE, puis on lit le titre de
    son parent (« Q-SOCLE »). Sans arborescence complete (pages de test isolees), le
    module se lit dans le titre et le quartier reste inconnu.
    """
    brutes = [{"id": p["id"], "title": p["titre"], "version": p.get("version"),
               "parent_id": p.get("parent_id")} for p in pages]
    inventaire = {c["id"]: c for c in build_inventory(brutes)["pages"]}
    par_id = {b["id"]: b for b in brutes}
    for page_id, classement in inventaire.items():
        chaine = [page_id] + chaine_ascendance(page_id, par_id)
        for rang, ancetre in enumerate(chaine):
            if (inventaire.get(ancetre) or {}).get("type") == "MODULE" and rang + 1 < len(chaine):
                titre = normalize_title((par_id.get(chaine[rang + 1]) or {}).get("title"))
                trouve = RE_QUARTIER.match(titre)
                if trouve:
                    classement["quartier"] = trouve.group(0).upper()
                break
    return inventaire


# ==========================================================================
# Plan incremental
# ==========================================================================

def faits_existants(sortie, page_id):
    chemin = Path(sortie) / f"{page_id}.json"
    if not chemin.exists():
        return None
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except ValueError:
        return None


def a_relire(page, existant, config_version):
    if existant is None or existant.get("schema_version") != fx.SCHEMA_VERSION:
        return "nouvelle"
    if existant["page"].get("parse_status") == "failed":
        return "echec precedent"
    if existant["page"].get("confluence_version") != page.get("version"):
        return "version modifiee"
    if existant.get("collecteur_version") != fx.VERSION:
        return "collecteur modifie"
    if existant.get("config_version") != config_version:
        return "configuration modifiee"
    return None


def plan(pages, sortie, config_version, complet):
    """{page_id: motif} des pages a relire, dependances d'inclusion comprises."""
    existants = {p["id"]: faits_existants(sortie, p["id"]) for p in pages}
    motifs = {}
    for page in pages:
        motif = "run complet" if complet else a_relire(page, existants[page["id"]], config_version)
        if motif:
            motifs[page["id"]] = motif
    titres_relus = {mx.clean_page_title(p["titre"]) for p in pages if p["id"] in motifs}
    for page in pages:
        existant = existants[page["id"]]
        if page["id"] in motifs or existant is None:
            continue
        sources = {mx.clean_page_title(i.get("page_source"))
                   for i in existant.get("inclusions", [])}
        if sources & titres_relus:
            motifs[page["id"]] = "inclut une page relue"
    return motifs


# ==========================================================================
# Run
# ==========================================================================

def ecrit_json(chemin, donnees):
    temporaire = Path(str(chemin) + ".tmp")
    temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    temporaire.replace(chemin)


def execute(adf, pages_meta, sortie, complet=False, config=None):
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    config = fx.charge_config(config)
    pages = charge_metadonnees(pages_meta)
    fichiers = index_adf(adf)
    sans_adf = [p for p in pages if p["id"] not in fichiers]
    pages = [p for p in pages if p["id"] in fichiers]

    fournisseur = FournisseurLocal(pages, fichiers)
    carte = {mx.clean_page_title(p["titre"]): p["id"] for p in pages}
    resolveur = rs.Resolveur(fournisseur, carte)
    collecteur = fx.Collecteur(config, {p["id"]: normalize_title(p["titre"]) for p in pages})
    inventaire = classe(pages)
    # Une page exclue (archive, copie, brouillon, ou rangee sous une telle page) reste
    # lisible par le resolver comme source d'extraits, mais n'a pas de faits.
    exclues = [p for p in pages if inventaire[p["id"]].get("excluded")]
    pages = [p for p in pages if not inventaire[p["id"]].get("excluded")]
    motifs = plan(pages, sortie, config.get("version"), complet)

    rapport = {"run_version": VERSION, "collecteur_version": fx.VERSION,
               "config_version": config.get("version"),
               "genere_le": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "mode": "complet" if complet else "incremental",
               "pages": len(pages), "relues": [], "inchangees": 0, "echecs": [],
               "partielles": [], "sans_adf": [p["id"] for p in sans_adf],
               "exclues": [{"id": p["id"], "titre": p["titre"],
                            "motif": inventaire[p["id"]].get("exclusion_reason")} for p in exclues]}

    for page in pages:
        if page["id"] not in motifs:
            rapport["inchangees"] += 1
            continue
        classement = inventaire[page["id"]]
        type_page = type_de(page, classement)
        meta = {"id": page["id"], "titre": page["titre"], "type": type_page,
                "parent_id": page.get("parent_id"), "confluence_version": page.get("version"),
                "module": classement.get("module") or module_par_titre(normalize_title(page["titre"])),
                "quartier": classement.get("quartier")}
        try:
            adf_page = fournisseur.adf(page["id"])
            try:
                _, faits_resolver = resolveur.resout(adf_page, page["titre"], page["id"])
                erreur_resolution = None
            except mx.ResolutionError as erreur:
                # Definition en double (contrat normalisation_adf.md §1.8) : le resolver
                # leve, a raison. La page garde ses faits, sans le statut de ses inclusions,
                # et l'erreur devient un fait : c'est le cas que K57 doit signaler.
                faits_resolver, erreur_resolution = [], str(erreur)
            faits = collecteur.collecte(adf_page, meta, faits_resolver)
            if erreur_resolution:
                faits["inconnus"].append({"ou": {}, "quoi": "resolution", "valeur": erreur_resolution})
                faits["page"]["parse_status"] = "partial"
        except (mx.ResolutionError, KeyError, ValueError, TypeError) as erreur:
            # Une page en echec n'interrompt pas le run : elle est listee et retentee
            # au run suivant (parse_status failed force la relecture).
            faits = {"schema_version": fx.SCHEMA_VERSION, "collecteur_version": fx.VERSION,
                     "config_version": config.get("version"),
                     "genere_le": rapport["genere_le"],
                     "page": dict(fx.sans_null(meta), parse_status="failed"),
                     "erreur": f"{type(erreur).__name__} : {erreur}"}
            rapport["echecs"].append({"id": page["id"], "titre": page["titre"],
                                      "erreur": faits["erreur"]})
        fx.ecrit_faits(faits, sortie)
        rapport["relues"].append({"id": page["id"], "titre": page["titre"],
                                  "motif": motifs[page["id"]]})

    tous = [f for f in (faits_existants(sortie, p["id"]) for p in pages) if f]
    for faits in tous:
        if faits["page"].get("parse_status") == "partial":
            rapport["partielles"].append({"id": faits["page"]["id"], "titre": faits["page"]["titre"],
                                          "inconnus": len(faits.get("inconnus", []))})
    valides = [f for f in tous if f["page"].get("parse_status") != "failed"]
    ecrit_json(sortie / "graphe.json", gr.construit_graphe(valides))
    ecrit_json(sortie / "rapport_collecte.json", rapport)
    return rapport


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collecte des faits des pages SINAPSE")
    parser.add_argument("--adf", required=True, help="dossier des ADF bruts {page_id}.json")
    parser.add_argument("--pages", required=True, help="metadonnees des pages (json)")
    parser.add_argument("--sortie", required=True, help="dossier des faits")
    parser.add_argument("--complet", action="store_true", help="relire toutes les pages")
    parser.add_argument("--config", help="configuration du collecteur (faits_types.json)")
    args = parser.parse_args(argv)
    rapport = execute(args.adf, args.pages, args.sortie, args.complet, args.config)
    print(f"main v{VERSION} - {rapport['mode']} : {rapport['pages']} pages, "
          f"{len(rapport['relues'])} relues, {rapport['inchangees']} inchangees, "
          f"{len(rapport['echecs'])} en echec, {len(rapport['partielles'])} partielles, "
          f"{len(rapport['sans_adf'])} sans ADF")
    for echec in rapport["echecs"]:
        print(f"  ECHEC {echec['id']} : {echec['erreur']}")
    return 1 if rapport["echecs"] else 0


if __name__ == "__main__":
    sys.exit(main())
