#!/usr/bin/env python3
"""
Tests des cles de resolution du contenu reutilise — pipeline/src/multiexcerpt.py.

Les cas sont tires des fixtures reelles CU-NOTE-CREER (28344321) et CU-NOTE-MODIFIER
(28344344), plus le doublon d'UUID CU-NOTE-TYPENOTE.* trouve au balayage du corpus.
Chaque test protege une decision de contracts/normalisation_adf.md.

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


def charge(page_id):
    return json.loads((FIXTURES / f"{page_id}.json").read_text(encoding="utf-8"))


def collecte(adf):
    """Tous les noeuds de reutilisation d'un document, par nature."""
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


def run():
    echecs = 0
    creer = collecte(charge("28344321"))       # CU-NOTE-CREER
    modifier = collecte(charge("28344344"))    # CU-NOTE-MODIFIER

    # ------------------------------------------------------------------
    # 1. Nettoyage des noms de multiexcerpt : entites + espace de tete
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

    # La jointure doit coller alors que les deux cotes portent l'espace de tete.
    # Definition sur SF-NOTE (180256775), inclusion depuis CU-NOTE-CREER.
    definition = {"type": "bodiedExtension",
                  "attrs": {"extensionKey": "multiexcerpt-fast-block-macro",
                            "parameters": {"macroParams": {
                                "name": {"value": " RG-NOTE-ASSOCATION&period;PERSONNE"}}}}}
    inclusion = {"type": "extension",
                 "attrs": {"extensionKey": "multiexcerpt-fast-include-block-macro",
                           "parameters": {"macroParams": {
                               "name": {"value": " RG-NOTE-ASSOCATION&period;PERSONNE"},
                               "page": {"value": "SF-NOTE: Règles de gestion consolidées"}}}}}
    cle_def = mx.multiexcerpt_definition_key(
        definition, "SF-NOTE: Règles de gestion consolidées")
    cle_inc = mx.multiexcerpt_include_key(inclusion, "CU-NOTE-CREER")
    echecs += check(cle_def == cle_inc,
                    f"la jointure doit coller apres nettoyage : {cle_def} vs {cle_inc}")
    echecs += check(cle_def == ("SF-NOTE: Règles de gestion consolidées",
                                "RG-NOTE-ASSOCATION.PERSONNE"),
                    "la cle multiexcerpt est (titre de page, nom nettoye)")

    # Un cote nettoye et l'autre pas : c'est ce que le strip des deux cotes evite.
    echecs += check(mx.clean_name(" RG-NOTE-TRI") != " RG-NOTE-TRI",
                    "sans strip, la cle brute differe de la cle nettoyee")

    # Une inclusion sans parametre `page` vise la page courante.
    local = {"type": "extension",
             "attrs": {"extensionKey": "multiexcerpt-include-macro",
                       "parameters": {"macroParams": {"name": {"value": "test"},
                                                      "page": {"value": ""}}}}}
    echecs += check(mx.multiexcerpt_include_key(local, "Page hote") == ("Page hote", "test"),
                    "page vide = inclusion sur la page courante")

    # ------------------------------------------------------------------
    # 2. Les 6 variantes de macro sont reconnues, et separees def/include
    # ------------------------------------------------------------------
    echecs += check(len(mx.MULTIEXCERPT_DEFINITION_KEYS) == 3
                    and len(mx.MULTIEXCERPT_INCLUDE_KEYS) == 3,
                    "6 variantes attendues : 3 definitions, 3 inclusions")
    echecs += check(not (mx.MULTIEXCERPT_DEFINITION_KEYS & mx.MULTIEXCERPT_INCLUDE_KEYS),
                    "aucune variante ne peut etre a la fois definition et inclusion")
    echecs += check(mx.classify_reuse_node(definition) == "multiexcerpt_definition",
                    "bodiedExtension multiexcerpt = definition")
    echecs += check(mx.classify_reuse_node(inclusion) == "multiexcerpt_include",
                    "extension multiexcerpt-*-include-* = inclusion")

    # ------------------------------------------------------------------
    # 3. syncBlock : deux cles distinctes, sur les fixtures reelles
    # ------------------------------------------------------------------
    echecs += check(len(creer.get("sync_definition", [])) == 2,
                    "CU-NOTE-CREER porte 2 bodiedSyncBlock")
    echecs += check(len(modifier.get("sync_include", [])) == 2,
                    "CU-NOTE-MODIFIER porte 2 syncBlock")
    echecs += check(all(not (n.get("content") or []) for n in modifier["sync_include"]),
                    "le contenu est absent de la page consommatrice (content: [])")
    echecs += check(all(n.get("content") for n in creer["sync_definition"]),
                    "la definition porte le contenu reel")

    # Un syncBlock n'est PAS un noeud Extension : le visiteur doit le voir quand meme.
    echecs += check(all(n["type"] not in mx.EXTENSION_NODE_TYPES
                        for n in modifier["sync_include"]),
                    "syncBlock n'est pas un noeud Extension")

    cles_inc = sorted(mx.sync_include_key(n) for n in modifier["sync_include"])
    cles_def = sorted(mx.sync_definition_key(n, "28344321") for n in creer["sync_definition"])
    echecs += check(cles_inc == cles_def,
                    f"les cles des deux cotes doivent coincider : {cles_inc} vs {cles_def}")
    echecs += check(all(pid == "28344321" for pid, _ in cles_inc),
                    "l'inclusion designe la page source par IDENTIFIANT")

    # Le doublon reel : meme UUID defini sur deux pages, contenus diverges.
    uuid_double = "2342b419-9e51-43bd-81f4-c45e0ca27d9b"
    faux = {"type": "bodiedSyncBlock", "attrs": {"resourceId": uuid_double}}
    k1 = mx.sync_definition_key(faux, "28344321")
    k2 = mx.sync_definition_key(faux, "396361729")
    echecs += check(k1 != k2,
                    "(page_id, uuid) doit distinguer deux definitions du meme UUID")
    echecs += check(k1[1] == k2[1],
                    "l'UUID seul ne distingue rien : c'est bien la page qui tranche")

    # Formes de resourceId : inclusion prefixee, definition nue. Jamais confondues.
    inc_node = {"type": "syncBlock",
                "attrs": {"resourceId": f"confluence-page/28344321/{uuid_double}"}}
    echecs += check(mx.sync_include_key(inc_node) == ("28344321", uuid_double),
                    "resourceId d'inclusion : confluence-page/{id}/{uuid}")
    for mauvais, fn in ((faux, mx.sync_include_key),
                        (inc_node, lambda n: mx.sync_definition_key(n, "1"))):
        try:
            fn(mauvais)
            echecs += check(False, "une forme de resourceId inattendue doit lever")
        except mx.ResolutionError:
            echecs += check(True, "")

    # ------------------------------------------------------------------
    # 4. nested-table : contenu integralement recuperable
    # ------------------------------------------------------------------
    echecs += check(len(creer.get("nested_table", [])) == 1
                    and len(modifier.get("nested_table", [])) == 1,
                    "une extension nested-table dans chaque fixture")
    for lot, page in ((creer, "CU-NOTE-CREER"), (modifier, "CU-NOTE-MODIFIER")):
        noeud = lot["nested_table"][0]
        contenu = mx.nested_table_content(noeud)
        echecs += check(bool(contenu),
                        f"{page} : le contenu de la table imbriquee doit etre extrait")
        echecs += check(any(n.get("type") == "table" for n in contenu),
                        f"{page} : le contenu extrait doit contenir un noeud table")
        params = noeud["attrs"]["parameters"]
        echecs += check("cxhtml" in params and "adf" in params,
                        f"{page} : cxhtml coexiste avec adf")

    # reason est localise : anglais sur une page, francais sur l'autre. Ne jamais
    # s'en servir pour detecter le cas.
    r_creer = creer["nested_table"][0]["attrs"]["parameters"].get("reason", "")
    r_modif = modifier["nested_table"][0]["attrs"]["parameters"].get("reason", "")
    echecs += check(r_creer != r_modif,
                    "les deux fixtures doivent porter des reason de langues differentes")
    echecs += check(mx.is_nested_table(creer["nested_table"][0]),
                    "la detection se fait par extensionKey")
    sans_reason = {"type": "extension",
                   "attrs": {"extensionKey": "nested-table",
                             "parameters": {"adf": json.dumps(
                                 {"type": "doc", "content": [{"type": "table"}]})}}}
    echecs += check(mx.is_nested_table(sans_reason)
                    and mx.nested_table_content(sans_reason),
                    "un nested-table sans reason doit rester detecte et exploitable")

    # Seul cas justifiant un parse_status: partial — aucune occurrence dans le corpus.
    for params in ({"reason": "x", "cxhtml": "<table/>"}, {"adf": "{pas du json"},
                   {"adf": "[]"}):
        try:
            mx.nested_table_content({"type": "extension",
                                     "attrs": {"extensionKey": "nested-table",
                                               "parameters": params}})
            echecs += check(False, f"adf absent ou illisible doit lever : {params}")
        except mx.ResolutionError:
            echecs += check(True, "")

    # ------------------------------------------------------------------
    # 5. Recursion : detection de cycle, cles des deux mecanismes melangees
    # ------------------------------------------------------------------
    guard = mx.CycleGuard()
    with guard.enter("multiexcerpt", ("SF-NOTE", "RG-NOTE-TRI")):
        with guard.enter("sync", ("28344321", uuid_double)):
            try:
                with guard.enter("multiexcerpt", ("SF-NOTE", "RG-NOTE-TRI")):
                    echecs += check(False, "un cycle doit lever")
            except mx.ResolutionError as exc:
                echecs += check("cycle" in str(exc), "le message doit nommer le cycle")
            # Une cle sync et une cle multiexcerpt de meme forme ne collisionnent pas.
            echecs += check(len(guard.pile) == 2, "la pile doit contenir les 2 niveaux")
    echecs += check(guard.pile == [], "la pile doit se vider en sortie de contexte")

    guard2 = mx.CycleGuard(profondeur_max=2)
    try:
        with guard2.enter("multiexcerpt", ("p", "a")):
            with guard2.enter("multiexcerpt", ("p", "b")):
                with guard2.enter("multiexcerpt", ("p", "c")):
                    echecs += check(False, "la profondeur max doit lever")
    except mx.ResolutionError:
        echecs += check(True, "")

    if echecs:
        print(f"\n{echecs} echec(s) sur {TOTAL} verifications")
        return 1
    print(f"OK - {TOTAL} verifications passees")
    return 0


if __name__ == "__main__":
    sys.exit(run())


def test_multiexcerpt():
    """Point d'entree pytest."""
    assert run() == 0
