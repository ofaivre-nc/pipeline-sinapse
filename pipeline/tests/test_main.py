#!/usr/bin/env python3
"""
Tests de la chaine minimale : graphe (graphe.py) et run incremental (main.py).

Point d'entree autonome : `python pipeline/tests/test_main.py`, sans rien installer.
"""

import json
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "src"))
sys.path.insert(0, str(ICI))

import main as mn  # noqa: E402
from test_faits import check, definition, doc, inclusion, para, table, titre, txt  # noqa: E402

BASE = "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/"


def corpus():
    """Quatre pages : un CU inclut une RG qui appelle une route, exposee par une API vers un SA."""
    rg = doc(titre(3, "RG-X-CREER"),
             definition("RG-X-CREER", para(txt("Règle RG-X-CREER", "strong")),
                        para(txt("Appeler "), txt("POST /x", href=BASE + "4"),
                             txt(" puis "), txt("SA-X-CONTROLER", href=BASE + "999"))))
    cu = doc(titre(1, "Règles"), table(["Description"], [inclusion("RG-X-CREER", "SF-X: Règles de gestion consolidées", "l1")]))
    api = doc(titre(1, "1. Inventaire des routes"),
              table(["Route", "SA associés"], ["POST /x", para(txt("SA-X-CREER", href=BASE + "3"))]))
    sa = doc(titre(1, "5. Règles de gestion"), table(["Règle"], [inclusion("RG-X-CREER", "SF-X: Règles de gestion consolidées", "l2")]))
    pages = [("1", "SF-X: Règles de gestion consolidées", "RG", rg), ("2", "CU-X-CREER", "CU", cu),
             ("3", "SA-X-CREER", "SA", sa), ("4", "API-X", "API", api)]
    return pages


def ecrit_corpus(dossier, pages, versions):
    adf = Path(dossier) / "adf"
    adf.mkdir(exist_ok=True)
    for page_id, _, _, contenu in pages:
        (adf / f"{page_id}.json").write_text(json.dumps(contenu), encoding="utf-8")
    meta = {"pages": [{"id": p[0], "titre": p[1], "type": p[2], "version": versions[p[0]]}
                      for p in pages]}
    (Path(dossier) / "pages.json").write_text(json.dumps(meta), encoding="utf-8")
    return adf, Path(dossier) / "pages.json"


def verifie_run_et_graphe():
    echecs = 0
    pages = corpus()
    versions = {"1": 5, "2": 3, "3": 2, "4": 7}
    with tempfile.TemporaryDirectory() as dossier:
        adf, meta = ecrit_corpus(dossier, pages, versions)
        sortie = Path(dossier) / "faits"
        rapport = mn.execute(adf, meta, sortie)
        echecs += check(len(rapport["relues"]) == 4 and not rapport["echecs"], f"{rapport}")

        graphe = json.loads((sortie / "graphe.json").read_text(encoding="utf-8"))
        aretes = {(a["de"], a["type"], a["vers"]) for a in graphe["aretes"]}
        attendues = {("CU-X-CREER", "reference", "RG-X-CREER"),
                     ("SA-X-CREER", "reference", "RG-X-CREER"),
                     ("RG-X-CREER", "appelle", "POST /x"),
                     ("RG-X-CREER", "appelle", "SA-X-CONTROLER"),
                     ("POST /x", "expose", "SA-X-CREER")}
        echecs += check(attendues <= aretes, f"aretes manquantes : {attendues - aretes}")
        echecs += check({"vers": "SA-X-CONTROLER", "type": "appelle", "page_id": "1"}
                        in graphe["hors_corpus"],
                        f"SA appele hors corpus : {graphe['hors_corpus']}")
        cu = json.loads((sortie / "2.json").read_text(encoding="utf-8"))
        echecs += check(cu["inclusions"][0].get("statut") == "resolue", f"{cu['inclusions']}")

        rapport = mn.execute(adf, meta, sortie)
        echecs += check(rapport["relues"] == [] and rapport["inchangees"] == 4,
                        f"second run : rien a relire, {rapport['relues']}")

        # La page RG change : elle est relue, et les deux pages qui l'incluent aussi.
        versions["1"] = 6
        adf, meta = ecrit_corpus(dossier, pages, versions)
        rapport = mn.execute(adf, meta, sortie)
        relues = {r["id"]: r["motif"] for r in rapport["relues"]}
        echecs += check(relues == {"1": "version modifiee", "2": "inclut une page relue",
                                   "3": "inclut une page relue"}, f"dependances : {relues}")

        rapport = mn.execute(adf, meta, sortie, complet=True)
        echecs += check(len(rapport["relues"]) == 4, "--complet relit tout")
    return echecs


def verifie_echec_isole():
    """Une page illisible n'arrete pas le run : faits failed, relue au run suivant."""
    echecs = 0
    pages = corpus()
    with tempfile.TemporaryDirectory() as dossier:
        adf, meta = ecrit_corpus(dossier, pages, {"1": 1, "2": 1, "3": 1, "4": 1})
        (adf / "4.json").write_text("{pas du json", encoding="utf-8")
        sortie = Path(dossier) / "faits"
        rapport = mn.execute(adf, meta, sortie)
        echecs += check([e["id"] for e in rapport["echecs"]] == ["4"], f"{rapport['echecs']}")
        faits = json.loads((sortie / "4.json").read_text(encoding="utf-8"))
        echecs += check(faits["page"]["parse_status"] == "failed" and "erreur" in faits, f"{faits}")
        rapport = mn.execute(adf, meta, sortie)
        echecs += check([r["id"] for r in rapport["relues"]] == ["4"],
                        "une page en echec est retentee au run suivant")
    return echecs


VERIFICATIONS = (verifie_run_et_graphe, verifie_echec_isole)


def test_main():
    echecs = sum(v() for v in VERIFICATIONS)
    assert echecs == 0, f"{echecs} echec(s)"


if __name__ == "__main__":
    total = sum(v() for v in VERIFICATIONS)
    if total:
        print(f"ECHEC - {total} verification(s) en echec")
        sys.exit(1)
    print("OK - toutes les verifications de main et du graphe passent")
