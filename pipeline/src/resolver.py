#!/usr/bin/env python3
"""
Resolution du contenu reutilise — les trois mecanismes, en un seul parcours.

VERSION : 1.0

Ce module remplace le contenu reutilise par sa valeur et injecte les tables imbriquees,
AVANT toute normalisation et tout rendu markdown. L'ordre importe : le contrat resout
puis normalise puis rend, jamais l'inverse. Une substitution de chaine faite apres
conversion — ce que faisait le resolver d'origine — ne peut ni distinguer deux
definitions de meme nom, ni redescendre dans ce qu'elle vient d'injecter.

Toute la couche deterministe vient de multiexcerpt.py : natures, cles, index par
famille, garde-fou de cycle, decodage des noms. Rien n'en est redefini ici.

UN SEUL PARCOURS pour les deux transformations — injection des tables imbriquees et
resolution de la reutilisation. Motif : chacune peut reveler du travail pour l'autre.
Une table imbriquee peut contenir une inclusion ; un corps de definition peut contenir
une table imbriquee. Aucun de ces deux croisements n'a d'occurrence dans les 9 fixtures :
le parcours unique est pris par precaution, il ne coute pas plus cher que deux passes.

CE MODULE NE JOINT PAS LE RESEAU. La seule porte vers Confluence est le `fournisseur`
qu'on lui passe, a deux methodes :

    par_titre(titre)          -> (page_id, page_title, adf) ou None
    par_identifiant(page_id)  -> (page_id, page_title, adf) ou None

C'est ce qui rend les tests hors reseau possibles : l'implementation reelle s'adosse a
confluence_client, celle des tests lit pipeline/fixtures/.

CE MODULE NE REND AUCUN VERDICT. Il consigne des faits — une inclusion resolue, une
definition absente, une page source absente — et laisse au rapport de run et a
l'index croise le soin d'en deduire `parse_status`. Changer un seuil ne doit pas
imposer de toucher au resolver.

Contrat de reference : contracts/normalisation_adf.md §1, §1.8 et §2.
"""

import copy

import multiexcerpt as mx

VERSION = "1.0"


# ==========================================================================
# BLOC DE CONSTANTES
# ==========================================================================

# Prefixe de pile du garde-fou, par famille de macro. Le prefixe n'est pas decoratif :
# sans lui, la cle (page, nom) d'un multiexcerpt et la MEME cle d'un excerpt se
# confondraient dans la pile, et une imbrication legitime passerait pour un cycle.
MECANISME_PAR_FAMILLE = {
    mx.FAMILLE_MULTIEXCERPT: "multiexcerpt",
    mx.FAMILLE_EXCERPT: "excerpt",
}
MECANISME_SYNC = "sync"

STATUT_RESOLUE = "resolue"
STATUT_DEFINITION_ABSENTE = "definition_absente"
STATUT_PAGE_SOURCE_ABSENTE = "page_source_absente"

MOTIFS = {
    STATUT_DEFINITION_ABSENTE: "definition introuvable sur la page source",
    STATUT_PAGE_SOURCE_ABSENTE: "page source introuvable",
}


# ==========================================================================
# Marquage dans le resultat
# ==========================================================================
# Le contrat demande que le contenu reutilise soit marque VISIBLEMENT dans le .md. Le
# marqueur est un paragraphe de texte portant un commentaire HTML : le renderer le
# laisse passer tel quel, aucun type de noeud nouveau n'est a declarer, et le contrat
# de normalisation n'a pas a bouger.

def _marqueur(texte):
    return {"type": "paragraph", "content": [{"type": "text", "text": f"<!-- {texte} -->"}]}


def marqueur_ouvrant(titre_source, nom):
    return _marqueur(f"inclusion : {titre_source} / {nom}")


def marqueur_fermant(titre_source, nom):
    return _marqueur(f"fin inclusion : {titre_source} / {nom}")


def marqueur_non_resolue(cible, nom, motif):
    return _marqueur(f"inclusion non resolue : {cible} / {nom} — {motif}")


# ==========================================================================
# Carte titre -> identifiant
# ==========================================================================

def carte_titres(inventaire):
    """Carte titre -> page_id, construite UNE FOIS depuis pages_inventory.json.

    Elle rend gratuite la resolution d'une inclusion par titre : aucun appel reseau
    tant que la page cible est dans le perimetre.

    LEVE si deux pages du perimetre portent le meme titre. Le controle est fait au
    moment de CONSTRUIRE la carte, pas a chaque usage — meme choix que la detection de
    collision de slug dans inventory.py : un conflit de donnees se signale une fois,
    globalement, pas au hasard de la premiere inclusion qui tombe dessus.

    Les DEUX formes du titre sont indexees quand elles different : `title` (normalise
    par inventory.normalize_title — entites decodees, tirets Unicode replies) et
    `title_raw` (le titre tel que Confluence le rend). Une inclusion ecrite dans l'ADF
    porte la forme brute, que clean_page_title() ne replie pas ; sans les deux formes,
    une page dont le titre contient un tiret insecable serait introuvable. Cas reel du
    corpus : `299499522`, CU-PERSONNE-RECHERCHER, dont le premier tiret est U+2011.
    """
    carte = {}
    pages = (inventaire or {}).get("pages") or {}
    entrees = pages.values() if isinstance(pages, dict) else pages
    for page in entrees:
        page_id = str(page.get("id"))
        for titre in (page.get("title"), page.get("title_raw")):
            titre = mx.clean_page_title(titre)
            if not titre:
                continue
            deja = carte.get(titre)
            if deja is not None and deja != page_id:
                raise mx.ResolutionError(
                    f"deux pages du perimetre portent le titre {titre!r} : {deja} ET "
                    f"{page_id}. La resolution par titre ne peut pas trancher ; "
                    f"corriger l'un des deux titres dans Confluence.")
            carte[titre] = page_id
    return carte


# ==========================================================================
# Resolveur
# ==========================================================================

class Resolveur:
    """Etat d'un run : index des definitions, carte des titres, pages deja lues.

    L'index est conserve d'une page a l'autre : on paie UN appel par page source
    distincte, jamais un par inclusion. Sur API-PORTAIL-FAVORIS, trois inclusions
    visent la meme page de regles generiques — c'est un appel, pas trois.
    """

    def __init__(self, fournisseur, carte=None, profondeur_max=20):
        self.fournisseur = fournisseur
        self.carte = dict(carte or {})
        self.ids_perimetre = set(self.carte.values())
        self.profondeur_max = profondeur_max
        self.index = mx.IndexDefinitions()          # macros, deux familles separees
        self.sync = {}                              # (page_id, uuid) -> entree
        self.pages_indexees = set()                 # page_id deja parcourus
        self.titres_indexes = set()                 # titres deja parcourus
        self.titres_absents = set()                 # titres deja cherches en vain
        self.ids_absents = set()                    # identifiants deja cherches en vain
        self.faits = []

    # ------------------------------------------------------------------
    # Indexation
    # ------------------------------------------------------------------

    def indexe_page(self, page_id, page_title, adf):
        """Indexe TOUTES les definitions d'une page, d'un coup.

        Deux passes sur la meme page sont necessaires : une inclusion peut preceder sa
        definition dans l'ordre du document, donc l'index doit etre complet avant que
        la resolution commence.
        """
        page_id = str(page_id)
        titre = mx.clean_page_title(page_title)
        if page_id in self.pages_indexees:
            return
        # Marquer AVANT de descendre : une definition syncBlock de la page peut viser
        # la page elle-meme, et IndexDefinitions leve sur une cle deja presente.
        self.pages_indexees.add(page_id)
        self.titres_indexes.add(titre)
        self._collecte_definitions(adf, titre, page_id)

    def _collecte_definitions(self, node, titre, page_id):
        if not isinstance(node, dict):
            return
        # Une definition peut etre logee dans une table imbriquee : son contenu n'est
        # pas dans `content` mais dans parameters.adf, il faut l'ouvrir pour la voir.
        if mx.is_nested_table(node):
            for enfant in mx.nested_table_content(node):
                self._collecte_definitions(enfant, titre, page_id)
            return
        nature = mx.classify_reuse_node(node)
        if nature == "sync_definition":
            cle = mx.sync_definition_key(node, page_id)
            deja = self.sync.get(cle)
            if deja is not None:
                raise mx.ResolutionError(
                    f"definition syncBlock en double pour la cle {cle!r} : "
                    f"{deja['emplacement']} ET {mx.emplacement(node, page_id, titre)}")
            self.sync[cle] = {"node": node, "page_title": titre, "page_id": page_id,
                              "emplacement": mx.emplacement(node, page_id, titre)}
        elif nature and nature.endswith("_definition"):
            self.index.ajoute(node, titre, page_id)
        for enfant in (node.get("content") or []):
            self._collecte_definitions(enfant, titre, page_id)

    # ------------------------------------------------------------------
    # Recuperation d'une page source
    # ------------------------------------------------------------------

    def _entree_page(self, valeur, quoi):
        """Normalise ce que rend le fournisseur. LEVE si plusieurs pages repondent."""
        if valeur is None:
            return None
        if isinstance(valeur, list):
            if len(valeur) > 1:
                raise mx.ResolutionError(
                    f"plusieurs pages repondent pour {quoi} : la resolution par titre "
                    f"ne peut pas trancher ({len(valeur)} pages)")
            if not valeur:
                return None
            valeur = valeur[0]
        page_id, page_title, adf = valeur
        return str(page_id), page_title, adf

    def assure_titre(self, titre):
        """Rend True si les definitions de la page de ce titre sont indexees.

        Ordre : index deja en memoire, puis carte du perimetre (gratuite), puis appel
        au fournisseur. Une page hors perimetre est LUE sans etre EXPORTEE — le
        perimetre d'export ne change pas pour autant.
        """
        titre = mx.clean_page_title(titre)
        if titre in self.titres_indexes:
            return True
        if titre in self.titres_absents:
            return False
        page_id = self.carte.get(titre)
        if page_id is not None and page_id in self.pages_indexees:
            self.titres_indexes.add(titre)
            return True
        if page_id is not None:
            entree = self._entree_page(self.fournisseur.par_identifiant(page_id),
                                      f"l'identifiant {page_id}")
        else:
            entree = self._entree_page(self.fournisseur.par_titre(titre),
                                       f"le titre {titre!r}")
        if entree is None:
            # Retenir l'echec : sans ca, N inclusions vers une page absente font
            # N appels pour le meme constat.
            self.titres_absents.add(titre)
            return False
        self.indexe_page(*entree)
        self.titres_indexes.add(titre)
        return True

    def assure_identifiant(self, page_id):
        """Meme role pour un syncBlock : la source est designee par IDENTIFIANT.

        Pas de carte de titres, donc pas de sensibilite au renommage.
        """
        page_id = str(page_id)
        if page_id in self.pages_indexees:
            return True
        if page_id in self.ids_absents:
            return False
        entree = self._entree_page(self.fournisseur.par_identifiant(page_id),
                                   f"l'identifiant {page_id}")
        if entree is None:
            self.ids_absents.add(page_id)
            return False
        self.indexe_page(*entree)
        return True

    # ------------------------------------------------------------------
    # Faits
    # ------------------------------------------------------------------

    def _consigne(self, mecanisme, cle, statut, hors_perimetre, ou):
        fait = {"mecanisme": mecanisme, "cle": cle, "statut": statut,
                "source_hors_perimetre": hors_perimetre, "emplacement": ou}
        self.faits.append(fait)
        return fait

    # Sans carte, on ne PEUT pas dire qu'une page est hors perimetre : le fait reste
    # faux plutot que d'affirmer a tort. C'est la carte qui definit le perimetre.

    def _hors_perimetre_titre(self, titre):
        return bool(self.carte) and mx.clean_page_title(titre) not in self.carte

    def _hors_perimetre_id(self, page_id):
        """Un syncBlock designe sa source par IDENTIFIANT : la carte se lit a l'envers.

        Chercher un identifiant parmi les CLES de la carte, qui sont des titres, rendrait
        toute source syncBlock hors perimetre — y compris la page voisine du meme module.
        """
        return bool(self.carte) and str(page_id) not in self.ids_perimetre

    # ------------------------------------------------------------------
    # Parcours
    # ------------------------------------------------------------------

    def resout(self, adf, page_title, page_id, guard=None):
        """Rend (adf_resolu, faits) pour une page. Ne modifie jamais l'ADF recu."""
        titre = mx.clean_page_title(page_title)
        pid = str(page_id)
        self.faits = []
        self.indexe_page(pid, titre, adf)
        guard = guard if guard is not None else mx.CycleGuard(self.profondeur_max)
        resolu = dict(adf)
        resolu["content"] = self._transforme(adf.get("content") or [], titre, pid, guard)
        return resolu, list(self.faits)

    def _transforme(self, noeuds, titre, page_id, guard):
        sortie = []
        for node in noeuds:
            sortie.extend(self._transforme_noeud(node, titre, page_id, guard))
        return sortie

    def _transforme_noeud(self, node, titre, page_id, guard):
        """Rend la LISTE de noeuds qui remplace `node` — vide, un, ou plusieurs.

        Ne descend que dans `content`. Un parcours qui suivrait toute cle nommee `type`
        remonterait `media.attrs.type = "file"` et `datasource.views[0].type = "table"`
        comme s'ils etaient des types de noeuds.
        """
        if not isinstance(node, dict):
            return [node]

        # 1. Table imbriquee : le contenu est integralement recuperable, on le remet en
        #    place de l'extension puis on redescend dedans — il peut porter une inclusion.
        if mx.is_nested_table(node):
            return self._transforme(mx.nested_table_content(node), titre, page_id, guard)

        nature = mx.classify_reuse_node(node)

        # 2a. Definition : on descend dans le corps SANS le remplacer. Une definition
        #     s'affiche aussi la ou elle est definie.
        if nature and nature.endswith("_definition"):
            copie = dict(node)
            copie["content"] = self._transforme(node.get("content") or [],
                                                titre, page_id, guard)
            return [copie]

        # 2b. Inclusion : resoudre, puis redescendre dans l'injecte.
        if nature == "sync_include":
            return self._resout_sync(node, titre, page_id, guard)
        if nature and nature.endswith("_include"):
            return self._resout_macro(node, titre, page_id, guard)

        # 2c. Noeud ordinaire.
        copie = dict(node)
        if isinstance(node.get("content"), list):
            copie["content"] = self._transforme(node["content"], titre, page_id, guard)
        return [copie]

    def _injecte(self, definition, mecanisme, cle, guard):
        """Corps d'une definition, resolu a son tour, sous garde-fou de cycle.

        Le contexte de page devient celui de la page SOURCE : une inclusion logee dans
        un corps de definition et sans parametre de page vise la page qui la definit,
        pas celle qui la consomme.
        """
        corps = copy.deepcopy(definition["node"].get("content") or [])
        with guard.enter(mecanisme, cle):
            return self._transforme(corps, definition["page_title"],
                                    definition["page_id"], guard)

    def _resout_macro(self, node, titre, page_id, guard):
        famille = mx.famille_macro(node)
        mecanisme = MECANISME_PAR_FAMILLE[famille]
        cible, nom = mx.macro_include_key(node, titre)
        ou = mx.emplacement(node, page_id, titre)
        hors = self._hors_perimetre_titre(cible)

        if not self.assure_titre(cible):
            self._consigne(mecanisme, (cible, nom), STATUT_PAGE_SOURCE_ABSENTE, hors, ou)
            return [marqueur_non_resolue(cible, nom, MOTIFS[STATUT_PAGE_SOURCE_ABSENTE])]

        definition = self.index.resout(node, titre)
        if definition is None:
            self._consigne(mecanisme, (cible, nom), STATUT_DEFINITION_ABSENTE, hors, ou)
            return [marqueur_non_resolue(cible, nom, MOTIFS[STATUT_DEFINITION_ABSENTE])]

        injecte = self._injecte(definition, mecanisme, (cible, nom), guard)
        self._consigne(mecanisme, (cible, nom), STATUT_RESOLUE, hors, ou)
        return ([marqueur_ouvrant(definition["page_title"], nom)] + injecte
                + [marqueur_fermant(definition["page_title"], nom)])

    def _resout_sync(self, node, titre, page_id, guard):
        cle = mx.sync_include_key(node)
        source_id, uuid = cle
        ou = mx.emplacement(node, page_id, titre)
        hors = self._hors_perimetre_id(source_id)

        if not self.assure_identifiant(source_id):
            self._consigne(MECANISME_SYNC, cle, STATUT_PAGE_SOURCE_ABSENTE, hors, ou)
            return [marqueur_non_resolue(source_id, uuid,
                                         MOTIFS[STATUT_PAGE_SOURCE_ABSENTE])]

        definition = self.sync.get(cle)
        if definition is None:
            self._consigne(MECANISME_SYNC, cle, STATUT_DEFINITION_ABSENTE, hors, ou)
            return [marqueur_non_resolue(source_id, uuid,
                                         MOTIFS[STATUT_DEFINITION_ABSENTE])]

        injecte = self._injecte(definition, MECANISME_SYNC, cle, guard)
        self._consigne(MECANISME_SYNC, cle, STATUT_RESOLUE, hors, ou)
        return ([marqueur_ouvrant(definition["page_title"], uuid)] + injecte
                + [marqueur_fermant(definition["page_title"], uuid)])


# ==========================================================================
# Interface d'une page
# ==========================================================================

def resout_document(adf, page_title, page_id, fournisseur, guard=None, carte=None):
    """Rend (adf_resolu, faits). Ne modifie jamais l'ADF recu.

    Interface d'une page isolee. Un run complet instancie Resolveur UNE FOIS et appelle
    sa methode resout() page par page : c'est ce qui conserve l'index des definitions
    d'une page a l'autre, donc un appel par page source distincte.

    `carte` est la carte titre -> identifiant produite par carte_titres() depuis
    pages_inventory.json. Sans elle, toute inclusion par titre passe par
    fournisseur.par_titre() : correct, mais un appel de plus par page source.
    """
    return Resolveur(fournisseur, carte).resout(adf, page_title, page_id, guard=guard)
