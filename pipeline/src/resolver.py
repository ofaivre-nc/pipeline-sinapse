#!/usr/bin/env python3
"""
Resolution du contenu reutilise — les trois mecanismes, en un seul parcours.

VERSION : 1.5 — une inclusion d'un nom defini deux fois est « definition absente », motif « nom
                defini plusieurs fois sur la page source » (multiexcerpt 1.4)
          1.4 — `page_id` et `local_id` structures dans chaque fait (jointure des faits v2)

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

Contrat de reference : contracts/normalisation_adf.md §1, §1.8, §1.9 et §2.
"""

import copy

import multiexcerpt as mx

VERSION = "1.5"


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

# Ces motifs partent dans un .md : ils sont accentues, comme tout contenu ecrit dans un
# fichier. Les valeurs de `statut` ci-dessus ne le sont pas — champs structures.
MOTIFS = {
    STATUT_DEFINITION_ABSENTE: "définition introuvable sur la page source",
    STATUT_PAGE_SOURCE_ABSENTE: "page source introuvable",
}
# Un nom defini deux fois : meme statut que l'absence (contrat §1.8), motif distinct.
MOTIF_AMBIGUE = "nom défini plusieurs fois sur la page source"

# Nom affiche dans les marqueurs pour l'extrait natif sans nom (cle (page, "")). Le fait
# garde le nom vide : seul le .md a besoin d'un libelle lisible. Contrat §1.8.
NOM_AFFICHE_PAR_DEFAUT = "extrait par défaut"

FORME_BLOC = "bloc"
FORME_INLINE = "inline"
SUBSTITUTION_INLINE = "inline"
SUBSTITUTION_SCINDEE = "scindee"

# Types inline du corpus, couverts par contracts/normalisation_adf.md §5.1, §6, §7 et §9.
# Sert UNIQUEMENT a qualifier le contenu d'une substitution inline. Un enfant de
# paragraphe hors de cet ensemble fait basculer la substitution en bloc, avec constat :
# le cas devient visible au rapport au lieu de produire un ADF invalide en silence.
#
# Si renderer.py finit par avoir besoin de la meme partition, elle DEMENAGE dans un
# endroit partage — elle ne se recopie pas. Un fait duplique en deux endroits diverge a
# la premiere correction (§5 du document de reference).
TYPES_INLINE = frozenset({
    "text", "hardBreak", "emoji", "date", "status", "mention", "inlineCard", "mediaInline",
})


# ==========================================================================
# Marquage dans le resultat
# ==========================================================================
# Le contrat demande que le contenu reutilise soit marque VISIBLEMENT dans le .md
# (§1.9) : une ligne en italique a l'ouverture et a la fermeture, portant le nom du
# contenu et sa page source. Le resolver depose un `paragraph` portant un noeud `text`
# marque `em` — JAMAIS d'asterisques litterales, qui s'afficheraient telles quelles a
# l'interieur d'une balise <em> en cellule de tableau HTML. Le marqueur suit ainsi la
# machinerie deja en place : aucun type de noeud nouveau n'est a declarer.
#
# UNE SEULE FONCTION DE FABRICATION PAR LIBELLE, partagee bloc/inline : le §1.9 en fait
# une exigence explicite — une seule surface de test. La forme inline reprendra ces
# libelles tels quels, en changeant seulement le porteur.

CARACTERES_NEUTRALISES = "|<>"


def _fragment(valeur):
    """Fragment de libelle sur, quel que soit l'etat des donnees.

    |, < et > sont remplaces par une ESPACE, pas supprimes : une suppression
    souderait deux mots. Ce sont les trois caracteres que le rendu echappe
    (contrat §9.1) ; un marqueur qui en porterait serait deforme en cellule.
    La garantie est par construction, jamais par l'etat du corpus du jour.
    """
    texte = str(valeur or "")
    for caractere in CARACTERES_NEUTRALISES:
        texte = texte.replace(caractere, " ")
    return " ".join(texte.split())


def libelle_ouvrant(nom, source):
    return f"↳ inclusion : {_fragment(nom)} — source : {_fragment(source)}"


def libelle_fermant(nom):
    return f"↳ fin inclusion : {_fragment(nom)}"


def libelle_non_resolue(nom, source, motif):
    return (f"↳ inclusion non résolue : {_fragment(nom)} — "
            f"source : {_fragment(source)} — {motif}")


def nom_sync(uuid):
    """Nom affiche d'un bloc synchronise. Contrat §1.9."""
    return f"bloc synchronisé {str(uuid)[:8]}"


def _texte_em(libelle):
    return {"type": "text", "text": libelle, "marks": [{"type": "em"}]}


def marqueur_bloc(libelle):
    return {"type": "paragraph", "content": [_texte_em(libelle)]}


def _marqueur(inline, libelle):
    """Le meme libelle, l'autre porteur. §1.9 : une seule surface de test."""
    return _texte_em(libelle) if inline else marqueur_bloc(libelle)


# ==========================================================================
# Substitution inline : qualification et enveloppe d'echappement
# ==========================================================================
# Une inclusion inline vit DANS le content d'un paragraphe. Y deposer un `paragraph` —
# ce que faisait la v1.0 — met un noeud de bloc a une place inline : 5 occurrences
# mesurees au corpus dore, a l'origine de la divergence 100 / 102 du §9.1.
#
# Quand le contenu resolu ne qualifie pas pour la substitution en place, il faut donc
# SCINDER le paragraphe hote. La scission n'est jamais pilotee par un test « ce noeud
# est-il de bloc ? » applique aux enfants existants de l'hote : un noeud preexistant que
# le resolver n'a pas injecte ne doit pas pouvoir la declencher. Elle est pilotee par ce
# que LA SUBSTITUTION ELLE-MEME a produit — d'ou cette enveloppe, deposee par
# _transforme_noeud et consommee par le conteneur qui l'assemble.
#
# L'enveloppe n'a PAS de cle `type` : elle n'est confondable avec aucun noeud ADF, et
# une enveloppe qui survivrait au parcours est une erreur interne, pas un rendu degrade.

CLE_ECHAPPEMENT = "__blocs_a_scinder__"


def _echappement(blocs, fait):
    """Enveloppe les blocs qu'une inclusion inline non qualifiante doit deposer.

    Elle transporte aussi le fait de cette inclusion : c'est le conteneur qui scinde
    qui sait le type de l'hote, pas le point de resolution.
    """
    return {CLE_ECHAPPEMENT: list(blocs), "fait": fait}


def _est_echappement(valeur):
    return isinstance(valeur, dict) and CLE_ECHAPPEMENT in valeur


def _deplie(noeuds):
    """Remplace chaque enveloppe par les blocs qu'elle porte, a plat.

    Employe la ou l'on assemble deja une liste de BLOCS — corps de definition, contenu
    du document. Y scinder n'aurait pas de sens : il n'y a pas de phrase a couper.
    """
    if not any(_est_echappement(n) for n in noeuds):
        return list(noeuds)
    sortie = []
    for noeud in noeuds:
        if _est_echappement(noeud):
            sortie.extend(noeud[CLE_ECHAPPEMENT])
        else:
            sortie.append(noeud)
    return sortie


def _qualifie_inline(injecte):
    """Le contenu resolu peut-il etre depose EN PLACE dans le paragraphe hote ?

    Les trois criteres du §1.9, dans l'ordre : un seul noeud de premier niveau, qui est
    un `paragraph`, dont tous les enfants directs sont d'un type inline. Mesure de
    reference : 44 des 45 inclusions inline resolubles du perimetre d'export qualifient.
    """
    if len(injecte) != 1:
        return False
    seul = injecte[0]
    if not isinstance(seul, dict) or seul.get("type") != "paragraph":
        return False
    return all(isinstance(enfant, dict) and enfant.get("type") in TYPES_INLINE
               for enfant in (seul.get("content") or []))


def _contient_echappement(noeud):
    """Une enveloppe subsiste-t-elle dans l'arbre ? Invariant interne du parcours."""
    if _est_echappement(noeud):
        return True
    if isinstance(noeud, dict):
        return any(_contient_echappement(valeur) for valeur in noeud.values())
    if isinstance(noeud, list):
        return any(_contient_echappement(valeur) for valeur in noeud)
    return False


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
        self.hotes_scindes = []                     # meme duree de vie que self.faits

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

    # ATTENTION AU MOT `forme` — deux faits voisins a ne pas fusionner a l'etape 4.
    # Ici, `forme` est celle de l'INCLUSION : ou son contenu doit etre depose. Le champ
    # `inline` de $defs/multiexcerpt dans contracts/reused_content_cache.schema.json est
    # celui de la DEFINITION. Une definition inline peut etre incluse en bloc et
    # reciproquement : ce sont deux mesures differentes sous un mot voisin.
    #
    # Second point ouvert de l'etape 4, note ici et non traite : `unresolved` de ce meme
    # schema est en `additionalProperties: false`, donc sans place pour le constat de
    # scission. Le cache n'est pas ecrit par ce module ; c'est un patch de contrat, pas
    # un commit de code.
    #
    # Retrouver la mesure « 44 sur 45 » du §1.9 demandera de lire statut ET substitution :
    # `substitution: "inline"` couvre aussi les inclusions inline NON RESOLUES, qui n'ont
    # rien substitue mais dont le marqueur est reste en place.

    def _consigne(self, mecanisme, cle, statut, hors_perimetre, ou, forme=FORME_BLOC,
                  node=None, page_id=None):
        fait = {"mecanisme": mecanisme, "cle": cle, "statut": statut,
                "source_hors_perimetre": hors_perimetre, "emplacement": ou,
                "forme": forme}
        # Jointure du collecteur de faits (contracts/faits.md §1) : la page qui PORTE le
        # noeud d'inclusion — la page source quand l'inclusion est dans un contenu
        # injecte — et le localId du noeud, en champs structures plutot que relus dans
        # le texte de `emplacement`. Cle absente si le noeud n'a pas de localId.
        if page_id is not None:
            fait["page_id"] = str(page_id)
        local_id = ((node or {}).get("attrs") or {}).get("localId")
        if local_id:
            fait["local_id"] = local_id
        if forme == FORME_INLINE:
            fait["substitution"] = SUBSTITUTION_INLINE
        self.faits.append(fait)
        return fait

    def _consigne_hote_scinde(self, conteneur, fait):
        """Un hote scinde qui n'est pas un `paragraph` : le cas n'est pas mesure.

        Aucune occurrence sur les 9 fixtures — les 5 inclusions inline du corpus dore
        ont toutes un `paragraph` pour parent direct. Le consigner le rend visible au
        lieu d'etre devine dans un rendu. Le niveau document entre ici aussi : un `doc`
        ne se scinde pas, ses blocs sont deposes a plat — mais il se consigne comme les
        autres, sans quoi le seul cas non couvert serait le seul cas muet.

        POINT OUVERT DE L'ETAPE 4 : resout() ne rend pas cette liste, donc le fait
        n'atteint aujourd'hui aucun consommateur. Zero occurrence au corpus : ca ne
        bloque pas, ca reste a brancher au rapport de run.
        """
        self.hotes_scindes.append({"type": conteneur.get("type"),
                                   "emplacement": fait.get("emplacement")})

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
        self.hotes_scindes = []
        self.indexe_page(pid, titre, adf)
        guard = guard if guard is not None else mx.CycleGuard(self.profondeur_max)
        resolu = dict(adf)
        enfants = self._transforme(adf.get("content") or [], titre, pid, guard)
        resolu["content"] = self._assemble_liste(resolu, enfants)
        # Invariant interne : une enveloppe qui survit au parcours signale un conteneur
        # qui ne l'a pas consommee. Elle LEVE — un ADF portant un dictionnaire sans
        # `type` casserait le renderer bien plus loin, sans dire pourquoi.
        if _contient_echappement(resolu):
            raise mx.ResolutionError(
                f"enveloppe de scission non consommee sur la page {pid} : un conteneur "
                f"n'assemble pas ses enfants par _assemble()")
        return resolu, list(self.faits)

    def _transforme(self, noeuds, titre, page_id, guard):
        sortie = []
        for node in noeuds:
            sortie.extend(self._transforme_noeud(node, titre, page_id, guard))
        return sortie

    # ------------------------------------------------------------------
    # Assemblage d'un conteneur — c'est ici que la scission se produit
    # ------------------------------------------------------------------

    def _assemble(self, conteneur, enfants):
        """Rend la LISTE de noeuds qui remplace `conteneur`, ses enfants transformes.

        Sans enveloppe — le cas de tous les noeuds du corpus a une exception pres —
        c'est une copie du conteneur, exactement comme avant. Avec, le conteneur est
        decoupe sur les enveloppes : les suites de noeuds restants sont reenveloppees
        dans une copie, les blocs deposes entre elles. UN MORCEAU VIDE NE PRODUIT PAS DE
        CONTENEUR VIDE — une inclusion seule dans son paragraphe n'emet pas de
        paragraphe vide avant ni apres.
        """
        if not any(_est_echappement(enfant) for enfant in enfants):
            copie = dict(conteneur)
            copie["content"] = enfants
            return [copie]

        sortie, courant = [], []
        for enfant in enfants:
            if not _est_echappement(enfant):
                courant.append(enfant)
                continue
            if conteneur.get("type") != "paragraph":
                self._consigne_hote_scinde(conteneur, enfant["fait"])
            if courant:
                sortie.append(dict(conteneur, content=courant))
                courant = []
            sortie.extend(enfant[CLE_ECHAPPEMENT])
        if courant:
            sortie.append(dict(conteneur, content=courant))
        return sortie

    def _assemble_liste(self, conteneur, enfants):
        """Assemble une liste de BLOCS : les enveloppes y sont depliees, pas scindees.

        Un `doc` ne se scinde pas en deux `doc` — il n'y a pas de phrase a couper au
        premier niveau. L'hote est consigne quand meme : sans cela, le seul cas non
        couvert serait le seul cas muet.
        """
        for enfant in enfants:
            if _est_echappement(enfant):
                self._consigne_hote_scinde(conteneur, enfant["fait"])
        return _deplie(enfants)

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
            return self._assemble(node, self._transforme(node.get("content") or [],
                                                         titre, page_id, guard))

        # 2b. Inclusion : resoudre, puis redescendre dans l'injecte.
        if nature == "sync_include":
            return self._resout_sync(node, titre, page_id, guard)
        if nature and nature.endswith("_include"):
            return self._resout_macro(node, titre, page_id, guard)

        # 2c. Noeud ordinaire.
        if isinstance(node.get("content"), list):
            return self._assemble(node, self._transforme(node["content"], titre,
                                                         page_id, guard))
        return [dict(node)]

    def _injecte(self, definition, mecanisme, cle, guard):
        """Corps d'une definition, resolu a son tour, sous garde-fou de cycle.

        Le contexte de page devient celui de la page SOURCE : une inclusion logee dans
        un corps de definition et sans parametre de page vise la page qui la definit,
        pas celle qui la consomme.
        """
        corps = copy.deepcopy(definition["node"].get("content") or [])
        with guard.enter(mecanisme, cle):
            injecte = self._transforme(corps, definition["page_title"],
                                       definition["page_id"], guard)
        # Un corps de definition est une liste de BLOCS : une enveloppe qui y remonte
        # s'y deplie. La scission a deja eu lieu plus bas, dans le paragraphe concerne.
        return _deplie(injecte)

    def _depose(self, injecte, nom, page_source, inline, fait):
        """Contenu resolu encadre de ses marqueurs, dans la forme que l'hote autorise.

        Table du §1.9 : un seul `paragraph` ne portant que de l'inline se depose EN
        PLACE, marks comprises ; tout le reste scinde l'hote et se rend en forme de
        bloc, avec constat. La scission n'est pas decidee ici — elle est demandee par
        l'enveloppe, et executee par le conteneur qui l'assemble.
        """
        ouvrant = libelle_ouvrant(nom, page_source)
        fermant = libelle_fermant(nom)
        if not inline:
            return [marqueur_bloc(ouvrant)] + injecte + [marqueur_bloc(fermant)]
        if _qualifie_inline(injecte):
            return ([_texte_em(ouvrant)] + list(injecte[0].get("content") or [])
                    + [_texte_em(fermant)])
        fait["substitution"] = SUBSTITUTION_SCINDEE
        return [_echappement(
            [marqueur_bloc(ouvrant)] + injecte + [marqueur_bloc(fermant)], fait)]

    def _resout_macro(self, node, titre, page_id, guard):
        famille = mx.famille_macro(node)
        mecanisme = MECANISME_PAR_FAMILLE[famille]
        cle = mx.macro_include_key(node, titre)
        cible, nom = cle[0], cle[1] or NOM_AFFICHE_PAR_DEFAUT   # libelle seulement
        ou = mx.emplacement(node, page_id, titre)
        hors = self._hors_perimetre_titre(cible)
        # La FORME est celle du noeud d'inclusion, decidee avant toute resolution : un
        # marqueur de non-resolution la suit aussi. Une inclusion inline introuvable
        # laisse un marqueur inline, jamais un paragraphe qui couperait la phrase.
        inline = mx.est_inclusion_inline(node)
        forme = FORME_INLINE if inline else FORME_BLOC

        if not self.assure_titre(cible):
            self._consigne(mecanisme, cle, STATUT_PAGE_SOURCE_ABSENTE,
                           hors, ou, forme, node, page_id)
            return [_marqueur(inline, libelle_non_resolue(
                nom, cible, MOTIFS[STATUT_PAGE_SOURCE_ABSENTE]))]

        definition = self.index.resout(node, titre)
        if definition is None:
            self._consigne(mecanisme, cle, STATUT_DEFINITION_ABSENTE,
                           hors, ou, forme, node, page_id)
            motif = (MOTIF_AMBIGUE if self.index.ambigue(node, titre)
                     else MOTIFS[STATUT_DEFINITION_ABSENTE])
            return [_marqueur(inline, libelle_non_resolue(nom, cible, motif))]

        injecte = self._injecte(definition, mecanisme, cle, guard)
        fait = self._consigne(mecanisme, cle, STATUT_RESOLUE, hors, ou, forme,
                              node, page_id)
        return self._depose(injecte, nom, definition["page_title"], inline, fait)

    def _resout_sync(self, node, titre, page_id, guard):
        cle = mx.sync_include_key(node)
        source_id, uuid = cle
        ou = mx.emplacement(node, page_id, titre)
        hors = self._hors_perimetre_id(source_id)
        # Le §1.9 demande le TITRE de la page source, exactement comme une macro. Seule
        # la non-resolution n'en a pas a disposition — la page est absente — et se
        # rabat sur la source DECLAREE, qui pour un syncBlock est un identifiant.
        nom = nom_sync(uuid)

        if not self.assure_identifiant(source_id):
            self._consigne(MECANISME_SYNC, cle, STATUT_PAGE_SOURCE_ABSENTE,
                           hors, ou, FORME_BLOC, node, page_id)
            return [marqueur_bloc(libelle_non_resolue(
                nom, f"page {source_id}", MOTIFS[STATUT_PAGE_SOURCE_ABSENTE]))]

        definition = self.sync.get(cle)
        if definition is None:
            self._consigne(MECANISME_SYNC, cle, STATUT_DEFINITION_ABSENTE,
                           hors, ou, FORME_BLOC, node, page_id)
            return [marqueur_bloc(libelle_non_resolue(
                nom, f"page {source_id}", MOTIFS[STATUT_DEFINITION_ABSENTE]))]

        injecte = self._injecte(definition, MECANISME_SYNC, cle, guard)
        # Un syncBlock n'a pas de forme inline : `syncBlock` est un type de noeud de
        # bloc, et est_inclusion_inline() rend False pour lui.
        fait = self._consigne(MECANISME_SYNC, cle, STATUT_RESOLUE, hors, ou, FORME_BLOC,
                              node, page_id)
        return self._depose(injecte, nom, definition["page_title"], False, fait)


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
