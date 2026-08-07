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

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

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


def tests_slugification():
    """Les 14 cas de contracts/slugification.md §13, plus les invariants de la regle."""
    echecs = 0
    sl = inventory.slugify

    # --- §13, tableau des cas attendus
    cas = [
        ("CU-NOTE-TYPENOTE.CREER", "9", "CU-NOTE-TYPENOTE.CREER",
         "le point est preserve"),
        ("CU-NOTE-TYPENOTE-CREER", "9", "CU-NOTE-TYPENOTE-CREER",
         "distinct du precedent : c'est tout l'enjeu du point conserve"),
        ("SF-COMPTE: gestion des comptes utilisateurs", "9",
         "SF-COMPTE-gestion-des-comptes-utilisateurs", "deux-points et espaces"),
        ("Archive CU-COMPTE (version monolithique, sans API)", "9",
         "Archive-CU-COMPTE-version-monolithique-sans-API",
         "parentheses et virgule tombent, pas de tiret double"),
        ("IV. Les Assurés Obligatoires Étudiants/Élèves (AOEE)", "9",
         "IV.-Les-Assures-Obligatoires-Etudiants-Eleves-AOEE",
         "accents replies, slash remplace"),
        ("Guide d’utilisation du BPMN", "9", "Guide-d-utilisation-du-BPMN",
         "apostrophe typographique"),
        ("-NEW- CU-COMPTE-PROFIL.GEST", "9", "NEW-CU-COMPTE-PROFIL.GEST",
         "tiret de tete rogne"),
        ("Bonnes pratiques RGAA 4.1.2 - Guide opérationnel BA & DEV", "9",
         "Bonnes-pratiques-RGAA-4.1.2-Guide-operationnel-BA-DEV",
         "esperluette, et points de version preserves"),
        ("  ", "42", "page-42", "titre de blancs : repli sur l'identifiant"),
        ("NUL", "9", "_NUL", "nom de peripherique DOS prefixe"),
    ]
    for titre, pid, attendu, motif in cas:
        obtenu = sl(titre, pid)
        echecs += check(obtenu == attendu,
                        f"slugify({titre!r}) = {obtenu!r}, attendu {attendu!r} — {motif}")

    # Plafond de segment : 120 caracteres -> 80 + ~{page_id}
    long_titre = "A" * 120
    obtenu = sl(long_titre, "123456")
    echecs += check(obtenu == "A" * 80 + "~123456",
                    f"titre de 120 car. doit etre tronque a 80 + ~id, obtenu {obtenu!r}")
    echecs += check(len(sl("B" * 79, "9")) == 79,
                    "un titre sous le plafond n'est pas tronque")
    echecs += check("~" not in sl("C" * 80, "9"),
                    "exactement 80 caracteres ne declenche pas la troncature")

    # --- Invariants de la liste blanche
    for titre in ("SF-COMPTE: gestion", "Archive (v2)", "a&b", "x'y", "IV. Élèves/AOEE",
                  "-NEW- X", "  ", "NUL", "A" * 120):
        slug = sl(titre, "9")
        echecs += check(re.fullmatch(r"[A-Za-z0-9._~-]+", slug) is not None,
                        f"slug hors liste blanche : {slug!r}")
        echecs += check(not slug.endswith(("-", ".", "_", " ")),
                        f"un nom Windows ne peut finir par un separateur : {slug!r}")
        # Le `_` de tete est legitime : c'est le prefixe des noms reserves, applique
        # APRES le rognage. Seuls `-`, `.` et l'espace sont proscrits en tete.
        echecs += check(not slug.startswith(("-", ".", " ")),
                        f"tete en separateur : {slug!r}")

    # La casse est conservee : c'est la forme de l'identifiant SINAPSE.
    echecs += check(sl("CU-PERSONNE-MODIFIER", "9") == "CU-PERSONNE-MODIFIER",
                    "la casse doit etre conservee")

    # slugify() ne refait pas la normalisation des titres : elle a lieu en amont.
    # Le risque n'est pas une collision manquee mais un NOM DE FICHIER FAUX — un slug
    # plausible, sans erreur, et un identifiant SINAPSE meconnaissable.
    echecs += check(sl("RG-COMPTE&period;GROUPE-CREER", "9")
                    == "RG-COMPTE-period-GROUPE-CREER",
                    "titre NON normalise : l'entite survit et abime l'identifiant")
    echecs += check(sl(inventory.normalize_title("RG-COMPTE&period;GROUPE-CREER"), "9")
                    == "RG-COMPTE.GROUPE-CREER",
                    "titre normalise en amont : le point est restitue")
    echecs += check(sl(inventory.normalize_title("SF-COMPTE&lowbar;INTERNET"), "9")
                    == "SF-COMPTE_INTERNET",
                    "&lowbar; doit redonner un tiret bas, pas -lowbar-")

    # --- §9, detection de collisions
    def page(pid, titre, parent):
        return {"id": pid, "title": titre, "parent_id": parent}

    # Deux titres qui ne different que par un accent : collision voulue.
    g = inventory.detecte_collisions([page("1", "Réflexion", "100"),
                                      page("2", "Reflexion", "100")])
    echecs += check(len(g) == 1 and {p["id"] for p in next(iter(g.values()))} == {"1", "2"},
                    "Reflexion et Réflexion freres doivent entrer en collision")

    # Casse seule : collision aussi, Windows et SharePoint y sont insensibles.
    g = inventory.detecte_collisions([page("1", "A", "100"), page("2", "a", "100")])
    echecs += check(len(g) == 1, "A et a freres doivent entrer en collision (casefold)")

    # Cas X/X.md : une fille dont le slug egale celui de sa mere.
    g = inventory.detecte_collisions([page("10", "X", "100"), page("11", "X", "10")])
    echecs += check(len(g) == 1,
                    "une fille de meme slug que sa mere doit entrer en collision (X/X.md)")
    if g:
        touchees = {p["id"] for p in next(iter(g.values()))}
        echecs += check(touchees == {"10", "11"},
                        f"le groupe doit nommer la mere ET la fille, obtenu {touchees}")

    # Parents differents : pas de collision, l'arborescence les isole.
    g = inventory.detecte_collisions([page("1", "X", "100"), page("2", "X", "200")])
    echecs += check(g == {},
                    "deux pages de parents differents ne collisionnent pas")

    # Une page seule ne collisionne pas avec elle-meme via les deux cles.
    echecs += check(inventory.detecte_collisions([page("1", "X", "100")]) == {},
                    "une page isolee ne doit pas se collisionner elle-meme")

    echecs += test_non_regression_corpus()
    return echecs


# Mesures de contracts/slugification.md §11, epinglees par le test ci-dessous.
# Ces valeurs sont derivees du corpus FIGE au 5 aout, pas de Confluence. Le jour ou
# la fixture sera rafraichie, elles doivent etre re-derivees DELIBEREMENT — jamais
# recopiees depuis la sortie du script, ce qui reviendrait a valider la regression
# qu'elles existent pour attraper.
#
# CORPUS INCOMPLET, ET C'EST SU : le recensement du 4 aout a perdu 334888965
# (SF-COORDONNEE: Regles de gestion consolidees, page RG) sur un timeout. Les sept
# mesures portent donc sur 246 pages au lieu de 247. Au rafraichissement du corpus,
# un ecart sur ces valeurs est ATTENDU — ce n'est pas une regression.
MESURES_ATTENDUES = {
    "pages exportees": 232,
    "collisions": 0,
    "slug le plus long": 77,
    "md_path median": 89,
    "md_path le plus long": 131,
    "md_path le plus long, doublement force": 164,
    "profondeur maximale sous specs/": 4,
}

# Fixture VERSIONNEE. 143 Ko de metadonnees de pages, sans contenu : le versionner
# coute peu et rend le test executable sur un depot fraichement clone comme en CI.
# Pointer sur recensement/, non versionne, rendait le test vert pour toujours ailleurs
# que sur le poste qui l'avait produit — pire qu'un test absent.
DUMP = RACINE / "fixtures" / "pages_classification_20260805.json"


def _md_path(page, par_id, meres, doublement_force=False):
    """Assemblage de md_path selon contracts/slugification.md §10.

    IMPLEMENTATION DE REFERENCE, LOCALE AU TEST. L'assemblage reel n'existe pas
    encore dans inventory.py — il arrive avec pages_inventory.json et le delta. Le
    jour ou il sera ecrit, ce test doit l'appeler LUI au lieu de cette copie, sinon
    il verifiera une seconde implementation au lieu de la vraie.
    """
    segments, courant = [], page
    while courant:
        segments.append(inventory.slugify(courant["title"], courant["id"]))
        courant = par_id.get(courant.get("parent_id") or "")
    segments.reverse()
    # Une page a filles porte son contenu dans {slug}/{slug}.md ; les segments
    # d'ancetres ne sont jamais doubles.
    if doublement_force or page["id"] in meres:
        segments.append(segments[-1])
    racine = "specs" if page["group"] == "A" else "docs"
    return f"{racine}/" + "/".join(segments) + ".md"


def mesures_corpus(pages):
    """Les 7 mesures du §11 sur un dump de classification."""
    par_id = {p["id"]: p for p in pages}
    meres = inventory.meres_exportantes(pages)
    exportees = [p for p in pages if p["exported"]]
    chemins = [_md_path(p, par_id, meres) for p in exportees]
    forces = [_md_path(p, par_id, meres, doublement_force=True) for p in exportees]
    longueurs = sorted(len(c) for c in chemins)
    milieu = longueurs[len(longueurs) // 2] if longueurs else 0
    return {
        "pages exportees": len(exportees),
        "collisions": len(inventory.detecte_collisions(pages)),
        "slug le plus long": max(len(inventory.slugify(p["title"], p["id"]))
                                 for p in pages),
        "md_path median": milieu,
        "md_path le plus long": max(len(c) for c in chemins),
        "md_path le plus long, doublement force": max(len(c) for c in forces),
        "profondeur maximale sous specs/": max(c.count("/") for c in chemins
                                               if c.startswith("specs")),
    }


def test_non_regression_corpus():
    """Epingle les mesures du §11 sur le dump de recensement.

    C'est la seule verification qui porte sur le corpus reel : les cas du §13 sont
    des exemples choisis, ils ne diraient rien d'une regle qui derive sur 246 titres
    authentiques. Sans ce test, une evolution de la regle perime les chiffres du §11
    en silence — ce qui s'est deja produit : le contrat annoncait un slug maximal de
    78, valeur heritee d'une regle candidate en liste noire, jamais recalculee au
    passage a la liste blanche.
    """
    echecs = 0
    # La fixture est versionnee : son absence est une anomalie du depot, pas une
    # circonstance. Un test qui se contenterait d'avertir serait vert pour toujours.
    echecs += check(DUMP.is_file(),
                    f"fixture de classification absente : {DUMP} — les "
                    f"{len(MESURES_ATTENDUES)} mesures du §11 ne sont pas verifiables")
    if not DUMP.is_file():
        return echecs

    pages = json.loads(DUMP.read_text(encoding="utf-8"))["pages"]
    obtenues = mesures_corpus(pages)
    for nom, attendu in MESURES_ATTENDUES.items():
        echecs += check(obtenues[nom] == attendu,
                        f"§11 — {nom} : {obtenues[nom]}, attendu {attendu}")

    # Le plafond de segment doit rester un garde-fou inactif : s'il devenait actif,
    # des fichiers seraient renommes sur le SharePoint au prochain run.
    echecs += check(obtenues["slug le plus long"] < inventory.SLUG_SEGMENT_MAX,
                    f"le plafond de {inventory.SLUG_SEGMENT_MAX} doit rester inactif, "
                    f"slug le plus long {obtenues['slug le plus long']}")
    echecs += check(not any("~" in inventory.slugify(p["title"], p["id"])
                            for p in pages),
                    "aucun slug du corpus ne doit porter la marque de troncature `~`")

    # Le point est significatif dans la nomenclature SINAPSE : il distingue deux
    # modules (SF-COMPTE / SF-COMPTE.INTERNET) et deux entites. Le reduire en tiret ne
    # ferait bouger AUCUNE des sept mesures — le corpus ne porte aucune paire de
    # freres qui n'en differe que par la. Cet invariant, lui, mord sur tous les titres
    # pointes d'un coup, la ou un cas unitaire n'en couvre qu'un.
    perdus = [p["title"] for p in pages
              if p["title"].count(".")
              != inventory.slugify(p["title"], p["id"]).count(".")]
    echecs += check(not perdus,
                    f"{len(perdus)} titre(s) perdent un point a la slugification, "
                    f"ex. {perdus[:2]}")
    pointes = sum(1 for p in pages if "." in p["title"])
    echecs += check(pointes > 50,
                    f"l'invariant du point doit porter sur un echantillon consequent, "
                    f"{pointes} titres pointes trouves")

    echecs += tests_mere_sans_fille_exportee(pages)
    return echecs


def tests_mere_sans_fille_exportee(pages_corpus):
    """Une mere dont toutes les filles sont exclues ne prend PAS de repertoire.

    Contrat §10. Aucune des sept mesures du §11 ne couvre ce cas : elles sont
    identiques dans les deux lectures. C'est ce qui le rend dangereux — pris a la
    lettre, « page avec filles » fabrique un repertoire a fichier unique.
    """
    echecs = 0

    def mere(pid, titre, parent, exportee=True):
        return {"id": pid, "title": titre, "parent_id": parent, "group": "A",
                "exported": exportee}

    # Mere + unique fille exclue -> la mere n'a pas de repertoire.
    cas = [mere("10", "CU-X", "1"), mere("11", "Archive CU-Y", "10", exportee=False)]
    par_id = {p["id"]: p for p in cas}
    meres = inventory.meres_exportantes(cas)
    chemin = _md_path(par_id["10"], par_id, meres)
    echecs += check(chemin.endswith("/CU-X.md") and "/CU-X/" not in chemin,
                    f"mere a fille unique exclue : attendu CU-X.md, obtenu {chemin}")

    # La meme mere, sa fille exportee : le repertoire apparait.
    cas[1]["exported"] = True
    meres = inventory.meres_exportantes(cas)
    chemin = _md_path(par_id["10"], par_id, meres)
    echecs += check(chemin.endswith("/CU-X/CU-X.md"),
                    f"mere a fille exportee : attendu CU-X/CU-X.md, obtenu {chemin}")

    # Le cas reel du corpus : CU-PERSONNE-CONSULTER, unique fille archivee.
    par_id = {p["id"]: p for p in pages_corpus}
    reelle = par_id.get("324730881")
    if reelle:
        filles = [p for p in pages_corpus if p.get("parent_id") == "324730881"]
        echecs += check(filles and not any(f["exported"] for f in filles),
                        "CU-PERSONNE-CONSULTER doit n'avoir que des filles exclues")
        meres = inventory.meres_exportantes(pages_corpus)
        chemin = _md_path(reelle, par_id, meres)
        echecs += check(chemin.endswith("/CU-PERSONNE-CONSULTER.md")
                        and "/CU-PERSONNE-CONSULTER/" not in chemin,
                        f"cas reel : pas de repertoire a fichier unique, obtenu {chemin}")
    else:
        echecs += check(False, "CU-PERSONNE-CONSULTER (324730881) absente de la fixture")
    return echecs


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

    echecs += tests_slugification()

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
