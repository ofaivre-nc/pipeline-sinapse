#!/usr/bin/env python3
"""
Tests du resolver de contenu reutilise — pipeline/src/resolver.py.

Les quatre premiers controles sont les quatre defauts STRUCTURELS du resolver d'origine
(script du skill confluence-outil-resolve-multiexcerpt v1.2), qui ont motive la decision
de reecrire plutot que de porter :

  1. cle par nom seul          -> deux `habilitation` se confondent
  2. injection par str.replace -> apres conversion, l'ordre inverse du contrat
  3. aucun decodage d'entites  -> `RG-NOTE-ASSOCATION&period;PERSONNE` ne joint jamais
  4. aucune recursion, aucun garde-fou de cycle

Suivent les controles de parcours (croisements table imbriquee / reutilisation, cles
non parcourues) et de recuperation (carte de titres, un appel par page source).

Aucun acces reseau : le resolver ne connait que le fournisseur qu'on lui passe, et
celui des tests lit pipeline/fixtures/.

  python -m pytest pipeline/tests/test_resolver.py   (ou : python test_resolver.py)
"""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

import multiexcerpt as mx  # noqa: E402
import resolver as rs  # noqa: E402

FIXTURES = RACINE / "fixtures"
TOTAL = 0

# Titres reels des 9 fixtures — ils servent de cible aux inclusions par titre, donc
# ils doivent etre exacts au caractere pres. Source : pipeline/fixtures/README.md.
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
    """Verifie qu'un appel leve ResolutionError, et si motif est donne, son message."""
    global TOTAL
    TOTAL += 1
    try:
        fn()
    except mx.ResolutionError as exc:
        if motif and motif not in str(exc):
            print(f"ECHEC : {message} — message obtenu : {exc}")
            return 1
        return 0
    print(f"ECHEC : {message}")
    return 1


# Seule fonction de ce fichier que pytest doit collecter.
POINT_ENTREE_PYTEST = "test_resolver"


def verifie_nommage_pytest():
    """Aucune auxiliaire ne doit porter un nom que pytest collecte.

    pytest collecte par defaut le motif `test*` — qui attrape aussi `tests_...`. Une
    auxiliaire ainsi nommee est executee comme un test, et si elle rend un compte
    d'echecs au lieu de lever, pytest la declare PASSANTE. Voir la meme fonction dans
    test_multiexcerpt.py et test_delta.py.
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
# Lecture des fixtures et fournisseur hors reseau
# --------------------------------------------------------------------------

def charge(page_id):
    return json.loads((FIXTURES / f"{page_id}.json").read_text(encoding="utf-8"))


class Fournisseur:
    """Les deux methodes que le resolver appelle, et un compteur d'appels.

    Le compteur est l'instrument du controle « un appel par page source distincte,
    jamais un par inclusion ».
    """

    def __init__(self, entrees=()):
        self._par_id = {}
        self._par_titre = {}
        for page_id, titre, adf in entrees:
            entree = (str(page_id), titre, adf)
            self._par_id[str(page_id)] = entree
            self._par_titre.setdefault(titre, []).append(entree)
        self.appels_id = []
        self.appels_titre = []

    def par_identifiant(self, page_id):
        self.appels_id.append(str(page_id))
        return self._par_id.get(str(page_id))

    def par_titre(self, titre):
        self.appels_titre.append(titre)
        trouves = self._par_titre.get(titre) or []
        if len(trouves) > 1:
            return list(trouves)      # ambiguite : au resolver de lever
        return trouves[0] if trouves else None


def fournisseur_fixtures(ids=None, extra=()):
    """Fournisseur alimente par les fixtures du depot, plus des pages synthetiques."""
    entrees = [(pid, TITRES[pid], charge(pid))
               for pid in (ids if ids is not None else TITRES)]
    return Fournisseur(list(entrees) + list(extra))


# --------------------------------------------------------------------------
# Fabriques de noeuds
# --------------------------------------------------------------------------

def document(noeuds):
    return {"type": "doc", "version": 1, "content": list(noeuds)}


def para(contenu, local_id=None):
    node = {"type": "paragraph", "content": [{"type": "text", "text": contenu}]}
    if local_id:
        node["attrs"] = {"localId": local_id}
    return node


def definition(nom, corps, famille="multiexcerpt", local_id=None):
    cle = ("multiexcerpt-fast-block-macro" if famille == "multiexcerpt" else "excerpt")
    node = {"type": "bodiedExtension",
            "attrs": {"extensionKey": cle,
                      "parameters": {"macroParams": {"name": {"value": nom}}}},
            "content": list(corps)}
    if local_id:
        node["attrs"]["localId"] = local_id
    return node


def inclusion(nom, page=None, famille="multiexcerpt", local_id=None):
    cle = ("multiexcerpt-fast-include-block-macro" if famille == "multiexcerpt"
           else "excerpt-include")
    params = {"name": {"value": nom}}
    if page is not None:
        # La famille excerpt range la page source sous la cle VIDE, pas sous `page`.
        params["page" if famille == "multiexcerpt" else ""] = {"value": page}
    node = {"type": "extension",
            "attrs": {"extensionKey": cle, "parameters": {"macroParams": params}}}
    if local_id:
        node["attrs"]["localId"] = local_id
    return node


def inclusion_inline(nom, page=None, cle="multiexcerpt-fast-include-inline-macro",
                     type_noeud="inlineExtension", local_id=None):
    """Inclusion de macro sous forme INLINE — deux axes INDEPENDANTS.

    Le type de noeud et la cle d'extension varient separement, parce que c'est
    exactement ce que l'union du §1.9 reconnait : `inlineExtension` OU une cle portant
    `include-inline`. Les fabriquer ensemble empecherait d'exercer une branche a la fois.
    """
    params = {"name": {"value": nom}}
    if page is not None:
        params["page"] = {"value": page}
    node = {"type": type_noeud,
            "attrs": {"extensionKey": cle, "parameters": {"macroParams": params}}}
    if local_id:
        node["attrs"]["localId"] = local_id
    return node


def txt(contenu, marks=None):
    node = {"type": "text", "text": contenu}
    if marks:
        node["marks"] = list(marks)
    return node


def para_de(enfants):
    """Paragraphe compose noeud par noeud — l'hote d'une inclusion inline."""
    return {"type": "paragraph", "content": list(enfants)}


def liste(*textes_):
    return {"type": "bulletList", "content": [
        {"type": "listItem", "content": [para(t)]} for t in textes_]}


def sync_definition(uuid, corps):
    return {"type": "bodiedSyncBlock",
            "attrs": {"resourceId": uuid, "localId": "def-" + uuid[:8]},
            "content": list(corps)}


def sync_inclusion(page_id, uuid):
    return {"type": "syncBlock",
            "attrs": {"resourceId": f"confluence-page/{page_id}/{uuid}",
                      "localId": "inc-" + uuid[:8]},
            "content": []}


def table_imbriquee(noeuds):
    """Le marqueur nested-table de Confluence : son ADF est une CHAINE JSON."""
    interne = json.dumps({"type": "doc", "version": 1, "content": list(noeuds)})
    return {"type": "extension",
            "attrs": {"extensionKey": "nested-table",
                      "parameters": {"adf": interne, "cxhtml": "<table/>",
                                     "reason": "A table in a table cell…"}}}


# --------------------------------------------------------------------------
# Lecture du resultat
# --------------------------------------------------------------------------

def texte(node):
    """Tout le texte d'un sous-arbre, dans l'ordre du document."""
    morceaux = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                morceaux.append(n.get("text", ""))
            for enfant in (n.get("content") or []):
                walk(enfant)
        elif isinstance(n, list):
            for enfant in n:
                walk(enfant)

    walk(node)
    return " ".join(morceaux)


def natures(adf):
    """Natures de reutilisation encore presentes dans un arbre."""
    trouvees = []

    def walk(n):
        if not isinstance(n, dict):
            return
        nature = mx.classify_reuse_node(n)
        if nature:
            trouvees.append(nature)
        if mx.is_nested_table(n):
            trouvees.append("nested_table")
        for enfant in (n.get("content") or []):
            walk(enfant)

    walk(adf)
    return trouvees


def zones(adf, nom):
    """Contenus injectes pour un nom donne, un par paire de marqueurs.

    Ne regarde que le premier niveau du document : les inclusions des documents de test
    y sont posees directement.
    """
    ouvertes, courant, dedans = [], [], False
    for node in (adf.get("content") or []):
        brut = texte(node).strip()
        if brut.startswith(f"↳ inclusion : {nom} — source : "):
            dedans, courant = True, []
            continue
        if dedans and brut.startswith("↳ fin inclusion :"):
            ouvertes.append(courant)
            dedans = False
            continue
        if dedans:
            courant.append(node)
    return ouvertes


def marqueurs(adf):
    """Tous les marqueurs d'inclusion du document, a plat."""
    return [t for t in (texte(n).strip() for n in (adf.get("content") or []))
            if t.startswith("↳")]


def textes(adf):
    """Valeurs de TOUS les noeuds `text` de l'arbre, a n'importe quelle profondeur.

    marqueurs() ne lit que le premier niveau, ce qui suffit aux documents synthetiques ;
    dans les fixtures reelles les inclusions vivent au fond des tableaux.
    """
    trouves = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                trouves.append(n.get("text", ""))
            for enfant in (n.get("content") or []):
                walk(enfant)
        elif isinstance(n, list):
            for enfant in n:
                walk(enfant)

    walk(adf)
    return trouves


def marqueurs_profonds(adf):
    """Tous les marqueurs de l'arbre, QUEL QUE SOIT LEUR PORTEUR.

    Un marqueur de bloc est un `paragraph` dont l'unique enfant est un `text` marque
    `em` ; un marqueur inline est ce meme `text`, depose dans le paragraphe hote. Les
    deux sont des noeuds `text` : un lecteur restreint a l'un des deux porteurs ferait
    passer l'invariant « deux marqueurs par inclusion resolue » en cessant de compter
    ceux de l'autre.

    Le filtre sur U+21B3 seul est licite parce qu'il a ete mesure : le caractere
    n'apparait dans AUCUN des 2791 noeuds `text` des 9 fixtures brutes, ni dans leur
    JSON, `parameters.adf` compris. Si une page venait a en porter, resserrer sur la
    mark `em` plus le prefixe.
    """
    return [t for t in textes(adf) if t.startswith("↳")]


def lisible(valeur):
    """Texte de marqueur pret a partir dans un message d'echec.

    U+21B3 est absent de cp1252 — contrairement a `e` accentue et a l'em-dash, qui y
    sont. Un message d'echec qui interpole un marqueur tel quel leve
    UnicodeEncodeError des que la sortie est redirigee, et le test plante A LA PLACE de
    son propre diagnostic : on ne sait plus lequel des controles a echoue. Les litteraux
    ATTENDUS, eux, restent ecrits en clair — c'est la forme qu'ils surveillent.
    """
    return ascii(valeur)


def mal_places(adf):
    """Types des enfants directs d'un `paragraph` qui ne sont PAS d'un type inline.

    C'est la mesure du §B.1 : 5 avant la substitution inline, 0 apres. Elle porte sur
    rs.TYPES_INLINE et non sur le seul type `paragraph` — on mesure et on compare a la
    liste vide, on ne cherche pas un coupable connu.
    """
    trouves = []

    def walk(n):
        if isinstance(n, dict):
            enfants = n.get("content") or []
            if n.get("type") == "paragraph":
                trouves.extend(e.get("type") for e in enfants
                               if isinstance(e, dict)
                               and e.get("type") not in rs.TYPES_INLINE)
            for enfant in enfants:
                walk(enfant)
        elif isinstance(n, list):
            for enfant in n:
                walk(enfant)

    walk(adf)
    return trouves


def identites(node):
    """id() de tous les objets mutables d'un sous-arbre — dictionnaires et listes.

    Sert a prouver qu'un contenu injecte ne partage rien avec sa source : l'egalite
    structurelle ne dit rien du partage, et c'est le partage qui est dangereux.
    """
    vus = set()

    def walk(n):
        if isinstance(n, dict):
            vus.add(id(n))
            for valeur in n.values():
                walk(valeur)
        elif isinstance(n, list):
            vus.add(id(n))
            for valeur in n:
                walk(valeur)

    walk(node)
    return vus


def corps_definition(page_id, nom):
    """Corps de la definition `nom` telle qu'elle est dans la fixture `page_id`."""
    adf = charge(page_id)
    trouve = []

    def walk(n):
        if not isinstance(n, dict):
            return
        if (mx.classify_reuse_node(n) or "").endswith("_definition") and mx.famille_macro(n):
            if mx.clean_name(mx.macro_param(n, "name")) == nom:
                trouve.append(n)
        for enfant in (n.get("content") or []):
            walk(enfant)

    walk(adf)
    if len(trouve) != 1:
        raise AssertionError(f"{nom} attendu une fois sur {page_id}, trouve {len(trouve)}")
    return trouve[0].get("content") or []


# --------------------------------------------------------------------------
# 1. La cle est (page, nom) — deux `habilitation` ne se confondent pas
# --------------------------------------------------------------------------

def verifie_cle_page_et_nom():
    """Defaut n°1 du resolver d'origine, sur donnees reelles.

    `habilitation` est defini sur trois fixtures. Une resolution par nom seul — le
    str.replace() de l'origine — recopierait le meme contenu dans les deux emplacements.

    NOTE SUR LES DONNEES : l'instruction annonce des contenus differents sur 28344321
    et 28344344 ; ils sont en realite identiques au localId pres (tous deux
    « HAB-NOTE-GERER », meme mark de fond). L'assertion de DIFFERENCE porte donc sur le
    couple 28344321 / 380567556, qui differe reellement de texte
    (« application:utilisateur:acceder »). Le couple annonce est conserve, avec
    l'assertion qui a du sens sur lui : chaque emplacement porte le corps EXACT de sa
    page source, localId compris — ce qu'une resolution par nom seul casse aussi.
    """
    echecs = 0
    fournisseur = fournisseur_fixtures()

    # --- Le couple qui differe reellement de contenu.
    doc = document([inclusion("habilitation", TITRES["28344321"]),
                    inclusion("habilitation", TITRES["380567556"])])
    resolu, faits = rs.resout_document(doc, "CU-TEST", "999", fournisseur)
    injecte = zones(resolu, "habilitation")
    echecs += check(len(injecte) == 2,
                    f"les deux inclusions doivent produire deux zones, obtenu {len(injecte)}")
    if len(injecte) == 2:
        gauche, droite = texte(injecte[0]), texte(injecte[1])
        echecs += check(gauche != droite,
                        "DEUX CIBLES DIFFERENTES DOIVENT DONNER DEUX CONTENUS DIFFERENTS "
                        f"— obtenu deux fois {gauche!r}")
        echecs += check(gauche == "HAB-NOTE-GERER",
                        f"l'inclusion visant CU-NOTE-CREER doit rendre son habilitation, "
                        f"obtenu {gauche!r}")
        echecs += check(droite == "application:utilisateur:acceder",
                        f"l'inclusion visant CU-PORTAIL-ACCUEIL doit rendre la sienne, "
                        f"obtenu {droite!r}")
    echecs += check([f["statut"] for f in faits] == ["resolue", "resolue"],
                    f"les deux inclusions doivent etre resolues : {faits}")
    echecs += check([f["cle"] for f in faits]
                    == [(TITRES["28344321"], "habilitation"),
                        (TITRES["380567556"], "habilitation")],
                    f"la cle consignee doit porter la page ET le nom : {faits}")

    # --- Le couple annonce par l'instruction : corps exact de sa propre page.
    doc2 = document([inclusion("habilitation", TITRES["28344321"]),
                     inclusion("habilitation", TITRES["28344344"])])
    resolu2, _ = rs.resout_document(doc2, "CU-TEST", "999", fournisseur_fixtures())
    injecte2 = zones(resolu2, "habilitation")
    echecs += check(len(injecte2) == 2, "deux zones attendues pour le second couple")
    if len(injecte2) == 2:
        echecs += check(injecte2[0] == corps_definition("28344321", "habilitation"),
                        "la premiere zone doit etre le corps EXACT de 28344321")
        echecs += check(injecte2[1] == corps_definition("28344344", "habilitation"),
                        "la seconde zone doit etre le corps EXACT de 28344344")
        echecs += check(injecte2[0] != injecte2[1],
                        "les deux corps portent des localId distincts : les confondre "
                        "signerait une resolution par nom seul")
    return echecs


# --------------------------------------------------------------------------
# 2. Les entites HTML sont decodees des deux cotes de la jointure
# --------------------------------------------------------------------------

def verifie_entites_html():
    """Defaut n°3 : ` RG-NOTE-ASSOCATION&period;PERSONNE` — entite ET espace de tete.

    La definition est sur 180256775 sous cette forme brute ; l'inclusion de 28344321
    l'ecrit de la meme facon. Sans clean_name() des deux cotes, la cle ne colle pas.
    """
    echecs = 0
    brut = " RG-NOTE-ASSOCATION&period;PERSONNE"
    propre = "RG-NOTE-ASSOCATION.PERSONNE"
    doc = document([inclusion(brut, TITRES["180256775"])])
    resolu, faits = rs.resout_document(doc, "CU-TEST", "999", fournisseur_fixtures())

    echecs += check([f["statut"] for f in faits] == ["resolue"],
                    f"une inclusion a entite doit joindre sa definition : {faits}")
    echecs += check(faits and faits[0]["cle"] == (TITRES["180256775"], propre),
                    f"la cle consignee doit porter le nom DECODE : {faits}")
    injecte = zones(resolu, propre)
    echecs += check(len(injecte) == 1,
                    f"le marqueur doit porter le nom decode, une zone attendue : "
                    f"{lisible(marqueurs(resolu))}")
    if len(injecte) == 1:
        attendu = corps_definition("180256775", propre)
        echecs += check(injecte[0] == attendu,
                        "le corps injecte doit etre celui de la definition")
        echecs += check(len(attendu) == 5,
                        f"la definition du corpus porte 5 noeuds, obtenu {len(attendu)}")

    # Le nom brut, non decode, ne doit surtout pas etre une cle valide.
    echecs += check(mx.clean_name(brut) == propre,
                    "clean_name doit rendre le nom decode et deshabille")
    return echecs


# --------------------------------------------------------------------------
# 3. La descente se poursuit dans ce qui vient d'etre injecte
# --------------------------------------------------------------------------

def verifie_recursion_dans_injecte():
    """Defaut n°4 (recursion) sur donnees reelles.

    `RG-NOTE-AUTEUR-AUTORISE-MODIFICATION-SUPPRESSION`, definie sur 180256775, contient
    elle-meme une inclusion de `habilitation` visant CU-NOTE-MODIFIER. En l'incluant,
    on force le resolver a redescendre dans le contenu injecte.
    """
    echecs = 0
    nom = "RG-NOTE-AUTEUR-AUTORISE-MODIFICATION-SUPPRESSION"
    doc = document([inclusion(nom, TITRES["180256775"])])
    resolu, faits = rs.resout_document(doc, "CU-TEST", "999", fournisseur_fixtures())

    echecs += check(natures(resolu) == [],
                    f"aucune inclusion ne doit subsister apres resolution : {natures(resolu)}")
    echecs += check(len(faits) == 2,
                    f"deux inclusions attendues — celle du document et celle du corps "
                    f"injecte : {faits}")
    echecs += check(all(f["statut"] == "resolue" for f in faits),
                    f"les deux doivent etre resolues : {faits}")
    echecs += check("HAB-NOTE-GERER" in texte(resolu),
                    "le contenu de l'inclusion imbriquee doit apparaitre dans le resultat")
    echecs += check(any(f["cle"] == (TITRES["28344344"], "habilitation") for f in faits),
                    f"l'inclusion imbriquee vise CU-NOTE-MODIFIER : {faits}")

    # La page hote entiere : 180256775 porte 2 inclusions logees dans des corps de
    # definition. Une definition est parcourue SUR PLACE, sans etre remplacee.
    resolu2, faits2 = rs.resout_document(charge("180256775"), TITRES["180256775"],
                                         "180256775", fournisseur_fixtures())
    restantes = [n for n in natures(resolu2) if n.endswith("_include")]
    echecs += check(restantes == [],
                    f"aucune inclusion non consommee sur la page hote : {restantes}")
    definitions = [n for n in natures(resolu2) if n.endswith("_definition")]
    echecs += check(len(definitions) == 24,
                    f"les 24 definitions de 180256775 restent en place, obtenu "
                    f"{len(definitions)}")
    echecs += check(len(faits2) == 2,
                    f"les 2 inclusions de la page doivent etre consignees : {faits2}")
    return echecs


# --------------------------------------------------------------------------
# 4. Cycle et prefixe de mecanisme
# --------------------------------------------------------------------------

def verifie_cycle():
    """Defaut n°4 (garde-fou) : A inclut B, B inclut A.

    Verifie aussi que le guard est ouvert AVEC le prefixe de mecanisme : sans lui, une
    cle (page, nom) multiexcerpt et la meme cle excerpt se confondraient dans la pile,
    et une imbrication legitime passerait pour un cycle.
    """
    echecs = 0
    page = "SF-CYCLE"
    adf_cycle = document([
        definition("A", [para("debut A"), inclusion("B", page)]),
        definition("B", [para("debut B"), inclusion("A", page)]),
    ])
    fournisseur = Fournisseur([("777", page, adf_cycle)])

    echecs += leve(
        lambda: rs.resout_document(adf_cycle, page, "777", fournisseur),
        "un cycle A -> B -> A doit lever", motif="cycle")

    # Le message doit nommer le chemin, pas seulement le fait.
    try:
        rs.resout_document(adf_cycle, page, "777", fournisseur)
    except mx.ResolutionError as exc:
        echecs += check("->" in str(exc) and "A" in str(exc) and "B" in str(exc),
                        f"le message de cycle doit nommer le chemin : {exc}")

    # Meme cle, deux mecanismes : ce n'est PAS un cycle. Sans prefixe, ca leverait.
    adf_deux = document([
        definition("X", [para("corps multiexcerpt X"), inclusion("X", page, famille="excerpt")]),
        definition("X", [para("corps excerpt X")], famille="excerpt"),
        inclusion("X", page),
    ])
    fournisseur2 = Fournisseur([("778", page, adf_deux)])
    resolu, faits = rs.resout_document(adf_deux, page, "778", fournisseur2)
    echecs += check(all(f["statut"] == "resolue" for f in faits),
                    f"la meme cle dans deux familles n'est pas un cycle : {faits}")
    echecs += check(sorted({f["mecanisme"] for f in faits}) == ["excerpt", "multiexcerpt"],
                    f"les deux mecanismes doivent etre consignes : {faits}")
    echecs += check("corps excerpt X" in texte(resolu),
                    "l'inclusion excerpt doit resoudre contre la definition excerpt")

    # Profondeur : un guard etroit doit lever avant de s'enfoncer.
    guard = mx.CycleGuard(profondeur_max=1)
    adf_deux_niveaux = document([
        definition("N1", [inclusion("N2", page)]),
        definition("N2", [para("fond")]),
        inclusion("N1", page),
    ])
    fournisseur3 = Fournisseur([("779", page, adf_deux_niveaux)])
    echecs += leve(
        lambda: rs.resout_document(adf_deux_niveaux, page, "779", fournisseur3, guard=guard),
        "un depassement de profondeur doit lever", motif="imbrication")
    return echecs


# --------------------------------------------------------------------------
# 5. Parcours — les deux croisements que le corpus n'exerce pas
# --------------------------------------------------------------------------

def verifie_croisements():
    """Table imbriquee <-> reutilisation, dans les deux sens.

    Aucun des deux croisements n'a d'occurrence dans les 9 fixtures : c'est la raison
    pour laquelle le parcours est unique, et la raison pour laquelle ces deux controles
    sont synthetiques. Sans eux, la precaution ne serait verifiee par rien.
    """
    echecs = 0
    page = "SF-CROISEMENT"

    # --- Une table imbriquee contient une inclusion.
    source = document([definition("DANS-TABLE", [para("valeur venue de la definition")])])
    hote = document([table_imbriquee([
        {"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [inclusion("DANS-TABLE", page)]}]}]}])])
    fournisseur = Fournisseur([("800", page, source)])
    resolu, faits = rs.resout_document(hote, "CU-HOTE", "801", fournisseur)
    echecs += check("nested_table" not in natures(resolu),
                    "la table imbriquee doit etre injectee, pas conservee")
    echecs += check("table" in [n.get("type") for n in (resolu.get("content") or [])],
                    f"le table injecte doit remonter au premier niveau : "
                    f"{[n.get('type') for n in resolu.get('content') or []]}")
    echecs += check([f["statut"] for f in faits] == ["resolue"],
                    f"l'inclusion LOGEE DANS la table imbriquee doit etre resolue : {faits}")
    echecs += check("valeur venue de la definition" in texte(resolu),
                    "le contenu de la definition doit apparaitre dans la table injectee")

    # --- Un corps de definition contient une table imbriquee.
    source2 = document([definition("AVEC-TABLE", [
        para("avant"),
        table_imbriquee([{"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [para("cellule imbriquee")]}]}]}]),
    ])])
    hote2 = document([inclusion("AVEC-TABLE", page)])
    fournisseur2 = Fournisseur([("802", page, source2)])
    resolu2, faits2 = rs.resout_document(hote2, "CU-HOTE", "803", fournisseur2)
    echecs += check("nested_table" not in natures(resolu2),
                    "la table imbriquee du corps injecte doit etre injectee a son tour")
    echecs += check("cellule imbriquee" in texte(resolu2),
                    "le contenu de la table imbriquee doit survivre a l'injection")
    echecs += check([f["statut"] for f in faits2] == ["resolue"], f"{faits2}")
    return echecs


def verifie_cles_non_parcourues():
    """Le parcours ne suit que `content` — jamais une cle nommee `type` au hasard.

    `media.attrs.type = "file"` et `datasource.views[0].type = "table"` sont des chaines
    de donnees, pas des types de noeuds. Un parcours naif les remonterait comme des
    noeuds a traiter. Et une inclusion posee dans les `attrs` d'un noeud n'est PAS dans
    le document : la resoudre inventerait du contenu.
    """
    echecs = 0
    page = "SF-ATTRS"
    media = {"type": "mediaSingle", "content": [
        {"type": "media", "attrs": {"id": "abc", "collection": "contentId-1",
                                    "type": "file", "alt": "image.png"}}]}
    carte_jira = {"type": "blockCard", "attrs": {"datasource": {
        "id": "jira", "parameters": {"cloudId": "x", "jql": "id in linkedIssues(REC-35)"},
        "views": [{"type": "table", "properties": {"columns": [{"key": "summary"}]}}]}}}
    # Une inclusion planquee dans les attrs : elle ne doit pas etre vue.
    piege = {"type": "paragraph",
             "attrs": {"parameters": {"macroParams": {"leurre": inclusion("PIEGE", page)}}},
             "content": [{"type": "text", "text": "texte porteur"}]}

    hote = document([media, carte_jira, piege])
    source = document([definition("PIEGE", [para("ne doit jamais apparaitre")])])
    fournisseur = Fournisseur([("810", page, source)])
    resolu, faits = rs.resout_document(hote, "CU-HOTE", "811", fournisseur)

    echecs += check(faits == [],
                    f"aucune inclusion n'est atteignable par `content` : {faits}")
    echecs += check("ne doit jamais apparaitre" not in texte(resolu),
                    "une inclusion logee dans les attrs ne doit pas etre resolue")
    echecs += check(resolu["content"][0] == media,
                    "un mediaSingle sans reutilisation doit ressortir a l'identique")
    echecs += check(resolu["content"][1] == carte_jira,
                    "un blockCard a datasource doit ressortir a l'identique")
    echecs += check(fournisseur.appels_titre == [] and fournisseur.appels_id == [],
                    f"aucun appel ne doit partir : {fournisseur.appels_titre}")
    return echecs


def verifie_adf_intact():
    """Le resolver ne modifie JAMAIS l'ADF recu.

    Le contrat l'exige, et le run en depend : la meme page sert de source a d'autres
    pages, apres avoir ete resolue pour elle-meme. Un arbre mute en place ferait
    dependre le resultat de l'ordre de traitement des pages.
    """
    echecs = 0
    entree = charge("28344344")
    empreinte = json.dumps(entree, sort_keys=True)
    resolu, _ = rs.resout_document(entree, TITRES["28344344"], "28344344",
                                   fournisseur_fixtures())
    echecs += check(json.dumps(entree, sort_keys=True) == empreinte,
                    "l'ADF passe en entree doit etre inchange apres resolution")
    echecs += check(resolu is not entree, "le resultat doit etre un nouvel arbre")

    # Deux inclusions du meme contenu ne doivent RIEN partager — pas meme un `attrs`
    # ou un `marks` en profondeur. Comparer les objets de premier niveau ne suffit pas :
    # le parcours reconstruit les dictionnaires qu'il traverse, donc deux injections
    # sans copie ont malgre tout des racines distinctes, et partagent tout le reste.
    doc = document([inclusion("habilitation", TITRES["28344321"]),
                    inclusion("habilitation", TITRES["28344321"])])
    source = charge("28344321")
    resolu2, _ = rs.resout_document(doc, "CU-TEST", "999",
                                    Fournisseur([("28344321", TITRES["28344321"], source)]))
    deux = zones(resolu2, "habilitation")
    echecs += check(len(deux) == 2 and deux[0] == deux[1],
                    "deux injections du meme contenu doivent etre egales")
    if len(deux) == 2:
        echecs += check(not (identites(deux[0]) & identites(deux[1])),
                        "deux injections ne doivent partager AUCUN objet mutable : "
                        "modifier l'une modifierait l'autre")
        echecs += check(not (identites(deux[0]) & identites(source)),
                        "un contenu injecte ne doit partager aucun objet avec l'ADF "
                        "source indexe : le mutter corromprait l'index pour tout le run")
    return echecs


# --------------------------------------------------------------------------
# 6. syncBlock et tables imbriquees sur donnees reelles
# --------------------------------------------------------------------------

def verifie_syncblock():
    """CU-NOTE-MODIFIER porte 2 syncBlock nus ; leurs definitions sont sur CU-NOTE-CREER.

    La source est designee par IDENTIFIANT : un GET direct, sans carte de titres et sans
    sensibilite au renommage.
    """
    echecs = 0
    fournisseur = fournisseur_fixtures()
    resolu, faits = rs.resout_document(charge("28344344"), TITRES["28344344"],
                                       "28344344", fournisseur)
    sync = [f for f in faits if f["mecanisme"] == "sync"]
    echecs += check(len(sync) == 2, f"2 inclusions syncBlock attendues : {len(sync)}")
    echecs += check(all(f["statut"] == "resolue" for f in sync),
                    f"les deux doivent resoudre contre 28344321 : {sync}")
    echecs += check([f["cle"][0] for f in sync] == ["28344321", "28344321"],
                    f"la cle syncBlock porte l'identifiant de la page source : {sync}")
    echecs += check(fournisseur.appels_id == ["28344321"],
                    f"UN appel pour les deux inclusions : {fournisseur.appels_id}")
    echecs += check("sync_include" not in natures(resolu),
                    "aucun syncBlock non resolu ne doit subsister")

    # L'UUID SEUL NE SUFFIT PAS — collision reelle du contrat §1.3 : le meme resourceId
    # est defini sur CU-NOTE-CREER (28344321, 3 noeuds) et sur sa copie
    # CU-NOTE-TYPENOTE.CREER (396361729, 2 noeuds), dont les contenus ont diverge.
    # 396361729 n'est pas dans le corpus dore : la page jumelle est synthetique, la
    # collision qu'elle reproduit ne l'est pas.
    partage = "2342b419-9e51-43bd-81f4-c45e0ca27d9b"
    jumelle = document([sync_definition(partage, [para("contenu de la page COPIE")])])
    f2 = Fournisseur([("28344321", TITRES["28344321"], charge("28344321")),
                      ("396361729", "CU-NOTE-TYPENOTE.CREER", jumelle)])
    resolveur = rs.Resolveur(f2)
    # Deux documents, un seul resolveur : les deux definitions cohabitent dans l'index,
    # c'est la condition pour qu'une resolution par UUID seul se trompe.
    vers_copie, faits_copie = resolveur.resout(
        document([sync_inclusion("396361729", partage)]), "CU-A", "991")
    vers_creer, faits_creer = resolveur.resout(
        document([sync_inclusion("28344321", partage)]), "CU-B", "992")
    echecs += check([f["statut"] for f in faits_copie] == ["resolue"], f"{faits_copie}")
    echecs += check([f["statut"] for f in faits_creer] == ["resolue"], f"{faits_creer}")
    echecs += check("contenu de la page COPIE" in texte(vers_copie),
                    "l'inclusion visant 396361729 doit rendre le contenu de 396361729")
    echecs += check("contenu de la page COPIE" not in texte(vers_creer),
                    "L'UUID SEUL NE SUFFIT PAS : l'inclusion visant 28344321 ne doit "
                    "PAS recevoir la definition homonyme de la page copie")
    echecs += check(texte(vers_creer) != texte(vers_copie),
                    "deux pages, meme uuid, deux contenus : ils doivent differer")

    # Un uuid absent de la page source reste une definition absente.
    doc = document([sync_inclusion("28344321", "0" * 8 + "-0000-0000-0000-" + "0" * 12)])
    resolu2, faits2 = rs.resout_document(doc, "CU-TEST", "999", fournisseur_fixtures())
    echecs += check([f["statut"] for f in faits2] == ["definition_absente"],
                    f"un uuid absent de la page source est une definition absente : {faits2}")

    # Page source injoignable.
    absent = "fb607b8e-c344-4322-93eb-6e86a5304bc8"
    doc3 = document([sync_inclusion("999999", absent)])
    resolu3, faits3 = rs.resout_document(doc3, "CU-TEST", "999", Fournisseur([]))
    echecs += check([f["statut"] for f in faits3] == ["page_source_absente"], f"{faits3}")
    echecs += check(marqueurs(resolu3)
                    == [f"↳ inclusion non résolue : bloc synchronisé {absent[:8]} — "
                        f"source : page 999999 — page source introuvable"],
                    f"le marqueur doit porter la cible et le motif : "
                    f"{lisible(marqueurs(resolu3))}")
    return echecs


def verifie_tables_imbriquees_reelles():
    """Les 2 nested-table du corpus dore sont injectees, pas conservees."""
    echecs = 0
    for pid in ("28344321", "28344344"):
        avant = natures(charge(pid)).count("nested_table")
        resolu, _ = rs.resout_document(charge(pid), TITRES[pid], pid,
                                       fournisseur_fixtures())
        echecs += check(avant == 1, f"{pid} porte 1 nested-table avant resolution")
        echecs += check("nested_table" not in natures(resolu),
                        f"{pid} : la table imbriquee doit etre injectee")

    # Un nested-table sans parametre `adf` leve : SEUL cas qui justifie un partial.
    casse = {"type": "extension",
             "attrs": {"extensionKey": "nested-table",
                       "parameters": {"cxhtml": "<table/>", "reason": "peu importe"}}}
    echecs += leve(
        lambda: rs.resout_document(document([casse]), "CU-TEST", "999", Fournisseur([])),
        "un nested-table sans `adf` doit lever", motif="adf")
    return echecs


# --------------------------------------------------------------------------
# 7. Recuperation : carte des titres, appels, perimetre
# --------------------------------------------------------------------------

def verifie_carte_titres():
    """La carte titre -> identifiant se construit une fois et leve sur un doublon."""
    echecs = 0
    inventaire = {"pages": [
        {"id": "28344321", "title": "CU-NOTE-CREER", "title_raw": None},
        {"id": "299499522", "title": "CU-PERSONNE-RECHERCHER",
         "title_raw": "CU‑PERSONNE-RECHERCHER"},
    ]}
    carte = rs.carte_titres(inventaire)
    echecs += check(carte.get("CU-NOTE-CREER") == "28344321",
                    f"le titre normalise doit etre indexe : {carte}")
    echecs += check(carte.get("CU‑PERSONNE-RECHERCHER") == "299499522",
                    "la forme BRUTE du titre doit etre indexee aussi : une inclusion "
                    "ecrite dans l'ADF porte le tiret insecable, que clean_page_title "
                    "ne replie pas")
    echecs += check(carte.get("CU-PERSONNE-RECHERCHER") == "299499522",
                    "la forme normalisee doit repondre egalement")

    # Deux pages, meme titre : la carte leve a la CONSTRUCTION.
    echecs += leve(
        lambda: rs.carte_titres({"pages": [
            {"id": "1", "title": "SF-DOUBLON", "title_raw": None},
            {"id": "2", "title": "SF-DOUBLON", "title_raw": None}]}),
        "deux pages de meme titre doivent lever", motif="SF-DOUBLON")

    # Un inventaire reel : le corpus de non-regression ne porte aucun doublon.
    reel = json.loads((FIXTURES / "pages_classification_20260805.json")
                      .read_text(encoding="utf-8"))
    carte_reelle = rs.carte_titres(reel)
    echecs += check(len(carte_reelle) >= 246,
                    f"les 246 pages du corpus doivent entrer dans la carte : "
                    f"{len(carte_reelle)}")

    # La carte rend la resolution gratuite : aucun appel par titre.
    fournisseur = fournisseur_fixtures()
    resolveur = rs.Resolveur(fournisseur, carte={"CU-NOTE-CREER": "28344321"})
    doc = document([inclusion("habilitation", "CU-NOTE-CREER")])
    resolu, faits = resolveur.resout(doc, "CU-TEST", "999")
    echecs += check(fournisseur.appels_titre == [],
                    f"la carte doit eviter tout appel par titre : {fournisseur.appels_titre}")
    echecs += check(fournisseur.appels_id == ["28344321"],
                    f"un appel par identifiant, celui que la carte a donne : "
                    f"{fournisseur.appels_id}")
    echecs += check(faits and faits[0]["statut"] == "resolue", f"{faits}")
    echecs += check(faits and faits[0]["source_hors_perimetre"] is False,
                    f"une page de la carte est DANS le perimetre : {faits}")

    # Hors carte mais lisible : la page est LUE sans etre exportee, et le fait le dit.
    fournisseur2 = fournisseur_fixtures()
    resolveur2 = rs.Resolveur(fournisseur2, carte={"CU-AUTRE": "1"})
    _, faits2 = resolveur2.resout(doc, "CU-TEST", "999")
    echecs += check(faits2 and faits2[0]["statut"] == "resolue",
                    f"une page hors perimetre reste lisible : {faits2}")
    echecs += check(faits2 and faits2[0]["source_hors_perimetre"] is True,
                    f"le fait doit signaler la source hors perimetre : {faits2}")
    echecs += check(fournisseur2.appels_titre == ["CU-NOTE-CREER"],
                    f"hors carte, l'appel se fait par titre : {fournisseur2.appels_titre}")

    # syncBlock : la carte se lit a l'ENVERS, par identifiant. Chercher un identifiant
    # parmi les titres rendrait toute source syncBlock hors perimetre.
    uuid = "fb607b8e-c344-4322-93eb-6e86a5304bc8"
    resolveur3 = rs.Resolveur(fournisseur_fixtures(),
                              carte={"CU-NOTE-CREER": "28344321"})
    _, faits3 = resolveur3.resout(document([sync_inclusion("28344321", uuid)]),
                                  "CU-TEST", "999")
    echecs += check(faits3 and faits3[0]["source_hors_perimetre"] is False,
                    f"28344321 est dans la carte : sa source syncBlock est dans le "
                    f"perimetre : {faits3}")
    return echecs


def verifie_un_appel_par_source():
    """Un appel par page source DISTINCTE, jamais un par inclusion."""
    echecs = 0
    # API-PORTAIL-FAVORIS : 7 inclusions, 3 pages sources distinctes.
    fournisseur = Fournisseur([])
    resolu, faits = rs.resout_document(charge("241532980"), TITRES["241532980"],
                                       "241532980", fournisseur)
    echecs += check(len(faits) == 7, f"7 inclusions sur la page : {len(faits)}")
    echecs += check(len(fournisseur.appels_titre) == 3,
                    f"3 pages sources distinctes = 3 appels, obtenu "
                    f"{len(fournisseur.appels_titre)} : {fournisseur.appels_titre}")
    echecs += check(all(f["statut"] == "page_source_absente" for f in faits),
                    "aucune des 3 pages n'est dans le fournisseur")

    # Les memes 3 inclusions, cette fois resolubles : toujours UN appel.
    regles = "Règles génériques utilisables pour les API"
    source = document([definition("RG-API-VALIDATION.REQUETE", [para("validation")]),
                       definition("RG-API-CONTROLE.SECURITE", [para("securite")]),
                       definition("RG-API-ERREUR.GATEWAY", [para("gateway")])])
    fournisseur2 = Fournisseur([("900", regles, source)])
    _, faits2 = rs.resout_document(charge("241532980"), TITRES["241532980"],
                                   "241532980", fournisseur2)
    resolues = [f for f in faits2 if f["statut"] == "resolue"]
    echecs += check(len(resolues) == 3, f"3 inclusions resolues attendues : {faits2}")
    echecs += check(fournisseur2.appels_titre.count(regles) == 1,
                    f"UN appel pour 3 inclusions de la meme page : "
                    f"{fournisseur2.appels_titre}")

    # L'index survit d'une page a l'autre : un seul Resolveur pour tout un run.
    fournisseur3 = fournisseur_fixtures()
    resolveur = rs.Resolveur(fournisseur3)
    resolveur.resout(charge("28344321"), TITRES["28344321"], "28344321")
    avant = len(fournisseur3.appels_titre)
    resolveur.resout(charge("28344344"), TITRES["28344344"], "28344344")
    echecs += check(len(fournisseur3.appels_titre) == avant,
                    f"la seconde page ne redemande aucune source deja indexee : "
                    f"{fournisseur3.appels_titre}")

    # Un titre introuvable n'est demande qu'une fois, meme pour 9 inclusions.
    fournisseur4 = Fournisseur([])
    _, faits4 = rs.resout_document(charge("380567556"), TITRES["380567556"],
                                   "380567556", fournisseur4)
    echecs += check(len(faits4) == 9, f"9 inclusions sur CU-PORTAIL-ACCUEIL : {len(faits4)}")
    echecs += check(len(fournisseur4.appels_titre) == len(set(fournisseur4.appels_titre)),
                    f"aucun titre ne doit etre demande deux fois : "
                    f"{fournisseur4.appels_titre}")

    # Plusieurs pages pour un meme titre : le resolver leve, il ne choisit pas.
    ambigu = Fournisseur([("1", "SF-AMBIGU", document([definition("N", [para("a")])])),
                          ("2", "SF-AMBIGU", document([definition("N", [para("b")])]))])
    echecs += leve(
        lambda: rs.resout_document(document([inclusion("N", "SF-AMBIGU")]),
                                   "CU-TEST", "999", ambigu),
        "deux pages pour un titre doivent lever", motif="plusieurs pages")
    return echecs


def verifie_non_resolues():
    """Une inclusion non resolue laisse un marqueur visible ET un fait."""
    echecs = 0
    page = "SF-VIDE"
    fournisseur = Fournisseur([("910", page, document([para("page sans definition")]))])
    doc = document([inclusion("ABSENTE", page, local_id="loc-42")])
    resolu, faits = rs.resout_document(doc, "CU-TEST", "999", fournisseur)

    echecs += check([f["statut"] for f in faits] == ["definition_absente"], f"{faits}")
    echecs += check(faits[0]["emplacement"] == "page 999, localId loc-42",
                    f"le fait doit localiser l'inclusion : {faits[0]['emplacement']}")
    echecs += check(marqueurs(resolu) == ["↳ inclusion non résolue : ABSENTE — "
                                          "source : SF-VIDE — définition introuvable "
                                          "sur la page source"],
                    f"marqueur attendu, obtenu : {lisible(marqueurs(resolu))}")
    echecs += check(natures(resolu) == [],
                    "le noeud d'inclusion doit avoir disparu, remplace par le marqueur")

    # Page introuvable : autre statut, autre motif.
    doc2 = document([inclusion("N", "SF-INEXISTANTE")])
    resolu2, faits2 = rs.resout_document(doc2, "CU-TEST", "999", Fournisseur([]))
    echecs += check([f["statut"] for f in faits2] == ["page_source_absente"], f"{faits2}")
    echecs += check("page source introuvable" in marqueurs(resolu2)[0],
                    f"{lisible(marqueurs(resolu2))}")

    # Les deux familles portent le meme traitement.
    doc3 = document([inclusion("N", "SF-INEXISTANTE", famille="excerpt")])
    _, faits3 = rs.resout_document(doc3, "CU-TEST", "999", Fournisseur([]))
    echecs += check(faits3 and faits3[0]["mecanisme"] == "excerpt",
                    f"le mecanisme consigne doit etre la famille : {faits3}")
    return echecs


def verifie_extrait_sans_nom():
    """Un extrait natif sans nom est l'extrait par defaut de sa page (contrat §1.8).

    Cas reel du 22 octobre 2026 : 243695621 porte un extrait sans nom au milieu de ses
    definitions. La levee arretait l'indexation de la page source, et les definitions
    SUIVANTES passaient pour absentes sur toutes les pages qui les incluent.
    """
    echecs = 0
    page = "SF-SOURCE"
    source = document([definition("RG-AVANT", [para("avant")], famille="excerpt"),
                       definition("", [para("par défaut")], famille="excerpt"),
                       definition("RG-APRES", [para("après")], famille="excerpt")])
    fournisseur = Fournisseur([("920", page, source)])
    doc = document([inclusion("RG-APRES", page, famille="excerpt"),
                    inclusion("", page, famille="excerpt")])
    resolu, faits = rs.resout_document(doc, "SA-TEST", "999", fournisseur)

    echecs += check([f["statut"] for f in faits] == ["resolue", "resolue"],
                    f"une definition apres l'extrait sans nom doit rester trouvable : {faits}")
    echecs += check([f["cle"] for f in faits] == [(page, "RG-APRES"), (page, "")],
                    f"le fait garde le nom vide, pas le libelle : {[f['cle'] for f in faits]}")
    echecs += check("par défaut" in textes(resolu) and "après" in textes(resolu),
                    f"les deux corps doivent etre injectes : {lisible(textes(resolu))}")
    echecs += check(f"↳ inclusion : {rs.NOM_AFFICHE_PAR_DEFAUT} — source : {page}"
                    in marqueurs(resolu),
                    f"le marqueur nomme l'extrait par defaut : {lisible(marqueurs(resolu))}")

    # Le multiexcerpt, lui, exige toujours un nom.
    source_mx = document([definition("", [para("x")])])
    echecs += leve(lambda: rs.resout_document(source_mx, "SF-MX", "921", Fournisseur([])),
                   "un multiexcerpt sans nom doit lever")
    return echecs


def verifie_page_courante_et_ordre():
    """Page absente ou vide = page courante ; une inclusion peut preceder sa definition."""
    echecs = 0
    page = "SF-LOCALE"
    # L'inclusion est ECRITE AVANT la definition : l'index doit etre complet d'abord.
    adf = document([inclusion("LOCALE"),
                    definition("LOCALE", [para("definie plus bas")])])
    resolu, faits = rs.resout_document(adf, page, "920", Fournisseur([]))
    echecs += check([f["statut"] for f in faits] == ["resolue"],
                    f"une inclusion sans parametre page vise la page courante, meme "
                    f"declaree avant sa definition : {faits}")
    echecs += check(faits[0]["cle"] == (page, "LOCALE"),
                    f"la cle doit porter le titre de la page hote : {faits}")
    echecs += check("definie plus bas" in texte(resolu), "le contenu doit etre injecte")
    echecs += check(len(zones(resolu, "LOCALE")) == 1, "une zone marquee attendue")

    # Page vide : meme regle, dans les deux familles.
    adf2 = document([inclusion("L2", page=""), definition("L2", [para("corps L2")])])
    _, faits2 = rs.resout_document(adf2, page, "921", Fournisseur([]))
    echecs += check([f["statut"] for f in faits2] == ["resolue"],
                    f"un parametre page VIDE vise la page courante : {faits2}")

    # La definition reste en place la ou elle est definie.
    definitions = [n for n in natures(resolu) if n.endswith("_definition")]
    echecs += check(definitions == ["multiexcerpt_definition"],
                    f"la definition n'est pas consommee par l'inclusion : {definitions}")

    # Une definition en double sur la meme page leve — contrat §1.8.
    echecs += leve(
        lambda: rs.resout_document(
            document([definition("D", [para("un")]), definition("D", [para("deux")])]),
            page, "922", Fournisseur([])),
        "une cle de definition en double doit lever", motif="double")
    return echecs


# --------------------------------------------------------------------------
# 8. La forme du marqueur — contrat §1.9
# --------------------------------------------------------------------------

def verifie_forme_marqueur():
    """Le marqueur est un paragraphe portant UN texte marque `em`, sans asterisque.

    Les asterisques du contrat sont le RENDU de la mark, pas des caracteres emis : en
    cellule de tableau HTML elles s'afficheraient telles quelles a l'interieur de la
    balise <em>. Les litteraux attendus sont ecrits en dur — les reconstruire en
    appelant libelle_ouvrant() laisserait le controle vert quand le code change de forme.
    """
    echecs = 0
    adf = document([inclusion("M"), definition("M", [para("corps M")])])
    resolu, faits = rs.resout_document(adf, "SF-MARQUEUR", "930", Fournisseur([]))
    echecs += check([f["statut"] for f in faits] == ["resolue"], f"{faits}")

    portants = [n for n in (resolu.get("content") or [])
                if texte(n).strip().startswith("↳")]
    echecs += check(len(portants) == 2,
                    f"une inclusion resolue encadre son contenu de deux marqueurs, "
                    f"obtenu {len(portants)} : {lisible(marqueurs(resolu))}")
    echecs += check(marqueurs(resolu) == ["↳ inclusion : M — source : SF-MARQUEUR",
                                          "↳ fin inclusion : M"],
                    f"libelles attendus, obtenu : {lisible(marqueurs(resolu))}")

    for rang, node in enumerate(portants):
        echecs += check(node.get("type") == "paragraph",
                        f"marqueur {rang} : un paragraph attendu, obtenu "
                        f"{node.get('type')!r}")
        enfants = node.get("content") or []
        echecs += check(len(enfants) == 1,
                        f"marqueur {rang} : un seul enfant attendu, obtenu {len(enfants)}")
        if len(enfants) != 1:
            continue
        enfant = enfants[0]
        echecs += check(enfant.get("type") == "text",
                        f"marqueur {rang} : l'enfant est un text, obtenu "
                        f"{enfant.get('type')!r}")
        echecs += check(enfant.get("marks") == [{"type": "em"}],
                        f"marqueur {rang} : la mark em et elle seule, obtenu "
                        f"{enfant.get('marks')!r}")
        echecs += check(enfant.get("text", "").count("*") == 0,
                        f"marqueur {rang} : les asterisques sont le rendu de la mark, "
                        f"pas du texte emis — obtenu {lisible(enfant.get('text'))}")
    return echecs


def verifie_nettoyage_libelle():
    """|, < et > deviennent une ESPACE a la fabrication du libelle. Contrat §1.9.

    Par construction, jamais par l'etat du corpus du jour : ce sont les trois caracteres
    que le rendu echappe (§9.1), et un marqueur qui en porterait serait deforme en
    cellule. Une SUPPRESSION souderait deux mots, d'ou l'espace.
    """
    echecs = 0
    nom = "RG|A<B>C"
    source = "SF<PAGE> | TITRE"

    echecs += check(rs.libelle_ouvrant(nom, source)
                    == "↳ inclusion : RG A B C — source : SF PAGE TITRE",
                    f"libelle ouvrant nettoye attendu, obtenu "
                    f"{lisible(rs.libelle_ouvrant(nom, source))}")
    echecs += check(rs.libelle_fermant(" <RG|A> ") == "↳ fin inclusion : RG A",
                    f"les extremites sont rognees et les espaces compactes, obtenu "
                    f"{lisible(rs.libelle_fermant(' <RG|A> '))}")
    echecs += check(rs.libelle_non_resolue(nom, source, "page source introuvable")
                    == "↳ inclusion non résolue : RG A B C — source : SF PAGE TITRE "
                       "— page source introuvable",
                    f"libelle de non-resolution nettoye attendu, obtenu "
                    f"{lisible(rs.libelle_non_resolue(nom, source, 'x'))}")
    echecs += check(rs.nom_sync("fb607b8e-c344-4322-93eb-6e86a5304bc8")
                    == "bloc synchronisé fb607b8e",
                    f"le nom d'un bloc synchronise est l'UUID tronque a 8 : "
                    f"{rs.nom_sync('fb607b8e-c344-4322-93eb-6e86a5304bc8')}")

    # Bout en bout : un titre de page reellement porteur des trois caracteres. C'est le
    # cas du premier renommage de page, que le corpus du jour ne montre pas.
    doc = document([inclusion("N", "SF<INEXISTANTE>|Z")])
    resolu, faits = rs.resout_document(doc, "CU-TEST", "999", Fournisseur([]))
    echecs += check([f["statut"] for f in faits] == ["page_source_absente"], f"{faits}")
    echecs += check(marqueurs(resolu) == ["↳ inclusion non résolue : N — source : "
                                          "SF INEXISTANTE Z — page source introuvable"],
                    f"le marqueur emis doit etre nettoye, obtenu "
                    f"{lisible(marqueurs(resolu))}")
    return echecs


def verifie_aucun_commentaire_html():
    """Sur les 9 fixtures resolues : aucun `text` produit ne commence par `<!--`.

    Le sommaire en commentaire est l'affaire du renderer, pas du resolver (§1.9). On
    mesure et on compare a 0 ; on ne cherche pas un coupable connu.
    """
    echecs = 0
    commentaires = 0
    marques = 0
    resolues = 0
    non_resolues = 0
    for pid, titre in sorted(TITRES.items()):
        resolu, faits = rs.resout_document(charge(pid), titre, pid, fournisseur_fixtures())
        commentaires += sum(1 for t in textes(resolu) if t.startswith("<!--"))
        marques += len(marqueurs_profonds(resolu))
        resolues += sum(1 for f in faits if f["statut"] == "resolue")
        non_resolues += sum(1 for f in faits if f["statut"] != "resolue")
    echecs += check(commentaires == 0,
                    f"aucun commentaire HTML ne doit sortir du resolver, obtenu "
                    f"{commentaires}")
    # Chaque fait laisse sa trace : deux marqueurs s'il est resolu, un seul sinon. La
    # relation croise deux chemins de code — _consigne et le marquage — au lieu de figer
    # un nombre qu'une mauvaise mesure rendrait vrai pour toujours.
    echecs += check(marques == 2 * resolues + non_resolues,
                    f"{marques} marqueurs pour {resolues} inclusions resolues et "
                    f"{non_resolues} non resolues, attendu "
                    f"{2 * resolues + non_resolues}")
    return echecs


# --------------------------------------------------------------------------
# 9. La substitution inline — contrat §1.9, cas non exerce par le corpus dore
# --------------------------------------------------------------------------
# Le corpus dore N'EXERCERA JAMAIS ce code : ses 5 inclusions inline visent toutes des
# pages sources absentes des 9 fixtures, aucune ne s'y resout, et verser une page
# porteuse n'y changerait rien tant que sa source n'entre pas aussi. C'est inscrit au
# §10 du contrat, et c'est la raison d'etre de ces controles synthetiques.

PAGE_INLINE = "SF-INLINE"
MARK_FOND = {"type": "backgroundColor", "attrs": {"color": "#fff0b3"}}
EM = [{"type": "em"}]
OUVRANT_HAB = "↳ inclusion : habilitation — source : SF-INLINE"
FERMANT_HAB = "↳ fin inclusion : habilitation"
VALEUR_HAB = "administration:parametre:gerer"


def source_inline(corps=None):
    """Page source portant `habilitation`.

    Par defaut, un unique paragraphe de texte pur : c'est ce que rendent 44 des 45
    inclusions inline resolubles du perimetre d'export. La mark backgroundColor n'est
    pas decorative — les valeurs d'habilitation sont surlignees dans le corpus reel, et
    c'est elle qui doit traverser la substitution intacte.
    """
    if corps is None:
        corps = [para_de([txt(VALEUR_HAB, [MARK_FOND])])]
    return document([definition("habilitation", corps)])


def hote_inline(noeud_inclusion):
    """Le cas majoritaire du perimetre : substitution AU MILIEU d'une phrase.

    24 inclusions resolubles sur 45 sont dans ce cas — c'est la mesure qui commande la
    forme, un noeud de bloc depose ici couperait ces 24 phrases en deux.
    """
    return document([para_de([txt("Habilitations : "), noeud_inclusion,
                              txt(" pour agir.")])])


def verifie_inclusion_inline():
    """Les 11 controles du §B.4 : union, substitution en place, escalade, recursion."""
    echecs = 0

    def substitue_en_place(noeud, etiquette):
        """Les trois formes de l'union doivent donner EXACTEMENT le meme resultat."""
        locaux = 0
        resolu, faits = rs.resout_document(
            hote_inline(noeud), "CU-HOTE", "940",
            Fournisseur([("941", PAGE_INLINE, source_inline())]))
        contenu = resolu.get("content") or []
        locaux += check(
            [n.get("type") for n in contenu] == ["paragraph"],
            f"{etiquette} : un seul paragraphe en sortie, obtenu "
            f"{[n.get('type') for n in contenu]}")
        if len(contenu) == 1:
            locaux += check(
                contenu[0].get("content") == [txt("Habilitations : "),
                                              txt(OUVRANT_HAB, EM),
                                              txt(VALEUR_HAB, [MARK_FOND]),
                                              txt(FERMANT_HAB, EM),
                                              txt(" pour agir.")],
                f"{etiquette} : tete, marqueur, valeur AVEC SA MARK, marqueur, queue — "
                f"obtenu {lisible(contenu[0].get('content'))}")
        locaux += check(mal_places(resolu) == [],
                        f"{etiquette} : aucun noeud de bloc a une place inline, obtenu "
                        f"{mal_places(resolu)}")
        locaux += check(
            [(f["statut"], f["forme"], f.get("substitution")) for f in faits]
            == [("resolue", "inline", "inline")],
            f"{etiquette} : fait resolue/inline/inline sans constat, obtenu {faits}")
        return locaux

    # --- 1. Substitution au milieu d'une phrase, forme courante du corpus.
    echecs += substitue_en_place(inclusion_inline("habilitation", PAGE_INLINE),
                                 "forme courante")

    # --- 2. Union, branche « TYPE DE NOEUD » : la variante historique.
    # Ce controle porte a lui seul le cas mesure a 1 occurrence au perimetre d'export.
    # Les deux assertions qui precedent la substitution sont ce qui l'empeche de se
    # reduire a un doublon du controle 1 : elles constatent que la cle ne dit rien.
    historique = inclusion_inline("habilitation", PAGE_INLINE,
                                  cle="multiexcerpt-include-macro")
    echecs += check(mx.CLE_FORME_INLINE not in historique["attrs"]["extensionKey"],
                    f"la variante historique ne porte PAS include-inline dans sa cle "
                    f"({historique['attrs']['extensionKey']!r}) — sans quoi ce controle "
                    f"ne serait qu'un doublon du precedent")
    echecs += check(historique["type"] == mx.TYPE_INLINE_EXTENSION,
                    "c'est son TYPE DE NOEUD qui la designe comme inline")
    echecs += check(mx.est_inclusion_inline(historique) is True,
                    "un test sur la seule cle de macro manquerait cette forme")
    echecs += substitue_en_place(historique, "variante historique")

    # --- 3. Union, branche « CLE » : un `extension` portant include-inline.
    par_cle = inclusion_inline("habilitation", PAGE_INLINE, type_noeud="extension")
    echecs += check(par_cle["type"] != mx.TYPE_INLINE_EXTENSION,
                    f"ce noeud n'est pas un inlineExtension ({par_cle['type']!r}) : "
                    f"sans la branche « cle », l'union ne le verrait pas")
    echecs += check(mx.CLE_FORME_INLINE in par_cle["attrs"]["extensionKey"],
                    "c'est sa CLE qui la designe comme inline")
    echecs += check(mx.est_inclusion_inline(par_cle) is True,
                    "un test sur le seul type de noeud manquerait cette forme")
    echecs += substitue_en_place(par_cle, "extension a cle include-inline")

    # --- 4. Escalade en bloc : la definition depose deux bulletList.
    # Reproduit RG-API-VALIDATION.REQUETE, la 45e inclusion du perimetre — la seule qui
    # apporte du bloc au milieu d'une cellule de tableau.
    fournisseur = Fournisseur([("943", PAGE_INLINE,
                                source_inline([liste("a", "b"), liste("c")]))])
    resolu, faits = rs.resout_document(
        hote_inline(inclusion_inline("habilitation", PAGE_INLINE)), "CU-HOTE", "942",
        fournisseur)
    echecs += check([n.get("type") for n in resolu["content"]]
                    == ["paragraph", "paragraph", "bulletList", "bulletList",
                        "paragraph", "paragraph"],
                    f"escalade : tete, marqueur, les deux listes, marqueur, queue — "
                    f"obtenu {[n.get('type') for n in resolu['content']]}")
    echecs += check([texte(n).strip() for n in resolu["content"]]
                    == ["Habilitations :", OUVRANT_HAB, "a b", "c", FERMANT_HAB,
                        "pour agir."],
                    f"le texte qui suivait devient son propre paragraphe : "
                    f"{lisible([texte(n).strip() for n in resolu['content']])}")
    echecs += check(marqueurs_profonds(resolu) == [OUVRANT_HAB, FERMANT_HAB],
                    f"les marqueurs passent en forme de BLOC : "
                    f"{lisible(marqueurs_profonds(resolu))}")
    echecs += check(mal_places(resolu) == [],
                    f"une escalade ne laisse aucun bloc a une place inline : "
                    f"{mal_places(resolu)}")
    echecs += check([(f["statut"], f["forme"], f.get("substitution")) for f in faits]
                    == [("resolue", "inline", "scindee")],
                    f"la scission est un CONSTAT, pas un incident : le statut reste "
                    f"resolue et la page scorable — {faits}")

    # --- 5. Escalade, hote sans tete ni queue : aucun paragraphe vide.
    seul = document([para_de([inclusion_inline("habilitation", PAGE_INLINE)])])
    resolu5, _ = rs.resout_document(seul, "CU-HOTE", "944", fournisseur)
    echecs += check([n.get("type") for n in resolu5["content"]]
                    == ["paragraph", "bulletList", "bulletList", "paragraph"],
                    f"un morceau vide ne produit pas de conteneur vide : "
                    f"{[n.get('type') for n in resolu5['content']]}")
    vides = [n for n in resolu5["content"]
             if n.get("type") == "paragraph" and not n.get("content")]
    echecs += check(vides == [], f"aucun paragraphe vide emis : {vides}")

    # --- 6. Escalade, definition a deux paragraphes : meme forme qu'au 4.
    f6 = Fournisseur([("945", PAGE_INLINE,
                       source_inline([para("premier"), para("second")]))])
    resolu6, faits6 = rs.resout_document(
        hote_inline(inclusion_inline("habilitation", PAGE_INLINE)), "CU-HOTE", "946", f6)
    echecs += check([texte(n).strip() for n in resolu6["content"]]
                    == ["Habilitations :", OUVRANT_HAB, "premier", "second",
                        FERMANT_HAB, "pour agir."],
                    f"deux noeuds de premier niveau escaladent aussi : "
                    f"{lisible([texte(n).strip() for n in resolu6['content']])}")
    echecs += check(faits6 and faits6[0].get("substitution") == "scindee",
                    f"constat attendu : {faits6}")
    echecs += check(mal_places(resolu6) == [], f"{mal_places(resolu6)}")

    # --- 7. Non-resolution : le marqueur suit la FORME de l'inclusion.
    doc7 = hote_inline(inclusion_inline("habilitation", "SF-ABSENTE"))
    resolu7, faits7 = rs.resout_document(doc7, "CU-HOTE", "947", Fournisseur([]))
    echecs += check([n.get("type") for n in resolu7["content"]] == ["paragraph"],
                    f"le paragraphe hote n'est pas scinde par une non-resolution : "
                    f"{[n.get('type') for n in resolu7['content']]}")
    echecs += check(
        resolu7["content"][0]["content"]
        == [txt("Habilitations : "),
            txt("↳ inclusion non résolue : habilitation — source : SF-ABSENTE — "
                "page source introuvable", EM),
            txt(" pour agir.")],
        f"le marqueur reste INLINE, pas un paragraphe qui couperait la phrase : "
        f"{lisible(resolu7['content'][0]['content'])}")
    echecs += check([(f["statut"], f["forme"]) for f in faits7]
                    == [("page_source_absente", "inline")], f"{faits7}")

    # Definition absente : meme forme, autre motif.
    f8 = Fournisseur([("948", PAGE_INLINE, document([para("page sans definition")]))])
    doc8 = hote_inline(inclusion_inline("habilitation", PAGE_INLINE))
    resolu8, faits8 = rs.resout_document(doc8, "CU-HOTE", "949", f8)
    echecs += check([n.get("type") for n in resolu8["content"]] == ["paragraph"],
                    "une definition absente ne scinde pas davantage")
    echecs += check(marqueurs_profonds(resolu8)
                    == ["↳ inclusion non résolue : habilitation — source : SF-INLINE — "
                        "définition introuvable sur la page source"],
                    f"{lisible(marqueurs_profonds(resolu8))}")
    echecs += check([(f["statut"], f["forme"]) for f in faits8]
                    == [("definition_absente", "inline")], f"{faits8}")

    # --- 8. Recursion : une definition inline qui en contient une autre.
    imbrique = document([
        definition("externe", [para_de([txt("avant "),
                                        inclusion_inline("interne", PAGE_INLINE),
                                        txt(" apres")])]),
        definition("interne", [para_de([txt("VALEUR")])])])
    f9 = Fournisseur([("950", PAGE_INLINE, imbrique)])
    resolu9, faits9 = rs.resout_document(
        hote_inline(inclusion_inline("externe", PAGE_INLINE)), "CU-HOTE", "951", f9)
    echecs += check([n.get("type") for n in resolu9["content"]] == ["paragraph"],
                    f"tout reste dans le paragraphe hote : "
                    f"{[n.get('type') for n in resolu9['content']]}")
    echecs += check(marqueurs_profonds(resolu9)
                    == ["↳ inclusion : externe — source : SF-INLINE",
                        "↳ inclusion : interne — source : SF-INLINE",
                        "↳ fin inclusion : interne",
                        "↳ fin inclusion : externe"],
                    f"les marqueurs s'emboitent dans l'ordre : "
                    f"{lisible(marqueurs_profonds(resolu9))}")
    echecs += check("VALEUR" in texte(resolu9),
                    "le contenu de l'inclusion imbriquee doit apparaitre")
    echecs += check(mal_places(resolu9) == [], f"{mal_places(resolu9)}")
    echecs += check(all(f["forme"] == "inline" and f.get("substitution") == "inline"
                        for f in faits9) and len(faits9) == 2,
                    f"deux inclusions inline substituees en place : {faits9}")

    # --- 9. Non-partage : les noeuds deposes ne partagent rien avec la source.
    source = source_inline()
    resolu10, _ = rs.resout_document(
        hote_inline(inclusion_inline("habilitation", PAGE_INLINE)), "CU-HOTE", "952",
        Fournisseur([("953", PAGE_INLINE, source)]))
    depose = resolu10["content"][0]["content"]
    echecs += check(not (identites(depose) & identites(source)),
                    "un noeud depose ne doit partager AUCUN objet mutable avec la "
                    "definition source : la muter corromprait l'index pour tout le run")

    # --- 10 et 11. Invariants sur le corpus dore.
    formes = {}
    statuts_inline = set()
    for pid, titre in sorted(TITRES.items()):
        resolu, faits = rs.resout_document(charge(pid), titre, pid, fournisseur_fixtures())
        echecs += check(mal_places(resolu) == [],
                        f"{pid} : aucun noeud de bloc a une place inline, obtenu "
                        f"{mal_places(resolu)}")
        echecs += check(rs._contient_echappement(resolu) is False,
                        f"{pid} : aucune enveloppe de scission ne survit au parcours")
        for fait in faits:
            formes[fait["forme"]] = formes.get(fait["forme"], 0) + 1
            if fait["forme"] == "inline":
                statuts_inline.add(fait["statut"])
    echecs += check(formes == {"bloc": 27, "inline": 5},
                    f"5 inclusions inline et 27 de bloc au corpus dore : {formes}")
    echecs += check(statuts_inline == {"page_source_absente"},
                    f"les 5 inline visent des pages hors des 9 fixtures : "
                    f"{statuts_inline}")
    return echecs


def verifie_corpus_dore():
    """Mesure de reference sur les 9 fixtures — 32 inclusions, statuts figes.

    Le fournisseur ne connait que les 9 fixtures : les 19 sources absentes le sont
    parce qu'elles sont hors du corpus dore, pas parce que Confluence les a perdues.
    Le seul statut a lire comme une anomalie du CORPUS est le definition_absente de
    CU-NOTE-MODIFIER (RG-NOTE-AUTEUR-AUTORISE-CREATION-MODIFICATION, defini nulle part
    dans les 250 pages recensees).
    """
    echecs = 0
    compte = {}
    inclusions = 0
    for pid, titre in sorted(TITRES.items()):
        resolu, faits = rs.resout_document(charge(pid), titre, pid, fournisseur_fixtures())
        inclusions += len(faits)
        for fait in faits:
            cle = (fait["mecanisme"], fait["statut"])
            compte[cle] = compte.get(cle, 0) + 1
        restantes = [n for n in natures(resolu)
                     if n.endswith("_include") or n == "nested_table"]
        echecs += check(restantes == [],
                        f"{pid} : ni inclusion ni table imbriquee ne doit subsister "
                        f"apres resolution, reste {restantes}")
    echecs += check(inclusions == 32,
                    f"32 inclusions dans le corpus dore, obtenu {inclusions}")
    echecs += check(compte.get(("multiexcerpt", "resolue")) == 10,
                    f"10 inclusions multiexcerpt resolues, obtenu {compte}")
    echecs += check(compte.get(("sync", "resolue")) == 2,
                    f"2 inclusions syncBlock resolues, obtenu {compte}")
    echecs += check(compte.get(("multiexcerpt", "definition_absente")) == 1,
                    f"1 definition absente — l'anomalie de CU-NOTE-MODIFIER : {compte}")
    echecs += check(compte.get(("multiexcerpt", "page_source_absente")) == 19,
                    f"19 sources hors corpus dore, obtenu {compte}")
    return echecs


def run():
    echecs = verifie_nommage_pytest()
    echecs += verifie_cle_page_et_nom()
    echecs += verifie_entites_html()
    echecs += verifie_recursion_dans_injecte()
    echecs += verifie_cycle()
    echecs += verifie_croisements()
    echecs += verifie_cles_non_parcourues()
    echecs += verifie_adf_intact()
    echecs += verifie_syncblock()
    echecs += verifie_tables_imbriquees_reelles()
    echecs += verifie_carte_titres()
    echecs += verifie_un_appel_par_source()
    echecs += verifie_non_resolues()
    echecs += verifie_extrait_sans_nom()
    echecs += verifie_page_courante_et_ordre()
    echecs += verifie_forme_marqueur()
    echecs += verifie_nettoyage_libelle()
    echecs += verifie_aucun_commentaire_html()
    echecs += verifie_inclusion_inline()
    echecs += verifie_corpus_dore()

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0


def test_resolver():
    """Point d'entree pytest."""
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
