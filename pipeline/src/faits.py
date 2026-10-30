#!/usr/bin/env python3
"""
Collecteur de faits — ADF brut d'une page -> faits de la page (contracts/faits.md).

VERSION : 1.3 — statut d'une inclusion sans localId : jointure de repli par (mecanisme, cle) quand
                toutes les inclusions de meme cle de la page ont le meme statut
          1.2 — type d'agregat des entites MCD (agregat), libelle « Description » retire
                de la description (TEMPLATE_MCD du 2026-10-23)
          1.1 — description des entites MCD, whitelist de tri des SA (tri), tableaux du corps des RG
          1.0 — premiere version, schema 2 du contrat de faits

Le collecteur releve ce qui est ECRIT, avec son emplacement. Il ne rend aucun verdict :
la conformite est l'affaire du catalogue de controles (depot sinapse-skills). Changer
un seuil ne doit jamais toucher au pipeline.

Trois entrees, aucune ne joint le reseau :
  - l'ADF BRUT de la page, pas l'ADF resolu : le brut garde les noms d'extraits tels
    qu'ecrits (K55 en a besoin) et montre les inclusions comme des references ;
  - les faits du resolver (resolver.py), joints par (page_id, local_id), qui donnent le
    statut de chaque inclusion ;
  - les metadonnees de la page (inventaire) : type, module, quartier, parent.

La STRUCTURE des pages (titres de section, en-tetes de colonnes, synonymes) vient de
pipeline/config/faits_types.json, pas du code : les vraies pages ne suivent pas toutes
le template, et SA, ASYNC et JOB bougent encore. Ce que la configuration ne reconnait
pas part dans `inconnus` — rien ne disparait en silence.
"""

import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import multiexcerpt as mx
from inventory import TIRETS_UNICODE
from renderer import cible_de_lien

VERSION = "1.3"
SCHEMA_VERSION = 2
CONFIG_DEFAUT = Path(__file__).resolve().parent.parent / "config" / "faits_types.json"
BASE_URL = "https://sinapse-gie-nc.atlassian.net"


# ==========================================================================
# BLOC DE CONSTANTES
# ==========================================================================

# Conteneurs de bloc : leur contenu est du texte de la page, sans role structurel.
CONTENEURS = frozenset({
    "paragraph", "heading", "bulletList", "orderedList", "listItem", "blockquote",
    "panel", "expand", "nestedExpand", "codeBlock", "layoutSection", "layoutColumn",
    "taskList", "taskItem", "decisionList", "decisionItem", "mediaSingle", "mediaGroup",
    "table", "tableRow", "tableCell", "tableHeader", "bodiedSyncBlock", "caption",
    "bodiedExtension",
})
# Feuilles de texte de l'index `textes` : une entree par bloc de ce type, hors tableau.
FEUILLES = frozenset({"paragraph", "heading", "codeBlock"})
TYPES_MEDIA = frozenset({"media", "mediaSingle", "mediaGroup", "mediaInline"})

RE_NUMERO = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+")
RE_LINKED_ISSUES = re.compile(r"linkedIssues\(\s*\"?([A-Z][A-Z0-9_]*-\d+)", re.I)
RE_BROWSE = re.compile(r"/browse/([A-Z][A-Z0-9_]*-\d+)")
RE_ROUTE_DECOMPOSEE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)")
# Relations du MCD, reprises de confluence-mcd-sync (legacy/skills, parse_mcd_page.py).
RE_JETON_RELATION = re.compile(
    r"\(([^)]+)\)|(<->|↔︎?|⇔︎?)|([A-Za-z][A-Za-z0-9_.]*)")
RE_NOM_RELATION = re.compile(r",\s*lien\s*[«\"']([^»\"']+)[»\"']", re.I)
CARDINALITES = {
    "0,N": "0..N", "1,N": "1..N", "0,1": "0..1", "1,1": "1..1",
    "0..N": "0..N", "1..N": "1..N", "0..1": "0..1", "1..1": "1..1",
    "N": "0..N", "1": "1..1",
}


# ==========================================================================
# Normalisation
# ==========================================================================

def normalise_nom(valeur):
    """Nom normalise une seule fois, ici : entites decodees, strip, tirets replies."""
    return html.unescape(str(valeur or "")).translate(TIRETS_UNICODE).strip()


def reduit(valeur):
    """Forme reduite pour comparer un titre ou un en-tete a la configuration.

    Minuscules, sans accents, apostrophes et tirets unifies, ponctuation et espaces
    normalises. Deux ecritures d'un meme titre ont la meme forme reduite.
    """
    texte = normalise_nom(valeur).replace("’", "'").lower()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"[^a-z0-9'*&<>/]+", " ", texte)
    return " ".join(texte.split())


def sans_numero(titre):
    """(numero, titre sans sa numerotation de tete). « 3.2 Codes retours » -> (3.2, …)."""
    trouve = RE_NUMERO.match(titre or "")
    if trouve:
        return trouve.group(1), titre[trouve.end():]
    return None, titre or ""


def correspond(valeur, synonymes):
    """La valeur est-elle l'un des synonymes ? Un synonyme termine par * est un prefixe."""
    cible = reduit(valeur)
    if not cible:
        return False
    for synonyme in synonymes:
        if synonyme.endswith("*"):
            if cible.startswith(reduit(synonyme[:-1])):
                return True
        elif cible == reduit(synonyme):
            return True
    return False


def charge_config(chemin=None):
    with open(chemin or CONFIG_DEFAUT, encoding="utf-8") as fichier:
        config = json.load(fichier)
    config["_citations"] = [(type_, re.compile(motif))
                            for type_, motif in config["citations"].items()]
    return config


# ==========================================================================
# Texte : la forme de toute valeur redigee (contrat §3.1)
# ==========================================================================

class _Accumulateur:
    """Morceaux de texte d'une valeur, avec leur forme, leur barre et leur couleur."""

    def __init__(self):
        self.morceaux = []        # (chaine, forme, barre, couleur)
        self.liens = []
        self.inclusions = []
        self.media = False
        self._href = None         # lien en cours : deux text consecutifs, un seul Lien

    def ajoute(self, chaine, forme="prose", barre=False, couleur=None):
        self.morceaux.append((chaine, forme, barre, couleur))

    def coupe(self, separateur="\n"):
        self._href = None
        if self.morceaux and self.morceaux[-1][0] != separateur:
            self.ajoute(separateur)


class Lecteur:
    """Lit les valeurs redigees d'une page : texte, liens, inclusions, citations."""

    def __init__(self, config, page_id, page_titre, titres_par_id=None, faits_resolver=None):
        self.config = config
        self.page_id = str(page_id)
        self.page_titre = page_titre
        self.titres_par_id = titres_par_id or {}
        self.statuts = {}
        # Repli pour un noeud sans localId (macros anciennes) : (mecanisme, cle) -> faits.
        self.statuts_par_cle = {}
        for fait in faits_resolver or []:
            if str(fait.get("page_id", self.page_id)) != self.page_id:
                continue
            if fait.get("local_id"):
                self.statuts[fait["local_id"]] = fait
            elif fait.get("cle") is not None:
                self.statuts_par_cle.setdefault((fait["mecanisme"], tuple(fait["cle"])), []).append(fait)

    # ------------------------------------------------------------------

    def texte(self, noeuds):
        """Texte d'un noeud ou d'une liste de noeuds, a plat."""
        acc = _Accumulateur()
        for noeud in (noeuds if isinstance(noeuds, list) else [noeuds]):
            self._visite(noeud, acc)
        return self._termine(acc)

    def _visite(self, node, acc):
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        attrs = node.get("attrs") or {}

        if ntype == "text":
            self._texte_simple(node, acc)
            return
        if ntype == "hardBreak":
            acc.coupe()
            return
        if ntype == "inlineCard":
            self._carte(attrs.get("url"), "carte", acc)
            return
        if ntype == "blockCard":
            if attrs.get("url"):
                self._carte(attrs["url"], "bloc", acc)
            return
        if ntype in ("mention", "status", "placeholder"):
            acc.ajoute(attrs.get("text") or "")
            return
        if ntype == "emoji":
            acc.ajoute(attrs.get("text") or attrs.get("shortName") or "")
            return
        if ntype == "date":
            acc.ajoute(_date_lisible(attrs.get("timestamp")))
            return
        if ntype in TYPES_MEDIA:
            acc.media = True
            return
        if mx.is_nested_table(node):
            for enfant in mx.nested_table_content(node):
                self._visite(enfant, acc)
            return

        nature = mx.classify_reuse_node(node)
        if nature and nature.endswith("_include"):
            inclusion = self.inclusion(node)
            acc.inclusions.append(inclusion)
            acc._href = None
            acc.ajoute("{inclusion:" + inclusion["nom"] + "}", "inclusion")
            return
        if ntype in mx.EXTENSION_NODE_TYPES and nature is None:
            # Macro sans contenu redige (toc, jira…) : ses parametres vont a l'index
            # de la page, pas dans le texte de la valeur qui la porte.
            for enfant in (node.get("content") or []):
                self._visite(enfant, acc)
            return

        for enfant in (node.get("content") or []):
            self._visite(enfant, acc)
        if ntype in CONTENEURS:
            acc.coupe()

    def _texte_simple(self, node, acc):
        chaine = node.get("text") or ""
        marks = {m.get("type"): (m.get("attrs") or {}) for m in (node.get("marks") or [])}
        barre = "strike" in marks
        couleur = (marks.get("textColor") or {}).get("color")
        href = (marks.get("link") or {}).get("href")
        if href:
            forme = "lien"
        elif "code" in marks:
            forme = "code"
        elif "strong" in marks:
            forme = "gras"
        else:
            forme = "prose"
        if href:
            if acc._href == href and acc.liens:
                acc.liens[-1]["texte"] += chaine
            else:
                acc.liens.append(self.lien(href, chaine, "lien"))
            acc._href = href
        else:
            acc._href = None
        acc.ajoute(chaine, forme, barre, couleur)

    def _carte(self, url, forme, acc):
        lien = self.lien(url, None, forme)
        acc.liens.append(lien)
        acc._href = None
        acc.ajoute(lien["texte"], "lien")

    # ------------------------------------------------------------------

    def lien(self, url, texte, forme):
        """Lien (contrat §3.2). Le texte d'une carte est le titre de sa cible, connu ou non."""
        url = str(url or "")
        lien = {"texte": texte, "url": url, "forme": forme}
        ticket = RE_BROWSE.search(url)
        page_id, edition = cible_de_lien(url)
        if ticket:
            lien["cible"] = {"type": "jira", "ticket": ticket.group(1)}
        elif "/wiki/" in url and (page_id or "atlassian.net" in url):
            cible = {"type": "page"}
            if page_id:
                cible["page_id"] = page_id
                titre = self.titres_par_id.get(page_id)
                if titre:
                    cible["titre"] = titre
            lien["cible"] = cible
        else:
            lien["cible"] = {"type": "externe"}
        if "resumedraft.action" in url or "draftId=" in url:
            lien["etat"] = "brouillon"
        elif edition or "/edit-v2/" in url:
            lien["etat"] = "edition"
        if texte is None:
            lien["texte"] = lien["cible"].get("titre") or lien["cible"].get("ticket") or url
        return lien

    def inclusion(self, node):
        """Inclusion (contrat §3.3)."""
        attrs = node.get("attrs") or {}
        nature = mx.classify_reuse_node(node)
        if nature == "sync_include":
            source_id, uuid = mx.sync_include_key(node)
            inclusion = {"mecanisme": "sync", "nom_brut": uuid, "nom": uuid,
                         "page_source": self.titres_par_id.get(source_id, f"page {source_id}"),
                         "forme": "bloc"}
        else:
            famille = mx.famille_macro(node)
            brut = html.unescape(str(mx.macro_param(node, "name") or ""))
            cible, _ = mx.macro_page_source(node, self.page_titre)
            inclusion = {"mecanisme": famille, "nom_brut": brut, "nom": normalise_nom(brut),
                         "page_source": cible,
                         "forme": "inline" if mx.est_inclusion_inline(node) else "bloc"}
        local_id = attrs.get("localId")
        fait = self.statuts.get(local_id) if local_id else self._statut_par_cle(node, nature)
        if fait:
            inclusion["statut"] = fait["statut"]
            # Page source hors du corpus exporte : pas une anomalie (decision du
            # 2026-10-21), K56 ne la signale pas.
            if fait.get("source_hors_perimetre"):
                inclusion["hors_corpus"] = True
        if local_id:
            inclusion["local_id"] = local_id
        return inclusion

    def _statut_par_cle(self, node, nature):
        """Fait du resolver d'une inclusion sans localId, retrouve par sa cle.

        Seulement si toutes les inclusions de meme cle sur la page ont le meme statut :
        sinon on ne sait pas laquelle est laquelle, et le statut reste absent.
        """
        if nature == "sync_include":
            return None
        try:
            cle = mx.macro_include_key(node, self.page_titre)
        except mx.ResolutionError:
            return None
        faits = self.statuts_par_cle.get((mx.famille_macro(node), tuple(cle)), [])
        if faits and len({f["statut"] for f in faits}) == 1:
            return faits[0]
        return None

    # ------------------------------------------------------------------

    def _termine(self, acc):
        brut = "".join(m[0] for m in acc.morceaux)
        lignes = (" ".join(ligne.split()) for ligne in brut.split("\n"))
        texte = {"texte": "\n".join(ligne for ligne in lignes if ligne)}
        if acc.liens:
            for lien in acc.liens:
                lien["texte"] = " ".join(str(lien["texte"] or "").split())
            texte["liens"] = acc.liens
        if acc.inclusions:
            texte["inclusions"] = acc.inclusions
        citations = self._citations(acc.morceaux)
        if citations:
            texte["citations"] = citations
        pleins = [m for m in acc.morceaux if m[0].strip()]
        if pleins and all(m[2] for m in pleins):
            texte["barre"] = True
        couleurs = {m[3] for m in pleins}
        if len(couleurs) == 1 and None not in couleurs:
            texte["couleur"] = couleurs.pop()
        if acc.media:
            texte["_media"] = True
        return texte

    def _citations(self, morceaux):
        """Codes reconnus par motif (configuration), avec la forme du premier caractere."""
        brut, formes, debut = "", [], 0
        for chaine, forme, _, _ in morceaux:
            brut += chaine
            formes.append((debut, debut + len(chaine), forme))
            debut += len(chaine)
        replie = brut.translate(TIRETS_UNICODE)   # meme longueur : un caractere par tiret
        vues, citations = set(), []
        for type_, motif in self.config["_citations"]:
            for trouve in motif.finditer(replie):
                code = trouve.group(0).rstrip(".:")
                forme = next((f for d, fin, f in formes if d <= trouve.start() < fin), "prose")
                cle = (type_, code, forme)
                if cle not in vues:
                    vues.add(cle)
                    citations.append({"type": type_, "code": code, "forme": forme})
        return citations


def _date_lisible(horodatage):
    try:
        secondes = int(horodatage) / 1000
    except (TypeError, ValueError):
        return str(horodatage or "")
    return datetime.fromtimestamp(secondes, tz=timezone.utc).strftime("%Y-%m-%d")


def nettoie(texte):
    """Retire les marques internes d'un Texte avant ecriture."""
    texte.pop("_media", None)
    return texte


def est_vide(texte):
    return not texte.get("texte") and not texte.get("liens") and not texte.get("inclusions")


def sans_null(valeur):
    """Retire toute cle de valeur None : une information inconnue est une cle absente."""
    if isinstance(valeur, dict):
        return {k: sans_null(v) for k, v in valeur.items() if v is not None}
    if isinstance(valeur, list):
        return [sans_null(v) for v in valeur]
    return valeur


# ==========================================================================
# Structure de la page
# ==========================================================================

def _parcours(noeud):
    """Tous les noeuds d'un sous-arbre, dans l'ordre du document, tables imbriquees ouvertes."""
    if isinstance(noeud, list):
        for enfant in noeud:
            yield from _parcours(enfant)
        return
    if not isinstance(noeud, dict):
        return
    yield noeud
    if mx.is_nested_table(noeud):
        yield from _parcours(mx.nested_table_content(noeud))
        return
    yield from _parcours(noeud.get("content") or [])


def _titre_de(noeud):
    return " ".join("".join(n.get("text", "") for n in _parcours(noeud)
                            if n.get("type") == "text").split())


def _contient_libelle(noeud, config):
    texte = reduit(_titre_de(noeud))
    return any(reduit(libelle) in texte
               for libelles in config["cartouche"]["libelles"].values()
               for libelle in libelles)


class Page:
    """Decoupage d'une page en blocs, chacun rattache aux titres qui l'englobent."""

    def __init__(self, adf, config, regles_type):
        self.config = config
        self.regles = regles_type
        self.titres = []              # {niveau, titre, numero?, canonique?}
        self.blocs = []               # (noeud, chemin = indices des titres englobants)
        self.cartouche = None
        self.evolutions = None        # noeud table
        self.jql = None
        self._pile = []
        for noeud in (adf.get("content") or []):
            self._range(noeud, avant_titre=not self.titres)

    def _range(self, noeud, avant_titre):
        ntype = noeud.get("type")
        if ntype == "heading":
            self._titre(noeud)
            return
        if avant_titre and self.cartouche is None and ntype in ("layoutSection", "panel", "table") \
                and _contient_libelle(noeud, self.config):
            self.cartouche = noeud
            return
        if ntype == "blockCard" and self.jql is None:
            source = (noeud.get("attrs") or {}).get("datasource") or {}
            jql = (source.get("parameters") or {}).get("jql")
            if jql:
                self.jql = jql
                return
        if ntype == "expand" and correspond((noeud.get("attrs") or {}).get("title"),
                                            self.config["evolutions"]["titres"]):
            self.evolutions = next((n for n in _parcours(noeud) if n.get("type") == "table"),
                                   None)
            return
        if ntype in ("layoutSection", "layoutColumn", "expand", "nestedExpand"):
            for enfant in (noeud.get("content") or []):
                self._range(enfant, avant_titre and not self.titres)
            return
        self.blocs.append((noeud, tuple(self._pile)))

    def _titre(self, noeud):
        niveau = (noeud.get("attrs") or {}).get("level") or 1
        titre = _titre_de(noeud)
        numero, nu = sans_numero(normalise_nom(titre))
        entree = {"niveau": niveau, "titre": titre}
        if numero:
            entree["numero"] = numero
        for canon, section in self.regles.get("sections", {}).items():
            if correspond(nu, section.get("titres", [])):
                entree["canonique"] = canon
                break
        if self.evolutions is None and correspond(nu, self.config["evolutions"]["titres"]):
            entree["canonique"] = "evolutions"
        entree["_noeud"] = noeud
        while self._pile and self.titres[self._pile[-1]]["niveau"] >= niveau:
            self._pile.pop()
        self.titres.append(entree)
        self._pile.append(len(self.titres) - 1)

    # ------------------------------------------------------------------

    def section(self, canon):
        """Indice du premier titre de cette section canonique, ou None."""
        return next((i for i, t in enumerate(self.titres) if t.get("canonique") == canon), None)

    def appartient(self, chemin, indice):
        """Le bloc est-il dans la section `indice`, hors d'une sous-section reconnue ?

        Une sous-section canonique a ses propres faits : « Règles » rangé en titre de
        niveau 2 sous « IHM » ne doit pas donner un tableau IHM de plus.
        """
        if indice not in chemin:
            return False
        return not any(self.titres[j].get("canonique")
                       for j in chemin[chemin.index(indice) + 1:])

    def blocs_de(self, indice):
        return [noeud for noeud, chemin in self.blocs if self.appartient(chemin, indice)]

    def titre_le_plus_proche(self, chemin):
        return self.titres[chemin[-1]]["titre"] if chemin else None


def _tables(noeuds):
    """Tables d'une liste de blocs, sans descendre dans une table deja trouvee."""
    for noeud in noeuds:
        if not isinstance(noeud, dict):
            continue
        if noeud.get("type") == "table":
            yield noeud
        elif mx.is_nested_table(noeud):
            yield from _tables(mx.nested_table_content(noeud))
        else:
            yield from _tables(noeud.get("content") or [])


def _lignes_brutes(table):
    return [ligne for ligne in (table.get("content") or []) if ligne.get("type") == "tableRow"]


def _cellules(ligne):
    return [c for c in (ligne.get("content") or [])
            if c.get("type") in ("tableCell", "tableHeader")]


# ==========================================================================
# Collecteur
# ==========================================================================

class Collecteur:
    def __init__(self, config=None, titres_par_id=None):
        self.config = config or charge_config()
        self.titres_par_id = titres_par_id or {}

    def collecte(self, adf, meta, faits_resolver=None, maintenant=None):
        """Faits d'une page. `meta` : id, titre, type, et si connus module, quartier,
        parent_id, url, confluence_version, version_date, exporte_le."""
        type_page = self.config.get("alias_types", {}).get(meta.get("type"), meta.get("type"))
        regles = self.config["types"].get(type_page, {"sections": {}, "attendues": []})
        titre_brut = meta.get("titre") or ""
        titre = normalise_nom(titre_brut)
        self.lecteur = Lecteur(self.config, meta["id"], titre_brut, self.titres_par_id,
                               faits_resolver)
        self.page = Page(adf, self.config, regles)
        self.regles = regles
        self.inconnus = []

        faits = {
            "schema_version": SCHEMA_VERSION,
            "collecteur_version": VERSION,
            "config_version": self.config.get("version"),
            "genere_le": maintenant or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "page": self._page(meta, type_page, titre, titre_brut),
        }
        if self.page.cartouche is not None:
            faits["cartouche"] = self._cartouche(self.page.cartouche)
        if self.page.jql:
            jira = {"jql": self.page.jql}
            ticket = RE_LINKED_ISSUES.search(self.page.jql)
            if ticket:
                jira["ticket_test"] = ticket.group(1)
            faits["jira"] = jira
        evolutions = self._evolutions()
        if evolutions is not None:
            faits["evolutions"] = evolutions
        faits["sections"] = [{k: v for k, v in t.items() if not k.startswith("_")}
                             for t in self.page.titres]

        par_type = {"CU": self._cu, "API": self._api, "SA": self._sa, "MCD": self._mcd}
        if type_page in par_type:
            faits.update(par_type[type_page]())
        if regles.get("regles_par_definition"):
            faits["regles"] = self._regles_definitions()

        faits.update(self._index())
        self._sections_manquantes()
        faits["inconnus"] = self.inconnus
        faits["page"]["parse_status"] = "partial" if self.inconnus else "ok"
        return sans_null(faits)

    # ------------------------------------------------------------------
    # Socle (contrat §4)
    # ------------------------------------------------------------------

    def _page(self, meta, type_page, titre, titre_brut):
        page = {"id": str(meta["id"]), "titre": titre}
        if titre_brut != titre:
            page["titre_brut"] = titre_brut
        page["type"] = type_page
        for cle in ("module", "quartier", "parent_id", "url", "confluence_version",
                    "version_date", "exporte_le"):
            if meta.get(cle) not in (None, ""):
                page[cle] = meta[cle]
        if "url" not in page:
            page["url"] = f"{BASE_URL}/wiki/spaces/SINAPSE/pages/{meta['id']}"
        return page

    def _cartouche(self, noeud):
        """Libelle : valeur, dans les paragraphes ou les cellules du cartouche (§4.2)."""
        libelles = self.config["cartouche"]["libelles"]
        tous = sorted(((cle, l) for cle, ls in libelles.items() for l in ls),
                      key=lambda x: -len(x[1]))
        motif = re.compile("|".join(f"(?P<l{i}>{re.escape(l)})\\s*:?" for i, (_, l)
                                    in enumerate(tous)), re.I)
        morceaux = []          # (cle ou None, chaine, Texte source)
        for bloc in _parcours(noeud):
            if bloc.get("type") not in ("paragraph", "heading"):
                continue
            texte = self.lecteur.texte(bloc)
            chaine = texte["texte"]
            positions = list(motif.finditer(chaine))
            if not positions:
                morceaux.append((None, chaine, texte))
                continue
            if positions[0].start() > 0:
                morceaux.append((None, chaine[:positions[0].start()], texte))
            for i, trouve in enumerate(positions):
                fin = positions[i + 1].start() if i + 1 < len(positions) else len(chaine)
                cle = tous[int(next(k for k, v in trouve.groupdict().items() if v)[1:])][0]
                morceaux.append((cle, chaine[trouve.end():fin], texte))

        cartouche = {}
        for i, (cle, valeur, source) in enumerate(morceaux):
            if cle is None or cle in cartouche:
                continue
            if cle == "lien_test":
                lien = next((l for l in source.get("liens", [])), None)
                if lien:
                    cartouche[cle] = lien
                continue
            if not valeur.strip() and i + 1 < len(morceaux) and morceaux[i + 1][0] is None:
                valeur, source = morceaux[i + 1][1], morceaux[i + 1][2]
            cartouche[cle] = self._sous_texte(valeur, source)
        return cartouche

    @staticmethod
    def _sous_texte(chaine, source):
        """Texte restreint a une partie de la chaine de sa source."""
        chaine = " ".join(chaine.split())
        texte = {"texte": chaine}
        for cle, champ in (("liens", "texte"), ("citations", "code")):
            garde = [x for x in source.get(cle, []) if x[champ] and x[champ] in chaine]
            if garde:
                texte[cle] = garde
        inclusions = [x for x in source.get("inclusions", []) if x["nom"] in chaine]
        if inclusions:
            texte["inclusions"] = inclusions
        for cle in ("barre", "couleur"):
            if cle in source:
                texte[cle] = source[cle]
        return texte

    def _evolutions(self):
        table = self.page.evolutions
        section = "evolutions"
        if table is None:
            indice = self.page.section("evolutions")
            if indice is None:
                return None
            section = self.page.titres[indice]["titre"]
            table = next(_tables(self.page.blocs_de(indice)), None)
            if table is None:
                return []
        colonnes = self.config["evolutions"]["colonnes"]
        lignes = self._lignes(table, colonnes, section, 1, signale=True)
        evolutions = []
        for ligne in lignes:
            cellules = ligne["cellules"]
            evolution = {"ou": ligne["ou"]}
            for cle in ("version", "date"):
                if cle in cellules:
                    evolution[cle] = cellules[cle]["texte"]
            if "description" in cellules:
                evolution["description"] = cellules["description"]
            ref = cellules.get("ref_jira", {})
            tickets = [c["code"] for c in ref.get("citations", []) if c["type"] == "TICKET"]
            tickets += [l["cible"]["ticket"] for l in ref.get("liens", [])
                        if l["cible"].get("type") == "jira"]
            evolution["tickets"] = list(dict.fromkeys(tickets))
            if ligne.get("barre"):
                evolution["barre"] = True
            evolutions.append(evolution)
        return evolutions

    # ------------------------------------------------------------------
    # Tableaux
    # ------------------------------------------------------------------

    def _carte_colonnes(self, entetes, tableau_cfg):
        """Rang de colonne -> nom canonique, ou None si l'en-tete n'est pas reconnu."""
        colonnes = tableau_cfg.get("colonnes", {})
        par_rang = {int(k): v for k, v in tableau_cfg.get("colonne_par_rang", {}).items()}
        carte = []
        for rang, entete in enumerate(entetes, start=1):
            if rang in par_rang:
                carte.append(par_rang[rang])
                continue
            carte.append(next((canon for canon, synonymes in colonnes.items()
                               if correspond(entete, synonymes)), None))
        return carte

    def _lignes(self, table, colonnes_ou_cfg, section, rang_tableau, signale=True):
        """Lignes d'un tableau (contrat §3.6). En-tete = premiere ligne."""
        cfg = (colonnes_ou_cfg if "colonnes" in colonnes_ou_cfg
               else {"colonnes": colonnes_ou_cfg})
        brutes = _lignes_brutes(table)
        if not brutes:
            return []
        entetes = [self.lecteur.texte(c)["texte"] for c in _cellules(brutes[0])]
        carte = self._carte_colonnes(entetes, cfg)
        ou_table = {"section": section, "tableau": rang_tableau}
        if signale:
            for entete, canon in zip(entetes, carte):
                if canon is None:
                    self.inconnus.append({"ou": dict(ou_table), "quoi": "colonne",
                                          "valeur": entete})
        lignes, groupe = [], None
        for numero, brute in enumerate(brutes[1:], start=1):
            # Ligne de regroupement : une seule cellule sur toute la largeur (« Tri et
            # pagination », « Authentification », un sous-objet « listeHabilitations[] »).
            # Elle n'est pas une ligne de donnees : elle qualifie les lignes qui suivent.
            seules = _cellules(brute)
            if len(entetes) > 1 and len(seules) == 1 \
                    and ((seules[0].get("attrs") or {}).get("colspan") or 1) >= len(entetes):
                groupe = self.lecteur.texte(seules[0])["texte"] or None
                continue
            ligne = {"ou": dict(ou_table, ligne=numero), "cellules": {}}
            if groupe:
                ligne["groupe"] = groupe
            autres = {}
            for rang, cellule in enumerate(_cellules(brute)):
                texte = nettoie(self.lecteur.texte(cellule))
                canon = carte[rang] if rang < len(carte) else None
                if canon is None:
                    entete = entetes[rang] if rang < len(entetes) else f"colonne {rang + 1}"
                    autres[entete] = texte
                elif canon not in ligne["cellules"]:
                    ligne["cellules"][canon] = texte
            if autres:
                ligne["autres"] = autres
            valeurs = list(ligne["cellules"].values()) + list(autres.values())
            if all(est_vide(v) for v in valeurs):
                continue
            pleines = [v for v in valeurs if not est_vide(v)]
            if pleines and all(v.get("barre") for v in pleines):
                ligne["barre"] = True
            lignes.append(ligne)
        return lignes

    def _tableaux_section(self, canon):
        """[(titre de rattachement, rang, table)] des tableaux d'une section canonique."""
        indice = self.page.section(canon)
        if indice is None:
            return None
        resultat, rang = [], 0
        for noeud, chemin in self.page.blocs:
            if not self.page.appartient(chemin, indice):
                continue
            for table in _tables([noeud]):
                rang += 1
                resultat.append((self.page.titre_le_plus_proche(chemin), rang, table))
        return resultat

    def _lignes_section(self, canon):
        """Lignes de tous les tableaux reconnus d'une section ; None si section absente."""
        tableaux = self._tableaux_section(canon)
        if tableaux is None:
            return None
        cfg = self.regles["sections"][canon].get("tableau", {})
        lignes = []
        for titre, rang, table in tableaux:
            if not self._reconnu(table, cfg, titre, rang, canon):
                continue
            lignes += self._lignes(table, cfg, titre, rang)
        return lignes

    def _reconnu(self, table, cfg, titre, rang, canon):
        """Un tableau dont aucun en-tete n'est reconnu n'est pas celui de la section."""
        brutes = _lignes_brutes(table)
        entetes = [self.lecteur.texte(c)["texte"] for c in _cellules(brutes[0])] if brutes else []
        if any(self._carte_colonnes(entetes, cfg)) and cfg:
            return True
        if not self.regles["sections"].get(canon, {}).get("tableaux_libres"):
            self.inconnus.append({"ou": {"section": titre, "tableau": rang}, "quoi": "tableau",
                                  "valeur": " | ".join(entetes)})
        return False

    def _texte_section(self, canon, sans_tableaux=False):
        indice = self.page.section(canon)
        if indice is None:
            return None
        blocs = self.page.blocs_de(indice)
        if sans_tableaux:
            blocs = [b for b in blocs if b.get("type") != "table"]
        return self.lecteur.texte(blocs)

    def _sections_manquantes(self):
        for canon in self.regles.get("attendues", []):
            if self.page.section(canon) is None:
                self.inconnus.append({"ou": {"section": canon}, "quoi": "section_manquante",
                                      "valeur": canon})
        for titre in self.page.titres:
            if titre["niveau"] == 1 and "canonique" not in titre and self.regles.get("sections"):
                self.inconnus.append({"ou": {"section": titre["titre"]}, "quoi": "section",
                                      "valeur": titre["titre"]})

    # ------------------------------------------------------------------
    # Par type (contrat §5)
    # ------------------------------------------------------------------

    def _cu(self):
        faits = {}
        texte = self._texte_section("description", sans_tableaux=True)
        if texte is not None:
            faits["description"] = nettoie(texte)
        for canon in ("nominal", "alternatif", "regles"):
            lignes = self._lignes_section(canon)
            if lignes is not None:
                faits[canon] = lignes
        texte = self._texte_section("processus")
        if texte is not None:
            processus = {"diagramme": bool(texte.get("_media"))}
            processus["texte"] = nettoie(texte)
            faits["processus"] = processus
        tableaux = self._tableaux_section("ihm")
        if tableaux is not None:
            cfg = self.regles["sections"]["ihm"]["tableau"]
            faits["ihm"] = [{"titre": titre, "lignes": self._lignes(table, cfg, titre, rang)}
                            for titre, rang, table in tableaux
                            if self._reconnu(table, cfg, titre, rang, "ihm")]
        return faits

    def _api(self):
        faits = {}
        routes = self._lignes_section("routes")
        if routes is not None:
            for ligne in routes:
                route = ligne["cellules"].get("route", {}).get("texte", "")
                trouve = RE_ROUTE_DECOMPOSEE.match(route.translate(TIRETS_UNICODE))
                if trouve:
                    ligne["verbe"], ligne["chemin"] = trouve.group(1), trouve.group(2)
            faits["routes"] = routes
        dtos = self._dtos()
        if dtos is not None:
            faits["dtos"] = dtos
        mappings = self._mappings()
        if mappings is not None:
            faits["mappings"] = mappings
        return faits

    def _dtos(self):
        """Catalogue §2 : les DTO sont les COLONNES des matrices, les attributs les lignes."""
        tableaux = self._tableaux_section("dtos")
        if tableaux is None:
            return None
        premiere = self.regles["sections"]["dtos"]["matrice"]["premiere_colonne"]
        dtos = []
        for titre, rang, table in tableaux:
            brutes = _lignes_brutes(table)
            if not brutes:
                continue
            entetes = [nettoie(self.lecteur.texte(c)) for c in _cellules(brutes[0])]
            if not entetes or not correspond(entetes[0]["texte"], premiere):
                self.inconnus.append({"ou": {"section": titre, "tableau": rang},
                                      "quoi": "tableau",
                                      "valeur": " | ".join(e["texte"] for e in entetes)})
                continue
            for colonne, entete in enumerate(entetes[1:], start=1):
                dto = {"nom": normalise_nom(entete["texte"]),
                       "ou": {"section": titre, "tableau": rang, "colonne": entete["texte"]},
                       "attributs": []}
                if entete["texte"] != dto["nom"]:
                    dto["nom_brut"] = entete["texte"]
                for numero, brute in enumerate(brutes[1:], start=1):
                    cellules = _cellules(brute)
                    if len(cellules) <= colonne:
                        continue
                    nom = nettoie(self.lecteur.texte(cellules[0]))
                    marqueur = nettoie(self.lecteur.texte(cellules[colonne]))
                    if not nom["texte"]:
                        continue
                    # « R - ActualiteReponse[] » : le marqueur est le premier mot, le
                    # reste precise le type. Les deux sont gardes.
                    valeur, _, precision = marqueur["texte"].partition(" - ")
                    attribut = {"nom": normalise_nom(nom["texte"]), "marqueur": valeur.strip(),
                                "ou": {"section": titre, "tableau": rang, "ligne": numero,
                                       "colonne": entete["texte"]}}
                    if precision.strip():
                        attribut["precision"] = precision.strip()
                    if nom.get("barre"):
                        attribut["barre"] = True
                    dto["attributs"].append(attribut)
                dtos.append(dto)
        return dtos

    def _mappings(self):
        tableaux = self._tableaux_section("mappings")
        if tableaux is None:
            return None
        cfg = self.regles["sections"]["mappings"]["tableau"]
        un_pour_un = cfg.get("valeurs_un_pour_un", [])
        mappings = []
        for titre, rang, table in tableaux:
            if not self._reconnu(table, cfg, titre, rang, "mappings"):
                continue
            brutes = _lignes_brutes(table)
            entetes = _cellules(brutes[0])
            mapping = {"sa": nettoie(self.lecteur.texte(entetes[1])) if len(entetes) > 1
                       else {"texte": ""},
                       "ou": {"section": titre, "tableau": rang}}
            lignes = self._lignes(table, cfg, titre, rang)
            mapping["un_pour_un"] = [
                normalise_nom(l["cellules"]["element"]["texte"]) for l in lignes
                if "element" in l["cellules"]
                and correspond(l["cellules"].get("contrat_sa", {}).get("texte", ""), un_pour_un)]
            mapping["lignes"] = lignes
            mappings.append(mapping)
        return mappings

    def _sa(self):
        faits = {}
        texte = self._texte_section("objet", sans_tableaux=True)
        if texte is None:
            texte = self._texte_section(self.regles.get("objet_repli", "but"), sans_tableaux=True)
        if texte is not None:
            faits["objet"] = nettoie(texte)
        scenarios = self._lignes_section("scenarios")
        if scenarios is None and self.page.section("but") is not None:
            cfg = self.regles["sections"]["scenarios"]["tableau"]
            scenarios = []
            for titre, rang, table in self._tableaux_section("but"):
                brutes = _lignes_brutes(table)
                entetes = [self.lecteur.texte(c)["texte"] for c in _cellules(brutes[0])]
                if any(self._carte_colonnes(entetes, cfg)):
                    scenarios += self._lignes(table, cfg, titre, rang)
            scenarios = scenarios or None
        if scenarios is not None:
            faits["scenarios"] = scenarios
        for canon in ("contrat_entree", "codes", "regles"):
            lignes = self._lignes_section(canon)
            if lignes is not None:
                faits[canon] = lignes
        texte = self._texte_section("objet_restitue")
        if texte is not None:
            faits["objet_restitue"] = nettoie(texte)
        traitement = self._traitement()
        if traitement is not None:
            faits["traitement"] = traitement
        tri = self._tri(faits)
        if tri:
            faits["tri"] = tri
        return faits

    def _tri(self, faits):
        """Whitelist de tri du SA de recherche, au §2 (ligne `sort`) et au §4 (TEMPLATE_SA, NB
        « Whitelist de tri ») ; une whitelist donnée par renvoi à une RG n'est pas relevée."""
        tri = {}
        for ligne in faits.get("contrat_entree", []):
            if ligne["cellules"].get("attribut", {}).get("texte") == "sort":
                valeurs = _whitelist(ligne["cellules"].get("description", {}).get("texte", ""))
                if valeurs:
                    tri["contrat"] = {"valeurs": valeurs, "ou": dict(ligne["ou"], colonne="description")}
                    break
        for ligne in faits.get("traitement", {}).get("texte", "").split("\n"):
            valeurs = _whitelist(ligne) if "sort" in ligne else None
            if valeurs:
                tri["traitement"] = {"valeurs": valeurs,
                                     "ou": {"section": self.page.titres[self.page.section("traitement")]["titre"]}}
                break
        return tri

    def _traitement(self):
        """Section 4 en entier, plus ses etapes : sous-titres et paragraphes tout en gras."""
        indice = self.page.section("traitement")
        if indice is None:
            return None
        blocs = [(n, c) for n, c in self.page.blocs if indice in c]
        traitement = nettoie(self.lecteur.texte([n for n, _ in blocs]))
        etapes, courante, sous_section = [], None, None
        for noeud, chemin in blocs:
            sous = chemin[-1] if chemin[-1] != indice else None
            if sous is not None and sous != sous_section:
                sous_section = sous
                courante = {"titre": self.page.titres[sous]["titre"], "_blocs": []}
                etapes.append(courante)
            if _tout_en_gras(noeud):
                courante = {"titre": _titre_de(noeud), "_blocs": []}
                etapes.append(courante)
                continue
            if courante is not None:
                courante["_blocs"].append(noeud)
        if etapes:
            traitement["etapes"] = [{"titre": e["titre"],
                                     "texte": nettoie(self.lecteur.texte(e["_blocs"]))}
                                    for e in etapes]
        return traitement

    def _mcd(self):
        faits = {}
        indice = self.page.section("modelisation")
        if indice is not None:
            faits["relations"] = self._relations(indice)
        tableaux = self._tableaux_section("inventaire")
        if tableaux is not None:
            faits["entites"] = self._entites(tableaux)
            proses = self._proses_entites()
            noms = [entite["nom"] for entite in faits["entites"]]
            for entite in faits["entites"]:
                agregat, description = self._agregat_et_description(
                    proses.get(entite["libelle"], []), entite, noms)
                if agregat:
                    entite["agregat"] = agregat
                if description and description["texte"]:
                    entite["description"] = description
        return faits

    def _proses_entites(self):
        """{titre: noeuds} : la prose (hors tableaux) placée sous le titre de chaque entité de
        l'inventaire, « Objet permettant de représenter une Note… » (TEMPLATE_MCD, Description)."""
        indice = self.page.section("inventaire")
        par_titre = {}
        for noeud, chemin in self.page.blocs:
            if not self.page.appartient(chemin, indice) or next(_tables([noeud]), None) is not None:
                continue
            par_titre.setdefault(self.page.titre_le_plus_proche(chemin), []).append(noeud)
        return par_titre

    def _agregat_et_description(self, noeuds, entite, noms):
        """(agregat, description) d'une entité, depuis sa prose.

        TEMPLATE_MCD du 2026-10-23 : le type d'agrégat se place entre « Propriétés de [Entite] »
        et « Description ». Sans paragraphe « Description », toute la prose est la description
        (ancien format) et aucun agrégat n'est relevé. Le type est reconnu par les synonymes de
        la configuration (`entite.agregat`) ; la racine d'une entité interne ou d'un objet valeur
        est une autre entité de la page citée dans le texte, clé absente sinon.
        """
        if not noeuds:
            return None, None
        cfg = self.regles.get("entite", {})
        libelles = [reduit(l) for l in cfg.get("description", [])]
        rang = next((i for i, noeud in enumerate(noeuds)
                     if any(reduit(self.lecteur.texte(noeud)["texte"]).startswith(l) for l in libelles)),
                    None)
        if rang is None:
            return None, nettoie(self.lecteur.texte(noeuds))
        description = nettoie(self.lecteur.texte(noeuds[rang:]))
        libelle = "|".join(re.escape(l) for l in cfg.get("description", []))
        description["texte"] = re.sub(rf"^\s*(?:{libelle})\s*:?\s*", "", description["texte"], count=1,
                                      flags=re.I)
        if rang == 0:
            return None, description
        texte = nettoie(self.lecteur.texte(noeuds[:rang]))
        if est_vide(texte):
            return None, description
        agregat = {"ou": {"section": entite["libelle"]}, "texte": texte}
        forme = reduit(texte["texte"])
        for type_agregat, synonymes in cfg.get("agregat", {}).items():
            if any(reduit(synonyme) in forme for synonyme in synonymes):
                agregat["type"] = type_agregat
                break
        if agregat.get("type") in ("entite_interne", "objet_valeur"):
            racine = _racine_citee(texte["texte"], entite["nom"], noms)
            if racine:
                agregat["racine"] = racine
        return agregat, description

    def _relations(self, indice):
        """Relations de la section Modelisation, une par paire d'entites (premiere vue).

        Le dedoublonnage est celui du legacy : une phrase d'explication qui cite
        « Recent ↔ Personne » apres la relation ne cree pas une seconde relation.
        """
        relations, vues = [], set()
        for noeud, chemin in self.page.blocs:
            if indice not in chemin:
                continue
            texte = self.lecteur.texte(noeud)
            ou = {"section": self.page.titre_le_plus_proche(chemin)}
            for ligne in texte["texte"].split("\n"):
                if "<->" in ligne or "↔" in ligne or "⇔" in ligne:
                    for relation in _relations_de_ligne(ligne):
                        cle = tuple(sorted((relation["de"], relation["vers"])))
                        if cle in vues:
                            continue
                        vues.add(cle)
                        relation["ou"] = ou
                        if texte.get("barre"):
                            relation["barre"] = True
                        relations.append(relation)
        return relations

    def _entites(self, tableaux):
        """Entites du MCD : entite = prefixe commun de « Nom du champ » (legacy mcd-sync)."""
        cfg = self.regles["sections"]["inventaire"]["tableau"]
        entites = {}
        for titre, rang, table in tableaux:
            if not self._reconnu(table, cfg, titre, rang, "inventaire"):
                continue
            lignes = self._lignes(table, cfg, titre, rang)
            noms = [l["cellules"].get("nom_champ", {}).get("texte", "") for l in lignes
                    if not l.get("barre")]
            prefixes = {n.rsplit(".", 1)[0] for n in noms if "." in n}
            if not noms or len(prefixes) != 1 or any("." not in n for n in noms):
                self.inconnus.append({"ou": {"section": titre, "tableau": rang},
                                      "quoi": "tableau", "valeur": "entité sans préfixe commun"})
                continue
            nom_entite = prefixes.pop()
            entite = entites.setdefault(nom_entite, {"nom": nom_entite, "libelle": titre,
                                                     "ou": {"section": titre, "tableau": rang},
                                                     "attributs": []})
            for ligne in lignes:
                cellules = ligne["cellules"]
                champ = cellules.get("nom_champ", {}).get("texte", "")
                attribut = {"ou": ligne["ou"], "champ_brut": champ,
                            "attribut": champ[len(nom_entite) + 1:]
                            if champ.startswith(nom_entite + ".") else champ}
                for cle in ("designation", "commentaire", "valeurs"):
                    if cle in cellules:
                        attribut[cle] = cellules[cle]
                for cle in ("format", "longueur"):
                    if cle in cellules:
                        attribut[cle] = cellules[cle]["texte"]
                if ligne.get("barre"):
                    attribut["barre"] = True
                entite["attributs"].append(attribut)
        return list(entites.values())

    def _regles_definitions(self):
        """RG et GENERIQUE : une regle par definition d'extrait (contrat §5.4)."""
        regles = []
        for noeud, chemin in self.page.blocs:
            for definition in _parcours(noeud):
                nature = mx.classify_reuse_node(definition)
                if not nature or not nature.endswith("_definition") or nature.startswith("sync"):
                    continue
                regles.append(self._regle(definition, chemin))
        return regles

    def _regle(self, definition, chemin):
        brut = html.unescape(str(mx.macro_param(definition, "name") or ""))
        titres = [self.page.titres[i] for i in chemin]
        regle = {"ou": {"section": titres[-1]["titre"] if titres else None}}
        local = (definition.get("attrs") or {}).get("localId")
        if local:
            regle["ou"]["local_id"] = local
        groupe = next((t["titre"] for t in reversed(titres) if t["niveau"] <= 2), None)
        if groupe:
            regle["groupe"] = groupe
        if titres:
            regle["titre_section"] = titres[-1]["titre"]
        regle["mecanisme"] = mx.famille_macro(definition)
        regle["nom_brut"] = brut
        regle["nom"] = normalise_nom(brut)
        # Convention TEMPLATE_RG : le corps s'ouvre sur « Règle RG-X concernant … ». Le
        # gras n'en couvre parfois que le premier mot : la ligne de titre est donc le
        # premier paragraphe, quand il commence en gras ou par « Règle ».
        titre, commence_gras = _premier_paragraphe(definition)
        gras = _premier_gras(definition)
        if gras:
            regle["titre_gras"] = gras
        if titre and (commence_gras or reduit(titre).startswith("regle")):
            regle["titre"] = titre
            motif_rg = dict(self.config["_citations"])["RG"]
            code = motif_rg.search(titre.translate(TIRETS_UNICODE))
            if code:
                regle["code_titre"] = code.group(0).rstrip(".:")
            trouve = re.search(r"\bconcernant\b\s*(.*)$", titre, re.I)
            if trouve and trouve.group(1).strip():
                regle["concernant"] = trouve.group(1).strip()
        regle["corps"] = nettoie(self.lecteur.texte(definition.get("content") or []))
        tableaux = [t for t in (self._tableau_simple(table, rang)
                                for rang, table in enumerate(_tables(definition.get("content") or []), 1)) if t]
        if tableaux:
            regle["corps"]["tableaux"] = tableaux
        return regle

    def _tableau_simple(self, table, rang):
        """Tableau du corps d'une RG, en texte : en-têtes (première ligne), puis lignes
        (« Attributs du DTO X » | « Alimentation », contrôle K65)."""
        lignes = [[nettoie(self.lecteur.texte(c))["texte"] for c in _cellules(ligne)]
                  for ligne in _lignes_brutes(table)]
        if not lignes:
            return None
        return {"rang": rang, "entetes": lignes[0], "lignes": lignes[1:]}

    # ------------------------------------------------------------------
    # Index de la page (contrat §4.5)
    # ------------------------------------------------------------------

    def _index(self):
        textes, liens, inclusions, definitions = [], [], [], []

        def releve(texte, ou):
            texte = nettoie(texte)
            if est_vide(texte):
                return
            textes.append({"ou": ou, **texte})
            liens.extend({"ou": ou, **l} for l in texte.get("liens", []))
            inclusions.extend({"ou": ou, **i} for i in texte.get("inclusions", []))

        def parcourt(noeud, section, titre_section, rangs):
            if not isinstance(noeud, dict):
                return
            ntype = noeud.get("type")
            nature = mx.classify_reuse_node(noeud)
            if nature and nature.endswith("_definition"):
                definitions.append(self._definition(noeud, section, titre_section))
            if ntype == "table":
                rangs[section] = rangs.get(section, 0) + 1
                self._index_table(noeud, section, rangs[section], releve)
                return
            if mx.is_nested_table(noeud):
                for enfant in mx.nested_table_content(noeud):
                    parcourt(enfant, section, titre_section, rangs)
                return
            if ntype in FEUILLES or (nature and nature.endswith("_include")):
                ou = {"section": section}
                local = (noeud.get("attrs") or {}).get("localId")
                if local:
                    ou["local_id"] = local
                releve(self.lecteur.texte(noeud), ou)
                return
            if ntype in mx.EXTENSION_NODE_TYPES and nature is None:
                params = ((noeud.get("attrs") or {}).get("parameters") or {}).get("macroParams")
                valeurs = [str((v or {}).get("value") if isinstance(v, dict) else v)
                           for v in (params or {}).values()]
                valeurs = [v for v in valeurs if v and v != "None"]
                if valeurs:
                    textes.append({"ou": {"section": section,
                                          "macro": (noeud.get("attrs") or {}).get("extensionKey")},
                                   "texte": " ".join(valeurs)})
            for enfant in (noeud.get("content") or []):
                parcourt(enfant, section, titre_section, rangs)

        rangs = {}
        if self.page.cartouche is not None:
            parcourt(self.page.cartouche, "cartouche", None, rangs)
        if self.page.evolutions is not None:
            parcourt(self.page.evolutions, "evolutions", None, rangs)
        for titre in self.page.titres:
            releve(self.lecteur.texte(titre["_noeud"]), {"section": titre["titre"]})
        for noeud, chemin in self.page.blocs:
            section = self.page.titre_le_plus_proche(chemin)
            parcourt(noeud, section, section, rangs)
        return {"textes": textes, "liens": liens, "inclusions": inclusions,
                "definitions": definitions}

    def _index_table(self, table, section, rang, releve):
        """Une entree par cellule ; la colonne est canonique si la section est reconnue."""
        brutes = _lignes_brutes(table)
        if not brutes:
            return
        entetes = [self.lecteur.texte(c)["texte"] for c in _cellules(brutes[0])]
        canon_section = next((t.get("canonique") for t in self.page.titres
                              if t["titre"] == section and t.get("canonique")), None)
        cfg = (self.regles.get("sections", {}).get(canon_section, {}).get("tableau")
               if canon_section else None)
        if section == "evolutions":
            cfg = {"colonnes": self.config["evolutions"]["colonnes"]}
        carte = self._carte_colonnes(entetes, cfg) if cfg else [None] * len(entetes)
        for numero, brute in enumerate(brutes):
            for colonne, cellule in enumerate(_cellules(brute)):
                nom = (carte[colonne] if colonne < len(carte) and carte[colonne]
                       else (entetes[colonne] if colonne < len(entetes) else str(colonne + 1)))
                ou = {"section": section, "tableau": rang, "ligne": numero, "colonne": nom}
                releve(self.lecteur.texte(cellule), ou)

    def _definition(self, noeud, section, titre_section):
        nature = mx.classify_reuse_node(noeud)
        ou = {"section": section}
        local = (noeud.get("attrs") or {}).get("localId")
        if local:
            ou["local_id"] = local
        if nature == "sync_definition":
            uuid = mx.sync_definition_key(noeud, self.lecteur.page_id)[1]
            definition = {"mecanisme": "sync", "nom_brut": uuid, "nom": uuid}
        else:
            brut = html.unescape(str(mx.macro_param(noeud, "name") or ""))
            definition = {"mecanisme": mx.famille_macro(noeud), "nom_brut": brut,
                          "nom": normalise_nom(brut)}
        definition["ou"] = ou
        if titre_section:
            definition["titre_section"] = titre_section
        return definition


def _racine_citee(texte, soi, noms):
    """Entité de la page citée dans le texte d'agrégat (mot entier), hors l'entité elle-même ;
    la première après le mot « racine » s'il y figure, sinon la première du texte."""
    debut = re.search(r"racine", texte, re.I)
    positions = []
    for nom in noms:
        if nom == soi:
            continue
        for trouve in re.finditer(rf"(?<![\w.]){re.escape(nom)}(?!\w)", texte):
            positions.append((trouve.start(), nom))
    apres = [p for p in positions if debut and p[0] > debut.start()]
    choix = sorted(apres or positions)
    return choix[0][1] if choix else None


RE_WHITELIST = re.compile(r"whitelist\s*(?::|\()?\s*([^.\n)]*)", re.I)
MOTS_HORS_WHITELIST = {"cf", "de", "du", "des", "la", "le", "les", "voir"}


def _whitelist(texte):
    """Attributs nommés après « whitelist » : « whitelist : code, libelle », « (date, auteur) »,
    « dateDebut / dateFin ». None si la phrase renvoie ailleurs (« whitelist de RG-… »)."""
    trouve = RE_WHITELIST.search(texte or "")
    if not trouve:
        return None
    morceaux = [m for m in re.split(r"\s*(?:,|/|\bet\b|\bou\b)\s*", trouve.group(1).strip()) if m]
    if not morceaux or any(m.lower() in MOTS_HORS_WHITELIST or not re.fullmatch(r"[a-z][A-Za-z0-9]*", m)
                           for m in morceaux):
        return None
    return morceaux


def _tout_en_gras(noeud):
    """Paragraphe dont tout le texte non vide est en gras : un titre d'etape du §4 d'un SA."""
    if noeud.get("type") != "paragraph":
        return False
    textes = [n for n in (noeud.get("content") or []) if n.get("type") == "text"
              and n.get("text", "").strip()]
    return bool(textes) and all(any(m.get("type") == "strong" for m in (n.get("marks") or []))
                                for n in textes)


def _premier_paragraphe(noeud):
    """(texte du premier paragraphe non vide du corps, commence-t-il en gras ?)."""
    for n in _parcours(noeud.get("content") or []):
        if n.get("type") != "paragraph":
            continue
        textes = [t for t in (n.get("content") or []) if t.get("type") == "text"]
        texte = " ".join("".join(t.get("text", "") for t in textes).split())
        if texte:
            premier = next(t for t in textes if t.get("text", "").strip())
            gras = any(m.get("type") == "strong" for m in (premier.get("marks") or []))
            return texte, gras
    return None, False


def _premier_gras(noeud):
    """Premier passage en gras du corps d'une definition : le titre de la regle."""
    morceaux, commence = [], False
    for n in _parcours(noeud.get("content") or []):
        if n.get("type") != "text":
            if commence and n.get("type") in ("paragraph", "hardBreak"):
                break
            continue
        gras = any(m.get("type") == "strong" for m in (n.get("marks") or []))
        if gras:
            commence = True
            morceaux.append(n.get("text", ""))
        elif commence:
            break
    titre = " ".join("".join(morceaux).split())
    return titre or None


def _relations_de_ligne(ligne):
    """Relations d'une ligne « A (c) <-> (c) B (c) <-> (c) C », chainage compris."""
    nom = RE_NOM_RELATION.search(ligne)
    noeuds, carte_avant, fleche, precedent = [], None, False, None
    for jeton in RE_JETON_RELATION.finditer(ligne):
        carte, est_fleche, entite = jeton.group(1), jeton.group(2), jeton.group(3)
        if entite:
            noeuds.append({"nom": entite, "avant": carte_avant if fleche else None,
                           "apres": None, "lie": fleche})
            carte_avant, fleche, precedent = None, False, "entite"
        elif carte is not None:
            if precedent == "entite" and noeuds:
                noeuds[-1]["apres"] = carte
            else:
                carte_avant = carte
            precedent = "carte"
        elif est_fleche:
            fleche, precedent = True, "fleche"
    relations = []
    for gauche, droite in zip(noeuds, noeuds[1:]):
        if not droite["lie"]:
            continue
        relations.append({
            "de": gauche["nom"], "vers": droite["nom"],
            "card_de": _cardinalite(gauche["apres"]),
            "card_vers": _cardinalite(droite["avant"]),
        })
    if nom and relations:
        relations[-1]["libelle"] = nom.group(1).strip()
    return relations


def _cardinalite(brute):
    brute = (brute or "").replace(" ", "")
    return CARDINALITES.get(brute, brute)


# ==========================================================================
# Ecriture
# ==========================================================================

def ecrit_faits(faits, dossier):
    """faits/{page_id}.json, ecriture atomique et seulement si le contenu change.

    `genere_le` est exclu de la comparaison : sans cela, chaque run reecrirait tout.
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / f"{faits['page']['id']}.json"
    contenu = json.dumps(faits, ensure_ascii=False, indent=1)
    if cible.exists():
        try:
            ancien = json.loads(cible.read_text(encoding="utf-8"))
            ancien["genere_le"] = faits["genere_le"]
            if json.dumps(ancien, ensure_ascii=False, indent=1) == contenu:
                return False
        except (ValueError, KeyError):
            pass    # fichier illisible ou d'un autre schema : il est simplement reecrit
    temporaire = cible.with_suffix(".json.tmp")
    temporaire.write_text(contenu, encoding="utf-8")
    temporaire.replace(cible)
    return True
