#!/usr/bin/env python3
"""
Projections des faits — JSON carto et JSON MCD (contracts/faits.md §7).

VERSION : 1.2 — entites des aretes RG -> entite en « SF.ENTITE » (forme reconnue par la visualisation)
          1.1 — perimetre par SF, heuristique RG -> entite, fusion du JSON MCD, commande
          1.0 — noeuds, aretes structurelles, entites et relations

Condition posee le 2026-10-21 : les deux JSON se deduisent des faits par un script
COURT et sans heuristique cachee. Ce module ne lit que les faits de page et le graphe ;
il ne relit jamais l'ADF.

L'heuristique RG -> entite (aretes `lecture`, `ecriture`, `lecture_critere`, `categorie`
des RG) est celle de la procedure carto §2.6. C'est une heuristique de la PROJECTION,
jamais un fait ni un score : chaque arete porte sa `confiance`.

Aucun appel Jira ici (decision du depot) : `jira{}` et les tickets du JSON MCD sont
ajoutes ensuite par `sinapse-skills/tools/enrichir_jira.py`.

Usage :
    python pipeline/src/projections.py --faits <dossier> --sf NOTE,PORTAIL --sortie <dossier>
        [--nom palier1] [--mcd-precedent mcd_sinapse_data_*.json]
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

VERSION = "1.2"
VERBES = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Un champ du MCD dans le texte d'une regle : Entite.attribut. Les DTO (…Reponse,
# …Requete) ont la meme forme et sont ecartes, comme les entites inconnues du MCD.
RE_CHAMP = re.compile(r"(?<![\w.])([A-Z][A-Za-z0-9]*)\.([a-z][A-Za-z0-9]*)(?![\w(])")
RE_AFFECTATION = re.compile(r"\s*(?:=(?!=)|:=|<-|←)")
RE_LECTURE = re.compile(r"ENRICH|RESTITU|CONSULT|AFFICH|RECHERCH|LISTE|MAPPING")
# Dans une regle de recherche ou de controle, « Note.personneId = … » est un critere, pas une ecriture.
RE_CRITERE = re.compile(r"RECHERCH|FILTRE|TROUVER|VERIFIER|CONTROL|EXISTENCE|EXISTANCE|TRI")


def _phrase(texte):
    """Premiere ligne d'un Texte : la description courte d'un noeud carto."""
    return (texte or {}).get("texte", "").split("\n")[0].strip()


def _tickets(faits):
    return list(dict.fromkeys(t for e in faits.get("evolutions", []) for t in e.get("tickets", [])))


def _une_ligne(texte):
    """Texte d'une cellule sur une ligne, comme get_text(separator=" ") du legacy."""
    return " ".join((texte or {}).get("texte", "").split())


def _sans_inclusion(texte):
    """Texte d'une cellule, sauf s'il n'est fait que d'inclusions (contenu d'une autre page)."""
    texte = texte or {}
    if texte.get("inclusions") and not texte.get("texte", "").replace(
            "".join("{inclusion:" + i["nom"] + "}" for i in texte["inclusions"]), "").strip():
        return None
    return texte.get("texte")


def id_entite(entite, entites):
    """Identifiant d'une entite dans le JSON carto : « SF.ENTITE » en capitales (NOTE.NOTE).

    C'est la forme de la cartographie de reference du 18 octobre, et celle que l'outil de
    visualisation (carto_sinapse_*.html) reconnait comme entite : il la rapproche ensuite
    du JSON MCD par (sf + '.' + id).upper(). `entites` : {nom de l'entite: SF}.
    """
    sf = entites.get(entite) if isinstance(entites, dict) else None
    return f"{sf or 'MCD'}.{entite}".upper()


def _sans_vide(noeud):
    """Le JSON carto omet les listes et textes vides (notice §8)."""
    return {k: v for k, v in noeud.items() if v not in (None, "", [], {})}


# ==========================================================================
# Heuristique RG -> entite (procedure carto §2.6)
# ==========================================================================

def classe_regle(regle, entites, appelle_sa):
    """(categorie, confiance, [(entite, attribut, type)]) d'une regle.

    - nom en PERSISTANCE-CREATION / -MODIFICATION : tout Entite.attribut est une ecriture ;
      -SUPPRESSION : un critere de lecture (`lecture_critere`). Confiance forte : le nom
      de la regle le dit. PERSISTENCE (faute frequente) compte comme PERSISTANCE.
    - sinon le sens vient de la position : un champ suivi de `=` est ecrit, les autres lus.
    - aucun champ et un appel a un SA : `controle_integrite` (le lien est sur le SA appele).
    """
    nom = f"{regle.get('nom', '')} {regle.get('code_titre', '')}".upper().replace("PERSISTENCE", "PERSISTANCE")
    force = None
    for motif, categorie, type_ in (("PERSISTANCE-CREATION", "persistance_creation", "ecriture"),
                                    ("PERSISTANCE-MODIFICATION", "persistance_modification", "ecriture"),
                                    ("PERSISTANCE-SUPPRESSION", "persistance_suppression", "lecture_critere")):
        if motif in nom:
            force = (categorie, type_)
            break
    trouves = []
    for ligne in (regle.get("corps") or {}).get("texte", "").split("\n"):
        for champ in RE_CHAMP.finditer(ligne):
            entite, attribut = champ.groups()
            if entite not in entites or entite.endswith(("Reponse", "Requete")):
                continue
            if force:
                type_ = force[1]
            else:
                affecte = RE_AFFECTATION.match(ligne[champ.end():])
                type_ = ("lecture_critere" if RE_CRITERE.search(nom) else "ecriture") if affecte else "lecture"
            trouves.append((entite, attribut, type_))
    trouves = list(dict.fromkeys(trouves))
    if force:
        return force[0], "heuristique_v0_forte_nom_rg", trouves
    if not trouves:
        return ("controle_integrite" if appelle_sa else "validation"), "heuristique_v0", []
    if RE_LECTURE.search(nom) and all(t != "ecriture" for _, _, t in trouves):
        return "lecture", "heuristique_v0", trouves
    return "validation", "heuristique_v0", trouves


# ==========================================================================
# JSON carto (notice de cartographie §8)
# ==========================================================================

def projette_carto(pages, graphe, perimetre=None, sfs=None, entites=None):
    """JSON carto des pages CU, SA et API du perimetre.

    `perimetre` : identifiants de page ; `sfs` : modules (NOTE, PORTAIL…) ; tout si aucun.
    Les RG retenues sont celles que les CU et SA du perimetre referencent. `entites` :
    noms des entites du MCD, pour l'heuristique RG -> entite (sans eux, pas d'arete).
    Les cibles hors du perimetre vont dans `_meta.references_non_resolues`.
    """
    par_id = {f["page"]["id"]: f for f in pages}
    sfs = {s.upper().removeprefix("SF-") for s in sfs} if sfs else None

    def dans(f):
        if perimetre is not None and f["page"]["id"] not in perimetre:
            return False
        return sfs is None or f["page"].get("module") in sfs

    retenues = [f for f in pages if f["page"]["type"] in ("CU", "SA", "API") and dans(f)]
    titres = {f["page"]["titre"] for f in retenues}
    aretes = graphe["aretes"]

    references = [a for a in aretes if a["type"] == "reference" and a["de"] in titres]
    rg_ids = {a["vers"] for a in references}
    endpoints = [n for n in graphe["noeuds"]["endpoint"] if n["api"] in titres]
    ep_ids = {n["id"] for n in endpoints}
    appels_rg = {}
    for a in aretes:
        if a["type"] == "appelle":
            appels_rg.setdefault(a["de"], []).append(a["vers"])

    noeuds = {"cu": [], "endpoint": [], "sa": [], "rg": [], "api": []}
    for faits in retenues:
        page = faits["page"]
        base = {"id": page["titre"], "sf": page.get("module"), "url": page.get("url")}
        if page["type"] == "CU":
            noeuds["cu"].append(_sans_vide(dict(
                base, description=_phrase(faits.get("description")),
                habilitation=faits.get("cartouche", {}).get("habilitation", {}).get("texte"),
                tickets=_tickets(faits))))
        elif page["type"] == "SA":
            noeuds["sa"].append(_sans_vide(dict(base, description=_phrase(faits.get("objet")),
                                                tickets=_tickets(faits))))
        else:
            noeuds["api"].append(_sans_vide(dict(base, tickets=_tickets(faits))))

    expose = {a["de"]: a for a in aretes if a["type"] == "expose"}
    for noeud in endpoints:
        api = next(f for f in retenues if f["page"]["titre"] == noeud["api"])
        ligne = next((l for l in api.get("routes", [])
                      if f"{l.get('verbe')} {l.get('chemin')}" == noeud["id"]), {})
        arete = expose.get(noeud["id"])
        noeuds["endpoint"].append(_sans_vide({
            "id": noeud["id"], "api": noeud["api"],
            "sa": arete["vers"] if arete and not arete.get("confiance") else None,
            "description": _phrase(ligne.get("cellules", {}).get("objet")),
            "habilitation": _sans_inclusion(ligne.get("cellules", {}).get("habilitation")),
            "confiance": (arete or {}).get("confiance", "structure" if arete else None)}))

    edges, vues = [], set()

    def ajoute(de, vers, type_, confiance, **autres):
        cle = (de, vers, type_, autres.get("attribut"))
        if cle not in vues:
            vues.add(cle)
            edges.append(_sans_vide(dict({"from": de, "to": vers, "type": type_}, **autres,
                                         confiance=confiance)))

    pages_generiques = {}
    sa_ids = {f["page"]["titre"] for f in pages if f["page"]["type"] == "SA"}
    for noeud in graphe["noeuds"]["rg"]:
        if noeud["id"] not in rg_ids:
            continue
        source = par_id[noeud["page_id"]]
        regle = next((r for r in source.get("regles", []) if r["nom"] == noeud["id"]), {})
        appelle_sa = any(v in sa_ids or v.startswith("SA-") for v in appels_rg.get(noeud["id"], []))
        categorie, confiance, champs = classe_regle(regle, entites or set(), appelle_sa)
        noeuds["rg"].append(_sans_vide({"id": noeud["id"], "sf": noeud.get("sf"), "url": noeud.get("url"),
                                        "description": regle.get("concernant"),
                                        "categorie": categorie, "confiance": confiance}))
        if source["page"]["type"] == "GENERIQUE":
            pages_generiques[source["page"]["id"]] = source["page"]["titre"]
        for entite, attribut, type_ in champs:
            ajoute(noeud["id"], id_entite(entite, entites or {}), type_, confiance, attribut=attribut)
    for liste in noeuds.values():
        deja = set()
        liste[:] = [n for n in liste if not (n["id"] in deja or deja.add(n["id"]))]

    # CU -> endpoint : composition CU -> RG (reference) + RG -> endpoint (appelle) ; les
    # liens de route sont dans le corps des RG, pas dans les CU (contrat §6).
    types_page = {f["page"]["titre"]: f["page"]["type"] for f in retenues}
    for a in references:
        if types_page.get(a["de"]) == "CU":
            for vers in appels_rg.get(a["vers"], []):
                if vers in ep_ids:
                    ajoute(a["de"], vers, "appelle", "composition")
    for a in aretes:
        if a["type"] == "appelle" and a["de"] in titres and a["vers"] in ep_ids:
            ajoute(a["de"], a["vers"], "appelle", "lien")
    for noeud in noeuds["endpoint"]:
        arete = expose.get(noeud["id"])
        if arete:
            ajoute(noeud["id"], arete["vers"], "expose", arete.get("confiance", "structure"))
    for a in references:
        ajoute(a["de"], a["vers"], "reference", "structure")
    for rg in rg_ids:
        for vers in appels_rg.get(rg, []):
            if vers.split(" ", 1)[0] not in VERBES:
                ajoute(rg, vers, "appelle", "lien")

    connus = {n["id"] for liste in noeuds.values() for n in liste} | {id_entite(e, entites or {})
                                                                       for e in (entites or ())}
    non_resolues = sorted({e["to"] for e in edges if e["to"] not in connus})
    return {
        "_meta": _sans_vide({
            "projection_version": VERSION,
            "exportDate": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sf_scope": sorted(sfs) if sfs else None,
            "pages_generiques": [{"id": i, "titre": t} for i, t in sorted(pages_generiques.items())],
            "pages_connues": [_sans_vide({"id": f["page"]["id"], "type": f["page"]["type"],
                                          "sf": f["page"].get("module"), "titre": f["page"]["titre"],
                                          "confluence_version": f["page"].get("confluence_version")})
                              for f in retenues],
            "methode_rg_entite": "heuristique v0 (procedure carto §2.6) : Entite.attribut du corps de la RG, "
                                 "entite validee contre le MCD ; ecriture forcee par le nom PERSISTANCE-"
                                 "CREATION/MODIFICATION, lecture_critere pour -SUPPRESSION, sinon sens par "
                                 "position (champ suivi de = : ecriture)",
            "references_non_resolues": non_resolues,
        }),
        "nodes": noeuds,
        "edges": edges,
    }


# ==========================================================================
# JSON MCD (v2.0)
# ==========================================================================

def projette_mcd(pages):
    """`entities` et `relations` du JSON MCD, depuis les faits des pages MCD.

    Les lignes et relations barrees (evolution a venir) ne sont pas projetees, comme
    le faisait le skill legacy confluence-mcd-sync. `quartiers`, `paliers` et les
    tickets viennent de l'etape Jira ou du fichier precedent (contrat §7.2).
    """
    entites, relations, vues = [], [], set()
    for faits in pages:
        if faits["page"]["type"] != "MCD":
            continue
        sf = faits["page"].get("module")
        for entite in faits.get("entites", []):
            attrs = []
            for a in entite["attributs"]:
                if a.get("barre"):
                    continue
                # Regles du legacy confluence-mcd-sync, que le fichier reel suit : format
                # sans longueur, et `commentaire` pris dans « Valeurs possibles » (sa
                # table de colonnes retenait la DERNIERE colonne qui parle de valeur).
                valeurs = _une_ligne(a.get("valeurs"))
                attrs.append({"nom": a["attribut"],
                              "designation": _une_ligne(a.get("designation")) or a["attribut"],
                              "format": " ".join(a.get("format", "").split()) or "string",
                              "commentaire": "" if valeurs == "-" else valeurs})
            entites.append({"id": entite["nom"], "label": entite["nom"], "sf": sf,
                            "attrs": attrs})
        for r in faits.get("relations", []):
            cle = "|".join(sorted((r["de"], r["vers"])))
            if r.get("barre") or cle in vues:
                continue
            vues.add(cle)
            relation = {"from": r["de"], "to": r["vers"], "cardFrom": r["card_de"],
                        "cardTo": r["card_vers"]}
            if r.get("libelle"):
                relation["name"] = r["libelle"]
            relations.append(relation)
    return {"entities": entites, "relations": relations}


def fusionne_mcd(precedent, pages):
    """JSON MCD complet : le fichier precedent, mis a jour pour les SF dont la page MCD a ete lue.

    Les entites d'un SF relu sont remplacees ; une relation est remplacee des qu'elle touche
    une entite d'un SF relu. Le reste (quartiers, paliers, couleurs, tickets, SF non relus)
    est repris tel quel : il vient de l'etape Jira ou de la saisie manuelle.
    """
    nouveau = projette_mcd(pages)
    relus = {f["page"].get("module") for f in pages if f["page"]["type"] == "MCD"}
    resultat = json.loads(json.dumps(precedent))
    anciennes = [e for e in resultat.get("entities", []) if e.get("sf") in relus]
    touchees = {e["id"] for e in anciennes} | {e["id"] for e in nouveau["entities"]}
    resultat["entities"] = [e for e in resultat.get("entities", []) if e.get("sf") not in relus] \
        + nouveau["entities"]
    cles = {"|".join(sorted((r["from"], r["to"]))) for r in nouveau["relations"]}
    resultat["relations"] = [r for r in resultat.get("relations", [])
                             if r["from"] not in touchees and r["to"] not in touchees
                             and "|".join(sorted((r["from"], r["to"]))) not in cles] + nouveau["relations"]
    pages_mcd = {f["page"].get("module"): f["page"] for f in pages if f["page"]["type"] == "MCD"}
    for quartier in resultat.get("quartiers", []):
        for sf in quartier.get("sfs", []):
            page = pages_mcd.get(sf.get("id"))
            if page:
                sf["confluencePage"] = {"title": page["titre"], "url": page.get("url")}
    meta = resultat.setdefault("_meta", {})
    meta["sf_relus_depuis_confluence"] = sorted(relus)
    meta["projection_version"] = VERSION
    return resultat


# ==========================================================================
# Commande
# ==========================================================================

def charge_faits(dossier):
    dossier = Path(dossier)
    pages = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(dossier.glob("*.json"))
             if f.stem.isdigit()]
    pages = [p for p in pages if p.get("page", {}).get("parse_status") != "failed"]
    graphe = json.loads((dossier / "graphe.json").read_text(encoding="utf-8"))
    return pages, graphe


def main(argv=None):
    parser = argparse.ArgumentParser(description="Projette les faits en JSON carto et JSON MCD")
    parser.add_argument("--faits", required=True, help="dossier des faits (sortie de main.py)")
    parser.add_argument("--sf", help="modules du perimetre, separes par des virgules (defaut : tous)")
    parser.add_argument("--nom", help="nom du perimetre dans le nom du fichier (ex. palier1)")
    parser.add_argument("--mcd-precedent", help="JSON MCD a mettre a jour (sinon : entites et relations seules)")
    parser.add_argument("--sortie", required=True, help="dossier de sortie")
    args = parser.parse_args(argv)

    pages, graphe = charge_faits(args.faits)
    sfs = [s.strip() for s in args.sf.split(",") if s.strip()] if args.sf else None
    # {entite: SF} : les entites lues dans les pages MCD l'emportent sur le fichier precedent.
    entites = {}
    precedent = None
    if args.mcd_precedent:
        precedent = json.loads(Path(args.mcd_precedent).read_text(encoding="utf-8"))
        entites.update({e["id"]: e.get("sf") for e in precedent.get("entities", [])})
    entites.update({e["id"]: e.get("sf") for e in projette_mcd(pages)["entities"]})
    horodatage = datetime.now().strftime("%Y%m%d%H%M")
    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)

    carto = projette_carto(pages, graphe, sfs=sfs, entites=entites)
    nom = args.nom or ("-".join(f"sf{s.lower().replace('.', '')}" for s in sfs) if sfs else "tout")
    chemin_carto = sortie / f"carto_sinapse_data_{nom}_{horodatage}.json"
    chemin_carto.write_text(json.dumps(carto, ensure_ascii=False, indent=1), encoding="utf-8")
    mcd = fusionne_mcd(precedent, pages) if precedent else projette_mcd(pages)
    chemin_mcd = sortie / f"mcd_sinapse_data_{horodatage}.json"
    chemin_mcd.write_text(json.dumps(mcd, ensure_ascii=False, indent=1), encoding="utf-8")

    compte = {t: len(n) for t, n in carto["nodes"].items()}
    print(f"projections v{VERSION} - carto : {compte}, {len(carto['edges'])} aretes -> {chemin_carto.name}")
    print(f"  MCD : {len(mcd['entities'])} entites, {len(mcd['relations'])} relations -> {chemin_mcd.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
