#!/usr/bin/env python3
"""
Tests de la chaine minimale : graphe (graphe.py) et run incremental (main.py).

Point d'entree autonome : `python pipeline/tests/test_main.py`, sans rien installer.
"""

import json
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "src"))
sys.path.insert(0, str(ICI))

import main as mn  # noqa: E402
from test_faits import check, definition, doc, inclusion, para, table, titre, txt  # noqa: E402

BASE = "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/"


def corpus():
    """Quatre pages : un CU inclut une RG qui appelle une route, exposee par une API vers un SA."""
    rg = doc(titre(3, "RG-X-CREER"),
             definition("RG-X-CREER", para(txt("Règle RG-X-CREER", "strong")),
                        para(txt("Appeler "), txt("POST /x", href=BASE + "4"),
                             txt(" puis "), txt("SA-X-CONTROLER", href=BASE + "999"))))
    cu = doc(titre(1, "Règles"), table(["Description"], [inclusion("RG-X-CREER", "SF-X: Règles de gestion consolidées", "l1")]))
    api = doc(titre(1, "1. Inventaire des routes"),
              table(["Route", "SA associés"], ["POST /x", para(txt("SA-X-CREER", href=BASE + "3"))]))
    sa = doc(titre(1, "5. Règles de gestion"), table(["Règle"], [inclusion("RG-X-CREER", "SF-X: Règles de gestion consolidées", "l2")]))
    pages = [("1", "SF-X: Règles de gestion consolidées", "RG", rg), ("2", "CU-X-CREER", "CU", cu),
             ("3", "SA-X-CREER", "SA", sa), ("4", "API-X", "API", api)]
    return pages


def ecrit_corpus(dossier, pages, versions):
    adf = Path(dossier) / "adf"
    adf.mkdir(exist_ok=True)
    for page_id, _, _, contenu in pages:
        (adf / f"{page_id}.json").write_text(json.dumps(contenu), encoding="utf-8")
    meta = {"pages": [{"id": p[0], "titre": p[1], "type": p[2], "version": versions[p[0]]}
                      for p in pages]}
    (Path(dossier) / "pages.json").write_text(json.dumps(meta), encoding="utf-8")
    return adf, Path(dossier) / "pages.json"


def verifie_run_et_graphe():
    echecs = 0
    pages = corpus()
    versions = {"1": 5, "2": 3, "3": 2, "4": 7}
    with tempfile.TemporaryDirectory() as dossier:
        adf, meta = ecrit_corpus(dossier, pages, versions)
        sortie = Path(dossier) / "faits"
        rapport = mn.execute(adf, meta, sortie)
        echecs += check(len(rapport["relues"]) == 4 and not rapport["echecs"], f"{rapport}")

        graphe = json.loads((sortie / "graphe.json").read_text(encoding="utf-8"))
        aretes = {(a["de"], a["type"], a["vers"]) for a in graphe["aretes"]}
        attendues = {("CU-X-CREER", "reference", "RG-X-CREER"),
                     ("SA-X-CREER", "reference", "RG-X-CREER"),
                     ("RG-X-CREER", "appelle", "POST /x"),
                     ("RG-X-CREER", "appelle", "SA-X-CONTROLER"),
                     ("POST /x", "expose", "SA-X-CREER")}
        echecs += check(attendues <= aretes, f"aretes manquantes : {attendues - aretes}")
        echecs += check({"vers": "SA-X-CONTROLER", "type": "appelle", "page_id": "1"}
                        in graphe["hors_corpus"],
                        f"SA appele hors corpus : {graphe['hors_corpus']}")
        cu = json.loads((sortie / "2.json").read_text(encoding="utf-8"))
        echecs += check(cu["inclusions"][0].get("statut") == "resolue", f"{cu['inclusions']}")

        rapport = mn.execute(adf, meta, sortie)
        echecs += check(rapport["relues"] == [] and rapport["inchangees"] == 4,
                        f"second run : rien a relire, {rapport['relues']}")

        # La page RG change : elle est relue, et les deux pages qui l'incluent aussi.
        versions["1"] = 6
        adf, meta = ecrit_corpus(dossier, pages, versions)
        rapport = mn.execute(adf, meta, sortie)
        relues = {r["id"]: r["motif"] for r in rapport["relues"]}
        echecs += check(relues == {"1": "version modifiee", "2": "inclut une page relue",
                                   "3": "inclut une page relue"}, f"dependances : {relues}")

        rapport = mn.execute(adf, meta, sortie, complet=True)
        echecs += check(len(rapport["relues"]) == 4, "--complet relit tout")
    return echecs


def verifie_echec_isole():
    """Une page illisible n'arrete pas le run : faits failed, relue au run suivant."""
    echecs = 0
    pages = corpus()
    with tempfile.TemporaryDirectory() as dossier:
        adf, meta = ecrit_corpus(dossier, pages, {"1": 1, "2": 1, "3": 1, "4": 1})
        (adf / "4.json").write_text("{pas du json", encoding="utf-8")
        sortie = Path(dossier) / "faits"
        rapport = mn.execute(adf, meta, sortie)
        echecs += check([e["id"] for e in rapport["echecs"]] == ["4"], f"{rapport['echecs']}")
        faits = json.loads((sortie / "4.json").read_text(encoding="utf-8"))
        echecs += check(faits["page"]["parse_status"] == "failed" and "erreur" in faits, f"{faits}")
        rapport = mn.execute(adf, meta, sortie)
        echecs += check([r["id"] for r in rapport["relues"]] == ["4"],
                        "une page en echec est retentee au run suivant")
    return echecs


def verifie_arborescence():
    """Module et quartier lus dans l'arborescence ; une page archivee n'a pas de faits."""
    echecs = 0
    pages = [{"id": "10", "titre": "Q-SOCLE", "parent_id": "1474581"},
             {"id": "11", "titre": "SF-X", "parent_id": "10"},
             {"id": "12", "titre": "Réflexion sur les écrans", "parent_id": "11"},
             {"id": "13", "titre": "Archive CU-X-ANCIEN", "parent_id": "11"},
             {"id": "14", "titre": "CU-X-ANCIEN-DETAIL", "parent_id": "13"}]
    inventaire = mn.classe(pages)
    echecs += check(inventaire["12"].get("module") == "X" and inventaire["12"].get("quartier") == "Q-SOCLE",
                    f"module et quartier par l'arborescence : {inventaire['12']}")
    echecs += check(inventaire["13"]["excluded"] and inventaire["14"]["excluded"],
                    "exclusion par prefixe, heritee par le sous-arbre")

    with tempfile.TemporaryDirectory() as dossier:
        adf = Path(dossier) / "adf"
        adf.mkdir()
        for page in pages:
            (adf / f"{page['id']}.json").write_text(json.dumps(doc(para(txt("x")))), encoding="utf-8")
        meta = Path(dossier) / "recensement_pages.json"
        meta.write_text(json.dumps({"pages_analysees": [
            {"id": p["id"], "title": p["titre"], "version": 1, "parent_id": p["parent_id"]} for p in pages]}),
            encoding="utf-8")
        rapport = mn.execute(adf, meta, Path(dossier) / "faits")
        echecs += check(sorted(e["id"] for e in rapport["exclues"]) == ["13", "14"], f"{rapport['exclues']}")
        faits = json.loads((Path(dossier) / "faits" / "12.json").read_text(encoding="utf-8"))
        echecs += check(faits["page"].get("quartier") == "Q-SOCLE", f"{faits['page']}")
    return echecs


def verifie_projections():
    """Heuristique RG -> entite (procedure carto §2.6) et fusion du JSON MCD."""
    import projections as pj
    echecs = 0
    entites = {"Note", "Personne"}
    regle = {"nom": "RG-X-PERSISTENCE-CREATION",
             "corps": {"texte": "Note.noteId = attribue\nNote.contenu = saisi\nNoteReponse.id = x"}}
    categorie, confiance, champs = pj.classe_regle(regle, entites, False)
    echecs += check(categorie == "persistance_creation" and confiance == "heuristique_v0_forte_nom_rg"
                    and champs == [("Note", "noteId", "ecriture"), ("Note", "contenu", "ecriture")],
                    f"PERSISTENCE compte comme PERSISTANCE, DTO ecarte : {categorie} {champs}")
    regle = {"nom": "RG-X-ENTITES-RECHERCHER", "corps": {"texte": "Note.personneId = personneId\nretourne Note.contenu"}}
    _, _, champs = pj.classe_regle(regle, entites, False)
    echecs += check(champs == [("Note", "personneId", "lecture_critere"), ("Note", "contenu", "lecture")],
                    f"recherche : critere, pas ecriture : {champs}")
    categorie, _, champs = pj.classe_regle({"nom": "RG-X-VERIFIER", "corps": {"texte": "appel du SA"}},
                                           entites, True)
    echecs += check(categorie == "controle_integrite" and champs == [], f"{categorie}")
    # Forme reconnue par la visualisation carto_sinapse_*.html : « SF.ENTITE » en capitales.
    echecs += check(pj.id_entite("TypeNote", {"TypeNote": "NOTE"}) == "NOTE.TYPENOTE"
                    and pj.id_entite("Inconnue", {}) == "MCD.INCONNUE", "identifiant d'entite du JSON carto")

    precedent = {"quartiers": [{"id": "Q", "sfs": [{"id": "X", "jiraTickets": [{"code": "REC-1"}]}]}],
                 "entities": [{"id": "Vieille", "sf": "X", "attrs": []}, {"id": "Autre", "sf": "Y", "attrs": []}],
                 "relations": [{"from": "Vieille", "to": "Autre"}, {"from": "Autre", "to": "Tierce"}]}
    mcd_page = {"page": {"id": "9", "titre": "SF-X: Modélisation des données", "type": "MCD", "module": "X",
                         "url": "u"},
                "entites": [{"nom": "Neuve", "attributs": []}],
                "relations": [{"de": "Neuve", "vers": "Autre", "card_de": "1..1", "card_vers": "0..N"}]}
    resultat = pj.fusionne_mcd(precedent, [mcd_page])
    echecs += check(sorted(e["id"] for e in resultat["entities"]) == ["Autre", "Neuve"],
                    f"entites du SF relu remplacees : {resultat['entities']}")
    echecs += check(sorted((r["from"], r["to"]) for r in resultat["relations"])
                    == [("Autre", "Tierce"), ("Neuve", "Autre")], f"{resultat['relations']}")
    sf = resultat["quartiers"][0]["sfs"][0]
    echecs += check(sf["jiraTickets"] == [{"code": "REC-1"}] and sf["confluencePage"]["url"] == "u",
                    "tickets conserves, page Confluence mise a jour")
    return echecs


def verifie_md():
    """--md : un .md par page, frontmatter du contrat, contenu reutilise resolu, write-if-changed."""
    echecs = 0
    pages = corpus()
    with tempfile.TemporaryDirectory() as dossier:
        adf, meta = ecrit_corpus(dossier, pages, {"1": 1, "2": 1, "3": 1, "4": 1})
        sortie, md = Path(dossier) / "faits", Path(dossier) / "md"
        rapport = mn.execute(adf, meta, sortie, md=md)
        fichiers = sorted(p.name for p in md.rglob("*.md"))
        echecs += check(rapport["md_ecrits"] == 4 and fichiers == ["API-X.md", "CU-X-CREER.md",
                                                                    "SA-X-CREER.md",
                                                                    "SF-X-Regles-de-gestion-consolidees.md"],
                        f"un .md par page : {fichiers}")
        texte = next(md.rglob("CU-X-CREER.md")).read_text(encoding="utf-8")
        echecs += check(texte.startswith('---\npage_id: "2"\npage_title: "CU-X-CREER"'),
                        f"frontmatter du contrat : {texte[:80]!r}")
        echecs += check("↳ inclusion : RG-X-CREER" in texte and "POST /x" in texte,
                        "le contenu de la RG incluse est rendu, encadre de ses marqueurs")
        rapport = mn.execute(adf, meta, sortie, md=md)
        echecs += check(rapport["md_ecrits"] == 0 and rapport["relues"] == [],
                        "second passage : rien a relire ni a reecrire")
        next(md.rglob("API-X.md")).unlink()
        rapport = mn.execute(adf, meta, sortie, md=md)
        echecs += check([r["motif"] for r in rapport["relues"]] == ["md absent"], f"{rapport['relues']}")
    return echecs


VERIFICATIONS = (verifie_run_et_graphe, verifie_echec_isole, verifie_arborescence, verifie_projections,
                 verifie_md)


def test_main():
    echecs = sum(v() for v in VERIFICATIONS)
    assert echecs == 0, f"{echecs} echec(s)"


if __name__ == "__main__":
    total = sum(v() for v in VERIFICATIONS)
    if total:
        print(f"ECHEC - {total} verification(s) en echec")
        sys.exit(1)
    print("OK - toutes les verifications de main et du graphe passent")
