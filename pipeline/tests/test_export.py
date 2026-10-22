#!/usr/bin/env python3
"""
Tests de l'export incremental (pipeline/src/export_confluence.py), hors reseau.

Point d'entree autonome : `python pipeline/tests/test_export.py`, sans rien installer.
"""

import json
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "src"))

import export_confluence as ec  # noqa: E402


def check(condition, message):
    if not condition:
        print("ECHEC :", message)
    return 0 if condition else 1


class FauxClient:
    """L'espace : une racine, deux pages dessous, une page ailleurs."""

    def __init__(self, versions):
        self.versions = versions
        self.lus = []
        self.appels = 0

    def liste_espace(self):
        pages = [("1474581", None, "Racine"), ("10", "1474581", "SF-X"), ("11", "10", "CU-X-CREER"),
                 ("99", None, "Ailleurs")]
        return [{"id": i, "titre": t, "parent_id": p, "version": self.versions.get(i, 1),
                 "version_date": "2026-10-22T00:00:00Z"} for i, p, t in pages if i in self.versions]

    def adf(self, ids):
        self.lus += list(ids)
        return {i: {"type": "doc", "content": []} for i in ids}


def verifie_incremental():
    echecs = 0
    with tempfile.TemporaryDirectory() as dossier:
        client = FauxClient({"1474581": 1, "10": 1, "11": 1, "99": 1})
        bilan = ec.exporte(client, dossier, ["1474581"])
        echecs += check(sorted(client.lus) == ["10", "11"], f"perimetre : descendantes de la racine {client.lus}")
        pages = json.loads((Path(dossier) / "pages.json").read_text(encoding="utf-8"))["pages"]
        echecs += check(sorted(p["id"] for p in pages) == ["10", "11"] and bilan["nouvelles"] == ["10", "11"],
                        f"{pages}")

        client = FauxClient({"1474581": 1, "10": 1, "11": 2, "99": 5})
        bilan = ec.exporte(client, dossier, ["1474581"])
        echecs += check(client.lus == ["11"] and bilan["modifiees"] == ["11"],
                        f"seule la page modifiee est relue : {client.lus}")

        client = FauxClient({"1474581": 1, "10": 1})
        bilan = ec.exporte(client, dossier, ["1474581"])
        echecs += check(bilan["supprimees"] == ["11"] and not (Path(dossier) / "adf" / "11.json").exists(),
                        "page supprimee : retiree de pages.json et son ADF efface")
        client = FauxClient({"1474581": 1, "10": 1})
        ec.exporte(client, dossier, ["1474581"], complet=True)
        echecs += check(client.lus == ["10"], "--complet relit tout")
    return echecs


def test_export():
    assert verifie_incremental() == 0


if __name__ == "__main__":
    total = verifie_incremental()
    if total:
        print(f"ECHEC - {total} verification(s) en echec")
        sys.exit(1)
    print("OK - toutes les verifications de l'export passent")
