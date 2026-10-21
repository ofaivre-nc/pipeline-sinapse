#!/usr/bin/env python3
"""
Tests des cles de resolution du contenu reutilise — pipeline/src/multiexcerpt.py.

Les cas sont tires des fixtures reelles CU-NOTE-CREER (28344321) et CU-NOTE-MODIFIER
(28344344), du doublon d'UUID CU-NOTE-TYPENOTE.*, et des extraits du 6 aout 2026 qui
ont revele la famille `excerpt` native. Chaque test protege une decision de
contracts/normalisation_adf.md.

Aucun acces reseau. Les fixtures lues sont celles du depot (pipeline/fixtures/).

  python -m pytest pipeline/tests/test_multiexcerpt.py   (ou : python test_multiexcerpt.py)
"""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

import multiexcerpt as mx  # noqa: E402

FIXTURES = RACINE / "fixtures"
TOTAL = 0


def check(condition, message):
    global TOTAL
    TOTAL += 1
    if not condition:
        print(f"ECHEC : {message}")
        return 1
    return 0


# Seule fonction de ce fichier que pytest doit collecter.
POINT_ENTREE_PYTEST = "test_multiexcerpt"


def verifie_nommage_pytest():
    """Aucune auxiliaire ne doit porter un nom que pytest collecte.

    pytest collecte par defaut le motif `test*` — qui attrape aussi `tests_...`. Une
    auxiliaire ainsi nommee est executee comme un test, et si elle rend un compte
    d'echecs au lieu de lever, **pytest 9.1.1 se contente d'un avertissement et la
    declare PASSANTE** (verifie : 1 passed, 1 warning, code de sortie 0). Il n'y a
    donc aucun filet du cote de pytest : cette verification est la protection.

    Elle tourne dans les deux mondes : run() l'appelle, et test_multiexcerpt()
    appelle run(). Voir la meme fonction dans test_inventory.py — dupliquee a deux
    exemplaires parce qu'elle inspecte le namespace de SON module ; un troisieme
    fichier de tests justifierait un harnais partage.
    """
    echecs = 0

    # Assertion POSITIVE, et non "pas de coupable" : la liste doit valoir exactement
    # le point d'entree attendu. Une liste vide echoue donc aussi, quelle qu'en soit
    # la cause — bloc __main__ mal place, point d'entree renomme, filtre de namespace
    # devenu faux. Un controle qui ne peut echouer que sur un coupable identifie est
    # vert quand il ne mesure rien.
    collectees = sorted(nom for nom, objet in globals().items()
                        if callable(objet)
                        and getattr(objet, "__module__", None) == __name__
                        and nom.startswith("test"))
    echecs += check(
        collectees == [POINT_ENTREE_PYTEST],
        f"pytest collecterait {collectees}, attendu ['{POINT_ENTREE_PYTEST}'] — "
        f"soit une auxiliaire porte un nom en test* (elle se nomme verifie_*), soit "
        f"{POINT_ENTREE_PYTEST} est absent du namespace au moment de l'appel")

    # Le FICHIER doit lui aussi matcher un motif de collecte de pytest. Renomme hors
    # de test_*.py / *_test.py, il n'est plus collecte du tout — en silence — pendant
    # que le point d'entree autonome continue d'afficher OK. La verification ci-dessus
    # ne verrait rien : elle inspecte un namespace que pytest ne visite jamais.
    nom_fichier = Path(__file__).name
    echecs += check(
        nom_fichier.startswith("test_") or nom_fichier.endswith("_test.py"),
        f"{nom_fichier} ne matche aucun motif de collecte pytest (test_*.py, "
        "*_test.py) : le fichier serait ignore sans un mot")

    return echecs


def leve(fn, message):
    """Verifie qu'un appel leve ResolutionError. Rend 1 en cas d'echec."""
    global TOTAL
    TOTAL += 1
    try:
        fn()
    except mx.ResolutionError:
        return 0
    print(f"ECHEC : {message}")
    return 1


def charge(page_id):
    return json.loads((FIXTURES / f"{page_id}.json").read_text(encoding="utf-8"))


def collecte(adf):
    trouves = {}

    def walk(node):
        nature = mx.classify_reuse_node(node)
        if nature:
            trouves.setdefault(nature, []).append(node)
        if mx.is_nested_table(node):
            trouves.setdefault("nested_table", []).append(node)
        for enfant in (node.get("content") or []) if isinstance(node, dict) else []:
            walk(enfant)

    walk(adf)
    return trouves


# --------------------------------------------------------------------------
# Fabriques de noeuds
# --------------------------------------------------------------------------

def macro(cle, params, corps=None, local_id=None):
    node = {
        "type": "bodiedExtension" if corps else "extension",
        "attrs": {"extensionKey": cle,
                  "parameters": {"macroParams": {k: {"value": v}
                                                 for k, v in params.items()}}},
    }
    if corps:
        node["content"] = corps
    if local_id:
        node["attrs"]["localId"] = local_id
    return node


CORPS = [{"type": "paragraph", "content": [{"type": "text", "text": "contenu"}]}]


def run():
    echecs = verifie_nommage_pytest()
    creer = collecte(charge("28344321"))       # CU-NOTE-CREER
    modifier = collecte(charge("28344344"))    # CU-NOTE-MODIFIER

    # ------------------------------------------------------------------
    # 1. Nettoyage des noms : entites + espace de tete
    # ------------------------------------------------------------------
    echecs += check(mx.clean_name(" RG-NOTE-ASSOCATION&period;PERSONNE")
                    == "RG-NOTE-ASSOCATION.PERSONNE",
                    "entite HTML et espace de tete doivent tomber tous les deux")
    echecs += check(mx.clean_name("RG-NOTE-TRI ") == "RG-NOTE-TRI",
                    "espace de fin doit tomber aussi")
    echecs += check(mx.clean_name(" &lowbar;X ") == "_X",
                    "unescape doit passer AVANT le strip")
    echecs += check(mx.clean_name(None) == "" and mx.clean_name("") == "",
                    "un nom absent ne doit pas lever")

    # ------------------------------------------------------------------
    # 2. Familles : reconnaissance par SOUS-CHAINE, jamais par enumeration
    # ------------------------------------------------------------------
    for cle in mx.VARIANTES_OBSERVEES[mx.FAMILLE_MULTIEXCERPT]:
        echecs += check(mx.famille_macro(macro(cle, {"name": "x"}))
                        == mx.FAMILLE_MULTIEXCERPT, f"{cle} doit etre multiexcerpt")
    for cle in mx.VARIANTES_OBSERVEES[mx.FAMILLE_EXCERPT]:
        echecs += check(mx.famille_macro(macro(cle, {"name": "x"}))
                        == mx.FAMILLE_EXCERPT, f"{cle} doit etre excerpt")

    # L'ordre des tests compte : "multiexcerpt" CONTIENT "excerpt".
    echecs += check(mx.famille_macro(macro("multiexcerpt-fast-block-macro", {"name": "x"}))
                    == mx.FAMILLE_MULTIEXCERPT,
                    "multiexcerpt-* ne doit jamais tomber en famille excerpt")
    # Une variante inconnue doit etre reconnue : c'est tout l'interet de la sous-chaine.
    echecs += check(mx.famille_macro(macro("multiexcerpt-v9-turbo", {"name": "x"}))
                    == mx.FAMILLE_MULTIEXCERPT,
                    "une variante multiexcerpt inedite doit etre reconnue")
    echecs += check(mx.famille_macro(macro("excerpt-include-v2", {"name": "x"}))
                    == mx.FAMILLE_EXCERPT,
                    "une variante excerpt inedite doit etre reconnue")
    echecs += check(mx.famille_macro(macro("toc", {})) is None,
                    "une macro sans excerpt dans la cle n'a pas de famille")
    echecs += check(mx.famille_macro({"type": "paragraph"}) is None,
                    "un noeud non-extension n'a pas de famille")

    # ------------------------------------------------------------------
    # 3. Corps present = definition, absent = inclusion — pour les 2 familles
    # ------------------------------------------------------------------
    for cle, famille in (("multiexcerpt-fast-block-macro", "multiexcerpt"),
                         ("excerpt", "excerpt")):
        avec = macro(cle, {"name": "n"}, corps=CORPS)
        sans = macro(cle, {"name": "n"})
        echecs += check(mx.classify_reuse_node(avec) == f"{famille}_definition",
                        f"{cle} avec corps = definition")
        echecs += check(mx.classify_reuse_node(sans) == f"{famille}_include",
                        f"{cle} sans corps = inclusion")

    # ------------------------------------------------------------------
    # 4. Page source : parametre different selon la famille
    # ------------------------------------------------------------------
    inc_mx = macro("multiexcerpt-fast-include-block-macro",
                   {"name": "RG-NOTE-TRI", "page": "SF-NOTE"})
    inc_ex = macro("excerpt-include", {"name": "RG-NOTE-TRI", "": "SF-NOTE"})
    echecs += check(mx.macro_page_source(inc_mx, "CU-X") == ("SF-NOTE", "page"),
                    "multiexcerpt lit la page dans macroParams.page")
    echecs += check(mx.macro_page_source(inc_ex, "CU-X") == ("SF-NOTE", ""),
                    "excerpt lit la page dans macroParams[''] — la cle VIDE")

    # Le piege : chercher `page` sur un excerpt-include ne trouve rien.
    echecs += check(mx.macro_param(inc_ex, "page") is None,
                    "un excerpt-include n'a PAS de parametre `page`")
    echecs += check(mx.macro_param(inc_ex, "") == "SF-NOTE",
                    "la cle vide est un parametre a part entiere")

    # Page absente ou vide = page courante, dans les deux familles.
    for cle, params in (("multiexcerpt-include-macro", {"name": "n", "page": ""}),
                        ("multiexcerpt-include-macro", {"name": "n"}),
                        ("excerpt-include", {"name": "n", "": ""}),
                        ("excerpt-include", {"name": "n"})):
        node = macro(cle, params)
        echecs += check(mx.macro_include_key(node, "Page hote") == ("Page hote", "n"),
                        f"page absente ou vide vise la page courante ({cle}, {params})")

    # Une definition n'a pas de parametre de page : sa cle vient de la page hote.
    echecs += check(mx.macro_definition_key(macro("excerpt", {"name": " X "}, CORPS),
                                            "SF-NOTE") == ("SF-NOTE", "X"),
                    "cle de definition = (page hote, nom nettoye)")
    # Nom vide apres nettoyage : legitime pour un extrait natif (extrait par defaut de la
    # page, cle (page, "")), interdit pour un multiexcerpt. Cas reel : 243695621.
    echecs += check(mx.macro_nom(macro("excerpt", {"name": "  "}, CORPS)) == "",
                    "un extrait natif sans nom est l'extrait par defaut : nom vide")
    echecs += check(mx.macro_nom(macro("excerpt", {}, CORPS)) == "",
                    "un extrait natif sans parametre name est l'extrait par defaut")
    echecs += check(mx.macro_include_key(macro("excerpt-include", {"": "SF-X"}), "CU-X")
                    == ("SF-X", ""), "un excerpt-include sans nom vise l'extrait par defaut")
    echecs += leve(lambda: mx.macro_nom(macro("multiexcerpt-fast-block-macro",
                                              {"name": "  "}, CORPS)),
                   "un multiexcerpt sans nom doit lever")

    # ------------------------------------------------------------------
    # 5. Index : une famille ne voit jamais l'autre
    # ------------------------------------------------------------------
    index = mx.IndexDefinitions()
    def_mx = macro("multiexcerpt-fast-block-macro", {"name": "habilitation"}, CORPS,
                   local_id="mx-1")
    def_ex = macro("excerpt", {"name": "habilitation"}, CORPS, local_id="ex-1")
    index.ajoute(def_mx, "SF-NOTE")
    index.ajoute(def_ex, "SF-NOTE")
    echecs += check(len(index) == 2,
                    "la meme cle dans deux familles cohabite sans conflit")
    echecs += check(index.cherche("multiexcerpt", ("SF-NOTE", "habilitation"))["node"]
                    is def_mx, "l'index multiexcerpt rend la definition multiexcerpt")
    echecs += check(index.cherche("excerpt", ("SF-NOTE", "habilitation"))["node"]
                    is def_ex, "l'index excerpt rend la definition excerpt")

    # Une inclusion ne resout que dans sa famille.
    inc_ex_vers_sfnote = macro("excerpt-include", {"name": "habilitation", "": "SF-NOTE"})
    inc_mx_vers_sfnote = macro("multiexcerpt-fast-include-block-macro",
                               {"name": "habilitation", "page": "SF-NOTE"})
    echecs += check(index.resout(inc_ex_vers_sfnote, "CU-X")["node"] is def_ex,
                    "une inclusion excerpt resout sur la definition excerpt")
    echecs += check(index.resout(inc_mx_vers_sfnote, "CU-X")["node"] is def_mx,
                    "une inclusion multiexcerpt resout sur la definition multiexcerpt")

    index_ex_seul = mx.IndexDefinitions()
    index_ex_seul.ajoute(macro("excerpt", {"name": "n"}, CORPS), "SF-NOTE")
    echecs += check(index_ex_seul.resout(
        macro("multiexcerpt-fast-include-block-macro", {"name": "n", "page": "SF-NOTE"}),
        "CU-X") is None,
        "une inclusion multiexcerpt ne doit PAS voir une definition excerpt")

    # ------------------------------------------------------------------
    # 6. LE PIEGE DE LA CLE VIDE — cas reel 27787265
    # ------------------------------------------------------------------
    # CU-NOTE-CONSULTER definit 'habilitation' localement ET l'inclut depuis
    # CU-NOTE-CREER. Un resolver qui cherche `page` ne trouve rien, conclut "page
    # courante", et sert la definition LOCALE : contenu faux, sans la moindre erreur.
    piege = mx.IndexDefinitions()
    def_locale = macro("excerpt", {"name": "habilitation"}, CORPS, local_id="locale")
    piege.ajoute(def_locale, "CU-NOTE-CONSULTER")
    inc_distante = macro("excerpt-include",
                         {"name": "habilitation", "": "CU-NOTE-CREER"})

    echecs += check(mx.macro_include_key(inc_distante, "CU-NOTE-CONSULTER")
                    == ("CU-NOTE-CREER", "habilitation"),
                    "la cle de l'inclusion doit viser CU-NOTE-CREER, pas la page hote")
    echecs += check(piege.resout(inc_distante, "CU-NOTE-CONSULTER") is None,
                    "PIEGE : une inclusion vers une autre page ne doit JAMAIS tomber "
                    "sur la definition locale de meme nom")

    def_distante = macro("excerpt", {"name": "habilitation"}, CORPS, local_id="distante")
    piege.ajoute(def_distante, "CU-NOTE-CREER")
    trouve = piege.resout(inc_distante, "CU-NOTE-CONSULTER")
    echecs += check(trouve is not None and trouve["node"] is def_distante,
                    "une fois la page source indexee, l'inclusion resout dessus")
    echecs += check(trouve["page_title"] == "CU-NOTE-CREER",
                    "la definition retenue doit etre celle de la page visee")

    # Une inclusion locale, elle, doit bien tomber sur la definition locale.
    inc_locale = macro("excerpt-include", {"name": "habilitation"})
    echecs += check(piege.resout(inc_locale, "CU-NOTE-CONSULTER")["node"] is def_locale,
                    "sans page source, l'inclusion vise bien la page courante")

    # ------------------------------------------------------------------
    # 7. Doublon de definition dans une meme famille — cas reel 27787265
    # ------------------------------------------------------------------
    doublon = mx.IndexDefinitions()
    d1 = macro("excerpt", {"name": "habilitation"}, CORPS, local_id="ce13daaf")
    d2 = macro("excerpt", {"name": "habilitation"}, CORPS, local_id="200d7829")
    doublon.ajoute(d1, "CU-NOTE-CONSULTER", page_id="27787265")
    try:
        doublon.ajoute(d2, "CU-NOTE-CONSULTER", page_id="27787265")
        echecs += check(False, "une cle en double dans la meme famille doit lever")
    except mx.ResolutionError as exc:
        message = str(exc)
        echecs += check("ce13daaf" in message and "200d7829" in message,
                        f"le message doit citer LES DEUX emplacements : {message}")
        echecs += check("27787265" in message,
                        "le message doit citer la page concernee")
        echecs += check("excerpt" in message, "le message doit citer la famille")

    # Le meme nom sur deux pages differentes n'est PAS un doublon.
    ok = mx.IndexDefinitions()
    ok.ajoute(macro("excerpt", {"name": "habilitation"}, CORPS), "PAGE-A")
    ok.ajoute(macro("excerpt", {"name": "habilitation"}, CORPS), "PAGE-B")
    echecs += check(len(ok) == 2, "(page, nom) : deux pages differentes cohabitent")

    echecs += leve(lambda: index.ajoute(inc_ex_vers_sfnote, "X"),
                   "indexer une inclusion comme definition doit lever")
    echecs += leve(lambda: index.resout(def_ex, "X"),
                   "resoudre une definition comme inclusion doit lever")

    # ------------------------------------------------------------------
    # 8. syncBlock : deux cles distinctes, sur les fixtures reelles
    # ------------------------------------------------------------------
    echecs += check(len(creer.get("sync_definition", [])) == 2,
                    "CU-NOTE-CREER porte 2 bodiedSyncBlock")
    echecs += check(len(modifier.get("sync_include", [])) == 2,
                    "CU-NOTE-MODIFIER porte 2 syncBlock")
    echecs += check(all(not (n.get("content") or []) for n in modifier["sync_include"]),
                    "le contenu est absent de la page consommatrice (content: [])")
    echecs += check(all(n.get("content") for n in creer["sync_definition"]),
                    "la definition porte le contenu reel")
    echecs += check(all(n["type"] not in mx.EXTENSION_NODE_TYPES
                        for n in modifier["sync_include"]),
                    "syncBlock n'est pas un noeud Extension")

    cles_inc = sorted(mx.sync_include_key(n) for n in modifier["sync_include"])
    cles_def = sorted(mx.sync_definition_key(n, "28344321") for n in creer["sync_definition"])
    echecs += check(cles_inc == cles_def,
                    f"les cles des deux cotes doivent coincider : {cles_inc} vs {cles_def}")
    echecs += check(all(pid == "28344321" for pid, _ in cles_inc),
                    "l'inclusion designe la page source par IDENTIFIANT")

    uuid_double = "2342b419-9e51-43bd-81f4-c45e0ca27d9b"
    faux = {"type": "bodiedSyncBlock", "attrs": {"resourceId": uuid_double}}
    k1 = mx.sync_definition_key(faux, "28344321")
    k2 = mx.sync_definition_key(faux, "396361729")
    echecs += check(k1 != k2,
                    "(page_id, uuid) doit distinguer deux definitions du meme UUID")
    echecs += check(k1[1] == k2[1],
                    "l'UUID seul ne distingue rien : c'est la page qui tranche")

    inc_node = {"type": "syncBlock",
                "attrs": {"resourceId": f"confluence-page/28344321/{uuid_double}"}}
    echecs += check(mx.sync_include_key(inc_node) == ("28344321", uuid_double),
                    "resourceId d'inclusion : confluence-page/{id}/{uuid}")
    echecs += leve(lambda: mx.sync_include_key(faux),
                   "un resourceId nu n'est pas une inclusion")
    echecs += leve(lambda: mx.sync_definition_key(inc_node, "1"),
                   "un resourceId prefixe n'est pas une definition")

    # ------------------------------------------------------------------
    # 9. nested-table : contenu integralement recuperable
    # ------------------------------------------------------------------
    echecs += check(len(creer.get("nested_table", [])) == 1
                    and len(modifier.get("nested_table", [])) == 1,
                    "une extension nested-table dans chaque fixture")
    for lot, page in ((creer, "CU-NOTE-CREER"), (modifier, "CU-NOTE-MODIFIER")):
        noeud = lot["nested_table"][0]
        contenu = mx.nested_table_content(noeud)
        echecs += check(any(n.get("type") == "table" for n in contenu),
                        f"{page} : le contenu extrait doit contenir un noeud table")
        echecs += check("cxhtml" in noeud["attrs"]["parameters"],
                        f"{page} : cxhtml coexiste avec adf")

    r_creer = creer["nested_table"][0]["attrs"]["parameters"].get("reason", "")
    r_modif = modifier["nested_table"][0]["attrs"]["parameters"].get("reason", "")
    echecs += check(r_creer != r_modif,
                    "les deux fixtures portent des reason de langues differentes")
    echecs += check(mx.is_nested_table(creer["nested_table"][0]),
                    "la detection se fait par extensionKey")
    echecs += check(mx.famille_macro(creer["nested_table"][0]) is None,
                    "nested-table n'est pas une macro de reutilisation")
    for params in ({"reason": "x", "cxhtml": "<table/>"}, {"adf": "{pas du json"},
                   {"adf": "[]"}):
        echecs += leve(
            lambda p=params: mx.nested_table_content(
                {"type": "extension",
                 "attrs": {"extensionKey": "nested-table", "parameters": p}}),
            f"adf absent ou illisible doit lever : {params}")

    # ------------------------------------------------------------------
    # 10. Recursion : detection de cycle, les 3 mecanismes dans la meme pile
    # ------------------------------------------------------------------
    guard = mx.CycleGuard()
    with guard.enter("multiexcerpt", ("SF-NOTE", "RG-NOTE-TRI")):
        # Meme cle, autre famille : ce n'est pas un cycle.
        with guard.enter("excerpt", ("SF-NOTE", "RG-NOTE-TRI")):
            with guard.enter("sync", ("28344321", uuid_double)):
                echecs += check(len(guard.pile) == 3,
                                "les 3 mecanismes cohabitent dans la pile")
                try:
                    with guard.enter("multiexcerpt", ("SF-NOTE", "RG-NOTE-TRI")):
                        echecs += check(False, "un cycle doit lever")
                except mx.ResolutionError as exc:
                    echecs += check("cycle" in str(exc),
                                    "le message doit nommer le cycle")
    echecs += check(guard.pile == [], "la pile doit se vider en sortie de contexte")

    guard2 = mx.CycleGuard(profondeur_max=2)
    try:
        with guard2.enter("excerpt", ("p", "a")):
            with guard2.enter("excerpt", ("p", "b")):
                with guard2.enter("excerpt", ("p", "c")):
                    echecs += check(False, "la profondeur max doit lever")
    except mx.ResolutionError:
        echecs += check(True, "")

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0



def test_multiexcerpt():
    """Point d'entree pytest."""
    assert run() == 0

if __name__ == "__main__":
    sys.exit(run())
