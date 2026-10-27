#!/usr/bin/env python3
"""
Cles de resolution du contenu reutilise — multiexcerpt, excerpt et syncBlock.

VERSION : 1.4 — nom defini deux fois : cle ambigue, l'indexation de la page continue (contrat §1.8,
                « traite comme une definition absente »)
          1.3 — extrait natif sans nom = extrait par defaut de la page (contrat §1.8)

Le corpus SINAPSE porte TROIS mecanismes de reutilisation, dont deux par macro :

  multiexcerpt  cle (page, nom)      page designee par TITRE, parametre `page`
  excerpt       cle (page, nom)      page designee par TITRE, parametre `""` (vide)
  syncBlock     cle (page_id, uuid)  page designee par IDENTIFIANT

Les deux familles de macro partagent la forme de leur cle mais PAS l'endroit ou elles
rangent la page source, et surtout pas leur index : Confluence ne croise jamais les
deux. Un `excerpt-include` ne voit pas une definition multiexcerpt, et reciproquement.
Si le pipeline les croisait, il produirait un `.md` plus complet que la page reelle et
masquerait un affichage casse — le contraire de ce qu'on attend d'un export fidele.

Une inclusion de macro porte en outre une FORME — bloc ou inline — orthogonale a sa
famille : la forme dit ou le contenu resolu doit etre depose, la famille dit contre quel
index il se resout. est_inclusion_inline() rend la premiere ; famille_macro() la seconde.

Ce module ne contient que la couche de cles et d'extraction — deterministe, sans
reseau, sans conversion vers markdown. Le parcours recursif attend l'arbitrage
reutiliser/reecrire le resolver ; CycleGuard est fourni ici parce qu'il en est
independant.

Contrat de reference : contracts/normalisation_adf.md, §1.9 pour la forme inline.
"""

import html
import json
import re

VERSION = "1.4"


# ==========================================================================
# BLOC DE CONSTANTES — documente dans contracts/normalisation_adf.md
# ==========================================================================

EXTENSION_NODE_TYPES = frozenset({"extension", "bodiedExtension", "inlineExtension"})

# --- Forme d'une inclusion : bloc ou inline. Les DEUX criteres de l'union du §1.9, dont
# aucun ne suffit seul — le type de noeud pour la forme historique, la sous-chaine de
# cle pour un `extension` qui l'annonce.
TYPE_INLINE_EXTENSION = "inlineExtension"
CLE_FORME_INLINE = "include-inline"

# --- Familles de macro : reconnaissance par SOUS-CHAINE de la cle d'extension.
# JAMAIS par enumeration de variantes : le corpus en compte 6 pour le seul
# multiexcerpt, la liste a deja bouge une fois (apparition d'`excerpt` le 5 aout 2026),
# et une variante inconnue tomberait silencieusement hors radar.
# L'ORDRE DES TESTS COMPTE : "multiexcerpt-fast-block-macro" contient "excerpt".
FAMILLE_MULTIEXCERPT = "multiexcerpt"
FAMILLE_EXCERPT = "excerpt"
FAMILLES = (FAMILLE_MULTIEXCERPT, FAMILLE_EXCERPT)

# Parametre portant le TITRE de la page source, par famille.
# La famille excerpt utilise la cle VIDE : heritage du parametre positionnel du wiki
# markup ({excerpt-include:Page|name=X}), que l'ADF conserve tel quel. Chercher `page`
# sur un excerpt-include ne trouve rien et fait conclure "page courante" — donc
# resoudre contre une definition locale de meme nom, sans lever la moindre erreur.
PARAM_PAGE_PAR_FAMILLE = {
    FAMILLE_MULTIEXCERPT: "page",
    FAMILLE_EXCERPT: "",
}

# Familles ou une macro SANS NOM est legitime. Un extrait natif sans nom est l'extrait
# PAR DEFAUT de sa page, et un excerpt-include sans nom l'inclut : la cle est alors
# (page, ""). Le multiexcerpt exige un nom ; sans nom, il leve toujours.
# Releve le 22 octobre 2026 sur `243695621` (SF-PORTAIL: Regles de gestion consolidees) :
# la levee arretait l'indexation de la page source au milieu, et toutes les definitions
# suivantes passaient pour absentes. Contrat §1.8.
FAMILLES_NOM_FACULTATIF = frozenset({FAMILLE_EXCERPT})
NOM_PAR_DEFAUT = ""

# Variantes relevees au 6 aout 2026. DOCUMENTAIRE UNIQUEMENT : rien ici ne sert a la
# reconnaissance, qui se fait par sous-chaine. Cette liste vieillira, pas le code.
VARIANTES_OBSERVEES = {
    FAMILLE_MULTIEXCERPT: (
        "multiexcerpt-fast-include-block-macro",   # extension,       inclusion
        "multiexcerpt-fast-block-macro",           # bodiedExtension, definition
        "multiexcerpt-macro",                      # bodiedExtension, definition
        "multiexcerpt-fast-include-inline-macro",  # inlineExtension, inclusion
        "multiexcerpt-include-macro",              # inlineExtension, inclusion
        "multiexcerpt-fast-inline-macro",          # bodiedExtension, definition
    ),
    FAMILLE_EXCERPT: (
        "excerpt",          # bodiedExtension, definition
        "excerpt-include",  # extension,       inclusion
    ),
}

# Les syncBlock ne sont PAS des noeuds Extension : un visiteur qui ne filtre que les
# extensions les manque en silence. Ce sont des types de noeuds a part entiere.
SYNC_DEFINITION_TYPES = frozenset({"bodiedSyncBlock"})
SYNC_INCLUDE_TYPES = frozenset({"syncBlock"})

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
    """Nom pret pour la jointure : entites decodees, puis strip. Les deux, dans cet ordre.

    Le corpus contient " RG-NOTE-ASSOCATION&period;PERSONNE" : une entite HTML ET un
    espace de tete. Le nettoyage s'applique des DEUX cotes de la jointure, definition
    comme inclusion, sinon la cle ne colle plus.
    """
    return html.unescape(str(nom or "")).strip()


def clean_page_title(titre):
    """Titre de page cible, meme traitement que le nom."""
    return html.unescape(str(titre or "")).strip()


# ==========================================================================
# Nature d'un noeud de reutilisation — POINT D'ENTREE UNIQUE
# ==========================================================================

def famille_macro(node):
    """Famille d'une macro de reutilisation, ou None. Par sous-chaine, ordre significatif."""
    if not isinstance(node, dict) or node.get("type") not in EXTENSION_NODE_TYPES:
        return None
    cle = ((node.get("attrs") or {}).get("extensionKey") or "").lower()
    if FAMILLE_MULTIEXCERPT in cle:      # doit passer AVANT : contient "excerpt"
        return FAMILLE_MULTIEXCERPT
    if FAMILLE_EXCERPT in cle:
        return FAMILLE_EXCERPT
    return None


def a_un_corps(node):
    """Corps present = definition ; absent = inclusion. Vrai pour les deux familles."""
    return bool(node.get("content"))


def classify_reuse_node(node):
    """Nature du noeud, ou None. Point d'entree unique du visiteur.

    Rend l'une de : multiexcerpt_definition, multiexcerpt_include, excerpt_definition,
    excerpt_include, sync_definition, sync_include.
    """
    if not isinstance(node, dict):
        return None
    ntype = node.get("type")
    if ntype in SYNC_DEFINITION_TYPES:
        return "sync_definition"
    if ntype in SYNC_INCLUDE_TYPES:
        return "sync_include"
    famille = famille_macro(node)
    if famille:
        return f"{famille}_{'definition' if a_un_corps(node) else 'include'}"
    return None


def est_inclusion_inline(node):
    """Forme inline d'une inclusion : UNION de deux criteres, jamais la seule cle.

    Est inline une inclusion portee par un noeud `inlineExtension`, OU dont
    l'extensionKey contient `include-inline`. La forme historique
    `multiexcerpt-include-macro` est portee par un inlineExtension dont la cle ne
    contient PAS `include-inline` : un test sur la seule cle la manque.
    Mesure du 11 aout 2026 : 1 occurrence au perimetre d'export, 4 sur les 248
    fixtures du recensement. Contrat §1.9.

    Rend False pour tout ce qui n'est pas une INCLUSION de macro — une definition, un
    syncBlock, un noeud quelconque. La FAMILLE continue de se reconnaitre par
    sous-chaine comme au §2.3 ; c'est la FORME qui demande l'union.
    """
    nature = classify_reuse_node(node)
    if nature not in tuple(f"{famille}_include" for famille in FAMILLES):
        return False
    if node.get("type") == TYPE_INLINE_EXTENSION:
        return True
    cle = ((node.get("attrs") or {}).get("extensionKey") or "").lower()
    return CLE_FORME_INLINE in cle


def macro_param(node, nom):
    """Valeur d'un parametre de macro : attrs.parameters.macroParams.<nom>.value.

    `nom` peut etre la chaine vide : c'est le parametre positionnel de la famille
    excerpt, une cle a part entiere dans macroParams.
    """
    params = ((node.get("attrs") or {}).get("parameters") or {})
    valeur = (params.get("macroParams") or {}).get(nom)
    if isinstance(valeur, dict):
        valeur = valeur.get("value")
    return valeur


# ==========================================================================
# Cle des macros : (page, nom) — la page est un TITRE
# ==========================================================================

def macro_page_source(node, page_title_hote):
    """(titre de la page source, parametre qui la portait).

    Une page absente ou vide vise la page COURANTE, dans les deux familles.
    """
    famille = famille_macro(node)
    if not famille:
        raise ResolutionError(f"noeud sans famille de macro : {node.get('type')!r}")
    param = PARAM_PAGE_PAR_FAMILLE[famille]
    cible = clean_page_title(macro_param(node, param))
    if cible:
        return cible, param
    return clean_page_title(page_title_hote), None


def macro_nom(node):
    """Nom nettoye. Vide pour un extrait natif sans nom : c'est l'extrait par defaut."""
    nom = clean_name(macro_param(node, "name"))
    if not nom:
        if famille_macro(node) in FAMILLES_NOM_FACULTATIF:
            return NOM_PAR_DEFAUT
        raise ResolutionError(
            f"macro {famille_macro(node)} sans nom exploitable "
            f"(extensionKey={(node.get('attrs') or {}).get('extensionKey')!r})")
    return nom


def macro_definition_key(node, page_title_hote):
    """Cle d'une definition : (titre de la page qui la porte, nom nettoye).

    Une definition ne porte pas de parametre de page — ni `page`, ni `""` : elle definit
    sur sa propre page. Le titre hote est donc fourni par l'appelant.
    """
    return clean_page_title(page_title_hote), macro_nom(node)


def macro_include_key(node, page_title_hote):
    """Cle d'une inclusion : (titre de la page cible, nom nettoye)."""
    cible, _ = macro_page_source(node, page_title_hote)
    return cible, macro_nom(node)


# ==========================================================================
# Cle syncBlock : (page_id, uuid) — la page est un IDENTIFIANT
# ==========================================================================

def sync_include_key(node):
    """Cle d'une inclusion syncBlock, lue dans attrs.resourceId.

    Le contenu est absent de la page consommatrice (content: []) : la source est
    designee par IDENTIFIANT, donc resolvable par un GET /pages/{id} direct, sans
    pages_inventory.json et sans sensibilite au renommage.
    """
    rid = ((node.get("attrs") or {}).get("resourceId")) or ""
    trouve = RE_SYNC_RESOURCE.match(rid)
    if not trouve:
        raise ResolutionError(f"resourceId d'inclusion syncBlock non reconnu : {rid!r}")
    return trouve.group("page_id"), trouve.group("uuid").lower()


def sync_definition_key(node, page_id_hote):
    """Cle d'une definition syncBlock : (identifiant de la page hote, uuid).

    L'UUID SEUL NE SUFFIT PAS. Le corpus porte le meme resourceId defini sur deux pages
    differentes — CU-NOTE-CREER (28344321) et CU-NOTE-TYPENOTE.CREER (396361729), copie
    de la premiere — avec des contenus qui ont depuis diverge.
    """
    rid = ((node.get("attrs") or {}).get("resourceId")) or ""
    trouve = RE_SYNC_UUID.match(rid)
    if not trouve:
        raise ResolutionError(f"resourceId de definition syncBlock non reconnu : {rid!r}")
    return str(page_id_hote), trouve.group("uuid").lower()


# ==========================================================================
# Index des definitions — UN PAR FAMILLE, jamais croises
# ==========================================================================

def emplacement(node, page_id=None, page_title=None):
    """Localisation lisible d'un noeud, pour les messages d'erreur."""
    local = (node.get("attrs") or {}).get("localId")
    ou = page_id or page_title or "?"
    return f"page {ou}" + (f", localId {local}" if local else "")


class IndexDefinitions:
    """Definitions indexees par (page, nom), SEPAREMENT par famille.

    Confluence ne croise pas les familles : une inclusion `excerpt-include` ne voit pas
    une definition multiexcerpt de meme nom, et reciproquement. Croiser les deux
    produirait un `.md` plus complet que la page reelle, et masquerait un affichage
    casse au lieu de le signaler.
    """

    def __init__(self):
        self._par_famille = {famille: {} for famille in FAMILLES}
        self._ambigues = {famille: {} for famille in FAMILLES}   # cle -> emplacements

    def ajoute(self, node, page_title, page_id=None):
        """Indexe une definition. Une cle deja presente DANS LA MEME FAMILLE devient ambigue.

        Contrat §1.8 : un nom defini deux fois est traite comme une definition absente. Le
        pipeline ne choisit pas entre les deux corps, et l'ambiguite n'echoue qu'au point
        d'usage : les autres definitions de la page restent indexees. Lever ici arretait
        l'indexation de la page source au milieu, et toutes les definitions suivantes
        passaient pour absentes (SF-COMPTE, deux extraits natifs sans nom).
        """
        nature = classify_reuse_node(node)
        if nature not in (f"{f}_definition" for f in FAMILLES):
            raise ResolutionError(f"ce noeud n'est pas une definition de macro : {nature}")
        famille = famille_macro(node)
        cle = macro_definition_key(node, page_title)
        ou = emplacement(node, page_id, page_title)
        if cle in self._ambigues[famille]:
            self._ambigues[famille][cle].append(ou)
            return cle
        deja = self._par_famille[famille].pop(cle, None)
        if deja is not None:
            self._ambigues[famille][cle] = [deja["emplacement"], ou]
            return cle
        self._par_famille[famille][cle] = {"node": node, "emplacement": ou,
                                           "page_title": page_title, "page_id": page_id}
        return cle

    def cherche(self, famille, cle):
        """Definition d'une famille donnee, ou None. Ne regarde jamais l'autre famille."""
        if famille not in self._par_famille:
            raise ResolutionError(f"famille inconnue : {famille!r}")
        return self._par_famille[famille].get(cle)

    def resout(self, node, page_title_hote):
        """Definition visee par une inclusion, ou None si absente.

        La recherche est confinee a la famille de l'inclusion.
        """
        nature = classify_reuse_node(node)
        if nature not in (f"{f}_include" for f in FAMILLES):
            raise ResolutionError(f"ce noeud n'est pas une inclusion de macro : {nature}")
        famille = famille_macro(node)
        return self.cherche(famille, macro_include_key(node, page_title_hote))

    def ambigue(self, node, page_title_hote):
        """Emplacements des definitions homonymes visees par une inclusion, ou None."""
        famille = famille_macro(node)
        return self._ambigues[famille].get(macro_include_key(node, page_title_hote))

    def cles(self, famille):
        return set(self._par_famille[famille])

    def __len__(self):
        return sum(len(v) for v in self._par_famille.values())


# ==========================================================================
# nested-table : contenu integralement recuperable
# ==========================================================================

def is_nested_table(node):
    """Marqueur nested-table pose par Confluence. Detection par extensionKey UNIQUEMENT.

    Le champ `reason` est localise — anglais et francais tous deux presents dans le
    corpus — et ne doit jamais servir de test.
    """
    if not isinstance(node, dict) or node.get("type") not in EXTENSION_NODE_TYPES:
        return False
    return ((node.get("attrs") or {}).get("extensionKey") or "") == NESTED_TABLE_KEY


def nested_table_content(node):
    """Noeuds ADF de la table imbriquee, extraits de parameters.adf.

    `adf` est une CHAINE JSON contenant un document ADF complet : second json.loads().
    Le contenu est integralement recuperable, donc ce cas n'est PAS un echec de
    conversion et ne declasse pas la page en parse_status: partial.

    `cxhtml` coexiste avec `adf` dans les 11 occurrences du corpus : on utilise `adf`.

    Leve si `adf` manque ou est illisible : SEUL cas nested-table justifiant un
    parse_status: partial. Aucune occurrence a ce jour.
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

    Les cles des trois mecanismes cohabitent dans la meme pile, prefixees par leur
    mecanisme pour qu'un (page_id, uuid) ne collisionne pas avec un (page, nom) — et
    pour qu'une cle multiexcerpt ne collisionne pas avec la meme cle excerpt.

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
