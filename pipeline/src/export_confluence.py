#!/usr/bin/env python3
"""
Export incremental des pages Confluence : seules les pages nouvelles ou modifiees sont lues.

VERSION : 1.0 — liste de l'espace en un passage, ADF par lots, delta par version.number

Deroulement :
  1. liste de TOUTES les pages de l'espace (API v2, 250 par appel : moins d'une seconde
     pour 621 pages), avec titre, page parente et numero de version ;
  2. perimetre : les descendantes des racines demandees (groupe A par defaut) ;
  3. delta par `version.number` contre le `pages.json` du passage precedent (jamais par
     date : decision du depot) ;
  4. ADF des seules pages nouvelles ou modifiees, par lots de 50 identifiants ;
  5. `pages.json` reecrit : le format que lit main.py (cle `pages`).

Sortie (--sortie) :
  pages.json          metadonnees du perimetre : id, titre, version, version_date, parent_id
  adf/{page_id}.json  ADF brut ; celui d'une page sortie du perimetre est supprime
  export.json         bilan du passage : nouvelles, modifiees, supprimees, inchangees

Authentification : ATLASSIAN_EMAIL et ATLASSIAN_API_TOKEN en variables d'environnement
(tools/exporter_adf.py de sinapse-skills les lit dans .env). Le jeton n'est jamais affiche.

Usage :
    python pipeline/src/export_confluence.py --sortie <dossier> [--racines 1474581,1277977] [--complet]
"""

import argparse
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

VERSION = "1.0"
BASE_URL = "https://sinapse-gie-nc.atlassian.net"
API_V2 = f"{BASE_URL}/wiki/api/v2"
ESPACE = "SINAPSE"
RACINES_SPECS = ("1474581", "1277977")   # groupe A (specs), comme inventory.ROOTS_GROUPE_A
LOT = 50


class AdaptateurSysteme(HTTPAdapter):
    """Certificats verifies avec le magasin du systeme (poste qui inspecte le HTTPS)."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = ssl.create_default_context()
        return super().init_poolmanager(*args, **kwargs)


class Client:
    def __init__(self, email, jeton):
        self.session = requests.Session()
        self.session.mount("https://", AdaptateurSysteme())
        self.session.auth = HTTPBasicAuth(email, jeton)
        self.session.headers["Accept"] = "application/json"
        self.appels = 0

    def get(self, url, params=None):
        """GET avec reprise : 429 (Retry-After), Timeout et coupure reseau (.claude/rules/python.md)."""
        for tentative in range(6):
            try:
                reponse = self.session.get(url, params=params, timeout=60)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                time.sleep(2 ** tentative)
                continue
            self.appels += 1
            if reponse.status_code == 429:
                time.sleep(int(reponse.headers.get("Retry-After", 2 ** tentative)))
                continue
            reponse.raise_for_status()
            return reponse.json()
        raise RuntimeError(f"echec apres 6 tentatives : {url}")

    def pagine(self, url, params):
        while url:
            donnees = self.get(url, params)
            yield from donnees.get("results", [])
            suivant = (donnees.get("_links") or {}).get("next")
            url, params = (f"{BASE_URL}{suivant}" if suivant else None), None

    def liste_espace(self, cle=ESPACE):
        espace = self.get(f"{API_V2}/spaces", {"keys": cle})["results"][0]
        return [{"id": str(p["id"]), "titre": p.get("title"),
                 "parent_id": str(p["parentId"]) if p.get("parentId") else None,
                 "version": (p.get("version") or {}).get("number"),
                 "version_date": (p.get("version") or {}).get("createdAt")}
                for p in self.pagine(f"{API_V2}/spaces/{espace['id']}/pages",
                                     {"limit": 250, "status": "current"})]

    def adf(self, ids):
        """{page_id: ADF} d'un lot de pages. Le corps est une CHAINE JSON : double parsing."""
        resultat = {}
        for page in self.pagine(f"{API_V2}/pages", {"id": ",".join(ids), "limit": 250,
                                                    "body-format": "atlas_doc_format"}):
            brut = ((page.get("body") or {}).get("atlas_doc_format") or {}).get("value")
            if brut:
                resultat[str(page["id"])] = json.loads(brut)
        return resultat


def descendants(pages, racines):
    """Identifiants des pages sous les racines (racines exclues), arborescence reconstituee."""
    enfants = {}
    for page in pages:
        enfants.setdefault(page["parent_id"], []).append(page["id"])
    trouves, file = set(), list(racines)
    while file:
        courant = file.pop()
        for enfant in enfants.get(courant, []):
            if enfant not in trouves:
                trouves.add(enfant)
                file.append(enfant)
    return trouves


def plan(perimetre, precedent, dossier_adf, complet=False):
    """(a_lire, motifs) : pages nouvelles, modifiees, ou dont l'ADF manque."""
    anciennes = {p["id"]: p for p in precedent}
    motifs = {}
    for page in perimetre:
        avant = anciennes.get(page["id"])
        if complet:
            motifs[page["id"]] = "complet"
        elif avant is None:
            motifs[page["id"]] = "nouvelle"
        elif avant.get("version") != page["version"]:
            motifs[page["id"]] = "modifiee"
        elif not (dossier_adf / f"{page['id']}.json").exists():
            motifs[page["id"]] = "adf absent"
    return motifs


def exporte(client, sortie, racines=RACINES_SPECS, complet=False):
    sortie = Path(sortie)
    dossier_adf = sortie / "adf"
    dossier_adf.mkdir(parents=True, exist_ok=True)
    chemin_pages = sortie / "pages.json"
    precedent = json.loads(chemin_pages.read_text(encoding="utf-8"))["pages"] if chemin_pages.exists() else []

    espace = client.liste_espace()
    ids = descendants(espace, racines)
    perimetre = [p for p in espace if p["id"] in ids]
    motifs = plan(perimetre, precedent, dossier_adf, complet)

    erreurs = []
    a_lire = sorted(motifs)
    for debut in range(0, len(a_lire), LOT):
        lot = a_lire[debut:debut + LOT]
        try:
            corps = client.adf(lot)
        except (requests.HTTPError, RuntimeError) as erreur:
            erreurs += [{"id": i, "erreur": str(erreur)} for i in lot]
            continue
        for page_id in lot:
            if page_id not in corps:
                erreurs.append({"id": page_id, "erreur": "corps ADF absent"})
                continue
            temporaire = dossier_adf / f"{page_id}.json.tmp"
            temporaire.write_text(json.dumps(corps[page_id], ensure_ascii=False), encoding="utf-8")
            temporaire.replace(dossier_adf / f"{page_id}.json")

    # Une page en erreur garde la version du passage precedent : elle sera relue au suivant.
    en_erreur = {e["id"] for e in erreurs}
    anciennes = {p["id"]: p for p in precedent}
    retenues = []
    for page in perimetre:
        if page["id"] in en_erreur:
            if page["id"] in anciennes:
                retenues.append(anciennes[page["id"]])
            continue
        retenues.append(page)
    supprimees = [p for p in precedent if p["id"] not in ids]
    for page in supprimees:
        (dossier_adf / f"{page['id']}.json").unlink(missing_ok=True)

    maintenant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (sortie / "pages.json").write_text(json.dumps(
        {"_meta": {"exporte_le": maintenant, "script": f"export_confluence.py v{VERSION}",
                   "racines": list(racines)}, "pages": retenues}, ensure_ascii=False, indent=1), encoding="utf-8")
    bilan = {"exporte_le": maintenant, "version": VERSION, "pages": len(retenues),
             "nouvelles": [i for i, m in motifs.items() if m == "nouvelle"],
             "modifiees": [i for i, m in motifs.items() if m in ("modifiee", "adf absent", "complet")],
             "supprimees": [p["id"] for p in supprimees], "erreurs": erreurs, "appels": client.appels}
    (sortie / "export.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    return bilan


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export incremental des pages Confluence SINAPSE")
    parser.add_argument("--sortie", required=True, help="dossier de l'export (pages.json, adf/)")
    parser.add_argument("--racines", default=",".join(RACINES_SPECS), help="pages racines du perimetre")
    parser.add_argument("--complet", action="store_true", help="relire toutes les pages")
    args = parser.parse_args(argv)
    email, jeton = os.environ.get("ATLASSIAN_EMAIL"), os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not jeton:
        sys.exit("ERREUR : renseigner ATLASSIAN_EMAIL et ATLASSIAN_API_TOKEN")
    racines = [r.strip() for r in args.racines.split(",") if r.strip()]
    bilan = exporte(Client(email, jeton), args.sortie, racines, args.complet)
    print(f"export_confluence v{VERSION} : {bilan['pages']} pages, {len(bilan['nouvelles'])} nouvelles, "
          f"{len(bilan['modifiees'])} relues, {len(bilan['supprimees'])} supprimees, "
          f"{len(bilan['erreurs'])} en erreur, {bilan['appels']} appels")
    return 1 if bilan["erreurs"] else 0


if __name__ == "__main__":
    sys.exit(main())
