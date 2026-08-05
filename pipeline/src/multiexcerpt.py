#!/usr/bin/env python3
"""
Cles de resolution du contenu reutilise — multiexcerpt et syncBlock.

VERSION : 1.0

Le corpus SINAPSE porte DEUX mecanismes de reutilisation, avec deux cles distinctes :

  multiexcerpt  cle (page, nom)      -- la page est designee par son TITRE
  syncBlock     cle (page_id, uuid)  -- la page est designee par son IDENTIFIANT

Les deux sont traites par le meme visiteur, mais jamais par la meme cle : confondre
les deux casse silencieusement la resolution. Ce module ne contient que la couche de
cles et d'extraction de parametres — deterministe, sans reseau, sans conversion vers
markdown. Le parcours recursif lui-meme attend l'arbitrage reutiliser/reecrire le
resolver (question ouverte n.3 du brief) ; CycleGuard est fourni ici parce qu'il est
independant de cet arbitrage.

Contrat de reference : contracts/normalisation_adf.md.
"""

import html
import json
import re

VERSION = "1.0"


# ==========================================================================
# BLOC DE CONSTANTES — documente dans contracts/normalisation_adf.md
# ==========================================================================

# Les 6 variantes de macro multiexcerpt du corpus, relevees au recensement du
# 4 aout 2026. Un visiteur limite au type de noeud "extension" en manquerait la
# moitie : les definitions sont des bodiedExtension, les inclusions se repartissent
# entre extension et inlineExtension.
MULTIEXCERPT_DEFINITION_KEYS = frozenset({
    "multiexcerpt-fast-block-macro",     # bodiedExtension, 190 occurrences
    "multiexcerpt-macro",                # bodiedExtension,  69
    "multiexcerpt-fast-inline-macro",    # bodiedExtension,   1
})
MULTIEXCERPT_INCLUDE_KEYS = frozenset({
    "multiexcerpt-fast-include-block-macro",   # extension,       595
    "multiexcerpt-fast-include-inline-macro",  # inlineExtension,  50
    "multiexcerpt-include-macro",              # inlineExtension,   3 (forme historique)
})

# Les syncBlock ne sont PAS des noeuds Extension : un visiteur qui ne filtre que les
# extensions les manque en silence. Ce sont des types de noeuds a part entiere.
SYNC_DEFINITION_TYPES = frozenset({"bodiedSyncBlock"})
SYNC_INCLUDE_TYPES = frozenset({"syncBlock"})

EXTENSION_NODE_TYPES = frozenset({"extension", "bodiedExtension", "inlineExtension"})

# resourceId d'une INCLUSION syncBlock : "confluence-page/{PAGE_ID}/{UUID}".
# Le meme UUID sans prefixe de chemin est le resourceId de la DEFINITION.
RE_SYNC_RESOURCE = re.compile(r"^confluence-page/(?P<page_id>\d+)/(?P<uuid>[0-9a-fA-F-]{36})$")
RE_SYNC_UUID = re.compile(r"^(?P<uuid>[0-9a-fA-F-]{36})$")

NESTED_TABLE_KEY = "nested-table"


class ResolutionError(Exception):
    """Echec de resolution. Remonte au rapport, jamais avale."""


# ==========================================================================
# Nettoyage des identifiants
# ==========================================================================

def clean_name(nom):
    """Nom de multiexcerpt pret pour la jointure : entites decodees, puis strip.

    Les deux operations sont obligatoires et dans cet ordre. Le corpus contient
    " RG-NOTE-ASSOCATION&period;PERSONNE" : une entite HTML ET un espace de tete.
    Le strip doit s'appliquer des DEUX cotes de la jointure, definition comme
    inclusion, sinon la cle ne colle plus.
    """
    return html.unescape(str(nom or "")).strip()


def clean_page_title(titre):
    """Titre de page cible d'une inclusion multiexcerpt, meme traitement que le nom."""
    return html.unescape(str(titre or "")).strip()


# ==========================================================================
# Nature d'un noeud de reutilisation
# ==========================================================================

def classify_reuse_node(node):
    """Nature du noeud : definition ou inclusion, multiexcerpt ou sync. None sinon.

    C'est le point d'entree unique du visiteur : un seul parcours, quatre natures.
    """
    if not isinstance(node, dict):
        return None
    ntype = node.get("type")
    if ntype in SYNC_DEFINITION_TYPES:
        return "sync_definition"
    if ntype in SYNC_INCLUDE_TYPES:
        return "sync_include"
    if ntype in EXTENSION_NODE_TYPES:
        cle = (node.get("attrs") or {}).get("extensionKey") or ""
        if cle in MULTIEXCERPT_DEFINITION_KEYS:
            return "multiexcerpt_definition"
        if cle in MULTIEXCERPT_INCLUDE_KEYS:
            return "multiexcerpt_include"
    return None


def macro_param(node, nom):
    """Valeur d'un parametre de macro : attrs.parameters.macroParams.<nom>.value."""
    params = ((node.get("attrs") or {}).get("parameters") or {})
    valeur = (params.get("macroParams") or {}).get(nom)
    if isinstance(valeur, dict):
        valeur = valeur.get("value")
    return valeur


# ==========================================================================
# Cle multiexcerpt : (page, nom) — la page est un TITRE
# ==========================================================================

def multiexcerpt_definition_key(node, page_title_hote):
    """Cle d'une definition : (titre de la page qui la porte, nom nettoye).

    Une definition ne porte AUCUN parametre `page` : elle definit sur sa propre page.
    Le titre hote est donc fourni par l'appelant.
    """
    nom = clean_name(macro_param(node, "name"))
    if not nom:
        raise ResolutionError("definition multiexcerpt sans nom exploitable")
    return clean_page_title(page_title_hote), nom


def multiexcerpt_include_key(node, page_title_hote):
    """Cle d'une inclusion : (titre de la page cible, nom nettoye).

    `page` vide signifie « sur la page courante » — la macro omet le parametre quand
    la source et la consommatrice sont la meme page.
    """
    nom = clean_name(macro_param(node, "name"))
    if not nom:
        raise ResolutionError("inclusion multiexcerpt sans nom exploitable")
    cible = clean_page_title(macro_param(node, "page")) or clean_page_title(page_title_hote)
    return cible, nom


# ==========================================================================
# Cle syncBlock : (page_id, uuid) — la page est un IDENTIFIANT
# ==========================================================================

def sync_include_key(node):
    """Cle d'une inclusion syncBlock, lue dans attrs.resourceId.

    Le contenu est absent de la page consommatrice (content: []) : la source est
    designee par IDENTIFIANT de page, donc resolvable par un GET /pages/{id} direct,
    sans passer par pages_inventory.json et sans etre sensible au renommage —
    contrairement au multiexcerpt, qui vise un titre.
    """
    rid = ((node.get("attrs") or {}).get("resourceId")) or ""
    trouve = RE_SYNC_RESOURCE.match(rid)
    if not trouve:
        raise ResolutionError(f"resourceId d'inclusion syncBlock non reconnu : {rid!r}")
    return trouve.group("page_id"), trouve.group("uuid").lower()


def sync_definition_key(node, page_id_hote):
    """Cle d'une definition syncBlock : (identifiant de la page hote, uuid).

    L'UUID SEUL NE SUFFIT PAS. Le corpus contient le meme resourceId defini sur deux
    pages differentes — CU-NOTE-CREER (28344321) et CU-NOTE-TYPENOTE.CREER
    (396361729), la seconde etant une copie de la premiere — avec des contenus qui ont
    depuis diverge. Une resolution par UUID seul choisirait l'une des deux au hasard.
    """
    rid = ((node.get("attrs") or {}).get("resourceId")) or ""
    trouve = RE_SYNC_UUID.match(rid)
    if not trouve:
        raise ResolutionError(f"resourceId de definition syncBlock non reconnu : {rid!r}")
    return str(page_id_hote), trouve.group("uuid").lower()


# ==========================================================================
# nested-table : contenu integralement recuperable
# ==========================================================================

def is_nested_table(node):
    """Vrai si le noeud est le marqueur nested-table pose par Confluence.

    Detection par extensionKey UNIQUEMENT. Le champ `reason` est localise — anglais
    et francais tous deux presents dans le corpus — et ne doit jamais servir de test.
    """
    if not isinstance(node, dict) or node.get("type") not in EXTENSION_NODE_TYPES:
        return False
    return ((node.get("attrs") or {}).get("extensionKey") or "") == NESTED_TABLE_KEY


def nested_table_content(node):
    """Noeuds ADF de la table imbriquee, extraits de parameters.adf.

    `adf` est une CHAINE JSON contenant un document ADF complet : second json.loads(),
    comme pour body.atlas_doc_format.value. Le contenu est integralement recuperable,
    donc ce cas n'est PAS un echec de conversion et ne doit pas declasser la page en
    parse_status: partial. `reason` decrit une limitation de l'editeur Confluence.

    `cxhtml` coexiste avec `adf` dans les 11 occurrences du corpus : on utilise `adf`
    et on ignore `cxhtml`, qui est la meme table en XHTML de stockage.

    Leve ResolutionError si `adf` manque ou est illisible : c'est le SEUL cas
    nested-table qui justifie un parse_status: partial. Aucune occurrence a ce jour.
    """
    params = ((node.get("attrs") or {}).get("parameters") or {})
    brut = params.get("adf")
    if not brut:
        raise ResolutionError(
            "nested-table sans parametre `adf` : contenu non recuperable "
            f"(cles presentes : {sorted(params)})")
    try:
        document = json.loads(brut) if isinstance(brut, str) else brut
    except (json.JSONDecodeError, TypeError) as exc:
        raise ResolutionError(f"nested-table : parametre `adf` illisible ({exc})") from exc
    if not isinstance(document, dict):
        raise ResolutionError("nested-table : `adf` n'est pas un document ADF")
    return document.get("content") or []


# ==========================================================================
# Recursion : garde-fou de cycle
# ==========================================================================

class CycleGuard:
    """Pile de resolution avec detection de cycle.

    Aucune imbrication dans les fixtures CU-NOTE-CREER / CU-NOTE-MODIFIER, mais rien
    ne l'interdit : une definition peut inclure un autre multiexcerpt ou un syncBlock.
    Les cles des deux mecanismes cohabitent dans la meme pile, prefixees par leur
    nature pour qu'un (page_id, uuid) ne puisse pas collisionner avec un (page, nom).

        with guard.enter("multiexcerpt", cle):
            ...
    """

    def __init__(self, profondeur_max=20):
        self.pile = []
        self.profondeur_max = profondeur_max

    def enter(self, mecanisme, cle):
        marque = (mecanisme,) + tuple(cle)
        if marque in self.pile:
            chemin = " -> ".join(str(m) for m in self.pile + [marque])
            raise ResolutionError(f"cycle de resolution : {chemin}")
        if len(self.pile) >= self.profondeur_max:
            raise ResolutionError(
                f"imbrication au-dela de {self.profondeur_max} niveaux : {marque}")
        self.pile.append(marque)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.pile.pop()
        return False
