#!/usr/bin/env python3
"""
Inventaire et classification des pages du corpus SINAPSE — etape 3 du pipeline.

VERSION : 1.2 — slugification et detection de collision

Trois responsabilites :
  - normaliser le titre AVANT tout filtrage (entites HTML, tirets Unicode) ;
  - en deduire le groupe (A specs / B documentation), le type de page et le module ;
  - en deduire trois attributs INDEPENDANTS : exported, content_source, scored.

Aucun appel reseau, aucun LLM : les pages sont fournies par confluence_client sous la
forme (id, title, version, parent_id). Le module est donc rejouable hors ligne sur la
sortie de recense_adf.py, ce qui sert de jeu de tests grandeur reelle.

Le contrat de classification est dans contracts/classification_pages.md : toute
evolution du bloc de constantes ci-dessous doit s'y repercuter, et inversement.

La slugification est couverte depuis la v1.2, l'assemblage de md_path depuis la
v1.3 (contracts/slugification.md §2, §9 et §10). Restent l'assemblage de
pages_inventory.json — la sortie actuelle est un tableau a plat, pas la carte
indexee par identifiant du schema — et le delta.

Exemples :
  python inventory.py --from-recensement ../../recensement/recensement_adf_20260804.json \
                      --report ../../recensement/classification_pages_20260805.md
"""

import argparse
import configparser
import html
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

VERSION = "1.4"
SCHEMA_VERSION = 1

# Le schema impose des identifiants numeriques comme cles de `pages`. Une page
# dont l'identifiant ne l'est pas part en `unclassified` : on ne peut ni la
# suivre d'un run a l'autre, ni la ranger dans la carte.
RE_PAGE_ID = re.compile(r"^[0-9]+$")


# ==========================================================================
# BLOC DE CONSTANTES — documente dans contracts/classification_pages.md
# ==========================================================================

# --- Perimetre : racines du brief §2 -------------------------------------
ROOTS_GROUPE_A = ("1474581", "1277977")          # specs fonctionnelles
ROOTS_GROUPE_B = ("1245499", "1310723", "219086849")  # documentation

# Sous-arbres classes UX : la seule page "Design System portail agent" et sa
# descendance. La page racine du sous-arbre en fait partie. Le reste de la racine A2
# (urbanisation, BPMN, menus, RGAA) n'est pas de l'UX au sens strict et tombe en
# REFERENTIEL, pas en A_QUALIFIER : ce sont des regles transverses assumees.
UX_SUBTREE_ROOTS = ("519897125",)

# --- Types residuels : par ascendance, jamais par motif de titre ---------
# Une page du groupe A ne partage jamais son type residuel avec une page du groupe B :
# confondre les deux ferait passer un residu de specs pour de la documentation libre,
# donc pour une situation normale.
RESIDUAL_TYPE_BY_ROOT = {
    "1277977": "REFERENTIEL",    # racine A2 hors sous-arbre UX : regles transverses
    "1474581": "A_QUALIFIER",    # racine A1 : residu a resorber, pas un etat normal
}
RESIDUAL_TYPE_GROUPE_B = "DOCUMENTATION"
RESIDUAL_TYPE_HORS_PERIMETRE = "HORS_PERIMETRE"

# --- Normalisation des titres --------------------------------------------
# Le corpus melange plusieurs tirets Unicode. NFKC ne suffit pas : seul U+FF0D y
# atteint le tiret ASCII. U+2011 se replie sur U+2010 et U+FE58 sur U+2014 -- donc
# sur d'autres tirets non-ASCII ; U+2010, U+2012..U+2015 et U+2212 traversent NFKC
# inchanges. Sans cette table, "CU-PERSONNE-RECHERCHER" ecrit avec U+2011 reste
# invisible au motif ^CU-, meme apres normalisation NFKC.
TIRETS_UNICODE = {
    0x2010: "-",  # hyphen
    0x2011: "-",  # non-breaking hyphen        <- rencontre dans le corpus
    0x2012: "-",  # figure dash
    0x2013: "-",  # en dash
    0x2014: "-",  # em dash
    0x2015: "-",  # horizontal bar
    0x2212: "-",  # minus sign
    0xFE58: "-",  # small em dash
    0xFF0D: "-",  # fullwidth hyphen-minus
}

# --- Types de pages, dans l'ORDRE de test --------------------------------
# L'ordre est porteur de sens, deux precedences sont imposees par le corpus reel :
#   1. les motifs de contenu (MDD, RG) passent AVANT le prefixe structurel SF- :
#      les 27 pages MDD et RG s'appellent toutes "SF-XXX: Modelisation des donnees"
#      ou "SF-XXX: Regles de gestion consolidees". Tester SF- d'abord les
#      reclasserait en MODULE et leur ferait perdre l'attribut scored ;
#   2. le prefixe DOMAINE Q- passe AVANT la sous-chaine GENERIQUE : sans cela
#      "Q-REFERENTIEL" tombe en GENERIQUE sur le mot "referentiel".
# Les prefixes sont ancres (^) : le desancrage ferait matcher un titre comme
# "Liste des CU-PERSONNE a reprendre". Les titres masques par un prefixe parasite
# sont traites par les exclusions, qui retirent le prefixe avant le typage.
TYPE_PATTERNS = (
    ("CU", re.compile(r"^CU-", re.I)),
    ("API", re.compile(r"^API-", re.I)),
    ("JOB", re.compile(r"^(?:JOB|BATCH)-", re.I)),
    ("SA", re.compile(r"^SA-", re.I)),
    ("MDD", re.compile(r"mod[ée]lisation des donn[ée]es", re.I)),
    ("RG", re.compile(r"r[èe]gles de gestion", re.I)),
    ("DOMAINE", re.compile(r"^Q-", re.I)),
    ("MODULE", re.compile(r"^SF-", re.I)),
    ("GENERIQUE", re.compile(r"g[ée]n[ée]rique|r[ée]f[ée]rentiel", re.I)),
)

# Types reserves, volontairement absents de TYPE_PATTERNS : DOC-* et TAB-*. Aucune
# page du corpus ne les porte a ce jour ; ecrire un motif pour un type inexistant
# creerait un faux positif silencieux. Voir contracts/classification_pages.md.
TYPES_RESERVES = ("DOC", "TAB")

# --- Attributs par type : TROIS AXES INDEPENDANTS ------------------------
# exported       : la page part en .md dans specs/ (groupe A) ou docs/ (groupe B)
# content_source : son ADF est parse et indexable comme source de multiexcerpt
#                  ou de syncBlock
# scored         : elle est soumise aux skills de validation
# Un type peut etre exporte sans etre scorable : une page chapeau de module n'a pas
# de regles a valider, mais son .md reste utile a la navigation.
#
# TOUTE page du groupe A est content_source, quel que soit son type : une definition
# de multiexcerpt peut vivre n'importe ou dans l'arbre des specs, et un faux negatif
# ici casse une inclusion en silence. La regle est reappliquee en fin de
# classify_page() pour qu'un type ajoute plus tard ne puisse pas y echapper par
# distraction.
ATTRIBUTS_PAR_TYPE = {
    "CU":            {"exported": True,  "content_source": True,  "scored": True},
    "RG":            {"exported": True,  "content_source": True,  "scored": True},
    "MDD":           {"exported": True,  "content_source": True,  "scored": True},
    "API":           {"exported": True,  "content_source": True,  "scored": True},
    "JOB":           {"exported": True,  "content_source": True,  "scored": True},
    "UX":            {"exported": True,  "content_source": True,  "scored": False},
    "GENERIQUE":     {"exported": True,  "content_source": True,  "scored": False},
    "SA":            {"exported": True,  "content_source": True,  "scored": False},
    "MODULE":        {"exported": True,  "content_source": True,  "scored": False},
    "DOMAINE":       {"exported": True,  "content_source": True,  "scored": False},
    "REFERENTIEL":   {"exported": True,  "content_source": True,  "scored": False},
    "A_QUALIFIER":   {"exported": True,  "content_source": True,  "scored": False},
    "DOCUMENTATION": {"exported": True,  "content_source": False, "scored": False},
    "HORS_PERIMETRE": {"exported": False, "content_source": False, "scored": False},
}

# --- Exclusions par prefixe de titre -------------------------------------
# Defauts, surchargeables par exclude_title_prefixes dans config.ini.
# ANCRAGE EN DEBUT DE TITRE UNIQUEMENT : une exclusion par sous-chaine ecarterait
# CU-DOSSIER-ARCHIVER, qui est une spec parfaitement valide.
# L'exclusion est HERITEE par tout le sous-arbre : une page rangee sous une page
# archivee est archivee avec elle, quel que soit son propre titre.
DEFAULT_EXCLUDE_TITLE_PREFIXES = ("Archive", "ARCHIVE_", "Copie de", "-NEW-", "DRAFT")

# --- Slugification : contracts/slugification.md ---------------------------
# Le slug est une CLE D'ADRESSAGE, pas un libelle. Le titre exact vit dans
# pages_inventory.json et dans le frontmatter ; rien n'est perdu quand le slug abime
# un titre. En revanche deux pages qui produisent le meme chemin font disparaitre une
# spec, silencieusement et sans retour. D'ou l'ordre : unicite d'abord, lisibilite
# ensuite.

# Liste BLANCHE, jamais liste noire. Une liste noire des caracteres interdits sous
# Windows laisserait passer parentheses, espaces et esperluettes : les parentheses
# cassent la syntaxe d'un lien markdown, et c'est ce qui permet d'ecrire md_path tel
# quel dans un lien, sans encodage (normalisation_adf.md §6.3).
SLUG_KEEP = re.compile(r"[^A-Za-z0-9._-]")

# Noms de peripheriques DOS : Windows refuse NUL.md comme nul. Le cout du garde-fou
# est nul, et le cas ne se verrait qu'a l'ecriture, sur une page a la fois.
SLUG_RESERVED = ({"CON", "PRN", "AUX", "NUL"}
                 | {f"COM{i}" for i in range(1, 10)}
                 | {f"LPT{i}" for i in range(1, 10)})

# Garde-fou contre un titre pathologique futur, pas un mecanisme actif : aucun slug
# du corpus ne l'atteint, donc zero renommage aujourd'hui et zero brassage de
# fichiers sur le SharePoint. Mesures au corpus : contrat §11, epinglees par le test
# de non-regression — ne pas les recopier ici, un chiffre duplique diverge.
SLUG_SEGMENT_MAX = 80


def slugify(title, page_id):
    """Segment de chemin derive d'un titre. Voir contracts/slugification.md §2.

    L'entree est le titre DEJA NORMALISE par normalize_title() : html.unescape() puis
    repli des tirets Unicode. slugify() ne refait pas cette normalisation — un seul
    endroit normalise les titres, le dupliquer garantirait une divergence le jour ou
    l'un des deux evoluerait.
    """
    # Repli des accents. Git et les clients de synchronisation ne s'accordent pas sur
    # la forme Unicode d'un nom accentue : un depot partage Windows/macOS voit des
    # fichiers "modifies" que personne n'a touches. Effet de bord recherche :
    # "Reflexion" et "Réflexion" produisent le meme slug et entrent en collision, au
    # lieu de deux fichiers voisins que personne ne rapprochera.
    s = unicodedata.normalize("NFD", str(title or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = unicodedata.normalize("NFC", s)

    s = SLUG_KEEP.sub("-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-._ ")

    if len(s) > SLUG_SEGMENT_MAX:
        # `~` n'appartient pas a la liste blanche : sa seule origine possible est
        # cette troncature, ce qui rend un slug tronque reconnaissable a l'oeil.
        # L'identifiant est repris ENTIER, un suffixe court ne garantit pas l'unicite.
        s = s[:SLUG_SEGMENT_MAX].rstrip("-._") + "~" + str(page_id)

    # Comparaison sur la partie qui precede le premier point, sans tenir compte de la
    # casse : Windows refuse NUL.md comme nul.
    if s.split(".")[0].upper() in SLUG_RESERVED:
        s = "_" + s

    return s or f"page-{page_id}"


def meres_exportantes(pages):
    """Identifiants des pages ayant au moins une fille EXPORTEE — contrat §10.

    Filles exportees seulement : une page dont toutes les filles sont exclues n'a pas
    de repertoire, il ne contiendrait que son propre fichier. Cas reel du corpus :
    CU-PERSONNE-CONSULTER, dont l'unique fille est ARCHIVE_CU-DOSS-CONSULT.

    C'est ce predicat qui decide de la forme du chemin : {slug}/{slug}.md pour une
    page qui figure ici, {slug}.md sinon. Il vit AUPRES de slugify() et non dans les
    tests, pour que l'assembleur de pages_inventory.json l'appelle au lieu d'en
    ecrire une seconde version — deux lectures de "page avec filles" divergeraient
    sans qu'aucune des mesures du contrat §11 ne le signale, elles sont identiques
    dans les deux cas.
    """
    return {p["parent_id"] for p in pages if p.get("parent_id") and p.get("exported")}


# Racine de sortie par groupe. Une page hors perimetre n'en a pas : elle n'est
# jamais exportee, et lui donner `docs/` par defaut la ferait atterrir dans la
# documentation sans que rien ne le signale.
RACINE_PAR_GROUPE = {"A": "specs", "B": "docs"}


def md_path(page, pages_par_id, meres):
    """Chemin du .md relatif a local_path. Voir contracts/slugification.md §10.

    Fonction PURE et purement geometrique : elle derive le chemin du titre, de
    l'ascendance et du predicat "a au moins une fille exportee", sans lire
    Confluence, sans config.ini, et sans consulter `exported`. C'est ce qui la
    rend appelable depuis pipeline/tests/test_inventory.py -- la copie locale au
    test avait deja diverge une fois.

    Elle ne decide PAS si le chemin est retenu : c'est l'assembleur de
    pages_inventory.json qui ecrit `null` pour une page non exportee ou en
    collision.

    `meres` : sortie de meres_exportantes(). Pour obtenir la mesure du §11
    "md_path le plus long si chaque feuille gagnait une fille", passer
    l'ensemble de TOUS les identifiants : seule la page elle-meme est concernee
    par le doublement, jamais ses ancetres.

    Rend None dans deux cas, tous deux non exportables :
      - groupe sans racine de sortie (hors perimetre) ;
      - chaine d'ascendance qui boucle.
    """
    racine = RACINE_PAR_GROUPE.get(page.get("group"))
    if racine is None:
        return None

    # Garde-cycle : la copie du test n'en avait pas et bouclait indefiniment sur
    # un parent_id circulaire. chaine_ascendance() porte le meme garde ; les deux
    # remontees doivent se comporter pareil.
    segments, courant, vus = [], page, set()
    while courant is not None:
        page_id = str(courant["id"])
        if page_id in vus:
            return None
        vus.add(page_id)
        segments.append(slugify(courant.get("title"), page_id))
        parent = courant.get("parent_id")
        courant = pages_par_id.get(parent) if parent else None
    segments.reverse()

    # Les 5 racines de perimetre ne sont pas collectees : la remontee s'arrete
    # d'elle-meme et elles ne contribuent aucun segment.
    #
    # Une page a filles porte son contenu dans {slug}/{slug}.md. Les segments
    # d'ancetres ne sont JAMAIS doubles.
    if str(page["id"]) in meres:
        segments.append(segments[-1])

    return f"{racine}/" + "/".join(segments) + ".md"


def detecte_collisions(pages):
    """Groupes de pages produisant le meme chemin. Voir contracts/slugification.md §9.

    `pages` : iterable de dicts portant au moins id, title, parent_id.

    Les titres doivent DEJA etre normalises par normalize_title() : la fonction
    consomme la sortie de build_inventory(), pas des pages brutes de
    confluence_client. Un titre non decode donne un slug plausible et faux —
    "RG-COMPTE&period;GROUPE" produit "RG-COMPTE-period-GROUPE".

    La cle est (identifiant du REPERTOIRE contenant, slug replie), et chaque page en
    alimente DEUX, dans le MEME espace de noms — c'est leur partage qui detecte le
    second cas :

      (parent_id, slug)  le fichier de la page vit dans le repertoire de son parent,
                         donc les FRERES se disputent ce nom ;
      (page_id,  slug)   cas X/X.md — une page a filles porte son contenu dans un
                         fichier de meme nom que son propre repertoire. Une fille dont
                         le slug egale celui de sa mere vise exactement ce chemin, et
                         sa cle (parent_id = id de la mere, slug) tombe sur celle-ci.

    Un espace de noms separe par nature de collision ne detecterait rien du second
    cas : la mere et la fille n'y seraient jamais comparees.

    Les cles sont repliees par `casefold()` : la casse est CONSERVEE dans le slug —
    c'est la forme de l'identifiant SINAPSE — mais Windows, SharePoint et Git sur
    Windows y sont insensibles, donc deux slugs qui n'en different que par la casse
    designent le meme fichier.

    Rend {cle: [pages du groupe]} pour les seuls groupes d'au moins 2 pages. Aucune
    desambiguisation : elle renommerait silencieusement des specs, y compris celle qui
    n'a pas bouge. Une collision est une anomalie editoriale, elle se corrige dans
    Confluence.
    """
    par_cle = defaultdict(list)
    for page in pages:
        page_id = str(page["id"])
        pli = slugify(page.get("title"), page_id).casefold()
        par_cle[(str(page.get("parent_id") or ""), pli)].append(page)
        par_cle[(page_id, pli)].append(page)

    groupes = {}
    for cle, lot in par_cle.items():
        uniques = {str(p["id"]): p for p in lot}
        if len(uniques) > 1:
            groupes[cle] = sorted(uniques.values(), key=lambda p: str(p["id"]))
    return groupes


# --- Extraction du module ------------------------------------------------
# Un module SF- peut porter un point : SF-COMPTE et SF-COMPTE.INTERNET sont deux
# modules distincts, chacun avec sa propre page de modelisation.
RE_MODULE_SF = re.compile(r"^SF-([A-Z0-9]+(?:\.[A-Z0-9]+)*)", re.I)
# Dans un titre de spec le module est le 2e segment, coupe au premier point :
# CU-PERSONNE-PP.CREER -> PERSONNE, et CU-TRACE.RECHERCHER -> TRACE.
RE_MODULE_SPEC = re.compile(r"^(?:CU|API|JOB|BATCH|SA)-([A-Z0-9]+)", re.I)


# ==========================================================================
# Normalisation
# ==========================================================================

def normalize_title(titre):
    """Titre pret pour le filtrage : entites HTML decodees, tirets replies en ASCII.

    A appeler avant TOUT matching. Les noms Confluence sont encodes en entites
    (&period;, &lowbar;) et les tirets Unicode sont invisibles a l'oeil nu.
    """
    if not titre:
        return ""
    decode = html.unescape(titre)
    return decode.translate(TIRETS_UNICODE).strip()


# ==========================================================================
# Exclusions
# ==========================================================================

def match_exclusion(titre_normalise, prefixes):
    """Prefixe d'exclusion en tete de titre, ou None. Comparaison insensible a la casse.

    Test du plus long au plus court : "ARCHIVE_" et "Archive" matchent tous deux
    ARCHIVE_CU-DOSS-CONSULT, et c'est le plus specifique qu'il faut reporter au motif.
    """
    for prefixe in sorted(prefixes, key=len, reverse=True):
        if titre_normalise.upper().startswith(prefixe.upper()):
            return prefixe
    return None


def exclusion_heritee(chaine, pages_par_id, prefixes):
    """Ancetre exclu le plus proche : (id, titre, prefixe), ou None.

    L'exclusion se propage vers le bas comme le groupe et le sous-arbre UX : une page
    rangee sous "Archive CU-COMPTE" appartient a l'archive, meme si son propre titre
    ne dit rien. Sans cet heritage, 9 pages de la branche archivee du module COMPTE
    restaient exportees et scorees comme des specs vivantes.

    Seule l'exclusion par prefixe de titre est heritee. exclude_page_ids reste
    nominative : c'est un scalpel pour une page precise, pas un marqueur de branche.
    """
    for ancetre in chaine:
        page = pages_par_id.get(ancetre)
        if not page:
            continue
        titre = normalize_title(page.get("title"))
        prefixe = match_exclusion(titre, prefixes)
        if prefixe:
            return ancetre, titre, prefixe
    return None


def strip_prefix(titre_normalise, prefixe):
    """Titre prive de son prefixe d'exclusion, pour pouvoir quand meme le typer.

    Une page archivee reste une page de cas d'utilisation : on veut savoir que
    "Archive CU-COMPTE (...)" est un CU exclu, pas une page de type inconnu.
    """
    return titre_normalise[len(prefixe):].lstrip(" _-:").strip()


# ==========================================================================
# Ascendance
# ==========================================================================

def chaine_ascendance(page_id, pages_par_id):
    """Ancetres stricts du plus proche au plus lointain, sans la racine de perimetre.

    Detection de cycle : un parent deja vu arrete la remontee au lieu de boucler.
    """
    chaine, courant, vus = [], pages_par_id.get(page_id, {}).get("parent_id"), set()
    while courant and courant in pages_par_id and courant not in vus:
        vus.add(courant)
        chaine.append(courant)
        courant = pages_par_id[courant].get("parent_id")
    if courant:  # parent hors corpus collecte : racine de perimetre ou page absente
        chaine.append(courant)
    return chaine


def racine_perimetre(chaine):
    """Racine A ou B au sommet d'une chaine d'ascendance, ou None si hors perimetre."""
    for ancetre in reversed(chaine):
        if ancetre in ROOTS_GROUPE_A or ancetre in ROOTS_GROUPE_B:
            return ancetre
    return None


def groupe_de_racine(racine):
    if racine in ROOTS_GROUPE_A:
        return "A"
    if racine in ROOTS_GROUPE_B:
        return "B"
    return "hors_perimetre"


# ==========================================================================
# Type et module
# ==========================================================================

def type_par_titre(titre_normalise):
    """Type deduit du seul titre, ou None. L'ordre de TYPE_PATTERNS est significatif."""
    for nom, motif in TYPE_PATTERNS:
        if motif.search(titre_normalise):
            return nom
    return None


def module_par_titre(titre_normalise):
    """Module lu dans le titre : prefixe SF- d'abord, sinon 2e segment d'un titre de spec."""
    trouve = RE_MODULE_SF.match(titre_normalise)
    if trouve:
        return trouve.group(1).upper()
    trouve = RE_MODULE_SPEC.match(titre_normalise)
    if trouve:
        return trouve.group(1).upper()
    return None


def module_par_ascendance(chaine, pages_par_id):
    """Module lu sur le plus proche ancetre SF-*.

    L'ascendance primve sur le titre : elle rattache correctement les pages dont le
    titre ne porte aucun code module ("Reflexion Document", "Briques techniques"),
    et elle est la seule source pour les pages de type MDD/RG dont le module ne
    figure qu'en prefixe.
    """
    for ancetre in chaine:
        page = pages_par_id.get(ancetre)
        if not page:
            continue
        trouve = RE_MODULE_SF.match(normalize_title(page.get("title")))
        if trouve:
            return trouve.group(1).upper()
    return None


# ==========================================================================
# Classification d'une page
# ==========================================================================

def classify_page(page, pages_par_id, exclude_prefixes=DEFAULT_EXCLUDE_TITLE_PREFIXES,
                  exclude_ids=()):
    """Enregistrement de classification d'une page. Ne leve jamais : tout part au rapport."""
    page_id = str(page["id"])
    titre_brut = page.get("title") or ""
    titre = normalize_title(titre_brut)
    avertissements = []

    chaine = chaine_ascendance(page_id, pages_par_id)
    racine = racine_perimetre(chaine)
    groupe = groupe_de_racine(racine)

    # --- Exclusions : propre titre d'abord, ascendance ensuite
    prefixe = match_exclusion(titre, exclude_prefixes)
    heritee = None if prefixe else exclusion_heritee(chaine, pages_par_id, exclude_prefixes)
    exclu_par_id = page_id in exclude_ids
    titre_pour_typage = strip_prefix(titre, prefixe) if prefixe else titre
    # Les libelles ci-dessous partent dans le rapport et le JSON : accentues.
    if exclu_par_id:
        motif_exclusion, source_exclusion = "listée dans exclude_page_ids", page_id
    elif prefixe:
        motif_exclusion, source_exclusion = f"préfixe de titre « {prefixe} »", page_id
    elif heritee:
        ancetre_id, ancetre_titre, ancetre_prefixe = heritee
        motif_exclusion = (f"héritée de « {ancetre_titre} » ({ancetre_id}), "
                           f"préfixe « {ancetre_prefixe} »")
        source_exclusion = ancetre_id
    else:
        motif_exclusion, source_exclusion = None, None

    # --- Type
    type_titre = type_par_titre(titre_pour_typage)
    est_ux = page_id in UX_SUBTREE_ROOTS or any(a in UX_SUBTREE_ROOTS for a in chaine)
    if groupe == "B":
        # La documentation n'est jamais une spec : "VII. Regles de gestion" est un
        # chapitre du guide CAFAT, le scorer comme des regles consolidees produirait
        # un rapport faux. Le type suggere par le titre est conserve comme fait.
        if type_titre:
            avertissements.append(
                f"type « {type_titre} » suggéré par le titre, ignoré : page du groupe B")
        type_page = RESIDUAL_TYPE_GROUPE_B
    elif groupe == "hors_perimetre":
        if type_titre:
            avertissements.append(
                f"type « {type_titre} » suggéré par le titre, ignoré : page hors périmètre")
        type_page = RESIDUAL_TYPE_HORS_PERIMETRE
    elif type_titre:
        type_page = type_titre
    elif est_ux:
        type_page = "UX"
    else:
        type_page = RESIDUAL_TYPE_BY_ROOT.get(racine, "A_QUALIFIER")
        if racine not in RESIDUAL_TYPE_BY_ROOT:
            avertissements.append(
                f"racine « {racine} » sans type résiduel déclaré : classée A_QUALIFIER")

    # --- Module : ascendance d'abord, titre a defaut
    mod_ascendance = module_par_ascendance(chaine, pages_par_id)
    mod_titre = module_par_titre(titre_pour_typage)
    if mod_ascendance:
        module, source_module = mod_ascendance, "ascendance"
    elif mod_titre:
        module, source_module = mod_titre, "titre"
    else:
        module, source_module = None, None
    if mod_ascendance and mod_titre and mod_ascendance != mod_titre:
        # Page probablement mal rangee : le titre annonce un module, l'arbre un autre.
        avertissements.append(
            f"module ambigu : ascendance « {mod_ascendance} », titre « {mod_titre} »")

    if groupe == "hors_perimetre":
        avertissements.append("page hors des 5 racines connues du périmètre")

    # --- Attributs
    attributs = dict(ATTRIBUTS_PAR_TYPE[type_page])
    if groupe == "A":
        # Garde-fou : aucune page de l'arbre des specs ne peut perdre content_source,
        # meme si un type est ajoute plus tard sans y penser. Un faux negatif ici
        # casse une inclusion de multiexcerpt en silence.
        attributs["content_source"] = True
    if motif_exclusion:
        # Une page exclue reste inventoriee : elle n'est ni exportee ni scoree, mais
        # son ADF demeure indexable, sinon un multiexcerpt inclus depuis une page
        # archivee deviendrait irresolvable. Vrai aussi pour les descendants.
        attributs["exported"] = False
        attributs["scored"] = False

    return {
        "id": page_id,
        "title": titre,
        "title_raw": titre_brut if titre_brut != titre else None,
        "version": page.get("version"),
        "parent_id": page.get("parent_id"),
        "parent_title": (pages_par_id.get(page.get("parent_id") or "", {}) or {}).get("title"),
        "group": groupe,
        "root_id": racine,
        "type": type_page,
        "module": module,
        "module_source": source_module,
        "excluded": bool(motif_exclusion),
        "exclusion_reason": motif_exclusion,
        "exclusion_source_id": source_exclusion,
        "exclusion_inherited": bool(motif_exclusion) and source_exclusion != page_id,
        "warnings": avertissements,
        **attributs,
    }


def build_inventory(pages, exclude_prefixes=DEFAULT_EXCLUDE_TITLE_PREFIXES, exclude_ids=()):
    """Classification de tout le corpus. `pages` : iterable de dicts id/title/version/parent_id."""
    pages_par_id = {str(p["id"]): dict(p, id=str(p["id"]),
                                       parent_id=str(p["parent_id"]) if p.get("parent_id") else None)
                    for p in pages}
    return {
        "schema_version": SCHEMA_VERSION,
        "inventory_version": VERSION,
        "pages": [classify_page(p, pages_par_id, exclude_prefixes, exclude_ids)
                  for p in pages_par_id.values()],
    }


def assemble_inventory(classification, *, complete, precedent=None, source=None):
    """pages_inventory.json conforme a contracts/pages_inventory.schema.json.

    `classification` : sortie de build_inventory() — tableau a plat.
    `complete`       : la collecte a-t-elle couvert TOUT le perimetre. Sans
                       valeur par defaut : voir la description du champ dans le
                       schema. C'est la seule autorisation de detruire.
    `precedent`      : inventaire du run precedent, pour reporter last_exported.
                       Ce champ est renseigne par l'exportateur, pas ici : une
                       page non reexportee doit conserver sa valeur.
    `source`         : origine des metadonnees, pour le rapport.

    N'ecrit aucun fichier et n'en lit aucun.
    """
    pages = classification["pages"]
    par_id = {p["id"]: p for p in pages}

    # 1. Les meres se mesurent AVANT toute mise en collision — slugification.md
    #    §9. L'ordre inverse est plus naturel a ecrire et il est faux : une mere
    #    dont les deux filles collisionnent perdrait son repertoire, et le
    #    rapport annoncerait un deplacement dont la cause est ailleurs.
    #    NE PAS DEPLACER CETTE LIGNE SOUS LA BOUCLE.
    meres = meres_exportantes(pages)

    # 2. Collisions : un fait de premier niveau, pas une chaine a relire dans
    #    les warnings. Trois consommateurs — delta, nettoyage des orphelins,
    #    rapport de run.
    collisions, groupe_de_page = [], {}
    for (directory_id, slug), lot in sorted(detecte_collisions(pages).items()):
        groupe = {"directory_id": directory_id, "slug": slug,
                  "page_ids": sorted(p["id"] for p in lot)}
        collisions.append(groupe)
        for page_id in groupe["page_ids"]:
            groupe_de_page[page_id] = groupe

    ancien = (precedent or {}).get("pages", {})
    retenues, unclassified = {}, []

    for page in pages:
        page_id = page["id"]

        # 3. Metadonnees inexploitables : la page QUITTE `pages`. Cas rare et
        #    volontairement etroit — sortir une page de la carte la rend
        #    indistinguable d'une suppression au run suivant.
        motif = None
        if not RE_PAGE_ID.match(page_id):
            motif = "identifiant non numérique"
        elif not (page.get("title") or "").strip():
            motif = "titre absent"

        fiche = dict(page)
        chemin = md_path(page, par_id, meres)
        # Une page d'un groupe exportable sans chemin n'a qu'une cause possible :
        # md_path() a rendu None sur son garde-cycle. Le cas hors perimetre est
        # deja ecarte, il n'appartient a aucun groupe exportable.
        if motif is None and page.get("group") in RACINE_PAR_GROUPE and chemin is None:
            motif = "chaîne d'ascendance circulaire"

        if motif:
            unclassified.append({"id": page_id, "title": page.get("title"),
                                 "reason": motif})
            continue

        groupe = groupe_de_page.get(page_id)
        if groupe:
            autres = [i for i in groupe["page_ids"] if i != page_id]
            fiche["exported"] = False
            fiche["md_path"] = None
            fiche["warnings"] = list(fiche.get("warnings", ())) + [
                f"collision de slug avec {', '.join(autres)} : "
                f"aucun .md produit ce run"]
        else:
            fiche["md_path"] = chemin if fiche["exported"] else None

        # Reporte tel quel, y compris None. L'exportateur l'ecrasera pour les
        # pages qu'il aura effectivement ecrites.
        fiche["last_exported"] = ancien.get(page_id, {}).get("last_exported")
        retenues[page_id] = fiche

    inventaire = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "inventory_version": VERSION,
        "complete": complete,
        "collisions": collisions,
        "pages": retenues,
        "unclassified": unclassified,
    }
    if source:
        inventaire["source"] = source
    return inventaire


# ==========================================================================
# Configuration
# ==========================================================================

def load_exclusions(config_path=None):
    """(prefixes de titre, ids de page) lus dans config.ini, defauts du code a defaut."""
    candidats = [Path(config_path)] if config_path else [
        Path(__file__).resolve().parents[1] / "config.ini",      # pipeline/config.ini
        Path(__file__).resolve().parents[2] / "config.ini",      # racine du depot
    ]
    for chemin in candidats:
        if not chemin.is_file():
            continue
        parser = configparser.ConfigParser()
        parser.read(chemin, encoding="utf-8")
        section = parser["confluence"] if parser.has_section("confluence") else {}
        prefixes = _liste(section.get("exclude_title_prefixes", "")) \
            or list(DEFAULT_EXCLUDE_TITLE_PREFIXES)
        return tuple(prefixes), tuple(_liste(section.get("exclude_page_ids", "")))
    return DEFAULT_EXCLUDE_TITLE_PREFIXES, ()


def _liste(valeur):
    """Valeur ini separee par des virgules -> liste nettoyee. Les espaces sont conserves
    a l'interieur d'un element ("Copie de")."""
    return [v.strip() for v in (valeur or "").split(",") if v.strip()]


# ==========================================================================
# Rapport
# ==========================================================================

def _coche(valeur):
    return "oui" if valeur else "—"


def build_report(inventaire, source_label, prefixes, exclude_ids):
    pages = inventaire["pages"]
    L = []
    add = L.append
    add("# Classification des pages du corpus SINAPSE\n")
    add(f"*Module `inventory.py` v{VERSION} — source : `{source_label}` — "
        f"{len(pages)} pages.*\n")

    add("## Attributs par type\n")
    add("Trois axes indépendants : `exported` (sortie `.md`), `content_source` (ADF "
        "parsé, indexable comme source de multiexcerpt ou de syncBlock), `scored` "
        "(soumis aux skills de validation).\n")
    add("| Type | Pages | exported | content_source | scored |")
    add("|---|---|---|---|---|")
    par_type = Counter(p["type"] for p in pages)
    for type_page, attributs in ATTRIBUTS_PAR_TYPE.items():
        if not par_type.get(type_page):
            continue
        add(f"| **{type_page}** | {par_type[type_page]} | {_coche(attributs['exported'])} "
            f"| {_coche(attributs['content_source'])} | {_coche(attributs['scored'])} |")
    add(f"\nTotaux effectifs : **{sum(1 for p in pages if p['exported'])}** exportées, "
        f"**{sum(1 for p in pages if p['content_source'])}** sources de contenu, "
        f"**{sum(1 for p in pages if p['scored'])}** scorées.\n")

    add("## Répartition par groupe et par type\n")
    groupes = sorted({p["group"] for p in pages})
    add("| Type | " + " | ".join(groupes) + " |")
    add("|---" * (len(groupes) + 1) + "|")
    for type_page in ATTRIBUTS_PAR_TYPE:
        if not par_type.get(type_page):
            continue
        cellules = [str(sum(1 for p in pages if p["type"] == type_page
                            and p["group"] == g) or "—") for g in groupes]
        add(f"| {type_page} | " + " | ".join(cellules) + " |")
    add("")

    a_qualifier = [p for p in pages if p["type"] == "A_QUALIFIER"]
    add(f"## ⚠ Anomalie à résorber — {len(a_qualifier)} pages du groupe A en "
        "`A_QUALIFIER`\n")
    add("**Ce compteur doit tendre vers zéro.** `A_QUALIFIER` n'est pas un état "
        "normal : c'est une page de l'arbre des specs qu'aucune règle mécanique ne "
        "sait nommer. Elle est exportée et reste source de contenu, mais aucun skill "
        "de validation ne la lit — une spec qui atterrirait ici serait invisible.\n")
    if a_qualifier:
        add("| page_id | Titre complet | Module | Parent direct |")
        add("|---|---|---|---|")
        for p in sorted(a_qualifier, key=lambda x: x["title"]):
            add(f"| `{p['id']}` | {p['title']} | {p['module'] or '—'} "
                f"| {p['parent_title'] or '(racine)'} |")
    else:
        add("*Aucune : toutes les pages de specs portent un type explicite.*")
    add("")

    exclues = [p for p in pages if p["excluded"]]
    directes = [p for p in exclues if not p["exclusion_inherited"]]
    heritees = [p for p in exclues if p["exclusion_inherited"]]
    add(f"## Pages exclues — {len(exclues)} "
        f"({len(directes)} directes, {len(heritees)} par héritage)\n")
    add("Inventoriées avec leur motif, ni exportées ni scorées. Leur ADF reste "
        "indexable : un multiexcerpt inclus depuis une page archivée doit encore "
        "pouvoir être résolu.\n")
    if exclues:
        add("| page_id | Titre | Type | Module | Motif |")
        add("|---|---|---|---|---|")
        for p in sorted(exclues, key=lambda x: (x["exclusion_inherited"], x["title"])):
            add(f"| `{p['id']}` | {p['title']} | {p['type']} | {p['module'] or '—'} "
                f"| {p['exclusion_reason']} |")
    else:
        add("*Aucune.*")
    add("")
    if heritees:
        add("Les pages héritées auraient été exportées et scorées sur la seule "
            "lecture de leur titre. Elles sont écartées parce qu'elles vivent sous "
            "une page archivée.\n")

    avertis = [p for p in pages if p["warnings"]]
    add(f"## Avertissements — {len(avertis)} pages\n")
    if avertis:
        add("| page_id | Titre | Avertissement |")
        add("|---|---|---|")
        for p in sorted(avertis, key=lambda x: x["title"]):
            add(f"| `{p['id']}` | {p['title']} | {' ; '.join(p['warnings'])} |")
    else:
        add("*Aucun.*")
    add("")

    renormalises = [p for p in pages if p["title_raw"]]
    add(f"## Titres corrigés par la normalisation — {len(renormalises)}\n")
    if renormalises:
        add("| page_id | Titre brut | Titre normalisé | Type obtenu |")
        add("|---|---|---|---|")
        for p in renormalises:
            add(f"| `{p['id']}` | `{p['title_raw']}` | `{p['title']}` | {p['type']} |")
    else:
        add("*Aucun.*")
    add("")

    add("## Paramètres du run\n")
    add(f"- Préfixes de titre exclus : {', '.join(f'`{x}`' for x in prefixes)}")
    add(f"- `exclude_page_ids` : {', '.join(f'`{x}`' for x in exclude_ids) or '*vide*'}")
    add(f"- Sous-arbres UX : {', '.join(f'`{x}`' for x in UX_SUBTREE_ROOTS)}")
    add(f"- Types réservés non implémentés : "
        f"{', '.join(f'`{x}-*`' for x in TYPES_RESERVES)}")
    add("")
    return "\n".join(L)


# ==========================================================================
# CLI
# ==========================================================================

def main():
    ap = argparse.ArgumentParser(description="Classification des pages SINAPSE")
    ap.add_argument("--from-recensement", required=True,
                    help="JSON produit par recense_adf.py (cle pages_analysees)")
    ap.add_argument("--report", help="rapport markdown a ecrire")
    ap.add_argument("--dump", dest="dump_out",
                    help="dump de classification a plat (produit la fixture de "
                         "non-regression)")
    ap.add_argument("--inventory", dest="inventory_out",
                    help="pages_inventory.json conforme au contrat")
    # `complete` n'a pas de defaut, ni en Python ni en ligne de commande : c'est la
    # seule autorisation de detruire, et un defaut la desarmerait en silence.
    couverture = ap.add_mutually_exclusive_group()
    couverture.add_argument("--complete", dest="complete", action="store_true",
                            default=None,
                            help="la collecte a couvert TOUT le perimetre")
    couverture.add_argument("--incomplete", dest="complete", action="store_false",
                            help="des pages manquent (echec de collecte, run partiel)")
    ap.add_argument("--config", help="config.ini a lire (defaut : recherche automatique)")
    args = ap.parse_args()

    if args.inventory_out and args.complete is None:
        sys.exit("ERREUR : --inventory exige --complete ou --incomplete. Aucune "
                 "valeur par defaut : `complete` est la seule autorisation de "
                 "detruire donnee au delta, la supposer vraie effacerait des .md "
                 "sur un run partiel.")

    source = Path(args.from_recensement)
    data = json.loads(source.read_text(encoding="utf-8"))
    pages = data.get("pages_analysees") or list(data.get("pages", {}).values())
    if not pages:
        sys.exit(f"ERREUR : aucune page dans {source}")

    prefixes, exclude_ids = load_exclusions(args.config)
    inventaire = build_inventory(pages, prefixes, exclude_ids)
    inventaire["source"] = source.name

    if args.report:
        Path(args.report).write_text(
            build_report(inventaire, source.name, prefixes, exclude_ids), encoding="utf-8")
        print(f"  rapport   : {args.report}")
    if args.dump_out:
        Path(args.dump_out).write_text(
            json.dumps(inventaire, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  dump      : {args.dump_out}")

    inventaire_assemble = None
    if args.inventory_out:
        inventaire_assemble = assemble_inventory(
            inventaire, complete=args.complete, source=source.name)
        Path(args.inventory_out).write_text(
            json.dumps(inventaire_assemble, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"  inventaire: {args.inventory_out}")

    p = inventaire["pages"]
    print(f"\n{len(p)} pages classees")
    for type_page, nb in Counter(x["type"] for x in p).most_common():
        print(f"  {type_page:10s} {nb}")
    print(f"  exportees {sum(1 for x in p if x['exported'])}, "
          f"sources {sum(1 for x in p if x['content_source'])}, "
          f"scorees {sum(1 for x in p if x['scored'])}, "
          f"exclues {sum(1 for x in p if x['excluded'])}")
    if inventaire_assemble is not None:
        # Affiches MEME A ZERO : une collision qui n'apparait nulle part est une
        # spec qui disparait sans trace.
        print(f"  collisions {len(inventaire_assemble['collisions'])}, "
              f"unclassified {len(inventaire_assemble['unclassified'])}")
        print(f"  complete {inventaire_assemble['complete']}")


if __name__ == "__main__":
    main()
