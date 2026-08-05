#!/usr/bin/env python3
"""
Tests de classification — pipeline/src/inventory.py.

Ces tests figent les pieges reveles par le corpus reel. Chacun protege une decision
documentee dans contracts/classification_pages.md : les supprimer laisse repasser une
regression silencieuse, du genre qui retire l'attribut scored a 27 pages de specs sans
qu'aucune erreur ne soit levee.

Aucun acces reseau : le corpus de test est un mini-arbre en dur.

  python -m pytest pipeline/tests/test_inventory.py      (ou : python test_inventory.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import inventory  # noqa: E402

# Mini-corpus : racines de perimetre absentes, comme dans un run reel ou seules les
# pages descendantes sont collectees.
CORPUS = [
    # Groupe A, racine A1
    {"id": "1900545", "title": "SF-COMPTE: gestion des comptes utilisateurs",
     "version": 3, "parent_id": "1638401"},
    {"id": "1638401", "title": "Q-ADMINISTRATION", "version": 2, "parent_id": "1474581"},
    {"id": "200", "title": "SF-COMPTE: Modélisation des données", "version": 5,
     "parent_id": "1900545"},
    {"id": "201", "title": "SF-COMPTE: Règles de gestion consolidées", "version": 5,
     "parent_id": "1900545"},
    {"id": "202", "title": "CU-COMPTE-CREER", "version": 9, "parent_id": "1900545"},
    {"id": "203", "title": "CU‑PERSONNE-RECHERCHER", "version": 4,
     "parent_id": "1900545"},
    {"id": "204", "title": "Archive CU-COMPTE (version monolithique)", "version": 1,
     "parent_id": "1900545"},
    # Heritage de l'exclusion sur deux niveaux sous la page 204
    {"id": "204a", "title": "CU-COMPTE-USER.GEST (version avant API)", "version": 1,
     "parent_id": "204"},
    {"id": "204b", "title": "API-COMPTE-USER.REINIT.PSW", "version": 1,
     "parent_id": "204a"},
    {"id": "211", "title": "DRAFT SF-NOTE: Modélisation des données (MLD)",
     "version": 1, "parent_id": "1900545"},
    {"id": "205", "title": "CU-DOSSIER-ARCHIVER", "version": 2, "parent_id": "1900545"},
    {"id": "206", "title": "SA-PERSONNE-RECHERCHER", "version": 1, "parent_id": "1900545"},
    {"id": "207", "title": "Q-REFERENTIEL", "version": 1, "parent_id": "1474581"},
    {"id": "208", "title": "Réflexion", "version": 1, "parent_id": "1900545"},
    {"id": "209", "title": "CU-TRACE.RECHERCHER", "version": 1, "parent_id": "1900545"},
    {"id": "210", "title": "SF-COMPTE.INTERNET: Modélisation des données", "version": 1,
     "parent_id": "1638401"},
    # Groupe A, racine A2 : sous-arbre UX (519897125) et residu REFERENTIEL
    {"id": "519897125", "title": "Design System portail agent", "version": 1,
     "parent_id": "1277977"},
    {"id": "300", "title": "4. Patterns", "version": 1, "parent_id": "519897125"},
    {"id": "301", "title": "Modale de confirmation", "version": 1, "parent_id": "300"},
    {"id": "302", "title": "Référentiel IHM", "version": 1, "parent_id": "1277977"},
    {"id": "303", "title": "Urbanisation du SI", "version": 1, "parent_id": "1277977"},
    # Groupe B
    {"id": "400", "title": "VII. Règles de gestion", "version": 1, "parent_id": "1245499"},
    {"id": "401", "title": "TEMPLATE_CU", "version": 1, "parent_id": "219086849"},
    # Hors perimetre
    {"id": "500", "title": "CU-ORPHELIN-CREER", "version": 1, "parent_id": "999999"},
]

INV = {p["id"]: p for p in inventory.build_inventory(CORPUS)["pages"]}


TOTAL = 0


def check(condition, message):
    """Retourne 1 en cas d'echec, pour cumul dans l'appelant. Compte les verifications."""
    global TOTAL
    TOTAL += 1
    if not condition:
        print(f"ECHEC : {message}")
        return 1
    return 0


def run():
    echecs = 0
    p = INV

    # --- Normalisation des titres
    echecs += check(inventory.normalize_title("CU‑PERSONNE-RECHERCHER")
                    == "CU-PERSONNE-RECHERCHER", "U+2011 non replie sur le tiret ASCII")
    echecs += check(inventory.normalize_title("RG&period;PERSONNE&lowbar;A")
                    == "RG.PERSONNE_A", "entites HTML non decodees")
    echecs += check(p["203"]["type"] == "CU",
                    "le tiret insecable laisse la page hors radar (doit etre CU)")
    echecs += check(p["203"]["scored"] is True,
                    "la page au tiret insecable doit etre scoree comme un CU")

    # --- Precedence 1 : les motifs de contenu passent avant le prefixe SF-
    echecs += check(p["200"]["type"] == "MDD",
                    "SF-COMPTE: Modelisation des donnees doit etre MDD, pas MODULE")
    echecs += check(p["201"]["type"] == "RG",
                    "SF-COMPTE: Regles de gestion doit etre RG, pas MODULE")
    echecs += check(p["1900545"]["type"] == "MODULE", "page chapeau SF- doit etre MODULE")

    # --- Precedence 2 : Q- passe avant la sous-chaine GENERIQUE
    echecs += check(p["207"]["type"] == "DOMAINE",
                    "Q-REFERENTIEL doit etre DOMAINE, pas GENERIQUE")
    echecs += check(p["302"]["type"] == "GENERIQUE",
                    "Referentiel IHM doit rester GENERIQUE")

    # --- Types residuels : un par groupe, jamais partages
    echecs += check(p["400"]["type"] == "DOCUMENTATION",
                    "residu du groupe B doit etre DOCUMENTATION")
    echecs += check(p["303"]["type"] == "REFERENTIEL",
                    "residu sous la racine A2 hors sous-arbre UX doit etre REFERENTIEL")
    echecs += check(p["208"]["type"] == "A_QUALIFIER",
                    "residu sous la racine A1 doit etre A_QUALIFIER")
    echecs += check(p["500"]["type"] == "HORS_PERIMETRE",
                    "une page hors perimetre doit avoir son propre type")
    echecs += check(len({p["400"]["type"], p["303"]["type"], p["208"]["type"]}) == 3,
                    "les trois types residuels doivent etre distincts")

    # --- Groupe B : jamais de type de spec, jamais score
    echecs += check(p["400"]["scored"] is False,
                    "VII. Regles de gestion (groupe B) ne doit pas etre scoree")
    echecs += check(any("groupe B" in w for w in p["400"]["warnings"]),
                    "le type suggere par le titre doit etre signale au rapport")

    # --- Exclusions : ancrees en debut de titre uniquement
    echecs += check(p["204"]["excluded"] is True, "prefixe 'Archive' non exclu")
    echecs += check(p["204"]["type"] == "CU",
                    "une page exclue doit garder son type (prefixe retire avant typage)")
    echecs += check(p["204"]["exported"] is False and p["204"]["scored"] is False,
                    "une page exclue ne doit etre ni exportee ni scoree")
    echecs += check(p["204"]["content_source"] is True,
                    "une page exclue reste indexable comme source de multiexcerpt")
    echecs += check(p["205"]["excluded"] is False,
                    "CU-DOSSIER-ARCHIVER ne doit PAS etre exclu (exclusion par sous-chaine)")
    echecs += check(p["211"]["excluded"] is True and p["211"]["type"] == "MDD",
                    "le prefixe DRAFT doit exclure, en laissant le type MDD")

    # --- Heritage de l'exclusion sur deux niveaux
    echecs += check(p["204a"]["excluded"] is True and p["204a"]["exclusion_inherited"],
                    "niveau 1 : enfant d'une page exclue doit etre exclu")
    echecs += check(p["204b"]["excluded"] is True and p["204b"]["exclusion_inherited"],
                    "niveau 2 : petit-enfant d'une page exclue doit etre exclu")
    echecs += check(p["204b"]["exclusion_source_id"] == "204",
                    "le motif doit designer la page ancetre responsable")
    echecs += check("Archive CU-COMPTE" in (p["204b"]["exclusion_reason"] or ""),
                    "le motif herite doit nommer l'ancetre, pas seulement le prefixe")
    echecs += check(p["204b"]["type"] == "API",
                    "un descendant exclu garde son propre type")
    echecs += check(p["204b"]["content_source"] is True
                    and p["204b"]["exported"] is False and p["204b"]["scored"] is False,
                    "un descendant exclu garde content_source mais rien d'autre")
    echecs += check(p["204"]["exclusion_inherited"] is False,
                    "la page exclue directement ne doit pas etre marquee heritee")
    echecs += check(p["202"]["excluded"] is False,
                    "une soeur d'une page exclue ne doit pas etre affectee")

    # --- Trois axes : tout le groupe A est content_source
    for pid, libelle in (("206", "SA"), ("1638401", "DOMAINE"), ("1900545", "MODULE"),
                         ("303", "REFERENTIEL"), ("208", "A_QUALIFIER")):
        echecs += check(p[pid]["content_source"] is True,
                        f"{libelle} (groupe A) doit etre content_source")
        echecs += check(p[pid]["scored"] is False, f"{libelle} ne doit pas etre score")
    echecs += check(p["400"]["content_source"] is False,
                    "le groupe B ne doit pas devenir content_source")
    echecs += check(p["301"]["type"] == "UX" and p["301"]["scored"] is False,
                    "UX doit etre exporte et source de contenu, mais pas score")

    # --- Perimetre UX restreint au sous-arbre Design System
    echecs += check(p["519897125"]["type"] == "UX",
                    "la page racine du sous-arbre Design System doit etre UX")
    echecs += check(p["300"]["type"] == "UX" and p["301"]["type"] == "UX",
                    "les descendants du Design System doivent etre UX")
    echecs += check(p["302"]["type"] == "GENERIQUE",
                    "un motif de titre l'emporte sur le sous-arbre UX")

    # --- Module : ascendance d'abord, titre a defaut
    echecs += check(p["208"]["module"] == "COMPTE"
                    and p["208"]["module_source"] == "ascendance",
                    "'Reflexion' doit heriter du module COMPTE par ascendance")
    echecs += check(p["207"]["module"] is None, "une page de domaine n'a pas de module")
    echecs += check(p["209"]["module"] == "COMPTE",
                    "l'ascendance doit primer sur le titre pour CU-TRACE.RECHERCHER")
    echecs += check(any("module ambigu" in w for w in p["209"]["warnings"]),
                    "un desaccord ascendance/titre doit etre signale (TRACE vs COMPTE)")
    echecs += check(inventory.module_par_titre("CU-TRACE.RECHERCHER") == "TRACE",
                    "module coupe au premier point dans un titre de spec")
    echecs += check(inventory.module_par_titre("SF-COMPTE.INTERNET: MDD")
                    == "COMPTE.INTERNET", "un module SF- conserve son point")
    echecs += check(p["302"]["module"] is None,
                    "une page UX sans ancetre SF- n'a pas de module")

    # --- Defaut d'exclusion
    echecs += check("DRAFT" in inventory.DEFAULT_EXCLUDE_TITLE_PREFIXES,
                    "DRAFT doit figurer dans les prefixes exclus par defaut")

    # --- Hors perimetre
    echecs += check(p["500"]["group"] == "hors_perimetre",
                    "une page sans racine connue doit etre hors_perimetre")
    echecs += check(p["500"]["exported"] is False and p["500"]["content_source"] is False
                    and p["500"]["scored"] is False,
                    "une page hors perimetre ne doit rien produire")

    # --- Types reserves non implementes
    echecs += check(all(nom not in dict(inventory.TYPE_PATTERNS)
                        for nom in inventory.TYPES_RESERVES),
                    "DOC et TAB doivent rester sans motif tant qu'aucune page n'existe")

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0


if __name__ == "__main__":
    sys.exit(run())


def test_inventory():
    """Point d'entree pytest."""
    assert run() == 0
