#!/usr/bin/env python3
"""
Ecriture des `.md` : chemin (inventaire), frontmatter (contracts/frontmatter.md), fichier.

VERSION : 1.0 — chemins par l'arborescence, frontmatter du contrat, ecriture atomique

Le rendu lui-meme est celui de renderer.py, sur l'ADF RESOLU par resolver.py : le contenu
reutilise y apparait encadre de ses marqueurs (normalisation_adf.md §1.9). Ce module ne
fait que placer et ecrire le resultat.

Chemins : `md_path()` de inventory.py (contracts/slugification.md), qui reproduit
l'arborescence Confluence sous `specs/`. Une page dont l'arborescence n'est pas connue
(pages de test isolees) va a plat sous `pages/`. Une collision de chemin n'est pas
resolue : les pages concernees ne sont pas ecrites et sont listees au rapport.
"""

import json
from pathlib import Path

from inventory import detecte_collisions, md_path, meres_exportantes, slugify

VERSION = "1.0"
SCHEMA_FRONTMATTER = 1


def chemins(inventaire):
    """{page_id: md_path} des pages exportees, et la liste des pages en collision.

    `inventaire` : {page_id: classement de inventory.classify_page()}.
    """
    # Une page dont l'arborescence n'est pas connue est classee hors perimetre, donc non
    # exportee : elle est quand meme ecrite, a plat, pour qu'une page de test ait son .md.
    pages = [c for c in inventaire.values() if not c.get("excluded")
             and (c.get("exported", True) or c.get("group") == "hors_perimetre")]
    par_id = {c["id"]: c for c in inventaire.values()}
    meres = meres_exportantes(pages)
    en_collision = {p["id"] for lot in detecte_collisions(pages).values() for p in lot}
    resultat = {}
    for page in pages:
        if page["id"] in en_collision:
            continue
        chemin = md_path(page, par_id, meres)
        if chemin is None:
            chemin = f"pages/{slugify(page.get('title'), page['id'])}.md"
        resultat[page["id"]] = chemin
    return resultat, sorted(en_collision)


def _yaml(valeur):
    """Valeur YAML : JSON est un sous-ensemble de YAML pour les chaines, nombres et null."""
    return json.dumps(valeur, ensure_ascii=False)


def frontmatter(faits, exporte_le, version_date=None, jira=None):
    page = faits["page"]
    champs = [
        ("page_id", page["id"]),
        ("page_title", page["titre"]),
        ("page_url", page.get("url")),
        ("confluence_version", page.get("confluence_version")),
        ("version_date", version_date),
        ("exported_at", exporte_le),
        ("pipeline_version", VERSION),
        ("schema_version", SCHEMA_FRONTMATTER),
        ("module", page.get("module")),
        ("type", page.get("type")),
        ("parse_status", page.get("parse_status")),
    ]
    if page.get("titre_brut"):
        champs.append(("title_raw", page["titre_brut"]))
    if jira:
        champs += [("jira_test_key", jira.get("ticket_test")), ("jira_jql", jira.get("jql"))]
    lignes = ["---"] + [f"{cle}: {_yaml(valeur)}" for cle, valeur in champs] + ["---", ""]
    return "\n".join(lignes)


def ecrit(racine, chemin, contenu):
    """Ecriture atomique et seulement si le contenu change. Rend True si le fichier a change."""
    cible = Path(racine) / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    if cible.exists() and cible.read_text(encoding="utf-8") == contenu:
        return False
    temporaire = cible.with_name(cible.name + ".tmp")
    temporaire.write_text(contenu, encoding="utf-8")
    temporaire.replace(cible)
    return True
