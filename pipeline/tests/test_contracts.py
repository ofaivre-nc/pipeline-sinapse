#!/usr/bin/env python3
"""
Validation de la sortie du pipeline contre les contrats commites.

C'est aujourd'hui la seule verification qui prouve que le pipeline HONORE son
propre schema au lieu de le paraphraser : test_inventory.py verifie que
assemble_inventory() produit ce que le code attend, celui-ci verifie qu'elle
produit ce que contracts/pages_inventory.schema.json exige.

FICHIER SEPARE, ET C'EST DELIBERE : il depend de `jsonschema`. La regle « les
tests tournent sur un depot fraichement clone sans rien installer » reste vraie
pour test_inventory.py et test_multiexcerpt.py, qui sont en stdlib pure.

L'absence de jsonschema fait ECHOUER ce fichier, jamais passer : un test de
contrat qui se saute quand son outil manque est vert partout ou l'outil manque,
c'est-a-dire exactement la ou on aurait besoin de lui.

  python -m pytest pipeline/tests/test_contracts.py   (ou : python test_contracts.py)
  installation : .venv\\Scripts\\python.exe -m pip install jsonschema
"""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DEPOT = RACINE.parent
sys.path.insert(0, str(RACINE / "src"))

import inventory  # noqa: E402

DUMP = RACINE / "fixtures" / "pages_classification_20260805.json"
SCHEMA_INVENTAIRE = DEPOT / "contracts" / "pages_inventory.schema.json"

TOTAL = 0

# Seule fonction de ce fichier que pytest doit collecter.
POINT_ENTREE_PYTEST = "test_contracts"


def check(condition, message):
    """Retourne 1 en cas d'echec, pour cumul dans l'appelant. Compte les verifications."""
    global TOTAL
    TOTAL += 1
    if not condition:
        print(f"ECHEC : {message}")
        return 1
    return 0


def verifie_nommage_pytest():
    """Aucune auxiliaire ne doit porter un nom que pytest collecte.

    Voir la meme fonction dans test_inventory.py pour le detail : pytest collecte
    le motif `test*`, et une auxiliaire ainsi nommee qui rend un compte d'echecs
    au lieu de lever est declaree PASSANTE par pytest 9.1.1.
    """
    echecs = 0
    collectees = sorted(nom for nom, objet in globals().items()
                        if callable(objet)
                        and getattr(objet, "__module__", None) == __name__
                        and nom.startswith("test"))
    echecs += check(
        collectees == [POINT_ENTREE_PYTEST],
        f"pytest collecterait {collectees}, attendu ['{POINT_ENTREE_PYTEST}'] — "
        f"soit une auxiliaire porte un nom en test* (elle se nomme verifie_*), soit "
        f"{POINT_ENTREE_PYTEST} est absent du namespace au moment de l'appel")
    nom_fichier = Path(__file__).name
    echecs += check(
        nom_fichier.startswith("test_") or nom_fichier.endswith("_test.py"),
        f"{nom_fichier} ne matche aucun motif de collecte pytest (test_*.py, "
        "*_test.py) : le fichier serait ignore sans un mot")
    return echecs


def verifie_outillage():
    """jsonschema present ? Son absence est un ECHEC, pas une raison de se taire."""
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return check(False,
                     "jsonschema absent : ce fichier valide les sorties contre les "
                     "contrats, il ne peut pas se sauter. Installer avec "
                     r".venv\Scripts\python.exe -m pip install jsonschema")
    return check(True, "")


def verifie_inventaire_contre_schema():
    """La sortie de assemble_inventory() valide-t-elle contre le schema commite ?"""
    from jsonschema import Draft202012Validator

    echecs = 0
    echecs += check(SCHEMA_INVENTAIRE.is_file(), f"schema absent : {SCHEMA_INVENTAIRE}")
    echecs += check(DUMP.is_file(), f"fixture absente : {DUMP}")
    if not (SCHEMA_INVENTAIRE.is_file() and DUMP.is_file()):
        return echecs

    schema = json.loads(SCHEMA_INVENTAIRE.read_text(encoding="utf-8"))

    # Le schema est-il lui-meme valide ? Un schema mal forme accepte tout en
    # silence : le valider est le prealable a s'en servir comme reference.
    try:
        Draft202012Validator.check_schema(schema)
        echecs += check(True, "")
    except Exception as exc:  # noqa: BLE001 — le motif exact part au message
        echecs += check(False, f"le schema n'est pas conforme au draft 2020-12 : {exc}")
        return echecs

    valideur = Draft202012Validator(schema)
    pages = json.loads(DUMP.read_text(encoding="utf-8"))["pages"]
    inv = inventory.assemble_inventory({"pages": pages}, complete=True,
                                       source=DUMP.name)

    erreurs = sorted(valideur.iter_errors(inv), key=lambda e: e.json_path)
    echecs += check(not erreurs,
                    f"{len(erreurs)} erreur(s) de validation contre le schema, "
                    f"premiere : "
                    + (f"{erreurs[0].json_path} — {erreurs[0].message[:160]}"
                       if erreurs else ""))

    # Un inventaire incomplet doit valider aussi : `complete: false` est un etat
    # legitime, ce n'est pas le schema qui interdit de detruire, c'est le delta.
    partiel = inventory.assemble_inventory({"pages": pages}, complete=False)
    echecs += check(not list(valideur.iter_errors(partiel)),
                    "un inventaire complete=false doit valider contre le schema")

    # Contre-epreuve : le schema doit REFUSER une enveloppe amputee. Sans elle, un
    # schema devenu permissif validerait n'importe quoi et ce test serait vert.
    for champ in ("complete", "collisions", "unclassified", "pages"):
        ampute = {c: v for c, v in inv.items() if c != champ}
        echecs += check(list(valideur.iter_errors(ampute)),
                        f"le schema doit refuser une enveloppe sans `{champ}` — "
                        "s'il l'accepte, il ne contraint plus rien")
    return echecs


def run():
    echecs = verifie_nommage_pytest()
    echecs += verifie_outillage()
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pass  # deja compte comme echec par verifie_outillage()
    else:
        echecs += verifie_inventaire_contre_schema()

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0


def test_contracts():
    """Point d'entree pytest."""
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
