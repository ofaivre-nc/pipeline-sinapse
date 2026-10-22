#!/usr/bin/env python3
"""
Projections des faits — JSON carto et JSON MCD (contracts/faits.md §7).

VERSION : 1.0 — premiere version : noeuds, aretes structurelles, entites et relations

Condition posee le 2026-10-21 : les deux JSON se deduisent des faits par un script
COURT et sans heuristique cachee. Ce module ne lit que les faits de page et le graphe ;
il ne relit jamais l'ADF.

Non produit en v1, et dit comme tel dans `_meta.non_produit` : l'heuristique RG -> entite
(`lecture`, `ecriture`, `lecture_critere`, `categorie` des RG). C'est une heuristique de
la projection, jamais un fait ni un score ; elle sera reprise de la procedure carto §2.6
si la cartographie en a besoin.
"""

VERSION = "1.0"


def _phrase(texte):
    """Premiere ligne d'un Texte : la description courte d'un noeud carto."""
    return (texte or {}).get("texte", "").split("\n")[0].strip()


def _tickets(faits):
    return list(dict.fromkeys(t for e in faits.get("evolutions", []) for t in e.get("tickets", [])))


def _une_ligne(texte):
    """Texte d'une cellule sur une ligne, comme get_text(separator=" ") du legacy."""
    return " ".join((texte or {}).get("texte", "").split())


def _sans_inclusion(texte):
    """Texte d'une cellule, sauf s'il n'est fait que d'inclusions (contenu d'une autre page)."""
    texte = texte or {}
    if texte.get("inclusions") and not texte.get("texte", "").replace(
            "".join("{inclusion:" + i["nom"] + "}" for i in texte["inclusions"]), "").strip():
        return None
    return texte.get("texte")


def _sans_vide(noeud):
    """Le JSON carto omet les listes et textes vides (notice §8)."""
    return {k: v for k, v in noeud.items() if v not in (None, "", [], {})}


# ==========================================================================
# JSON carto (notice de cartographie §8)
# ==========================================================================

def projette_carto(pages, graphe, perimetre=None):
    """JSON carto des pages du perimetre (ids de page CU, SA, API ; tout si None).

    Les RG retenues sont celles que les CU et SA du perimetre referencent, comme dans
    la cartographie de reference. Les cibles hors corpus vont dans
    `_meta.references_non_resolues`.
    """
    par_id = {f["page"]["id"]: f for f in pages}
    dans = (lambda f: True) if perimetre is None else (lambda f: f["page"]["id"] in perimetre)
    retenues = [f for f in pages if f["page"]["type"] in ("CU", "SA", "API") and dans(f)]
    titres = {f["page"]["titre"] for f in retenues}
    aretes = graphe["aretes"]

    references = [a for a in aretes if a["type"] == "reference" and a["de"] in titres]
    rg_ids = {a["vers"] for a in references}
    endpoints = [n for n in graphe["noeuds"]["endpoint"] if n["api"] in titres]
    ep_ids = {n["id"] for n in endpoints}

    noeuds = {"cu": [], "endpoint": [], "sa": [], "rg": [], "api": []}
    for faits in retenues:
        page = faits["page"]
        base = {"id": page["titre"], "sf": page.get("module"), "url": page.get("url")}
        if page["type"] == "CU":
            noeuds["cu"].append(_sans_vide(dict(
                base, habilitation=faits.get("cartouche", {}).get("habilitation", {}).get("texte"),
                tickets=_tickets(faits))))
        elif page["type"] == "SA":
            noeuds["sa"].append(_sans_vide(dict(base, description=_phrase(faits.get("objet")),
                                                tickets=_tickets(faits))))
        else:
            noeuds["api"].append(_sans_vide(dict(base, tickets=_tickets(faits))))

    expose = {a["de"]: a for a in aretes if a["type"] == "expose"}
    for noeud in endpoints:
        api = next(f for f in retenues if f["page"]["titre"] == noeud["api"])
        ligne = next((l for l in api.get("routes", [])
                      if f"{l.get('verbe')} {l.get('chemin')}" == noeud["id"]), {})
        arete = expose.get(noeud["id"])
        noeuds["endpoint"].append(_sans_vide({
            "id": noeud["id"], "api": noeud["api"],
            "sa": arete["vers"] if arete and not arete.get("confiance") else None,
            "description": _phrase(ligne.get("cellules", {}).get("objet")),
            "habilitation": _sans_inclusion(ligne.get("cellules", {}).get("habilitation")),
            "confiance": (arete or {}).get("confiance", "structure" if arete else None)}))

    for noeud in graphe["noeuds"]["rg"]:
        if noeud["id"] not in rg_ids:
            continue
        regle = next((r for r in par_id[noeud["page_id"]].get("regles", [])
                      if r["nom"] == noeud["id"]), {})
        noeuds["rg"].append(_sans_vide({"id": noeud["id"], "sf": noeud.get("sf"),
                                        "url": noeud.get("url"),
                                        "description": regle.get("concernant")}))
    for liste in noeuds.values():
        deja = set()
        liste[:] = [n for n in liste if not (n["id"] in deja or deja.add(n["id"]))]

    edges = []
    vues = set()

    def ajoute(de, vers, type_, confiance):
        if (de, vers, type_) not in vues:
            vues.add((de, vers, type_))
            edges.append(_sans_vide({"from": de, "to": vers, "type": type_,
                                     "confiance": confiance}))

    # CU -> endpoint : composition CU -> RG (reference) + RG -> endpoint (appelle) ; les
    # liens de route sont dans le corps des RG, pas dans les CU (contrat §6).
    appels_rg = {}
    for a in aretes:
        if a["type"] == "appelle":
            appels_rg.setdefault(a["de"], []).append(a["vers"])
    for a in references:
        page = next(f for f in retenues if f["page"]["titre"] == a["de"])
        if page["page"]["type"] == "CU":
            for vers in appels_rg.get(a["vers"], []):
                if vers in ep_ids:
                    ajoute(a["de"], vers, "appelle", "composition")
    for a in aretes:
        if a["type"] == "appelle" and a["de"] in titres and a["vers"] in ep_ids:
            ajoute(a["de"], a["vers"], "appelle", "lien")
    for noeud in noeuds["endpoint"]:
        arete = expose.get(noeud["id"])
        if arete:
            ajoute(noeud["id"], arete["vers"], "expose", arete.get("confiance", "structure"))
    for a in references:
        ajoute(a["de"], a["vers"], "reference", "structure")
    for rg in rg_ids:
        for vers in appels_rg.get(rg, []):
            if not vers.split(" ", 1)[0] in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                ajoute(rg, vers, "appelle", "lien")

    connus = {n["id"] for liste in noeuds.values() for n in liste}
    non_resolues = sorted({e["to"] for e in edges if e["to"] not in connus})
    return {
        "_meta": {"projection_version": VERSION,
                  "pages_connues": [_sans_vide({"id": f["page"]["id"], "type": f["page"]["type"],
                                                "module": f["page"].get("module"),
                                                "titre": f["page"]["titre"],
                                                "confluence_version": f["page"].get("confluence_version")})
                                    for f in retenues],
                  "references_non_resolues": non_resolues,
                  "non_produit": ["aretes RG -> entite (lecture, ecriture, lecture_critere)",
                                  "categorie des RG"]},
        "nodes": noeuds,
        "edges": edges,
    }


# ==========================================================================
# JSON MCD (v2.0)
# ==========================================================================

def projette_mcd(pages):
    """`entities` et `relations` du JSON MCD, depuis les faits des pages MCD.

    Les lignes et relations barrees (evolution a venir) ne sont pas projetees, comme
    le faisait le skill legacy confluence-mcd-sync. `quartiers`, `paliers` et les
    tickets viennent de l'etape Jira ou du fichier precedent (contrat §7.2).
    """
    entites, relations, vues = [], [], set()
    for faits in pages:
        if faits["page"]["type"] != "MCD":
            continue
        sf = faits["page"].get("module")
        for entite in faits.get("entites", []):
            attrs = []
            for a in entite["attributs"]:
                if a.get("barre"):
                    continue
                # Regles du legacy confluence-mcd-sync, que le fichier reel suit : format
                # sans longueur, et `commentaire` pris dans « Valeurs possibles » (sa
                # table de colonnes retenait la DERNIERE colonne qui parle de valeur).
                valeurs = _une_ligne(a.get("valeurs"))
                attrs.append({"nom": a["attribut"],
                              "designation": _une_ligne(a.get("designation")) or a["attribut"],
                              "format": " ".join(a.get("format", "").split()) or "string",
                              "commentaire": "" if valeurs == "-" else valeurs})
            entites.append({"id": entite["nom"], "label": entite["nom"], "sf": sf,
                            "attrs": attrs})
        for r in faits.get("relations", []):
            cle = "|".join(sorted((r["de"], r["vers"])))
            if r.get("barre") or cle in vues:
                continue
            vues.add(cle)
            relation = {"from": r["de"], "to": r["vers"], "cardFrom": r["card_de"],
                        "cardTo": r["card_vers"]}
            if r.get("libelle"):
                relation["name"] = r["libelle"]
            relations.append(relation)
    return {"entities": entites, "relations": relations}
