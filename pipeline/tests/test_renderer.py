#!/usr/bin/env python3
"""
Tests du renderer ADF -> markdown — pipeline/src/renderer.py.

L'entree du renderer est un ADF DEJA RESOLU ET DEJA INJECTE : les fixtures passent donc
par resolver.resout_document() avant d'etre rendues. C'est ce que main.py fera, et c'est
ce qui change la nature de plusieurs controles — mesure du 18 aout : plus aucun
`syncBlock` ni `nested-table` n'atteint ce module.

Aucun acces reseau, aucun inventaire lu sur le disque : le contexte est injecte.

  python -m pytest pipeline/tests/test_renderer.py   (ou : python test_renderer.py)
"""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

import renderer as rd  # noqa: E402
import resolver as rs  # noqa: E402

FIXTURES = RACINE / "fixtures"
TOTAL = 0

TITRES = {
    "10485761": "Référentiel IHM",
    "109543425": "SF-COMPTE: Modélisation des données",
    "110067713": "JOB-COMPTE-TOIP",
    "180256775": "SF-NOTE: Règles de gestion consolidées",
    "241532980": "API-PORTAIL-FAVORIS",
    "28344321": "CU-NOTE-CREER",
    "28344344": "CU-NOTE-MODIFIER",
    "380567556": "CU-PORTAIL-ACCUEIL",
    "560201732": "2. Fondation et tokens",
}


def check(condition, message):
    global TOTAL
    TOTAL += 1
    if not condition:
        print(f"ECHEC : {message}")
        return 1
    return 0


def leve(fn, message, motif=None):
    """Verifie qu'un appel leve RenduError, et si motif est donne, son message."""
    global TOTAL
    TOTAL += 1
    try:
        fn()
    except rd.RenduError as exc:
        if motif and motif not in str(exc):
            print(f"ECHEC : {message} — message obtenu : {exc}")
            return 1
        return 0
    print(f"ECHEC : {message}")
    return 1


def lisible(valeur):
    """Texte pret a partir dans un message d'echec.

    U+21B3 est absent de cp1252 : un message qui interpole un marqueur tel quel leve
    UnicodeEncodeError des que la sortie est redirigee, et le test plante A LA PLACE de
    son diagnostic. Les litteraux ATTENDUS restent ecrits en clair.
    """
    return ascii(valeur)


POINT_ENTREE_PYTEST = "test_renderer"


def verifie_nommage_pytest():
    """Aucune auxiliaire ne doit porter un nom que pytest collecte.

    pytest collecte par defaut le motif `test*` — qui attrape aussi `tests_...`. Une
    auxiliaire ainsi nommee est executee comme un test, et si elle rend un compte
    d'echecs au lieu de lever, pytest la declare PASSANTE.
    """
    echecs = 0
    collectees = sorted(nom for nom, objet in globals().items()
                        if callable(objet)
                        and getattr(objet, "__module__", None) == __name__
                        and nom.startswith("test"))
    echecs += check(
        collectees == [POINT_ENTREE_PYTEST],
        f"pytest collecterait {collectees}, attendu ['{POINT_ENTREE_PYTEST}']")
    nom_fichier = Path(__file__).name
    echecs += check(
        nom_fichier.startswith("test_") or nom_fichier.endswith("_test.py"),
        f"{nom_fichier} ne matche aucun motif de collecte pytest")
    return echecs


# --------------------------------------------------------------------------
# Lecture des fixtures et fournisseur hors reseau
# --------------------------------------------------------------------------

def charge(page_id):
    return json.loads((FIXTURES / f"{page_id}.json").read_text(encoding="utf-8"))


class Fournisseur:
    """Les deux methodes que le resolver appelle. Alimente par les 9 fixtures."""

    def __init__(self):
        self._par_id = {pid: (pid, TITRES[pid], charge(pid)) for pid in TITRES}
        self._par_titre = {TITRES[pid]: v for pid, v in self._par_id.items()}

    def par_identifiant(self, page_id):
        return self._par_id.get(str(page_id))

    def par_titre(self, titre):
        return self._par_titre.get(titre)


def resolue(page_id):
    """La fixture telle que le renderer la recevra : resolue et injectee."""
    adf, _ = rs.resout_document(charge(page_id), TITRES[page_id], page_id, Fournisseur())
    return adf


# --------------------------------------------------------------------------
# Fabriques de noeuds
# --------------------------------------------------------------------------

def document(noeuds):
    return {"type": "doc", "version": 1, "content": list(noeuds)}


def txt(contenu, marks=None):
    node = {"type": "text", "text": contenu}
    if marks:
        node["marks"] = list(marks)
    return node


def para(*enfants):
    return {"type": "paragraph", "content": list(enfants)}


def cellule(*enfants, entete=False, attrs=None):
    node = {"type": "tableHeader" if entete else "tableCell", "content": list(enfants)}
    if attrs:
        node["attrs"] = dict(attrs)
    return node


def ligne(*cellules):
    return {"type": "tableRow", "content": list(cellules)}


def tableau(*lignes):
    return {"type": "table", "content": list(lignes)}


def rend(adf, inventaire=None, source=None):
    return rd.rend_document(adf, inventaire=inventaire, md_path_source=source)


def niveaux(faits):
    return sorted({f["niveau"] for f in faits})


def codes(faits):
    return sorted(f["code"] for f in faits)


# --------------------------------------------------------------------------
# 1. Parite des deux modes — §C.2, assertion non negociable
# --------------------------------------------------------------------------

def verifie_parite_des_modes():
    """Les deux modes couvrent le MEME ensemble de types, et on l'affiche.

    Forme positive : on compare deux ensembles et on montre l'ecart. C'est la seule
    forme qui reste rouge quand un type est ajoute d'un cote et oublie de l'autre.
    Elle n'est ecrivable que parce que le dispatch passe par des tables et non par un
    match/case — l'enumerabilite est la condition de cette assertion.
    """
    echecs = 0
    markdown = rd.types_couverts(rd.MODE_MARKDOWN)
    html = rd.types_couverts(rd.MODE_HTML)
    echecs += check(markdown == html,
                    f"les deux modes doivent couvrir le meme ensemble de types — "
                    f"markdown seul : {sorted(markdown - html)} ; "
                    f"html seul : {sorted(html - markdown)}")
    echecs += check(len(markdown) == 36,
                    f"le contrat couvre 36 types du corpus complet, le renderer en "
                    f"couvre {len(markdown)} : {sorted(markdown)}")

    # Les 36 nommes un par un : un type retire de la table le ferait voir.
    attendus = {
        "doc", "paragraph", "heading", "rule", "codeBlock", "blockquote", "panel",
        "bulletList", "orderedList", "listItem", "layoutSection", "layoutColumn",
        "expand", "table", "tableRow", "tableCell", "tableHeader", "mediaSingle",
        "media", "caption", "blockCard", "taskList", "taskItem", "extension",
        "bodiedExtension", "inlineExtension", "syncBlock", "bodiedSyncBlock",
        "text", "hardBreak", "status", "mention", "date", "emoji", "inlineCard",
        "mediaInline"}
    echecs += check(markdown == attendus,
                    f"types manquants : {sorted(attendus - markdown)} ; "
                    f"types en trop : {sorted(markdown - attendus)}")

    echecs += leve(lambda: rd.types_couverts("pdf"),
                   "un mode inconnu doit lever", motif="mode inconnu")
    return echecs


# --------------------------------------------------------------------------
# 2. Les 9 fixtures se rendent sans incident
# --------------------------------------------------------------------------

def verifie_corpus_dore():
    """Aucun incident sur les 9 fixtures, et les constats attendus, eux, sont la."""
    echecs = 0
    inventaire = {pid: {"titre": TITRES[pid], "md_path": f"specs/{pid}.md"}
                  for pid in TITRES}
    tous = []
    for pid in sorted(TITRES):
        markdown, faits = rend(resolue(pid), inventaire, f"specs/{pid}.md")
        incidents = [f for f in faits if f["niveau"] == rd.NIVEAU_INCIDENT]
        echecs += check(incidents == [],
                        f"{pid} : aucun incident attendu, obtenu {incidents}")
        echecs += check(bool(markdown.strip()),
                        f"{pid} : le rendu ne doit pas etre vide")
        tous.extend(faits)

    # L'inventaire injecte ne porte que les 9 fixtures : les renvois vers le reste du
    # corpus sont donc hors perimetre, et c'est un constat legitime, pas un defaut.
    codes_vus = sorted({f["code"] for f in tous})
    echecs += check(codes_vus == ["jql_gabarit_non_substitue", "renvoi_hors_perimetre",
                                  "url_edition"],
                    f"trois codes de constat attendus au corpus dore, obtenu {codes_vus}")
    echecs += check(sum(1 for f in tous if f["code"] == "jql_gabarit_non_substitue") == 1,
                    "un seul JQL a gabarit non substitue dans les 9 fixtures")
    echecs += check(sum(1 for f in tous if f["code"] == "url_edition") == 1,
                    "une seule URL d'edition dans les 9 fixtures — l'anomalie de "
                    "380567556, qui pointe en edition vers elle-meme")
    return echecs


# --------------------------------------------------------------------------
# 3. La forme des faits et leurs deux niveaux
# --------------------------------------------------------------------------

def verifie_forme_des_faits():
    """Le niveau vit dans un CHAMP STRUCTURE, jamais dans une phrase."""
    echecs = 0
    inconnu = {"type": "decisionList", "content": []}
    _, faits = rend(document([inconnu]))
    echecs += check(len(faits) == 1, f"un fait attendu, obtenu {faits}")
    if faits:
        fait = faits[0]
        echecs += check(sorted(fait) == ["code", "detail", "emplacement", "niveau"],
                        f"cles attendues code/detail/emplacement/niveau, obtenu "
                        f"{sorted(fait)}")
        echecs += check(fait["niveau"] == "incident",
                        f"un type non couvert est un incident : {fait}")
        echecs += check(fait["code"] == "type_non_couvert", f"{fait}")
        echecs += check("decisionList" in fait["detail"],
                        f"le detail doit nommer le type : {fait}")
        echecs += check(fait["emplacement"] == "doc",
                        f"l'emplacement doit situer le noeud : {fait}")

    # Un constat ne porte pas le meme niveau, et ne perd aucun contenu.
    markdown, faits2 = rend(document([{"type": "heading",
                                       "content": [txt("Sans niveau")]}]))
    echecs += check(niveaux(faits2) == ["constat"],
                    f"un heading sans attrs.level est un CONSTAT : {faits2}")
    echecs += check(markdown == "# Sans niveau",
                    f"le repli au niveau 1 ne perd pas le texte : {markdown!r}")
    return echecs


def verifie_collecte_des_incidents():
    """Le premier type inconnu ne masque pas les suivants.

    En tout-ou-rien, il faut un run complet par type a decouvrir. En collecte, un seul
    run donne la liste entiere — et la page sort avec ce qui a pu etre rendu.
    """
    echecs = 0
    adf = document([
        para(txt("avant")),
        {"type": "decisionList", "content": []},
        para(txt("milieu")),
        {"type": "nestedExpand", "content": []},
        para(txt("apres")),
    ])
    markdown, faits = rend(adf)
    echecs += check(len(faits) == 2,
                    f"DEUX incidents doivent etre collectes en un seul parcours, "
                    f"obtenu {len(faits)} : {faits}")
    echecs += check(all(f["niveau"] == "incident" for f in faits), f"{faits}")
    details = " ".join(f["detail"] for f in faits)
    echecs += check("decisionList" in details and "nestedExpand" in details,
                    f"les deux types doivent etre nommes : {details}")
    echecs += check(markdown == "avant\n\nmilieu\n\napres",
                    f"la page sort avec ce qui a pu etre rendu : {markdown!r}")

    # Le noeud fautif ne produit rien — il ne laisse pas de trace dans le .md.
    echecs += check("decisionList" not in markdown,
                    "un noeud non couvert ne produit RIEN dans le .md")

    # Une racine qui n'est pas un `doc` n'est pas un fait du corpus : c'est un defaut
    # d'appel, et il remonte.
    echecs += leve(lambda: rd.rend_document({"type": "paragraph"}),
                   "une racine non-doc doit lever", motif="racine attendue")
    return echecs


# --------------------------------------------------------------------------
# 4. Liens — chemin relatif au fichier porteur, et cles CHAINES
# --------------------------------------------------------------------------

def carte(url):
    return {"type": "inlineCard", "attrs": {"url": url}}


def verifie_liens_relatifs():
    """Defaut n° 10 du releve : le chemin est relatif au PORTEUR, pas au local_path."""
    echecs = 0
    inventaire = {"28344321": {"titre": "CU-NOTE-CREER",
                               "md_path": "specs/SF-NOTE/CU-NOTE-CREER.md"}}
    url = "https://x.atlassian.net/wiki/spaces/SINAPSE/pages/28344321/CU-NOTE-CREER"

    # Depuis une page voisine, dans le meme repertoire.
    markdown, faits = rend(document([para(carte(url))]), inventaire,
                           "specs/SF-NOTE/CU-NOTE-MODIFIER.md")
    echecs += check(markdown == "[CU-NOTE-CREER](CU-NOTE-CREER.md)",
                    f"meme repertoire : chemin nu attendu, obtenu {markdown!r}")
    echecs += check(faits == [], f"une cible connue ne produit aucun fait : {faits}")

    # Depuis une page d'un autre module, deux niveaux plus bas.
    markdown2, _ = rend(document([para(carte(url))]), inventaire,
                        "specs/SF-COMPTE/API-COMPTE/API-COMPTE-GROUPE.md")
    echecs += check(
        markdown2 == "[CU-NOTE-CREER](../../SF-NOTE/CU-NOTE-CREER.md)",
        f"deux niveaux plus bas : chemin remontant attendu, obtenu {markdown2!r}")

    # Sans md_path_source, le chemin sort tel quel plutot que faux.
    markdown3, _ = rend(document([para(carte(url))]), inventaire, None)
    echecs += check(markdown3 == "[CU-NOTE-CREER](specs/SF-NOTE/CU-NOTE-CREER.md)",
                    f"sans porteur, le md_path brut : {markdown3!r}")
    return echecs


def verifie_identifiants_chaines():
    """Defaut n° 11 : les identifiants de page sont des CHAINES partout dans le depot.

    Un entier ne trouverait jamais sa cle : tous les renvois internes degraderaient en
    lien brut, et le constat « hors perimetre » serait consigne a tort pour chacun. La
    sortie resterait du markdown valide, seulement fausse.
    """
    echecs = 0
    url = "https://x.atlassian.net/wiki/spaces/SINAPSE/pages/28344321/CU-NOTE-CREER"
    page_id, edition = rd.cible_de_lien(url)
    echecs += check(page_id == "28344321",
                    f"l'identifiant extrait est une CHAINE, obtenu {page_id!r}")
    echecs += check(isinstance(page_id, str),
                    f"type attendu str, obtenu {type(page_id).__name__}")
    echecs += check(edition is False, "cette URL n'est pas une URL d'edition")

    # Le lien court decode vers le meme identifiant — trois paires du contrat §6.3.
    # `KwCcL` : 5 caracteres, un `A` de fin retire par Confluence (API-PORTAIL-ACTUALITES).
    for suffixe, attendu in (("AYCwAQ", "28344321"), ("LYBJDg", "239697965"),
                             ("NoC3AQ", "28803126"), ("KwCcL", "748421163")):
        obtenu = rd.page_id_depuis_lien_court(suffixe)
        echecs += check(obtenu == attendu,
                        f"lien court {suffixe} -> {attendu}, obtenu {obtenu!r}")

    court = "https://x.atlassian.net/wiki/x/AYCwAQ"
    inventaire = {"28344321": {"titre": "CU-NOTE-CREER", "md_path": "specs/n.md"}}
    markdown, faits = rend(document([para(carte(court))]), inventaire, "specs/m.md")
    echecs += check(markdown == "[CU-NOTE-CREER](n.md)",
                    f"un lien court doit joindre l'inventaire : {markdown!r}")
    echecs += check(faits == [], f"aucun fait attendu : {faits}")

    # Une cle entiere dans l'inventaire injecte ne doit PAS repondre : c'est le defaut.
    markdown2, faits2 = rend(document([para(carte(url))]),
                             {28344321: {"titre": "X", "md_path": "y.md"}}, "specs/m.md")
    echecs += check(codes(faits2) == ["renvoi_hors_perimetre"],
                    f"une cle entiere ne repond pas, et le constat le dit : {faits2}")
    echecs += check(markdown2 == f"[{url}]({url})",
                    f"lien brut attendu, obtenu {markdown2!r}")
    return echecs


def verifie_url_particulieres():
    """URL d'edition, identifiant hors inventaire, URL d'une autre nature."""
    echecs = 0
    edition = ("https://x.atlassian.net/wiki/spaces/SINAPSE/pages/edit-v2/380567556"
               "#IHM-concernant-la-gestion-du-profil")
    page_id, est_edition = rd.cible_de_lien(edition)
    echecs += check(page_id == "380567556",
                    f"le segment edit-v2 ne doit pas etre pris pour un identifiant, "
                    f"obtenu {page_id!r}")
    echecs += check(est_edition is True, "l'URL d'edition doit etre reconnue")
    _, faits = rend(document([para(carte(edition))]),
                    {"380567556": {"titre": "CU-PORTAIL-ACCUEIL", "md_path": "a.md"}},
                    "b.md")
    echecs += check(codes(faits) == ["url_edition"],
                    f"un constat url_edition attendu : {faits}")

    # Ticket Jira : aucune extraction, aucun fait.
    jira = "https://x.atlassian.net/browse/REC-342"
    markdown, faits2 = rend(document([para(carte(jira))]), {}, "b.md")
    echecs += check(markdown == f"[{jira}]({jira})", f"{markdown!r}")
    echecs += check(faits2 == [],
                    f"une URL d'une autre nature ne produit aucun fait : {faits2}")

    # Identifiant extrait mais absent : constat, pas incident.
    absent = "https://x.atlassian.net/wiki/spaces/SINAPSE/pages/999999/X"
    _, faits3 = rend(document([para(carte(absent))]), {}, "b.md")
    echecs += check(niveaux(faits3) == ["constat"],
                    f"un renvoi hors perimetre est un CONSTAT : {faits3}")
    return echecs


# --------------------------------------------------------------------------
# 5. Les defauts du releve verifiables sur le corpus dore
# --------------------------------------------------------------------------

def verifie_definitions_transparentes():
    """Defaut n° 2 : aucun marqueur de « definition » n'existe au contrat.

    Le §1.9 encadre le contenu RESOLU, c'est-a-dire une inclusion. Une definition
    s'affiche la ou elle est definie, sans marqueur. Les 41 definitions qui subsistent
    dans les 9 fixtures resolues rendraient l'invention visible.
    """
    echecs = 0
    for pid in sorted(TITRES):
        markdown, _ = rend(resolue(pid), {}, f"specs/{pid}.md")
        echecs += check("<!-- definition" not in markdown
                        and "<!-- fin definition" not in markdown,
                        f"{pid} : aucun marqueur de definition ne doit etre emis")

    # Le corps de la definition, lui, doit bien sortir.
    markdown2, faits = rend(resolue("180256775"), {}, "specs/x.md")
    echecs += check("HAB-NOTE-GERER" in markdown2,
                    "le corps d'une definition s'affiche la ou elle est definie")
    echecs += check(all(f["code"] != "inclusion_non_resolue" for f in faits),
                    f"aucune inclusion ne doit rester non resolue : {faits}")
    return echecs


def verifie_marqueurs_reutilisation():
    """Le marqueur arrive comme un `text` marque `em` et sort en italique markdown.

    Il n'y a plus rien de specifique au renderer : c'est la machinerie des marks qui
    s'en charge, sans aucun cas particulier. C'est ce que le §1.9 voulait obtenir.
    """
    echecs = 0
    markdown, _ = rend(resolue("180256775"), {}, "specs/x.md")
    echecs += check("*↳ inclusion : habilitation — source : CU-NOTE-MODIFIER*" in markdown,
                    f"marqueur ouvrant en italique attendu dans le rendu")
    echecs += check("*↳ fin inclusion : habilitation*" in markdown,
                    "marqueur fermant en italique attendu")
    echecs += check("<!--" not in markdown.replace("<!-- toc -->", ""),
                    "aucun commentaire HTML hors du sommaire")

    # En cellule de tableau HTML, le marqueur devient <em> et ne porte AUCUNE
    # asterisque litterale — c'est le defaut mesure a 30 occurrences que le §1.9 corrige.
    marqueur = txt("↳ inclusion : X — source : Y", [{"type": "em"}])
    adf = document([tableau(ligne(cellule(para(marqueur), para(txt("b")))))])
    html, _ = rend(adf, {}, "x.md")
    echecs += check("<em>↳ inclusion : X — source : Y</em>" in html,
                    f"le marqueur doit sortir en <em> en cellule HTML : {lisible(html)}")
    echecs += check("*" not in html,
                    f"aucune asterisque litterale en mode HTML : {lisible(html)}")
    return echecs


def verifie_text_adjacents():
    """Defaut n° 14 : le renderer CONTROLE la propriete du §8.3 plutot que d'y compter.

    Sur 804 paires du corpus, aucune ne porte le meme jeu de marks. Rien ne le garantit
    du cote d'Atlassian, et la violation produirait un balisage casse silencieux.
    """
    echecs = 0
    for pid in sorted(TITRES):
        _, faits = rend(resolue(pid), {}, "x.md")
        adjacents = [f for f in faits if f["code"] == "text_adjacents_memes_marks"]
        echecs += check(adjacents == [],
                        f"{pid} : aucune paire adjacente de memes marks au corpus, "
                        f"obtenu {adjacents}")

    # Le controle doit remonter son constat quand la propriete est violee.
    gras = [{"type": "strong"}]
    _, faits2 = rend(document([para(txt("a", gras), txt("b", gras))]))
    echecs += check(codes(faits2) == ["text_adjacents_memes_marks"],
                    f"deux text adjacents de memes marks : constat attendu, {faits2}")
    echecs += check(niveaux(faits2) == ["constat"],
                    f"c'est un CONSTAT — le balisage sort laid, rien n'est perdu, la "
                    f"page reste scorable : {faits2}")

    # Deux jeux differents ne declenchent rien.
    _, faits3 = rend(document([para(txt("a", gras), txt("b", [{"type": "em"}]))]))
    echecs += check(faits3 == [], f"jeux differents : aucun constat, {faits3}")
    return echecs


def verifie_legende_collee():
    """Defaut n° 17 : « immediatement sous l'image » se rend par un <br>."""
    echecs = 0
    media = {"type": "media", "attrs": {"id": "abc", "collection": "contentId-1",
                                        "alt": "image.png"}}
    legende = {"type": "caption", "content": [txt("Figure 1")]}
    adf = document([{"type": "mediaSingle", "content": [media, legende]}])
    markdown, _ = rend(adf)
    echecs += check(
        markdown == "![image.png](adf-media://abc?collection=contentId-1)<br>\n*Figure 1*",
        f"image et legende collees par un <br>, obtenu {markdown!r}")

    # Sans legende, aucun <br> parasite.
    markdown2, _ = rend(document([{"type": "mediaSingle", "content": [media]}]))
    echecs += check(markdown2 == "![image.png](adf-media://abc?collection=contentId-1)",
                    f"une image sans legende ne porte pas de <br> : {markdown2!r}")

    # Le corpus dore en porte 4 : aucune ne doit etre separee par une ligne vide.
    for pid in ("109543425", "380567556"):
        rendu, _ = rend(resolue(pid), {}, "x.md")
        for morceau in rendu.split("\n\n"):
            if "adf-media://" in morceau and "*" in morceau:
                echecs += check("<br>\n*" in morceau,
                                f"{pid} : legende collee attendue, obtenu "
                                f"{lisible(morceau[:120])}")
    return echecs


# --------------------------------------------------------------------------
# 6. Tableaux — les deux rendus
# --------------------------------------------------------------------------

def verifie_tableaux():
    """Pipes quand tout est inline, HTML des qu'une cellule porte du bloc."""
    echecs = 0
    simple = tableau(ligne(cellule(para(txt("A")), entete=True),
                           cellule(para(txt("B")), entete=True)),
                     ligne(cellule(para(txt("1"))), cellule(para(txt("2")))))
    markdown, _ = rend(document([simple]))
    echecs += check(markdown == "| A | B |\n| --- | --- |\n| 1 | 2 |",
                    f"tableau en pipes attendu, obtenu {markdown!r}")

    # Sans tableHeader : une ligne d'en-tete VIDE, sans quoi la syntaxe est invalide.
    sans_entete = tableau(ligne(cellule(para(txt("1"))), cellule(para(txt("2")))))
    markdown2, _ = rend(document([sans_entete]))
    echecs += check(markdown2 == "|  |  |\n| --- | --- |\n| 1 | 2 |",
                    f"ligne d'en-tete vide attendue, obtenu {markdown2!r}")

    # Une liste en cellule fait basculer TOUT le tableau en HTML.
    liste = {"type": "bulletList", "content": [
        {"type": "listItem", "content": [para(txt("x"))]}]}
    complexe = tableau(ligne(cellule(para(txt("A"))), cellule(liste)))
    markdown3, _ = rend(document([complexe]))
    echecs += check(markdown3.startswith("<table>") and markdown3.endswith("</table>"),
                    f"bascule en HTML attendue, obtenu {markdown3[:80]!r}")
    echecs += check("<ul><li><p>x</p></li></ul>" in markdown3,
                    f"la liste doit sortir en HTML : {markdown3}")
    echecs += check("- x" not in markdown3,
                    "aucun repli sur le rendu markdown dans une cellule HTML")

    # Le `|` d'une cellule en pipes est echappe, et lui seul.
    avec_pipe = tableau(ligne(cellule(para(txt("R|O|P")))))
    markdown4, _ = rend(document([avec_pipe]))
    echecs += check("R\\|O\\|P" in markdown4,
                    f"le | doit etre echappe en cellule de pipes : {markdown4!r}")

    # Les caracteres actifs du markdown, eux, sortent tels quels.
    markdown5, _ = rend(document([para(txt("a*b_c[d]!e#f"))]))
    echecs += check(markdown5 == "a*b_c[d]!e#f",
                    f"aucun echappement generique hors des deux cas : {markdown5!r}")
    return echecs


# --------------------------------------------------------------------------
# 7. Marks — la regle par porteur
# --------------------------------------------------------------------------

def verifie_marks():
    """Les six enveloppants, les sept jetes, les deux reserves au `text`."""
    echecs = 0
    echecs += check(len(rd.MARKS_CONNUS) == 15,
                    f"la liste blanche compte 15 marks, obtenu "
                    f"{len(rd.MARKS_CONNUS)} : {sorted(rd.MARKS_CONNUS)}")
    echecs += check("fontSize" in rd.MARKS_JETES,
                    "fontSize est connu ET jete : texte conserve, mise en forme perdue")
    echecs += check(len(rd.MARKS_JETES) == 7,
                    f"7 marks jetes, obtenu {sorted(rd.MARKS_JETES)}")

    rendus = {
        "strong": "**t**", "em": "*t*", "code": "`t`", "underline": "<u>t</u>",
        "strike": "~~t~~",
    }
    for mark, attendu in rendus.items():
        markdown, faits = rend(document([para(txt("t", [{"type": mark}]))]))
        echecs += check(markdown == attendu,
                        f"mark {mark} : {attendu!r} attendu, obtenu {markdown!r}")
        echecs += check(faits == [], f"mark {mark} sur un text : aucun fait, {faits}")

    lien = [{"type": "link", "attrs": {"href": "https://x/y"}}]
    markdown2, _ = rend(document([para(txt("t", lien))]))
    echecs += check(markdown2 == "[t](https://x/y)", f"{markdown2!r}")

    fond = [{"type": "backgroundColor", "attrs": {"color": "#f8e6a0"}}]
    markdown3, _ = rend(document([para(txt("t", fond))]))
    echecs += check(markdown3 == '<mark style="background:#f8e6a0">t</mark>',
                    f"le hex est conserve brut, sans table couleur -> sens : {markdown3!r}")

    couleur = [{"type": "textColor", "attrs": {"color": "#bf2600"}}]
    markdown4, _ = rend(document([para(txt("t", couleur))]))
    echecs += check(markdown4 == '<span style="color:#bf2600">t</span>', f"{markdown4!r}")

    # Un mark jete laisse le texte intact, et ne produit aucun fait.
    for jete in sorted(rd.MARKS_JETES):
        markdown5, faits5 = rend(document([para(txt("t", [{"type": jete}]))]))
        echecs += check(markdown5 == "t",
                        f"mark jete {jete} : texte intact attendu, obtenu {markdown5!r}")
        echecs += check(faits5 == [], f"un mark jete ne produit aucun fait : {faits5}")
    return echecs


def verifie_marks_sur_le_corpus():
    """Defaut n° 7 : les marks se lisent sur TOUS les noeuds.

    89 marks portes par un noeud autre que `text` au corpus dore, sur 10 couples. Ils y
    sont tous jetes : les ignorer produirait la bonne sortie, et aucune comparaison de
    .md ne verrait le defaut. Ce controle verifie donc ce qui est verifiable ici — que
    les lire n'introduit ni incident ni perte.
    """
    echecs = 0
    for pid in sorted(TITRES):
        _, faits = rend(resolue(pid), {}, "x.md")
        marks = [f for f in faits if f["code"].startswith("mark_")]
        echecs += check(marks == [],
                        f"{pid} : les 89 marks non-text du corpus sont tous jetes, "
                        f"aucun fait attendu, obtenu {marks}")
    return echecs


# --------------------------------------------------------------------------
# 8. Conteneurs transparents et blocs simples
# --------------------------------------------------------------------------

def verifie_transparents():
    """`panel`, `layoutSection`, `layoutColumn`, `taskList` : aucun marqueur propre."""
    echecs = 0
    panneau = {"type": "panel", "attrs": {"panelType": "info"},
               "content": [para(txt("dedans"))]}
    markdown, _ = rend(document([panneau]))
    echecs += check(markdown == "dedans",
                    f"le panel disparait, son contenu reste : {markdown!r}")

    # Un panelType inconnu ne leve pas.
    inconnu = {"type": "panel", "attrs": {"panelType": "chartreuse"},
               "content": [para(txt("dedans"))]}
    markdown2, faits = rend(document([inconnu]))
    echecs += check(markdown2 == "dedans" and faits == [],
                    f"un panelType inconnu est jete sans lever : {markdown2!r} {faits}")

    # Deux colonnes : une ligne vide entre elles, aucun marqueur de colonne.
    colonne = lambda t: {"type": "layoutColumn", "attrs": {"width": 50.0},
                         "content": [para(txt(t))]}
    section = {"type": "layoutSection", "content": [colonne("gauche"), colonne("droite")]}
    markdown3, _ = rend(document([section]))
    echecs += check(markdown3 == "gauche\n\ndroite",
                    f"une ligne vide separe les colonnes : {markdown3!r}")

    # Une colonne vide ne produit rien.
    vide = {"type": "layoutColumn", "content": [{"type": "paragraph"}]}
    section2 = {"type": "layoutSection", "content": [colonne("seule"), vide]}
    markdown4, _ = rend(document([section2]))
    echecs += check(markdown4 == "seule",
                    f"une colonne vide ne produit rien : {markdown4!r}")

    # expand : le titre en GRAS, jamais en titre markdown.
    depliant = {"type": "expand", "attrs": {"title": "EVOLUTIONS"},
                "content": [para(txt("corps"))]}
    markdown5, _ = rend(document([depliant]))
    echecs += check(markdown5 == "**EVOLUTIONS**\n\ncorps",
                    f"gras attendu, jamais un heading : {markdown5!r}")
    echecs += check(not markdown5.startswith("#"),
                    "emettre ## inseterait une section fantome dans l'index")

    sans_titre = {"type": "expand", "attrs": {}, "content": [para(txt("corps"))]}
    markdown6, _ = rend(document([sans_titre]))
    echecs += check(markdown6 == "corps",
                    f"sans titre, seul le contenu est emis : {markdown6!r}")
    return echecs


def verifie_blocs_simples():
    """`rule`, `codeBlock`, `blockquote`, listes, `toc`, `taskItem`."""
    echecs = 0
    markdown, _ = rend(document([para(txt("avant")), {"type": "rule"},
                                 para(txt("apres"))]))
    echecs += check(markdown == "avant\n\n---\n\napres",
                    f"une ligne vide precede le --- : {markdown!r}")

    code = {"type": "codeBlock", "attrs": {"language": "sql"},
            "content": [txt("SELECT 1")]}
    markdown2, _ = rend(document([code]))
    echecs += check(markdown2 == "```sql\nSELECT 1\n```", f"{markdown2!r}")

    citation = {"type": "blockquote", "content": [para(txt("cite"))]}
    markdown3, _ = rend(document([citation]))
    echecs += check(markdown3 == "> cite", f"{markdown3!r}")

    imbriquee = {"type": "bulletList", "content": [
        {"type": "listItem", "content": [
            para(txt("un")),
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [para(txt("un.a"))]}]}]},
        {"type": "listItem", "content": [para(txt("deux"))]}]}
    markdown4, _ = rend(document([imbriquee]))
    echecs += check(markdown4 == "- un\n\n  - un.a\n- deux",
                    f"indentation par niveau attendue, obtenu {markdown4!r}")

    ordonnee = {"type": "orderedList", "content": [
        {"type": "listItem", "content": [para(txt("a"))]},
        {"type": "listItem", "content": [para(txt("b"))]}]}
    markdown5, _ = rend(document([ordonnee]))
    echecs += check(markdown5 == "1. a\n2. b", f"{markdown5!r}")

    toc = {"type": "extension", "attrs": {"extensionKey": "toc", "parameters": {}}}
    markdown6, faits = rend(document([toc]))
    echecs += check(markdown6 == "<!-- toc -->",
                    f"le sommaire reste en commentaire : {markdown6!r}")
    echecs += check(faits == [], f"le toc ne produit aucun fait : {faits}")

    taches = {"type": "taskList", "content": [
        {"type": "taskItem", "attrs": {"state": "DONE"}, "content": [txt("faite")]},
        {"type": "taskItem", "attrs": {"state": "TODO"}, "content": [txt("a faire")]}]}
    markdown7, _ = rend(document([taches]))
    echecs += check(markdown7 == "- [x] faite\n- [ ] a faire", f"{markdown7!r}")

    saut = para(txt("a"), {"type": "hardBreak"}, txt("b"))
    markdown8, _ = rend(document([saut]))
    echecs += check(markdown8 == "a<br>b", f"{markdown8!r}")
    return echecs


def verifie_inline_simples():
    """`status`, `mention`, et le cas ou une mention leve."""
    echecs = 0
    statut = {"type": "status", "attrs": {"color": "yellow", "style": "bold",
                                          "text": "A VALIDER"}}
    markdown, _ = rend(document([para(statut)]))
    echecs += check(markdown == "A VALIDER",
                    f"texte nu attendu, sans decoration : {markdown!r}")

    mention = {"type": "mention", "attrs": {"text": "@Jean Dupont", "id": "557058"}}
    markdown2, _ = rend(document([para(mention)]))
    echecs += check(markdown2 == "@Jean Dupont", f"{markdown2!r}")

    sans_texte = {"type": "mention", "attrs": {"id": "557058"}}
    markdown3, _ = rend(document([para(sans_texte)]))
    echecs += check(markdown3 == "@557058", f"repli sur l'id : {markdown3!r}")

    nue = {"type": "mention", "attrs": {}}
    markdown4, faits = rend(document([para(nue)]))
    echecs += check(codes(faits) == ["mention_sans_identite"],
                    f"une mention sans text ni id est un incident : {faits}")
    echecs += check(markdown4 == "",
                    f"le noeud fautif ne produit rien : {markdown4!r}")
    return echecs


def verifie_cartes_bloc():
    """`blockCard` : cartouche Jira, lien simple, et le cas qui leve."""
    echecs = 0
    jql = '(id in linkedIssues(REC-35,"réfère"))'
    carte_jira = {"type": "blockCard", "attrs": {"datasource": {
        "id": "jira", "parameters": {"cloudId": "x", "jql": jql},
        "views": [{"type": "table", "properties": {
            "columns": [{"key": "summary"}, {"key": "status"}]}}]}}}
    markdown, faits = rend(document([carte_jira]))
    echecs += check(markdown == ("**Requête Jira (cartouche)**\n\n"
                                 "- vue : `table`\n"
                                 "- colonnes : summary, status\n"
                                 "- JQL :\n\n"
                                 f"```\n{jql}\n```"), f"{markdown!r}")
    echecs += check(faits == [], f"aucun fait pour un JQL sain : {faits}")

    gabarit = {"type": "blockCard", "attrs": {"datasource": {
        "parameters": {"jql": '"Specs[URL Field]" = "{{page.url}}"'}, "views": []}}}
    _, faits2 = rend(document([gabarit]))
    echecs += check(codes(faits2) == ["jql_gabarit_non_substitue"],
                    f"un JQL a gabarit est un CONSTAT : {faits2}")
    echecs += check(niveaux(faits2) == ["constat"],
                    f"la page est parsee correctement, c'est son contenu qui est "
                    f"fautif : {faits2}")

    lien = {"type": "blockCard", "attrs": {"url": "https://sharepoint/x"}}
    markdown3, _ = rend(document([lien]))
    echecs += check(markdown3 == "[https://sharepoint/x](https://sharepoint/x)",
                    f"{markdown3!r}")

    nue = {"type": "blockCard", "attrs": {}}
    _, faits3 = rend(document([nue]))
    echecs += check(codes(faits3) == ["blockcard_sans_cible"],
                    f"sans datasource ni url : incident, {faits3}")
    echecs += check(niveaux(faits3) == ["incident"], f"{faits3}")
    return echecs


# --------------------------------------------------------------------------
# 9. Les cas que le corpus dore n'exerce pas — §10 du contrat et releve du 18 aout
# --------------------------------------------------------------------------
# Trois d'entre eux sont PRESENTS au corpus dore SANS CONSEQUENCE OBSERVABLE : un
# renderer qui les porte sort vert sur les 9 fixtures, et une relecture des .md ne les
# verrait pas non plus, les fichiers etant corrects. Ce sont les plus dangereux.

def verifie_rule_et_heading_en_cellule():
    """Defaut n° 4 : `rule` et `heading` sont du contenu de bloc en cellule.

    HORS D'ATTEINTE DU CORPUS DORE. Mesure du 18 aout : 1 cellule porte un `rule` en
    enfant direct, 0 un `heading`, et le nombre de cellules ou la liste a sept types et
    la liste a neuf donnent un verdict different est ZERO — le tableau hote de cette
    cellule est complexe pour un autre motif. Le contrat qualifie lui-meme cette
    couverture de fortuite. Sans ce test, la liste amputee resterait verte.
    """
    echecs = 0
    echecs += check("rule" in rd.BLOCS_EN_CELLULE and "heading" in rd.BLOCS_EN_CELLULE,
                    f"rule et heading doivent etre du contenu de bloc en cellule : "
                    f"{sorted(rd.BLOCS_EN_CELLULE)}")
    echecs += check(len(rd.BLOCS_EN_CELLULE) == 9,
                    f"9 types de contenu de bloc en cellule, obtenu "
                    f"{sorted(rd.BLOCS_EN_CELLULE)}")

    # Une cellule dont le SEUL contenu est un `rule` : sans la regle, le tableau reste
    # en pipes et le `---` sort au milieu d'une ligne, qu'il rompt.
    avec_rule = tableau(ligne(cellule(para(txt("A"))), cellule({"type": "rule"})))
    markdown, _ = rend(document([avec_rule]))
    echecs += check(markdown.startswith("<table>"),
                    f"un `rule` en cellule fait basculer le tableau en HTML, obtenu "
                    f"{markdown[:80]!r}")
    echecs += check("<hr>" in markdown, f"le rule doit sortir en <hr> : {markdown}")
    echecs += check("---" not in markdown,
                    f"aucun `---` ne doit rompre la ligne de pipes : {markdown}")

    # Meme chose pour un `heading`.
    avec_titre = tableau(ligne(cellule(para(txt("A"))),
                               cellule({"type": "heading", "attrs": {"level": 2},
                                        "content": [txt("Titre")]})))
    markdown2, _ = rend(document([avec_titre]))
    echecs += check(markdown2.startswith("<table>"),
                    f"un `heading` en cellule fait basculer en HTML : {markdown2[:80]!r}")
    echecs += check("<h2>Titre</h2>" in markdown2, f"{markdown2}")
    echecs += check("## Titre" not in markdown2,
                    "aucun `##` ne doit sortir au milieu d'une ligne de pipes")
    return echecs


def verifie_table_en_cellule():
    """Defaut n° 6, garde-fou : une cellule dont le seul bloc est un `table`.

    Le renderer recoit un arbre DEJA INJECTE : il n'y a plus de `nested-table` a mal
    juger, et le defaut d'origine — evaluer la complexite avant injection — ne peut plus
    exister ici. Le risque residuel est de reintroduire une evaluation anticipee, et
    c'est ce que ce controle surveille : un `table` en cellule bascule, seul.

    HORS D'ATTEINTE DU CORPUS DORE : les 2 cellules qui portaient un `nested-table` sont
    complexes pour un autre motif, mesure du 18 aout.
    """
    echecs = 0
    interne = tableau(ligne(cellule(para(txt("x")))))
    externe = tableau(ligne(cellule(para(txt("A"))), cellule(interne)))
    markdown, faits = rend(document([externe]))
    echecs += check(markdown.startswith("<table>"),
                    f"un `table` en cellule fait basculer en HTML : {markdown[:80]!r}")
    echecs += check(markdown.count("<table>") == 2,
                    f"le tableau imbrique se rend en <table> complet, recursivement : "
                    f"{markdown}")
    echecs += check("| x |" not in markdown,
                    f"aucune syntaxe en pipes ne doit subsister : {markdown}")
    echecs += check(faits == [], f"aucun fait attendu : {faits}")
    return echecs


def verifie_entete_mixte():
    """§10 : la ligne d'en-tete mixte, troisieme declencheur de bascule.

    HORS D'ATTEINTE DU CORPUS DORE : 58 tableaux sur 58 puis 60 sur 60 ont une premiere
    ligne homogene et aucun `tableHeader` ailleurs. Sans la regle, le cas degrade en
    silence — tout l'en-tete passe en corps et une ligne d'en-tete vide est emise.
    """
    echecs = 0
    mixte = tableau(ligne(cellule(para(txt("A")), entete=True), cellule(para(txt("B")))),
                    ligne(cellule(para(txt("1"))), cellule(para(txt("2")))))
    markdown, _ = rend(document([mixte]))
    echecs += check(markdown.startswith("<table>"),
                    f"une premiere ligne mixte fait basculer en HTML : {markdown[:80]!r}")
    echecs += check("<th><p>A</p></th><td><p>B</p></td>" in markdown,
                    f"<th> et <td> cohabitent sans contrainte en HTML : {markdown}")

    # Un `tableHeader` hors de la premiere ligne fait basculer aussi.
    tardif = tableau(ligne(cellule(para(txt("A"))), cellule(para(txt("B")))),
                     ligne(cellule(para(txt("1")), entete=True), cellule(para(txt("2")))))
    markdown2, _ = rend(document([tardif]))
    echecs += check(markdown2.startswith("<table>"),
                    f"un tableHeader hors premiere ligne fait basculer : "
                    f"{markdown2[:80]!r}")

    # Une premiere ligne homogene SANS entete reste en pipes : ce n'est pas mixte.
    homogene = tableau(ligne(cellule(para(txt("1"))), cellule(para(txt("2")))))
    markdown3, _ = rend(document([homogene]))
    echecs += check(markdown3.startswith("|"),
                    f"une ligne homogene sans entete n'est pas mixte : {markdown3!r}")
    return echecs


def verifie_fusion_de_cellules():
    """§10 : `colspan` et `rowspan`. Zero dans les 9 fixtures, 6 et 10 au corpus complet.

    Un tableau en pipes n'a AUCUNE syntaxe pour les exprimer : la fusion disparaitrait
    sans trace. Ils ne sont emis que s'ils valent plus de 1.
    """
    echecs = 0
    fusion = tableau(ligne(cellule(para(txt("A")), entete=True,
                                   attrs={"colspan": 3}),),
                     ligne(cellule(para(txt("1"))), cellule(para(txt("2"))),
                           cellule(para(txt("3")))))
    markdown, _ = rend(document([fusion]))
    echecs += check(markdown.startswith("<table>"),
                    f"une fusion fait basculer en HTML : {markdown[:80]!r}")
    echecs += check('<th colspan="3">' in markdown, f"{markdown}")

    vertical = tableau(ligne(cellule(para(txt("A")), attrs={"rowspan": 2}),
                             cellule(para(txt("B")))),
                       ligne(cellule(para(txt("C")))))
    markdown2, _ = rend(document([vertical]))
    echecs += check('<td rowspan="2">' in markdown2, f"{markdown2}")

    # colspan = 1 n'est pas emis.
    unitaire = tableau(ligne(cellule(para(txt("A")), attrs={"colspan": 1}),
                             cellule({"type": "rule"})))
    markdown3, _ = rend(document([unitaire]))
    echecs += check("colspan" not in markdown3,
                    f"colspan=1 ne doit pas etre emis : {markdown3}")
    return echecs


def verifie_pas_de_repli_html():
    """Defaut n° 3 : un type sans regle HTML en cellule HTML est un INCIDENT.

    HORS D'ATTEINTE DU CORPUS DORE depuis que le renderer recoit un arbre injecte :
    mesure du 18 aout, AUCUN type sans regle HTML ne se trouve dans une cellule de
    tableau HTML. C'etait le `nested-table` qui rendait ce chemin atteignable.

    Le repli est tentant parce qu'il produit toujours quelque chose — mais ce quelque
    chose est `**Libelle**` affiche avec ses asterisques a l'interieur d'une balise.
    """
    echecs = 0
    inconnu = {"type": "decisionList", "content": [para(txt("**gras**"))]}
    liste = {"type": "bulletList", "content": [
        {"type": "listItem", "content": [para(txt("bloc"))]}]}
    # La liste fait basculer le tableau en HTML ; le type inconnu est dans l'autre cellule.
    adf = document([tableau(ligne(cellule(liste), cellule(inconnu)))])
    markdown, faits = rend(adf)
    echecs += check(markdown.startswith("<table>"),
                    f"le tableau doit etre en HTML : {markdown[:60]!r}")
    echecs += check(codes(faits) == ["type_sans_regle_html"],
                    f"le contrat nomme ce cas a part : {faits}")
    echecs += check(niveaux(faits) == ["incident"],
                    f"c'est un incident, pas un constat : {faits}")
    echecs += check("decisionList" in faits[0]["detail"] if faits else False,
                    f"le detail doit nommer le type : {faits}")
    echecs += check("<td></td>" in markdown,
                    f"le noeud fautif ne produit rien, la cellule sort vide : {markdown}")
    echecs += check("**gras**" not in markdown,
                    f"AUCUN repli sur le rendu markdown : {markdown}")

    # Le meme type hors tableau donne l'autre code : le mode change le diagnostic.
    _, faits2 = rend(document([inconnu]))
    echecs += check(codes(faits2) == ["type_non_couvert"],
                    f"hors cellule HTML, c'est un type non couvert : {faits2}")
    return echecs


def verifie_marks_hors_text():
    """Defaut n° 7 : la regle des marks se lit par PORTEUR.

    HORS D'ATTEINTE DU CORPUS DORE : les 89 marks non-`text` mesures y sont tous des
    marks jetes, donc les ignorer produit la BONNE sortie et aucune comparaison de .md
    ne verrait le defaut. Seul un cas synthetique l'atteint.
    """
    echecs = 0
    fond = [{"type": "backgroundColor", "attrs": {"color": "#f8e6a0"}}]

    # Sur un `paragraph` : rendu UNE SEULE FOIS autour du paragraphe rendu, et constat.
    paragraphe = {"type": "paragraph", "marks": fond,
                  "content": [txt("La date "), txt("doit etre", [{"type": "strong"}]),
                              txt(" de la forme JJ/MM/AAAA")]}
    markdown, faits = rend(document([paragraphe]))
    echecs += check(
        markdown == '<mark style="background:#f8e6a0">La date **doit etre** de la '
                    'forme JJ/MM/AAAA</mark>',
        f"le mark enveloppe le paragraphe RENDU, une seule fois : {markdown!r}")
    echecs += check(markdown.count("<mark") == 1,
                    f"une seule fois, pas une par noeud text : {markdown!r}")
    echecs += check(codes(faits) == ["mark_hors_text"],
                    f"un mark enveloppant hors `text` est un CONSTAT : {faits}")
    echecs += check(niveaux(faits) == ["constat"], f"{faits}")

    # Un mark hors des quinze : incident, quel que soit le porteur.
    for porteur in (txt("t", [{"type": "sparkle"}]),
                    {"type": "paragraph", "marks": [{"type": "sparkle"}],
                     "content": [txt("t")]}):
        _, faits2 = rend(document([porteur if porteur.get("type") == "paragraph"
                                   else para(porteur)]))
        echecs += check(codes(faits2) == ["mark_hors_liste_blanche"],
                        f"un mark hors des quinze est un incident : {faits2}")

    # `code` et `link` levent sur tout porteur autre que `text`.
    for mark in ("code", "link"):
        bloc = {"type": "paragraph", "marks": [{"type": mark, "attrs": {"href": "x"}}],
                "content": [txt("t")]}
        markdown3, faits3 = rend(document([bloc]))
        echecs += check(codes(faits3) == ["mark_porteur_inadmis"],
                        f"mark {mark} sur un paragraph : incident attendu, {faits3}")
        echecs += check(markdown3 == "t",
                        f"le contenu reste intact, seul le mark est perdu : {markdown3!r}")

    # Un mark enveloppant sur un conteneur de blocs : incident. `**` ne traverse pas une
    # ligne vide, et <mark> ne peut pas contenir un <ul>.
    for conteneur in ("table", "bulletList", "expand", "panel", "blockquote"):
        node = {"type": conteneur, "marks": [{"type": "strong"}], "content": []}
        _, faits4 = rend(document([node]))
        echecs += check("mark_porteur_inadmis" in codes(faits4),
                        f"mark enveloppant sur {conteneur} : incident attendu, {faits4}")

    # Les six admis sur les six porteurs admis ne produisent pas d'incident.
    for porteur in ("paragraph", "heading"):
        node = {"type": porteur, "marks": fond, "content": [txt("t")]}
        if porteur == "heading":
            node["attrs"] = {"level": 2}
        _, faits5 = rend(document([node]))
        echecs += check(niveaux(faits5) == ["constat"],
                        f"{porteur} admet un mark enveloppant, avec constat : {faits5}")
    return echecs


def verifie_fontsize():
    """§10 : `fontSize`. Zero dans les 9 fixtures, 3 au corpus complet.

    Porte par un `paragraph` et non par un noeud `text` : le jeter laisse le paragraphe
    et tout son contenu intacts, `status` compris. Deux defauts du prototype s'annulaient
    en apparence sur ce cas — il ne lisait pas les marks des paragraphes, donc il ne
    levait pas sur un mark qu'il ne connaissait pas.
    """
    echecs = 0
    statut = {"type": "status", "attrs": {"text": "A VALIDER"}}
    paragraphe = {"type": "paragraph", "marks": [{"type": "fontSize",
                                                  "attrs": {"fontSize": "small"}}],
                  "content": [txt("Legende : "), statut]}
    markdown, faits = rend(document([paragraphe]))
    echecs += check(markdown == "Legende : A VALIDER",
                    f"texte et status intacts, mise en forme jetee : {markdown!r}")
    echecs += check(faits == [],
                    f"un mark jete ne produit AUCUN fait, meme hors `text` : {faits}")
    return echecs


def verifie_date():
    """§7.4 : ISO 8601, en UTC EXPLICITE. Zero dans les 9 fixtures, 47 au corpus.

    La forme naive emploie le fuseau de la machine : sans effet a Noumea, mais un
    executant place dans un fuseau negatif decalerait les 47 dates d'un jour, sans un
    mot. Le defaut ne se voit jamais sur le poste ou il a ete ecrit.
    """
    echecs = 0
    date = {"type": "date", "attrs": {"localId": "8adb9609", "timestamp": "1776816000000"}}
    markdown, faits = rend(document([para(date, txt(" "))]))
    echecs += check(markdown == "2026-04-22 ",
                    f"ISO 8601 attendu, obtenu {markdown!r}")
    echecs += check(faits == [], f"{faits}")

    # Minuit UTC : la date ne doit pas glisser d'un jour.
    minuit = {"type": "date", "attrs": {"timestamp": "1735689600000"}}
    markdown2, _ = rend(document([para(minuit)]))
    echecs += check(markdown2 == "2025-01-01",
                    f"minuit UTC ne doit pas glisser : {markdown2!r}")

    # Le noeud ne vit pas seul dans son paragraphe : un renderer qui le jetterait
    # laisserait une cellule ne contenant qu'une espace, sans bascule en HTML.
    cellule_date = tableau(ligne(cellule(para(date, txt(" ")))))
    markdown3, _ = rend(document([cellule_date]))
    echecs += check("2026-04-22" in markdown3,
                    f"la date doit survivre en cellule de pipes : {markdown3!r}")

    for mauvais in (None, "", "hier", {}):
        _, faits2 = rend(document([para({"type": "date",
                                         "attrs": {"timestamp": mauvais}})]))
        echecs += check(codes(faits2) == ["date_timestamp_invalide"],
                        f"timestamp {mauvais!r} : incident attendu, {faits2}")
    return echecs


def verifie_emoji():
    """§7.5 : `attrs.text`, repli sur `shortName`. Zero dans les 9 fixtures, 21 au corpus."""
    echecs = 0
    atlassien = {"type": "emoji", "attrs": {"id": "atlassian-warning",
                                            "text": ":warning:",
                                            "shortName": ":warning:"}}
    markdown, faits = rend(document([para(atlassien)]))
    echecs += check(markdown == ":warning:",
                    f"shortcode GFM valide, pas un artefact : {markdown!r}")
    echecs += check(faits == [], f"{faits}")

    # Famille codepoint : `text` porte le vrai caractere.
    codepoint = {"type": "emoji", "attrs": {"id": "1f600", "text": "\U0001f600",
                                            "shortName": ":grinning:"}}
    markdown2, _ = rend(document([para(codepoint)]))
    echecs += check(markdown2 == "\U0001f600",
                    f"le rendu ne distingue pas les deux familles : {lisible(markdown2)}")

    repli = {"type": "emoji", "attrs": {"id": "x", "shortName": ":x:"}}
    markdown3, _ = rend(document([para(repli)]))
    echecs += check(markdown3 == ":x:", f"repli sur shortName : {markdown3!r}")

    nu = {"type": "emoji", "attrs": {"id": "x"}}
    _, faits2 = rend(document([para(nu)]))
    echecs += check(codes(faits2) == ["emoji_sans_texte"],
                    f"ni text ni shortName : incident, {faits2}")
    return echecs


def verifie_media_inline():
    """§5.1 : image au fil du texte, sans `alt`. Zero dans les 9 fixtures, 6 au corpus.

    NOEUD INLINE, contrairement au `mediaSingle` du §5 qui est un bloc : il se rend dans
    la chaine inline de son paragraphe, sans ligne vide autour.
    """
    echecs = 0
    image = {"type": "mediaInline", "attrs": {"id": "d73b9bbd",
                                              "collection": "contentId-428113938",
                                              "localId": "662318527c9f"}}
    markdown, faits = rend(document([para(txt("avant "), image, txt(" apres"))]))
    echecs += check(
        markdown == "avant ![](adf-media://d73b9bbd?collection=contentId-428113938) apres",
        f"rendu inline sans ligne vide autour, sans alt : {markdown!r}")
    echecs += check(faits == [], f"{faits}")
    echecs += check("\n" not in markdown,
                    f"un noeud inline ne coupe pas son paragraphe : {markdown!r}")
    return echecs


def verifie_blockcard_repli_url():
    """§6.1 : si `parameters.jql` manque, la requete se decode depuis `attrs.url`.

    HORS D'ATTEINTE DU CORPUS DORE : les 5 blockCard des 9 fixtures portent tous un
    `parameters.jql`, mesure du 18 aout. Le prototype levait au premier manque sans
    tenter le second chemin.
    """
    echecs = 0
    sans_jql = {"type": "blockCard", "attrs": {
        "url": "https://x.atlassian.net/issues/?jql=project%20%3D%20REC",
        "datasource": {"id": "jira", "parameters": {"cloudId": "x"}, "views": []}}}
    markdown, faits = rend(document([sans_jql]))
    echecs += check("project = REC" in markdown,
                    f"le JQL doit etre decode depuis attrs.url : {markdown!r}")
    echecs += check(faits == [], f"aucun fait : le repli est prevu au contrat, {faits}")

    # Les DEUX absents : le noeud leve.
    ni_ni = {"type": "blockCard", "attrs": {
        "datasource": {"id": "jira", "parameters": {"cloudId": "x"}, "views": []}}}
    _, faits2 = rend(document([ni_ni]))
    echecs += check(codes(faits2) == ["blockcard_sans_jql"],
                    f"les deux absents : incident, {faits2}")
    echecs += check(niveaux(faits2) == ["incident"], f"{faits2}")
    return echecs


def verifie_inclusion_non_resolue():
    """Un noeud de reutilisation non consomme a l'entree du renderer.

    HORS D'ATTEINTE DU CORPUS DORE, et volontairement : la mesure du 18 aout donne zero
    `syncBlock` et zero `nested-table` a l'entree du renderer, le resolver les ayant tous
    consommes. Le contrat ne nomme pas ce cas — il suppose qu'il ne se produit pas. Le
    traiter en incident est le choix conservateur : du contenu manquerait dans le .md.
    """
    echecs = 0
    inclusion = {"type": "extension", "attrs": {
        "extensionKey": "multiexcerpt-fast-include-block-macro",
        "parameters": {"macroParams": {"name": {"value": "habilitation"}}}}}
    markdown, faits = rend(document([inclusion]))
    echecs += check(codes(faits) == ["inclusion_non_resolue"],
                    f"une inclusion non consommee est un incident : {faits}")
    echecs += check(markdown == "", f"le noeud fautif ne produit rien : {markdown!r}")

    sync = {"type": "syncBlock", "attrs": {"resourceId": "confluence-page/1/abc"},
            "content": []}
    _, faits2 = rend(document([sync]))
    echecs += check(codes(faits2) == ["inclusion_non_resolue"], f"{faits2}")

    imbriquee = {"type": "extension", "attrs": {
        "extensionKey": "nested-table", "parameters": {"adf": "{}"}}}
    _, faits3 = rend(document([imbriquee]))
    echecs += check(codes(faits3) == ["nested_table_non_injectee"],
                    f"un nested-table non injecte est un incident : {faits3}")

    # Une macro inconnue leve : la table du §2.3 est une LISTE BLANCHE.
    inconnue = {"type": "extension", "attrs": {"extensionKey": "jira", "parameters": {}}}
    _, faits4 = rend(document([inconnue]))
    echecs += check(codes(faits4) == ["macro_non_couverte"],
                    f"une macro non listee leve, elle ne passe pas en silence : {faits4}")

    # Une DEFINITION, elle, est transparente et ne produit aucun fait.
    definition = {"type": "bodiedExtension", "attrs": {
        "extensionKey": "multiexcerpt-fast-block-macro",
        "parameters": {"macroParams": {"name": {"value": "hab"}}}},
        "content": [para(txt("corps"))]}
    markdown5, faits5 = rend(document([definition]))
    echecs += check(markdown5 == "corps" and faits5 == [],
                    f"une definition est transparente, sans marqueur : "
                    f"{markdown5!r} {faits5}")
    return echecs


def run():
    echecs = verifie_nommage_pytest()
    echecs += verifie_parite_des_modes()
    echecs += verifie_corpus_dore()
    echecs += verifie_forme_des_faits()
    echecs += verifie_collecte_des_incidents()
    echecs += verifie_liens_relatifs()
    echecs += verifie_identifiants_chaines()
    echecs += verifie_url_particulieres()
    echecs += verifie_definitions_transparentes()
    echecs += verifie_marqueurs_reutilisation()
    echecs += verifie_text_adjacents()
    echecs += verifie_legende_collee()
    echecs += verifie_tableaux()
    echecs += verifie_marks()
    echecs += verifie_marks_sur_le_corpus()
    echecs += verifie_transparents()
    echecs += verifie_blocs_simples()
    echecs += verifie_inline_simples()
    echecs += verifie_cartes_bloc()
    echecs += verifie_rule_et_heading_en_cellule()
    echecs += verifie_table_en_cellule()
    echecs += verifie_entete_mixte()
    echecs += verifie_fusion_de_cellules()
    echecs += verifie_pas_de_repli_html()
    echecs += verifie_marks_hors_text()
    echecs += verifie_fontsize()
    echecs += verifie_date()
    echecs += verifie_emoji()
    echecs += verifie_media_inline()
    echecs += verifie_blockcard_repli_url()
    echecs += verifie_inclusion_non_resolue()

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0


def test_renderer():
    """Point d'entree pytest."""
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
