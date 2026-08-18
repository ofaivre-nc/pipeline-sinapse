#!/usr/bin/env python3
"""
Rendu de l'ADF vers markdown — deux modes, un seul parcours.

VERSION : 1.0

CE MODULE EST UNE FONCTION PURE. Aucun acces disque, aucune lecture de
pages_inventory.json, aucun appel reseau. Le contexte d'inventaire dont il a besoin —
`md_path` de la page porteuse, titre et `md_path` des cibles de lien — lui est INJECTE,
comme le resolver recoit son fournisseur de pages sources. C'est ce qui rend ses tests
executables sans inventaire reel sur le disque.

Le frontmatter et l'ecriture atomique ne sont pas a lui : ils appartiennent a main.py.

IL RECOIT UN ADF DEJA RESOLU ET DEJA INJECTE. Le resolver a remplace les inclusions par
leur contenu encadre de marqueurs, et les `extension :: nested-table` par les tables
qu'ils portaient. Mesure du 18 aout sur les 9 fixtures resolues : plus aucun `syncBlock`
ni `nested-table` n'atteint ce module ; y subsistent 39 definitions multiexcerpt, 2
definitions syncBlock et 8 `toc`.

MARKDOWN ET HTML SONT DEUX MODES D'UNE MEME FONCTION, pas deux modules ni deux classes.
C'est la duplication en deux chemins qui casse un renderer : une regle corrigee d'un cote
et pas de l'autre ne se voit pas. Le dispatch passe par des TABLES EXPLICITES et non par
un match/case — c'est ce qui rend les deux ensembles de types ENUMERABLES, donc
l'assertion de parite du contrat ecrivable. Un chemin de rendu qui ne serait pas dans sa
table ferait mentir cette assertion.

CE MODULE NE REND AUCUN VERDICT. Il rend le markdown ET ses faits, chacun portant son
niveau dans un champ structure :

    incident  le contenu manque dans le .md — main.py en deduira parse_status: partial
    constat   un fait a consigner, sans perte de contenu, la page reste ok

Les incidents SE COLLECTENT, ils n'arretent pas le parcours : en tout-ou-rien, le premier
type inconnu masque tous les suivants et il faut un run complet par type a decouvrir.
Seule l'exception typee de ce module est rattrapee ; toute autre exception remonte — un
KeyError avale comme un type non couvert serait un bug deguise en incident.

Contrat de reference : contracts/normalisation_adf.md, integralement.
"""

import base64
import posixpath
import struct
from datetime import datetime, timezone

VERSION = "1.0"


# ==========================================================================
# BLOC DE CONSTANTES — documente dans contracts/normalisation_adf.md
# ==========================================================================

MODE_MARKDOWN = "markdown"
MODE_HTML = "html"
MODES = (MODE_MARKDOWN, MODE_HTML)

NIVEAU_INCIDENT = "incident"
NIVEAU_CONSTAT = "constat"

# --- Marks : LISTE BLANCHE DE QUINZE. Un mark absent des quinze est un incident.
# 7 jetes (§8.2) + 6 enveloppants admis hors `text` (§8) + `code` et `link`, qui ne
# s'appliquent qu'a un `text`.
MARKS_JETES = frozenset({
    "breakout", "alignment", "fragment", "annotation", "border", "subsup", "fontSize",
})
MARKS_ENVELOPPANTS = frozenset({
    "strong", "em", "strike", "underline", "backgroundColor", "textColor",
})
MARKS_TEXTE_SEUL = frozenset({"code", "link"})
MARKS_CONNUS = MARKS_JETES | MARKS_ENVELOPPANTS | MARKS_TEXTE_SEUL

# Porteurs qui admettent un mark enveloppant. Hors `text`, c'est un CONSTAT ; hors de
# cette liste, un incident. Un conteneur de blocs n'y figure pas : un mark inline ne
# franchit pas une frontiere de bloc.
PORTEURS_ENVELOPPE = frozenset({
    "text", "paragraph", "heading", "inlineCard", "status", "mention",
})

# --- Tableaux (§9.1) : ces types en enfant DIRECT d'une cellule font du contenu de bloc.
# `rule` et `heading` en font partie depuis le 11 aout : sans eux, une cellule n'en
# contenant qu'un est jugee simple et son `---` ou son `## x` rompt la ligne de pipes.
BLOCS_EN_CELLULE = frozenset({
    "bulletList", "orderedList", "table", "panel", "codeBlock", "blockquote",
    "mediaSingle", "rule", "heading",
})
CELLULES = frozenset({"tableCell", "tableHeader"})

# --- Enveloppes de mark, par mode.
ENVELOPPES_MARKDOWN = {
    "strong": ("**", "**"), "em": ("*", "*"), "code": ("`", "`"),
    "underline": ("<u>", "</u>"), "strike": ("~~", "~~"),
}
ENVELOPPES_HTML = {
    "strong": ("<strong>", "</strong>"), "em": ("<em>", "</em>"),
    "code": ("<code>", "</code>"), "underline": ("<u>", "</u>"),
    "strike": ("<del>", "</del>"),
}


class RenduError(Exception):
    """Exception TYPEE de ce module, et la seule que le parcours rattrape.

    Toute autre exception remonte : c'est un defaut du code, pas un fait du corpus, et
    l'absorber en incident le rendrait indiscernable d'un noeud Confluence inattendu.
    """


# ==========================================================================
# Cibles de lien — §6.3
# ==========================================================================

def page_id_depuis_lien_court(suffixe):
    """Identifiant de page encode dans un lien `/wiki/x/{suffixe}`, ou None.

    Entier 8 octets little-endian, octets nuls de fin tronques, base64 URL-safe sans
    bourrage. Verifie sur trois paires du corpus, sans aucun appel reseau.
    """
    try:
        brut = suffixe.replace("_", "/").replace("-", "+")
        brut += "=" * (-len(brut) % 4)
        octets = base64.b64decode(brut).ljust(8, b"\x00")
        return str(struct.unpack("<Q", octets[:8])[0])
    except (ValueError, struct.error):
        return None


def cible_de_lien(url):
    """(page_id ou None, url d'edition ?) pour une URL de carte.

    L'identifiant est rendu en CHAINE : les identifiants de page sont des chaines
    partout dans le depot. Un entier ne trouverait jamais sa cle dans l'inventaire, et
    TOUS les renvois internes degraderaient en lien brut sans que rien ne le signale.

    Le segment `edit-v2/` est tolere sans etre confondu avec un identifiant — anomalie
    reelle de `380567556`, qui pointe en edition vers elle-meme.
    """
    url = str(url or "")
    edition = "/pages/edit-v2/" in url
    if "/pages/" in url:
        queue = url.split("/pages/", 1)[1].split("#")[0].split("?")[0]
        for segment in queue.split("/"):
            if segment.isdigit():
                return segment, edition
        return None, edition
    if "/wiki/x/" in url:
        suffixe = url.split("/wiki/x/", 1)[1].split("#")[0].split("?")[0]
        return page_id_depuis_lien_court(suffixe), edition
    return None, edition


def chemin_relatif(md_path_cible, md_path_source):
    """Chemin de la cible RELATIF au fichier porteur, separateurs `/`.

    Pas au `local_path` : l'arborescence reproduit la hierarchie Confluence, et un lien
    absolu depuis une page qui n'est pas a la racine pointe a cote. posixpath et non
    os.path — sous Windows, os.path rendrait des antislashs.
    """
    if not md_path_source:
        return md_path_cible
    depart = posixpath.dirname(str(md_path_source).replace("\\", "/"))
    arrivee = str(md_path_cible).replace("\\", "/")
    if not depart:
        return arrivee
    return posixpath.relpath(arrivee, depart)


# ==========================================================================
# Renderer
# ==========================================================================

class Renderer:
    """Rendu d'un document. Une instance par page, ses faits sont ceux de cette page.

    `inventaire` : {page_id (CHAINE) : {"titre": ..., "md_path": ...}}, injecte.
    `md_path_source` : chemin du .md en cours d'ecriture, pour les liens relatifs.
    """

    def __init__(self, inventaire=None, md_path_source=None):
        self.inventaire = dict(inventaire or {})
        self.md_path_source = md_path_source
        self.faits = []
        self._chemin = []

    # ------------------------------------------------------------------
    # Faits
    # ------------------------------------------------------------------

    def _consigne(self, niveau, code, detail):
        fait = {"niveau": niveau, "code": code, "detail": detail,
                "emplacement": " > ".join(self._chemin) or "doc"}
        self.faits.append(fait)
        return fait

    def _incident(self, code, detail):
        return self._consigne(NIVEAU_INCIDENT, code, detail)

    def _constat(self, code, detail):
        return self._consigne(NIVEAU_CONSTAT, code, detail)

    # ------------------------------------------------------------------
    # Entree
    # ------------------------------------------------------------------

    def rend(self, adf):
        """Rend (markdown, faits). Ne modifie jamais l'ADF recu."""
        if not isinstance(adf, dict) or adf.get("type") != "doc":
            raise RenduError(
                f"racine attendue 'doc', recue {type(adf).__name__} "
                f"{(adf or {}).get('type') if isinstance(adf, dict) else ''!r}")
        self.faits = []
        self._chemin = []
        texte = self._blocs(adf.get("content") or [], MODE_MARKDOWN)
        return texte, list(self.faits)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _table(self, mode, inline):
        if inline:
            return INLINES_HTML if mode == MODE_HTML else INLINES_MARKDOWN
        return BLOCS_HTML if mode == MODE_HTML else BLOCS_MARKDOWN

    def _rend_bloc(self, node, mode):
        """Rend un noeud de bloc. Un type absent des deux tables est un INCIDENT."""
        if not isinstance(node, dict):
            return ""
        ntype = node.get("type")
        methode = self._table(mode, False).get(ntype) or self._table(mode, True).get(ntype)
        if methode is None:
            return self._type_non_couvert(ntype, mode)
        self._chemin.append(str(ntype))
        try:
            rendu = getattr(self, methode)(node, mode)
        finally:
            self._chemin.pop()
        return self._applique_marks(rendu, node, mode)

    def _rend_inline(self, node, mode):
        if not isinstance(node, dict):
            return ""
        ntype = node.get("type")
        methode = self._table(mode, True).get(ntype)
        if methode is None:
            # Un noeud de bloc rencontre en position inline se rend comme un bloc :
            # le cas n'existe pas au corpus, mais le jeter perdrait du contenu.
            if self._table(mode, False).get(ntype):
                return self._rend_bloc(node, mode)
            return self._type_non_couvert(ntype, mode)
        self._chemin.append(str(ntype))
        try:
            rendu = getattr(self, methode)(node, mode)
        finally:
            self._chemin.pop()
        return self._applique_marks(rendu, node, mode)

    def _type_non_couvert(self, ntype, mode):
        """Incident. En mode HTML le contrat le nomme a part, et INTERDIT le repli.

        Un repli sur le rendu markdown produirait `**Libelle**` affiche avec ses
        asterisques a l'interieur d'une balise — le defaut meme que le mode HTML existe
        pour supprimer, revenu par la porte de derriere.
        """
        if mode == MODE_HTML:
            self._incident("type_sans_regle_html",
                           f"type {ntype!r} sans regle de rendu HTML en cellule de "
                           f"tableau HTML")
        else:
            self._incident("type_non_couvert", f"type de noeud non couvert : {ntype!r}")
        return ""

    # ------------------------------------------------------------------
    # Assemblage
    # ------------------------------------------------------------------

    def _blocs(self, noeuds, mode, separateur=None):
        morceaux = [self._rend_bloc(n, mode) for n in noeuds]
        gardes = [m for m in morceaux if m]
        if mode == MODE_HTML:
            return "".join(gardes)
        return (separateur if separateur is not None else "\n\n").join(gardes)

    def _inlines(self, noeuds, mode):
        self._controle_text_adjacents(noeuds)
        return "".join(self._rend_inline(n, mode) for n in noeuds)

    def _controle_text_adjacents(self, noeuds):
        """Deux `text` adjacents de meme jeu de marks : CONSTAT (§8.3).

        Aucune passe de fusion n'est ecrite — sur 804 paires examinees, aucune ne porte
        le meme jeu. Mais rien ne le garantit contractuellement du cote d'Atlassian, et
        la violation produirait un balisage casse silencieux. On controle plutot que de
        s'y fier.
        """
        precedent = None
        for node in noeuds:
            if not isinstance(node, dict) or node.get("type") != "text":
                precedent = None
                continue
            marks = node.get("marks") or []
            if precedent is not None and precedent == marks:
                self._constat("text_adjacents_memes_marks",
                              f"deux noeuds text adjacents portent le meme jeu de "
                              f"marks : {[m.get('type') for m in marks]}")
            precedent = marks

    # ------------------------------------------------------------------
    # Marks — §8, la regle se lit par PORTEUR
    # ------------------------------------------------------------------

    def _applique_marks(self, rendu, node, mode):
        """Applique les marks du noeud au contenu DEJA RENDU. Sur tous les noeuds.

        Le renderer lit `marks` sur tous les noeuds, pas sur les seuls `text` : mesure
        du corpus dore, 89 marks portes par un noeud autre que `text` sur 10 couples.
        Ils y sont tous jetes — les ignorer produirait la bonne sortie, et aucune
        comparaison de .md ne verrait le defaut.

        « Une seule fois » n'est pas un detail de forme : sur un paragraphe, le mark
        enveloppe le paragraphe RENDU, pas chacun de ses noeuds text.
        """
        marks = node.get("marks") or []
        if not marks:
            return rendu
        porteur = node.get("type")
        for mark in marks:
            mtype = (mark or {}).get("type")
            attrs = (mark or {}).get("attrs") or {}
            if mtype not in MARKS_CONNUS:
                self._incident("mark_hors_liste_blanche",
                               f"mark {mtype!r} hors de la liste blanche des quinze, "
                               f"porte par {porteur!r}")
                continue
            if mtype in MARKS_JETES:
                continue
            if mtype in MARKS_TEXTE_SEUL and porteur != "text":
                # `code` avalerait en silence le balisage du paragraphe ; un lien ne
                # peut pas en contenir un autre.
                self._incident("mark_porteur_inadmis",
                               f"mark {mtype!r} sur un porteur {porteur!r} : il ne "
                               f"s'applique qu'a un noeud text")
                continue
            if mtype in MARKS_ENVELOPPANTS and porteur not in PORTEURS_ENVELOPPE:
                self._incident("mark_porteur_inadmis",
                               f"mark {mtype!r} sur un porteur {porteur!r}, qui ne "
                               f"l'admet pas")
                continue
            if porteur != "text":
                self._constat("mark_hors_text",
                              f"mark {mtype!r} enveloppant un noeud {porteur!r}")
            rendu = self._enveloppe(rendu, mtype, attrs, mode)
        return rendu

    def _enveloppe(self, rendu, mtype, attrs, mode):
        table = ENVELOPPES_HTML if mode == MODE_HTML else ENVELOPPES_MARKDOWN
        if mtype in table:
            ouvre, ferme = table[mtype]
            return f"{ouvre}{rendu}{ferme}"
        if mtype == "link":
            href = attrs.get("href", "")
            if mode == MODE_HTML:
                return f'<a href="{href}">{rendu}</a>'
            return f"[{rendu}]({href})"
        if mtype == "backgroundColor":
            return f'<mark style="background:{attrs.get("color")}">{rendu}</mark>'
        if mtype == "textColor":
            return f'<span style="color:{attrs.get("color")}">{rendu}</span>'
        raise RenduError(f"mark {mtype!r} connu mais sans enveloppe : table incomplete")

    # ------------------------------------------------------------------
    # Echappement
    # ------------------------------------------------------------------

    @staticmethod
    def echappe_html(texte):
        """`&` en PREMIER, sinon les entites produites seraient re-echappees."""
        return (str(texte).replace("&", "&amp;")
                .replace("<", "&lt;").replace(">", "&gt;"))

    # Le texte n'est jamais echappe hors des deux cas du contrat : le `|` d'une cellule
    # en pipes, et `&` `<` `>` en cellule HTML. Les caracteres actifs du markdown
    # sortent tels quels — le pipeline FABRIQUE de la syntaxe markdown, et un
    # echappement generique transformerait `![alt](adf-media://…)` en texte affiche.

    # ==================================================================
    # BLOCS
    # ==================================================================

    def _doc(self, node, mode):
        return self._blocs(node.get("content") or [], mode)

    def _transparent(self, node, mode):
        """Conteneur transparent : ses enfants sont emis a sa place, dans l'ordre.

        `panel` (§9.2), `layoutSection` / `layoutColumn` (§4.1), `taskList` (§7.2), et
        les definitions de contenu reutilise, qui s'affichent la ou elles sont definies
        SANS marqueur — le §1.9 n'encadre que le contenu RESOLU.
        """
        return self._blocs(node.get("content") or [], mode)

    def _paragraphe(self, node, mode):
        corps = self._inlines(node.get("content") or [], mode)
        if mode == MODE_HTML:
            return f"<p>{corps}</p>" if corps else ""
        return corps

    def _titre(self, node, mode):
        attrs = node.get("attrs") or {}
        niveau = attrs.get("level")
        if niveau is None:
            self._constat("heading_sans_level",
                          "heading sans attrs.level : rendu au niveau 1")
            niveau = 1
        niveau = int(niveau)
        corps = self._inlines(node.get("content") or [], mode)
        if mode == MODE_HTML:
            return f"<h{niveau}>{corps}</h{niveau}>"
        return "#" * niveau + " " + corps

    def _regle(self, node, mode):
        # La ligne vide qui precede vient du joint des blocs : sans elle, `---` sous un
        # paragraphe serait lu comme un titre setext de niveau 2.
        return "<hr>" if mode == MODE_HTML else "---"

    def _code(self, node, mode):
        langue = (node.get("attrs") or {}).get("language") or ""
        brut = "".join(c.get("text", "") for c in (node.get("content") or [])
                       if isinstance(c, dict) and c.get("type") == "text")
        if mode == MODE_HTML:
            return f"<pre><code>{self.echappe_html(brut)}</code></pre>"
        return f"```{langue}\n{brut}\n```"

    def _citation(self, node, mode):
        if mode == MODE_HTML:
            return f"<blockquote>{self._blocs(node.get('content') or [], mode)}</blockquote>"
        corps = self._blocs(node.get("content") or [], mode)
        return "\n".join(("> " + ligne) if ligne else ">" for ligne in corps.split("\n"))

    def _liste(self, node, mode):
        """Une liste se rend TOUJOURS a plat ; l'imbrication vient de _indente.

        Cumuler un niveau explicite et le retrait de continuation de _indente
        indenterait deux fois : un second niveau sortirait a quatre espaces au lieu de
        deux, et le troisieme a huit. Le retrait de continuation suffit et se compose.
        """
        ordonnee = node.get("type") == "orderedList"
        items = [n for n in (node.get("content") or []) if isinstance(n, dict)]
        if mode == MODE_HTML:
            balise = "ol" if ordonnee else "ul"
            rendus = "".join(f"<li>{self._blocs(i.get('content') or [], mode)}</li>"
                             for i in items)
            return f"<{balise}>{rendus}</{balise}>"
        lignes = []
        for rang, item in enumerate(items, 1):
            puce = f"{rang}. " if ordonnee else "- "
            lignes.append(self._item(item, mode, puce))
        return "\n".join(l for l in lignes if l)

    def _item(self, item, mode, puce):
        morceaux = [self._rend_bloc(e, mode) for e in (item.get("content") or [])]
        texte = "\n\n".join(m for m in morceaux if m)
        return self._indente(puce, texte)

    @staticmethod
    def _indente(puce, texte):
        """La puce sur la premiere ligne, deux espaces de continuation sur les autres."""
        lignes = texte.split("\n") if texte else [""]
        sortie = [puce + lignes[0]]
        sortie += [("  " + l) if l else "" for l in lignes[1:]]
        return "\n".join(sortie)

    def _element_liste(self, node, mode):
        """Un `listItem` rencontre hors de sa liste. N'existe pas au corpus."""
        return self._blocs(node.get("content") or [], mode)

    def _colonnes(self, node, mode):
        """`layoutSection` : transparent, UNE LIGNE VIDE entre deux colonnes.

        Elle n'est pas decorative : sans elle, le dernier paragraphe d'une colonne et le
        premier de la suivante fusionneraient en un seul bloc markdown. Elle separe,
        elle ne signale pas — aucun marqueur de colonne n'est ecrit.
        """
        return self._blocs(node.get("content") or [], mode)

    def _depliant(self, node, mode):
        """`expand` : le titre en GRAS, jamais en titre markdown.

        Le niveau correct ne s'infere pas de l'ADF : emettre `## EVOLUTIONS` au milieu
        d'une page dont le plan est en h2 insererait une section fantome dans l'index et
        deplacerait tout ce qui suit.
        """
        titre = (node.get("attrs") or {}).get("title")
        corps = self._blocs(node.get("content") or [], mode)
        if not titre:
            return corps
        if mode == MODE_HTML:
            return f"<p><strong>{self.echappe_html(titre)}</strong></p>{corps}"
        return f"**{titre}**\n\n{corps}" if corps else f"**{titre}**"

    def _media_bloc(self, node, mode):
        """`mediaSingle` : transparent, mais la legende est COLLEE a son image.

        « Immediatement sous l'image » se rend par un `<br>`, jamais par une ligne vide
        ni par un simple retour a la ligne — meme dispositif que `hardBreak`, et pour le
        meme motif : deux espaces en fin de ligne sont supprimes par les editeurs et ne
        fonctionnent pas en cellule de tableau.
        """
        morceaux = [self._rend_bloc(n, mode) for n in (node.get("content") or [])]
        gardes = [m for m in morceaux if m]
        if mode == MODE_HTML:
            return "".join(gardes)
        return "<br>\n".join(gardes)

    def _media(self, node, mode):
        attrs = node.get("attrs") or {}
        cible = f"adf-media://{attrs.get('id')}"
        if attrs.get("collection"):
            cible += f"?collection={attrs['collection']}"
        alt = attrs.get("alt") or ""
        if mode == MODE_HTML:
            return f'<img src="{cible}" alt="{self.echappe_html(alt)}">'
        return f"![{alt}]({cible})"

    def _legende(self, node, mode):
        corps = self._inlines(node.get("content") or [], mode)
        if mode == MODE_HTML:
            return f"<em>{corps}</em>"
        return f"*{corps}*" if corps else ""

    def _carte_bloc(self, node, mode):
        """`blockCard` : requete Jira du cartouche, ou simple lien. §6.1 et §6.2.

        AUCUN APPEL JIRA. Le pipeline remet la macro en clair et s'arrete la.
        """
        attrs = node.get("attrs") or {}
        source = attrs.get("datasource")
        if not source:
            url = attrs.get("url")
            if not url:
                self._incident("blockcard_sans_cible",
                               "blockCard sans datasource ni url")
                return ""
            return (f'<a href="{url}">{self.echappe_html(url)}</a>'
                    if mode == MODE_HTML else f"[{url}]({url})")
        jql = (source.get("parameters") or {}).get("jql")
        if jql is None:
            jql = self._jql_depuis_url(attrs.get("url"))
        if jql is None:
            self._incident("blockcard_sans_jql",
                           "blockCard a datasource sans jql, ni dans "
                           "parameters.jql ni dans le parametre jql de attrs.url")
            return ""
        if "{{" in jql:
            self._constat("jql_gabarit_non_substitue",
                          f"JQL a gabarit non substitue : {jql[:80]}")
        vues = source.get("views") or [{}]
        premiere = vues[0] if vues else {}
        colonnes = [c.get("key") for c
                    in ((premiere.get("properties") or {}).get("columns") or [])]
        return self._cartouche_jira(premiere.get("type") or "table", colonnes, jql, mode)

    @staticmethod
    def _jql_depuis_url(url):
        """Repli du §6.1 : la requete encodee dans le parametre `jql` de attrs.url."""
        from urllib.parse import parse_qs, unquote, urlparse
        if not url:
            return None
        valeurs = parse_qs(urlparse(str(url)).query).get("jql")
        return unquote(valeurs[0]) if valeurs else None

    def _cartouche_jira(self, vue, colonnes, jql, mode):
        if mode == MODE_HTML:
            return ("<p><strong>Requête Jira (cartouche)</strong></p>"
                    f"<ul><li>vue : <code>{self.echappe_html(vue)}</code></li>"
                    f"<li>colonnes : {self.echappe_html(', '.join(colonnes))}</li></ul>"
                    f"<pre><code>{self.echappe_html(jql)}</code></pre>")
        return ("**Requête Jira (cartouche)**\n\n"
                f"- vue : `{vue}`\n"
                f"- colonnes : {', '.join(colonnes)}\n"
                "- JQL :\n\n"
                f"```\n{jql}\n```")

    def _tache(self, node, mode):
        attrs = node.get("attrs") or {}
        coche = "x" if attrs.get("state") == "DONE" else " "
        corps = self._inlines(node.get("content") or [], mode)
        if mode == MODE_HTML:
            return f"<li>[{coche}] {corps}</li>"
        return f"- [{coche}] {corps}"

    def _taches(self, node, mode):
        items = [self._rend_bloc(n, mode) for n in (node.get("content") or [])]
        gardes = [i for i in items if i]
        if mode == MODE_HTML:
            return f"<ul>{''.join(gardes)}</ul>"
        return "\n".join(gardes)

    def _macro(self, node, mode):
        """`extension` / `bodiedExtension` — §2.3, dans l'ordre de reconnaissance.

        Une DEFINITION de contenu reutilise se rend transparente : elle s'affiche la ou
        elle est definie, et le §1.9 n'encadre que le contenu RESOLU. Aucun marqueur de
        definition n'existe au contrat.

        Une INCLUSION qui atteindrait ce module est un incident : le resolver ne l'a pas
        consommee, donc du contenu manque dans le .md. Le contrat ne nomme pas ce cas —
        il suppose qu'il ne se produit pas, et la mesure du 18 aout le confirme (zero
        occurrence). Le traiter en incident est le choix conservateur.
        """
        attrs = node.get("attrs") or {}
        cle = str(attrs.get("extensionKey") or "").lower()
        if cle == "nested-table":
            self._incident("nested_table_non_injectee",
                           "extension :: nested-table a l'entree du renderer : le "
                           "resolver ne l'a pas injectee")
            return ""
        if "multiexcerpt" in cle or "excerpt" in cle:
            if node.get("content"):
                return self._transparent(node, mode)
            self._incident("inclusion_non_resolue",
                           f"inclusion de contenu reutilise non resolue a l'entree du "
                           f"renderer : extensionKey={attrs.get('extensionKey')!r}")
            return ""
        if cle == "toc":
            # Un sommaire est regenere a l'affichage depuis les titres : il n'a aucun
            # contenu propre a convertir, et le lecteur le reconstruit depuis les `#`.
            return "<!-- toc -->"
        self._incident("macro_non_couverte",
                       f"macro non couverte par le contrat : "
                       f"{attrs.get('extensionKey')!r}")
        return ""

    def _sync_definition(self, node, mode):
        """`bodiedSyncBlock` : definition, transparente comme une definition de macro."""
        return self._transparent(node, mode)

    def _sync_inclusion(self, node, mode):
        self._incident("inclusion_non_resolue",
                       f"syncBlock non resolu a l'entree du renderer : "
                       f"{(node.get('attrs') or {}).get('resourceId')!r}")
        return ""

    # ==================================================================
    # TABLEAUX — §9.1
    # ==================================================================

    def _tableau(self, node, mode):
        lignes = [l for l in (node.get("content") or []) if isinstance(l, dict)]
        if mode == MODE_HTML or self._tableau_complexe(lignes):
            return self._tableau_html(lignes)
        return self._tableau_pipes(lignes)

    def _tableau_complexe(self, lignes):
        """Trois declencheurs : contenu de bloc, fusion, ligne d'en-tete mixte.

        La lecture porte sur les ENFANTS DIRECTS de la cellule. Elle est valide parce
        que l'arbre recu est deja resolu et deja injecte : les deux lectures — enfants
        directs et sous-arbre entier — retombent a l'egalite, 100 et 100. Un ecart entre
        elles signalerait un noeud de bloc depose a une place inline.
        """
        for ligne in lignes:
            for cellule in (ligne.get("content") or []):
                if not isinstance(cellule, dict):
                    continue
                attrs = cellule.get("attrs") or {}
                if (attrs.get("colspan") or 1) > 1 or (attrs.get("rowspan") or 1) > 1:
                    return True
                types = [e.get("type") for e in (cellule.get("content") or [])
                         if isinstance(e, dict)]
                if any(t in BLOCS_EN_CELLULE for t in types):
                    return True
                if types.count("paragraph") > 1:
                    return True
        return self._entete_mixte(lignes)

    @staticmethod
    def _entete_mixte(lignes):
        """Une premiere ligne non homogene, ou un `tableHeader` hors premiere ligne.

        Sans cette regle le cas degrade en silence : tout l'en-tete passe en corps et
        une ligne d'en-tete vide est emise. En HTML, `<th>` et `<td>` cohabitent.
        """
        if not lignes:
            return False
        premiere = [c for c in (lignes[0].get("content") or []) if isinstance(c, dict)]
        entetes = [c.get("type") == "tableHeader" for c in premiere]
        if entetes and not (all(entetes) or not any(entetes)):
            return True
        for ligne in lignes[1:]:
            for cellule in (ligne.get("content") or []):
                if isinstance(cellule, dict) and cellule.get("type") == "tableHeader":
                    return True
        return False

    def _tableau_pipes(self, lignes):
        grille = []
        for ligne in lignes:
            self._chemin.append("tableRow")
            try:
                grille.append([self._cellule_pipes(c)
                               for c in (ligne.get("content") or [])
                               if isinstance(c, dict)])
            finally:
                self._chemin.pop()
        largeur = max((len(r) for r in grille), default=0)
        grille = [r + [""] * (largeur - len(r)) for r in grille]
        premiere = [c for c in (lignes[0].get("content") or [])
                    if isinstance(c, dict)] if lignes else []
        avec_entete = bool(premiere) and all(c.get("type") == "tableHeader"
                                             for c in premiere)
        if avec_entete:
            entete, corps = grille[0], grille[1:]
        else:
            # Un tableau sans tableHeader recoit une ligne d'en-tete VIDE : sans elle,
            # la syntaxe en pipes est invalide.
            entete, corps = [""] * largeur, grille
        sortie = ["| " + " | ".join(entete) + " |",
                  "| " + " | ".join(["---"] * largeur) + " |"]
        sortie += ["| " + " | ".join(r) + " |" for r in corps]
        return "\n".join(sortie)

    def _cellule_pipes(self, cellule):
        self._chemin.append(cellule.get("type") or "tableCell")
        try:
            morceaux = [self._rend_bloc(e, MODE_MARKDOWN)
                        for e in (cellule.get("content") or [])]
        finally:
            self._chemin.pop()
        contenu = " ".join(m for m in morceaux if m)
        # Sans cet echappement, un `|` rompt la structure du tableau : notations R/O/P
        # des contrats DTO, expressions logiques des regles.
        return contenu.replace("|", "\\|")

    def _tableau_html(self, lignes):
        sortie = ["<table>"]
        for ligne in lignes:
            sortie.append("<tr>")
            self._chemin.append("tableRow")
            try:
                for cellule in (ligne.get("content") or []):
                    if isinstance(cellule, dict):
                        sortie.append(self._cellule_html(cellule))
            finally:
                self._chemin.pop()
            sortie.append("</tr>")
        sortie.append("</table>")
        return "".join(sortie)

    def _cellule_html(self, cellule):
        balise = "th" if cellule.get("type") == "tableHeader" else "td"
        attrs = cellule.get("attrs") or {}
        ouvrant = ""
        # colspan et rowspan ne sont emis que s'ils valent plus de 1.
        if (attrs.get("colspan") or 1) > 1:
            ouvrant += f' colspan="{attrs["colspan"]}"'
        if (attrs.get("rowspan") or 1) > 1:
            ouvrant += f' rowspan="{attrs["rowspan"]}"'
        self._chemin.append(cellule.get("type") or "tableCell")
        try:
            contenu = self._blocs(cellule.get("content") or [], MODE_HTML)
        finally:
            self._chemin.pop()
        return f"<{balise}{ouvrant}>{contenu}</{balise}>"

    def _ligne(self, node, mode):
        """Un `tableRow` rencontre hors de son tableau. N'existe pas au corpus."""
        return self._blocs(node.get("content") or [], mode)

    def _cellule(self, node, mode):
        """Une cellule rencontree hors de son tableau. N'existe pas au corpus."""
        return self._blocs(node.get("content") or [], mode)

    # ==================================================================
    # INLINE
    # ==================================================================

    def _texte(self, node, mode):
        brut = node.get("text", "")
        return self.echappe_html(brut) if mode == MODE_HTML else brut

    def _saut(self, node, mode):
        # `<br>` plutot que deux espaces en fin de ligne : les editeurs et les linters
        # les suppriment, et ils ne fonctionnent pas en cellule de tableau.
        return "<br>"

    def _statut(self, node, mode):
        """Le TEXTE NU. `color` et `style` sont jetes : la couleur redouble le texte.

        Inventer une syntaxe creerait une ambiguite avec les liens ou avec le mark
        `code`, massivement employe par ailleurs, pour ne rien ajouter au sens.
        """
        brut = (node.get("attrs") or {}).get("text") or ""
        return self.echappe_html(brut) if mode == MODE_HTML else brut

    def _mention(self, node, mode):
        attrs = node.get("attrs") or {}
        brut = attrs.get("text")
        if not brut:
            if attrs.get("id"):
                brut = f"@{attrs['id']}"
            else:
                self._incident("mention_sans_identite",
                               "mention sans text ni id : une mention vide passerait "
                               "pour du texte manquant")
                return ""
        return self.echappe_html(brut) if mode == MODE_HTML else brut

    def _date(self, node, mode):
        """ISO 8601, conversion en UTC EXPLICITE.

        La forme naive emploie le fuseau de la machine : sans effet a Noumea, ou minuit
        UTC reste le meme jour, mais un executant place dans un fuseau negatif
        decalerait les 47 dates d'un jour, sans un mot. Le defaut ne se voit jamais sur
        le poste ou il a ete ecrit.
        """
        brut = (node.get("attrs") or {}).get("timestamp")
        try:
            millisecondes = int(str(brut).strip())
        except (TypeError, ValueError):
            self._incident("date_timestamp_invalide",
                           f"date sans timestamp exploitable : {brut!r}")
            return ""
        moment = datetime.fromtimestamp(millisecondes / 1000, tz=timezone.utc)
        return moment.strftime("%Y-%m-%d")

    def _emoji(self, node, mode):
        """`attrs.text`, repli sur `shortName`. Les deux absents : incident.

        Sur 19 des 21 occurrences le .md portera `:warning:` et non le caractere. C'est
        un shortcode GitHub Flavored Markdown valide — de la syntaxe, pas un artefact.
        """
        attrs = node.get("attrs") or {}
        brut = attrs.get("text") or attrs.get("shortName")
        if not brut:
            self._incident("emoji_sans_texte",
                           f"emoji sans text ni shortName : id={attrs.get('id')!r}")
            return ""
        return self.echappe_html(brut) if mode == MODE_HTML else brut

    def _carte_inline(self, node, mode):
        """Renvoi entre pages — §6.3, dans l'ordre du contrat."""
        url = (node.get("attrs") or {}).get("url") or ""
        page_id, edition = cible_de_lien(url)
        if edition:
            self._constat("url_edition",
                          f"inlineCard vers une URL d'edition : {url}")
        cible = self.inventaire.get(page_id) if page_id else None
        if cible:
            chemin = chemin_relatif(cible.get("md_path"), self.md_path_source)
            titre = cible.get("titre") or url
            if mode == MODE_HTML:
                return f'<a href="{chemin}">{self.echappe_html(titre)}</a>'
            return f"[{titre}]({chemin})"
        if page_id:
            # Pas une erreur de parsing : un renvoi vers une page hors perimetre.
            self._constat("renvoi_hors_perimetre",
                          f"identifiant {page_id} absent de l'inventaire injecte")
        if mode == MODE_HTML:
            return f'<a href="{url}">{self.echappe_html(url)}</a>'
        return f"[{url}]({url})"

    def _media_inline(self, node, mode):
        """Image au fil du texte. Pas d'`alt` : le noeud n'en porte pas.

        En fabriquer un — l'identifiant recopie, un mot generique — serait inventer une
        description. Un alt vide est de la syntaxe markdown legale.
        """
        attrs = node.get("attrs") or {}
        cible = f"adf-media://{attrs.get('id')}"
        if attrs.get("collection"):
            cible += f"?collection={attrs['collection']}"
        if mode == MODE_HTML:
            return f'<img src="{cible}" alt="">'
        return f"![]({cible})"


# ==========================================================================
# TABLES DE DISPATCH — la parite des deux modes se lit ici
# ==========================================================================
# Deux tables par mode, et non un match/case : c'est ce qui rend les ensembles de types
# ENUMERABLES, donc l'assertion de parite du contrat ecrivable. Un chemin de rendu qui
# ne serait pas dans sa table ferait mentir cette assertion.

_BLOCS_COMMUNS = {
    "doc": "_doc",
    "paragraph": "_paragraphe",
    "heading": "_titre",
    "rule": "_regle",
    "codeBlock": "_code",
    "blockquote": "_citation",
    "panel": "_transparent",
    "bulletList": "_liste",
    "orderedList": "_liste",
    "listItem": "_element_liste",
    "layoutSection": "_colonnes",
    "layoutColumn": "_transparent",
    "expand": "_depliant",
    "table": "_tableau",
    "tableRow": "_ligne",
    "tableCell": "_cellule",
    "tableHeader": "_cellule",
    "mediaSingle": "_media_bloc",
    "media": "_media",
    "caption": "_legende",
    "blockCard": "_carte_bloc",
    "taskList": "_taches",
    "taskItem": "_tache",
    "extension": "_macro",
    "bodiedExtension": "_macro",
    "syncBlock": "_sync_inclusion",
    "bodiedSyncBlock": "_sync_definition",
}

_INLINES_COMMUNS = {
    "text": "_texte",
    "hardBreak": "_saut",
    "status": "_statut",
    "mention": "_mention",
    "date": "_date",
    "emoji": "_emoji",
    "inlineCard": "_carte_inline",
    "mediaInline": "_media_inline",
    "inlineExtension": "_macro",
}

BLOCS_MARKDOWN = dict(_BLOCS_COMMUNS)
BLOCS_HTML = dict(_BLOCS_COMMUNS)
INLINES_MARKDOWN = dict(_INLINES_COMMUNS)
INLINES_HTML = dict(_INLINES_COMMUNS)


def types_couverts(mode):
    """Ensemble des types de noeuds couverts par un mode. 36 au contrat."""
    if mode == MODE_HTML:
        return set(BLOCS_HTML) | set(INLINES_HTML)
    if mode == MODE_MARKDOWN:
        return set(BLOCS_MARKDOWN) | set(INLINES_MARKDOWN)
    raise RenduError(f"mode inconnu : {mode!r}")


# ==========================================================================
# Interface d'une page
# ==========================================================================

def rend_document(adf, inventaire=None, md_path_source=None):
    """Rend (markdown, faits). Ne modifie jamais l'ADF recu.

    `inventaire` : {page_id (CHAINE) : {"titre": ..., "md_path": ...}}.
    `md_path_source` : chemin du .md en cours d'ecriture, pour les liens relatifs.
    """
    return Renderer(inventaire, md_path_source).rend(adf)
