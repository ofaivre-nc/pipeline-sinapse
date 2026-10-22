#!/usr/bin/env python3
"""
Couche graphe — faits de toutes les pages -> faits/graphe.json (contracts/faits.md §6).

VERSION : 1.0 — premiere version, schema 2 du contrat de faits

Le graphe se construit a partir des fichiers de faits, sans relire l'ADF. Il reprend
le modele du JSON carto (notice de cartographie §4 et §8) : toute relation est une
arete, un appel entre SA passe par la RG qui le porte, et un noeud n'existe que si sa
page a ete lue. Une cible absente du corpus reste une chaine dans `vers` et part dans
`hors_corpus` : ce n'est pas une anomalie (decision du 2026-10-21).

Il est reconstruit en entier a chaque run : une page inchangee peut devenir incoherente
parce que sa voisine a change.
"""

import re

VERSION = "1.0"
SCHEMA_VERSION = 2

RE_ROUTE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)$")


def _endpoint(texte):
    """« GET /notes » -> « GET /notes », normalise ; None si ce n'est pas une route."""
    trouve = RE_ROUTE.match(" ".join(str(texte or "").split()))
    return f"{trouve.group(1)} {trouve.group(2)}" if trouve else None


class Graphe:
    def __init__(self, pages):
        """`pages` : liste des faits de page (dictionnaires au format faits/{id}.json)."""
        self.pages = pages
        self.par_id = {f["page"]["id"]: f for f in pages}
        self.noeuds = {"cu": [], "api": [], "endpoint": [], "sa": [], "rg": [], "entite": []}
        self.aretes = []
        self.hors_corpus = []
        self._ids = {}            # type de noeud -> ensemble des id
        self._vus_hors = set()
        self._vues = set()

    # ------------------------------------------------------------------

    def construit(self):
        for faits in self.pages:
            self._noeuds_page(faits)
        for type_, noeuds in self.noeuds.items():
            self._ids[type_] = {n["id"] for n in noeuds}
        for faits in self.pages:
            self._aretes_page(faits)
        return {
            "schema_version": SCHEMA_VERSION,
            "graphe_version": VERSION,
            "pages": len(self.pages),
            "noeuds": self.noeuds,
            "aretes": self.aretes,
            "hors_corpus": self.hors_corpus,
        }

    def _base(self, faits, ident):
        page = faits["page"]
        noeud = {"id": ident, "page_id": page["id"], "url": page.get("url")}
        if page.get("module"):
            noeud["sf"] = page["module"]
        return {k: v for k, v in noeud.items() if v is not None}

    def _noeuds_page(self, faits):
        type_ = faits["page"]["type"]
        titre = faits["page"]["titre"]
        if type_ == "CU":
            self.noeuds["cu"].append(self._base(faits, titre))
        elif type_ == "SA":
            self.noeuds["sa"].append(self._base(faits, titre))
        elif type_ == "API":
            self.noeuds["api"].append(self._base(faits, titre))
            for ligne in faits.get("routes", []):
                ident = _endpoint(f"{ligne.get('verbe', '')} {ligne.get('chemin', '')}")
                if ident and not ligne.get("barre"):
                    noeud = self._base(faits, ident)
                    noeud["api"] = titre
                    self.noeuds["endpoint"].append(noeud)
        elif type_ in ("RG", "GENERIQUE"):
            for regle in faits.get("regles", []):
                noeud = self._base(faits, regle["nom"])
                noeud["page"] = titre
                self.noeuds["rg"].append(noeud)
        elif type_ == "MCD":
            for entite in faits.get("entites", []):
                self.noeuds["entite"].append(self._base(faits, entite["nom"]))

    # ------------------------------------------------------------------

    def _arete(self, de, vers, type_, faits, ou, type_cible=None, **autres):
        # Une arete par (de, vers, type) et par page source : une RG qui cite deux fois
        # la meme route n'appelle pas deux fois. Le premier emplacement est garde.
        cle = (de, vers, type_, faits["page"]["id"])
        if cle in self._vues:
            return
        self._vues.add(cle)
        arete = {"de": de, "vers": vers, "type": type_,
                 "source": {"page_id": faits["page"]["id"], "ou": ou}}
        arete.update({k: v for k, v in autres.items() if v is not None})
        self.aretes.append(arete)
        if type_cible and vers not in self._ids.get(type_cible, set()):
            cle = (vers, type_, faits["page"]["id"])
            if cle not in self._vus_hors:
                self._vus_hors.add(cle)
                self.hors_corpus.append({"vers": vers, "type": type_,
                                         "page_id": faits["page"]["id"]})

    def _titre_page(self, lien):
        """Titre de la page visee par un lien, si elle est dans le corpus."""
        cible = lien.get("cible", {})
        page = self.par_id.get(cible.get("page_id"))
        return page["page"]["titre"] if page else None

    def _aretes_page(self, faits):
        type_ = faits["page"]["type"]
        titre = faits["page"]["titre"]

        # reference : tableau des regles (CU) ou §5 (SA) — seule source des aretes vers
        # les RG (decision heritee de la notice de cartographie).
        if type_ in ("CU", "SA"):
            for ligne in faits.get("regles", []):
                for inclusion in ligne["cellules"].get("regle", {}).get("inclusions", []):
                    self._arete(titre, inclusion["nom"], "reference", faits, ligne["ou"], "rg")

        if type_ == "API":
            for ligne in faits.get("routes", []):
                ident = _endpoint(f"{ligne.get('verbe', '')} {ligne.get('chemin', '')}")
                if not ident or ligne.get("barre"):
                    continue
                cellule = ligne["cellules"].get("sa", {})
                cibles = [self._titre_page(l) or l["texte"] for l in cellule.get("liens", [])]
                if not cibles:
                    cibles = [c["code"] for c in cellule.get("citations", []) if c["type"] == "SA"]
                for cible in dict.fromkeys(cibles):
                    etat = next((l.get("etat") for l in cellule.get("liens", [])
                                 if l.get("etat")), None)
                    self._arete(ident, cible, "expose", faits, ligne["ou"], "sa",
                                confiance="lien_brouillon_non_resolu" if etat else None)

        if type_ in ("RG", "GENERIQUE"):
            for regle in faits.get("regles", []):
                self._appels(regle["nom"], regle.get("corps", {}), faits, regle["ou"])

        if type_ == "CU":
            for lien in faits.get("liens", []):
                ident = _endpoint(lien.get("texte"))
                if ident:
                    self._arete(titre, ident, "appelle", faits, lien["ou"], "endpoint")

        for inclusion in faits.get("inclusions", []):
            self._arete(titre, inclusion["nom"], "inclut", faits, inclusion["ou"],
                        page_source=inclusion.get("page_source"), statut=inclusion.get("statut"))
        for lien in faits.get("liens", []):
            cible = lien.get("cible", {})
            if cible.get("type") != "page":
                continue
            vers = self._titre_page(lien)
            if vers:
                self._arete(titre, vers, "lien", faits, lien["ou"])
            elif cible.get("page_id"):
                cle = (cible["page_id"], "lien", faits["page"]["id"])
                if cle not in self._vus_hors:
                    self._vus_hors.add(cle)
                    self.hors_corpus.append({"vers": lien["texte"], "page_id_cible": cible["page_id"],
                                             "type": "lien", "page_id": faits["page"]["id"]})

    def _appels(self, rg, corps, faits, ou):
        """RG -> endpoint (lien dont le texte est une route) et RG -> SA (lien vers un SA)."""
        for lien in corps.get("liens", []):
            ident = _endpoint(lien.get("texte"))
            if ident:
                self._arete(rg, ident, "appelle", faits, ou, "endpoint")
                continue
            titre = self._titre_page(lien)
            page = self.par_id.get(lien.get("cible", {}).get("page_id"))
            if page and page["page"]["type"] == "SA":
                self._arete(rg, titre, "appelle", faits, ou, "sa")
            elif not page and str(lien.get("texte", "")).startswith("SA-"):
                self._arete(rg, lien["texte"], "appelle", faits, ou, "sa")


def construit_graphe(pages):
    return Graphe(pages).construit()
