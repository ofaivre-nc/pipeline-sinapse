#!/usr/bin/env python3
"""
Tests du delta — pipeline/src/delta.py.

Les onze scenarios partent d'un inventaire reellement assemble depuis
pipeline/fixtures/pages_classification_20260805.json. Les valeurs attendues sont
MESUREES : un ecart est une divergence d'implementation, pas un chiffre a mettre
a jour.

Stdlib pure — pas de jsonschema ici : ce fichier doit tourner sur un depot
fraichement clone sans rien installer.

  python -m pytest pipeline/tests/test_delta.py   (ou : python test_delta.py)
"""

import copy
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

import delta  # noqa: E402
import inventory  # noqa: E402

DUMP = RACINE / "fixtures" / "pages_classification_20260805.json"
HORODATAGE = "2026-08-08T07:00:00+11:00"

TOTAL = 0

# Seule fonction de ce fichier que pytest doit collecter.
POINT_ENTREE_PYTEST = "test_delta"


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

    Voir test_inventory.py pour le detail : pytest collecte le motif `test*`, et
    une auxiliaire ainsi nommee qui rend un compte d'echecs au lieu de lever est
    declaree PASSANTE par pytest 9.1.1.
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


# --------------------------------------------------------------------------
# Fabrique d'inventaires
# --------------------------------------------------------------------------

def inventaire_abouti():
    """Inventaire assemble depuis la fixture, tel qu'un run PRECEDENT ABOUTI.

    Toutes les pages exportees recoivent un last_exported non nul. Sans lui, le
    garde-fou (d) — page jamais ecrite — ferait tout reexporter et masquerait les
    dix autres scenarios.
    """
    pages = json.loads(DUMP.read_text(encoding="utf-8"))["pages"]
    inv = inventory.assemble_inventory({"pages": pages}, complete=True,
                                       source=DUMP.name)
    for fiche in inv["pages"].values():
        if fiche["md_path"]:
            fiche["last_exported"] = HORODATAGE
    return inv


def ids_avec_chemin(inv, combien=None):
    lot = sorted(i for i, f in inv["pages"].items() if f["md_path"])
    return lot if combien is None else lot[:combien]


def ids_sans_chemin(inv, combien=None):
    lot = sorted(i for i, f in inv["pages"].items() if not f["md_path"])
    return lot if combien is None else lot[:combien]


def compte_etats(plan, etat):
    return sum(1 for e in plan["etats"].values() if e == etat)


def verifie_scenario(numero, libelle, plan, attendu):
    """Confronte un plan a la ligne du tableau du §5. `attendu` : dict partiel."""
    echecs = 0
    obtenu = {
        "run_complet": plan["run_complet"],
        "a_exporter": len(plan["a_exporter"]),
        "suppressions": len(plan["suppressions"]),
        "retenues": len(plan["suppressions_retenues"]),
    }
    for cle, valeur in attendu.items():
        if cle == "etats":
            for etat, nb in valeur.items():
                reel = compte_etats(plan, etat)
                echecs += check(reel == nb,
                                f"scenario {numero} ({libelle}) — {etat} : {reel}, "
                                f"attendu {nb}")
            continue
        echecs += check(obtenu[cle] == valeur,
                        f"scenario {numero} ({libelle}) — {cle} : {obtenu[cle]}, "
                        f"attendu {valeur}")
    return echecs


# --------------------------------------------------------------------------
# Les onze scenarios du §5
# --------------------------------------------------------------------------

def verifie_scenarios():
    echecs = 0
    base = inventaire_abouti()

    # 1 — premier run : precedent None, pas un dictionnaire vide.
    plan = delta.compare(None, base)
    echecs += verifie_scenario(1, "premier run", plan,
                               {"run_complet": True, "a_exporter": 232,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"creation": 246}})
    echecs += check("aucun inventaire precedent" in " ".join(plan["raisons_run_complet"]),
                    "scenario 1 : la raison du run complet doit etre en clair")

    # 2 — rien n'a bouge.
    plan = delta.compare(base, inventaire_abouti())
    echecs += verifie_scenario(2, "rien n'a bouge", plan,
                               {"run_complet": False, "a_exporter": 0,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"inchangee": 246}})

    # 3 — une page modifiee : version differente, meme chemin.
    courant = inventaire_abouti()
    cible = ids_avec_chemin(courant, 1)[0]
    courant["pages"][cible]["version"] += 1
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(3, "une page modifiee", plan,
                               {"run_complet": False, "a_exporter": 1,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"modification": 1}})
    echecs += check(plan["a_exporter"] == [cible],
                    f"scenario 3 : seule {cible} doit etre exportee")

    # 4 — une page renommee : le chemin ET la version bougent.
    courant = inventaire_abouti()
    courant["pages"][cible]["version"] += 1
    courant["pages"][cible]["md_path"] = "specs/AUTRE-CHEMIN.md"
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(4, "une page renommee", plan,
                               {"run_complet": True, "a_exporter": 232,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"modification_deplacement": 1}})

    # 5 — trois pages a last_exported null.
    # COMMENTAIRE (5 vs 2) : memes versions, memes chemins que le scenario 2, et
    # pourtant trois pages a exporter. C'est last_exported SEUL qui les distingue
    # — la signature d'un run interrompu, l'inventaire s'ecrivant apres l'export.
    # Un relecteur qui « corrigerait » ce 3 en 0 desarmerait le garde-fou (d) et
    # laisserait ces pages definitivement manquantes.
    courant = inventaire_abouti()
    jamais = ids_avec_chemin(courant, 3)
    for page_id in jamais:
        courant["pages"][page_id]["last_exported"] = None
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(5, "trois pages jamais ecrites", plan,
                               {"run_complet": False, "a_exporter": 3,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"inchangee": 246}})
    echecs += check(plan["a_exporter"] == sorted(jamais),
                    "scenario 5 : exactement les trois pages jamais ecrites")

    # 6 — une page devient non exportee : retrait, donc un fichier a effacer.
    courant = inventaire_abouti()
    courant["pages"][cible]["exported"] = False
    courant["pages"][cible]["md_path"] = None
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(6, "page devenue non exportee", plan,
                               {"run_complet": True, "a_exporter": 231,
                                "suppressions": 1, "retenues": 0,
                                "etats": {"retrait": 1}})
    echecs += check(plan["suppressions"][0]["page_id"] == cible,
                    "scenario 6 : la suppression doit designer la page retiree")
    echecs += check(plan["suppressions"][0]["md_path"] == base["pages"][cible]["md_path"],
                    "scenario 6 : c'est l'ANCIEN chemin qu'il faut effacer")

    # 7 — la MEME page, mais en collision.
    # COMMENTAIRE (6 vs 7) : la meme page devenue sans chemin donne une
    # suppression au scenario 6 et rien ici. Le seul discriminant est
    # l'appartenance a courant["collisions"] — PAS le texte d'un warnings. C'est
    # la raison d'etre du champ : md_path a null et exported a false sont produits
    # a l'identique dans les deux cas, et la difference decide de l'effacement
    # d'un fichier.
    courant = inventaire_abouti()
    courant["pages"][cible]["exported"] = False
    courant["pages"][cible]["md_path"] = None
    courant["collisions"] = [{"directory_id": "1", "slug": "x",
                              "page_ids": sorted([cible, "999999999"])}]
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(7, "la meme page en collision", plan,
                               {"run_complet": False, "a_exporter": 0,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"retrait": 1}})

    # 8 — la page passe en unclassified : elle a QUITTE la carte.
    courant = inventaire_abouti()
    del courant["pages"][cible]
    courant["unclassified"] = [{"id": cible, "title": "   ", "reason": "titre absent"}]
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(8, "page passee en unclassified", plan,
                               {"run_complet": False, "a_exporter": 0,
                                "suppressions": 0, "retenues": 0})
    echecs += check(cible not in plan["etats"],
                    "scenario 8 : une page absente de courant n'a pas d'etat")

    # 9 — la page disparait de Confluence : absente, et non protegee.
    courant = inventaire_abouti()
    del courant["pages"][cible]
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(9, "page disparue de Confluence", plan,
                               {"run_complet": True, "a_exporter": 231,
                                "suppressions": 1, "retenues": 0})
    echecs += check(plan["suppressions"][0]["page_id"] == cible,
                    "scenario 9 : la suppression doit designer la page disparue")

    # 10 — collecte incomplete, quarante pages absentes.
    # COMMENTAIRE (39 et non 40) : l'une des quarante pages retirees n'avait pas
    # de md_path — il n'y a aucun fichier a supprimer, donc aucune suppression a
    # retenir. Un test qui attendrait 40 dirait que le delta compte des pages la
    # ou il doit compter des FICHIERS. La selection est explicite ci-dessous pour
    # que le 39 soit une consequence lisible, et non un hasard de tri.
    courant = inventaire_abouti()
    retirees = ids_avec_chemin(courant, 39) + ids_sans_chemin(courant, 1)
    for page_id in retirees:
        del courant["pages"][page_id]
    courant["complete"] = False
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(10, "collecte incomplete", plan,
                               {"run_complet": False, "a_exporter": 0,
                                "suppressions": 0, "retenues": 39,
                                "etats": {"inchangee": 206}})
    echecs += check(len(retirees) == 40, "scenario 10 : quarante pages retirees")
    echecs += check(all(s["md_path"] for s in plan["suppressions_retenues"]),
                    "scenario 10 : une suppression retenue porte toujours un chemin")

    # 11 — schema_version different.
    # COMMENTAIRE (11 converge avec 1) : ce scenario donne EXACTEMENT le meme plan
    # que le premier run, a la raison pres. Ce n'est pas une coincidence, c'est la
    # definition de la regle : un schema_version different fait REMPLACER le
    # precedent par None des l'entree de compare(). Aucun de ses champs n'est
    # ensuite lu — d'ou 246 `creation` et non 246 `inchangee`, et zero suppression.
    # « Traite comme absent » ne veut dire quelque chose que si rien n'est lu ;
    # calculer les etats par paires tout en refusant les suppressions ferait lire a
    # moitie un fichier declare non fiable.
    # Le prix est assume : des .md devenus orphelins survivent a ce run, faute de
    # precedent pour les reperer. Un orphelin se rattrape au run suivant, une spec
    # supprimee a tort ne se rattrape pas.
    courant = inventaire_abouti()
    courant["schema_version"] = 2
    plan = delta.compare(base, courant)
    echecs += verifie_scenario(11, "schema_version different", plan,
                               {"run_complet": True, "a_exporter": 232,
                                "suppressions": 0, "retenues": 0,
                                "etats": {"creation": 246}})
    echecs += check(plan["precedent_ignore"] is True,
                    "scenario 11 : le precedent doit etre signale comme ignore")
    echecs += check("schema_version" in " ".join(plan["raisons_run_complet"]),
                    "scenario 11 : la raison doit nommer schema_version")
    echecs += check(
        "aucun inventaire precedent" not in " ".join(plan["raisons_run_complet"]),
        "scenario 11 : la raison doit dire schema_version, pas « aucun precedent » "
        "— il y en avait un, il a ete ecarte")

    # Le plan est-il identique a celui du premier run, hors raisons ? C'est
    # l'assertion qui tient la regle : si l'un des deux derive, ils cessent de
    # converger et le test le dit.
    plan_premier = delta.compare(None, inventaire_abouti())
    comparable = lambda p: {c: p[c] for c in  # noqa: E731
                            ("run_complet", "a_exporter", "suppressions",
                             "suppressions_retenues", "etats")}
    echecs += check(comparable(plan) == comparable(plan_premier),
                    "scenario 11 doit produire le meme plan que le scenario 1, "
                    "hors raisons")
    return echecs


def verifie_purete():
    """compare() ne mute ni `precedent` ni `courant`.

    Une fonction declaree pure qui recopie ses entrees par reference est une
    regression invisible jusqu'au jour ou l'appelant reutilise l'inventaire apres
    le delta.
    """
    echecs = 0
    precedent, courant = inventaire_abouti(), inventaire_abouti()
    cible = ids_avec_chemin(courant, 1)[0]
    courant["pages"][cible]["version"] += 1
    courant["pages"][cible]["md_path"] = "specs/AILLEURS.md"

    avant_p, avant_c = copy.deepcopy(precedent), copy.deepcopy(courant)
    delta.compare(precedent, courant)
    echecs += check(precedent == avant_p, "compare() a mute `precedent`")
    echecs += check(courant == avant_c, "compare() a mute `courant`")
    return echecs


def verifie_etats_unitaires():
    """etat_page() sur les sept etats, hors contexte d'inventaire."""
    echecs = 0
    cas = [
        (None, {"md_path": "a.md", "version": 1}, "creation"),
        ({"md_path": "a.md", "version": 1}, {"md_path": None, "version": 1}, "retrait"),
        ({"md_path": None, "version": 1}, {"md_path": "a.md", "version": 1}, "retour"),
        ({"md_path": "a.md", "version": 1}, {"md_path": "a.md", "version": 2},
         "modification"),
        ({"md_path": "a.md", "version": 1}, {"md_path": "b.md", "version": 1},
         "deplacement"),
        ({"md_path": "a.md", "version": 1}, {"md_path": "b.md", "version": 2},
         "modification_deplacement"),
        ({"md_path": "a.md", "version": 1}, {"md_path": "a.md", "version": 1},
         "inchangee"),
    ]
    for avant, apres, attendu in cas:
        obtenu = delta.etat_page(avant, apres)
        echecs += check(obtenu == attendu,
                        f"etat_page({avant} -> {apres}) = {obtenu!r}, attendu {attendu!r}")

    # Un passage a None n'est PAS un deplacement : `retrait` l'emporte, meme si la
    # version a bouge. C'est le decoupage initial corrige — sans quoi une page
    # entree en collision declencherait un re-rendu complet alors que son .md
    # reste en place et qu'aucun lien entrant ne casse.
    echecs += check(
        delta.etat_page({"md_path": "a.md", "version": 1},
                        {"md_path": None, "version": 9}) == "retrait",
        "retrait doit l'emporter sur modification : pas de fichier, rien a dire "
        "sur le contenu")
    return echecs


def run():
    echecs = verifie_nommage_pytest()
    echecs += check(DUMP.is_file(), f"fixture absente : {DUMP}")
    if not DUMP.is_file():
        return 1
    echecs += verifie_etats_unitaires()
    echecs += verifie_scenarios()
    echecs += verifie_purete()

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0


def test_delta():
    """Point d'entree pytest."""
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
