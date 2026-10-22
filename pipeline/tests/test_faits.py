#!/usr/bin/env python3
"""
Tests du collecteur de faits (pipeline/src/faits.py), contrat contracts/faits.md.

Point d'entree autonome : `python pipeline/tests/test_faits.py`, sans rien installer.
Aucune fonctionnalite propre a pytest : seules les fonctions test_* sont collectees,
les auxiliaires s'appellent verifie_*.
"""

import json
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "src"))

import faits as fx  # noqa: E402

FIXTURES = ICI.parent / "fixtures"


# ==========================================================================
# Fabrication d'ADF
# ==========================================================================

def txt(texte, *marks, href=None, couleur=None):
    liste = [{"type": m} for m in marks]
    if href:
        liste.append({"type": "link", "attrs": {"href": href}})
    if couleur:
        liste.append({"type": "textColor", "attrs": {"color": couleur}})
    noeud = {"type": "text", "text": texte}
    if liste:
        noeud["marks"] = liste
    return noeud


def para(*enfants):
    return {"type": "paragraph", "content": list(enfants)}


def titre(niveau, texte):
    return {"type": "heading", "attrs": {"level": niveau}, "content": [txt(texte)]}


def cellule(*enfants):
    return {"type": "tableCell", "content": [para(*e) if isinstance(e, tuple) else e
                                             for e in enfants] or [para()]}


def table(*lignes):
    rangees = []
    for ligne in lignes:
        cellules = []
        for valeur in ligne:
            if isinstance(valeur, str):
                cellules.append(cellule(para(txt(valeur)) if valeur else para()))
            else:
                cellules.append(cellule(valeur))
        rangees.append({"type": "tableRow", "content": cellules})
    return {"type": "table", "content": rangees}


def inclusion(nom, page, local_id=None):
    attrs = {"extensionKey": "excerpt-include", "extensionType": "com.atlassian.confluence.macro.core",
             "parameters": {"macroParams": {"name": {"value": nom}, "": {"value": page}}}}
    if local_id:
        attrs["localId"] = local_id
    return {"type": "extension", "attrs": attrs}


def definition(nom, *corps):
    return {"type": "bodiedExtension",
            "attrs": {"extensionKey": "excerpt", "localId": "def-" + nom.strip(),
                      "parameters": {"macroParams": {"name": {"value": nom}}}},
            "content": list(corps)}


def colonnes(*cols):
    return {"type": "layoutSection",
            "content": [{"type": "layoutColumn", "content": list(c)} for c in cols]}


def doc(*blocs):
    return {"type": "doc", "version": 1, "content": list(blocs)}


ECHECS = []


def check(condition, message):
    if not condition:
        ECHECS.append(message)
        print("ECHEC :", message)
    return 0 if condition else 1


def collecte(adf, type_page, titre_page="PAGE-TEST", faits_resolver=None, titres=None):
    return fx.Collecteur(titres_par_id=titres or {}).collecte(
        adf, {"id": "100", "titre": titre_page, "type": type_page}, faits_resolver,
        maintenant="2026-10-22T00:00:00Z")


def nulls(valeur, chemin="faits"):
    if valeur is None:
        return [chemin]
    if isinstance(valeur, dict):
        return [n for k, v in valeur.items() for n in nulls(v, f"{chemin}.{k}")]
    if isinstance(valeur, list):
        return [n for i, v in enumerate(valeur) for n in nulls(v, f"{chemin}[{i}]")]
    return []


# ==========================================================================
# Verifications
# ==========================================================================

def verifie_normalisation():
    echecs = 0
    echecs += check(fx.reduit("2. Contrat d’entrée") == "2 contrat d'entree", fx.reduit("2. Contrat d’entrée"))
    echecs += check(fx.sans_numero("3.2 Codes retours") == ("3.2", "Codes retours"), "numero")
    echecs += check(fx.correspond("Message (à revoir, fonctionnement)", ["Message*"]), "prefixe *")
    echecs += check(not fx.correspond("Messages", ["Message"]), "egalite stricte sans *")
    echecs += check(fx.normalise_nom(" RG&period;NOTE‑X ") == "RG.NOTE-X",
                    "entites, strip et tiret U+2011")
    return echecs


def verifie_texte():
    """Forme Texte : barre, couleur, liens fusionnes, citations et leur forme."""
    echecs = 0
    lecteur = fx.Lecteur(fx.charge_config(), "100", "PAGE-TEST",
                         titres_par_id={"751173657": "SA-NOTE-CREER"})
    url = "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/751173657"
    t = lecteur.texte(para(txt("Voir "), txt("SA-NOTE", href=url), txt("-CREER", href=url),
                           txt(" puis "), txt("RG-NOTE-X", "strong"), txt(" et "),
                           txt("MSG-NOTE‑INTROUVABLE", "code"), txt(" note:gerer")))
    echecs += check(t["texte"] == "Voir SA-NOTE-CREER puis RG-NOTE-X et MSG-NOTE‑INTROUVABLE note:gerer",
                    f"texte brut conserve : {t['texte']!r}")
    echecs += check(len(t.get("liens", [])) == 1 and t["liens"][0]["texte"] == "SA-NOTE-CREER",
                    f"deux text sous le meme lien = un seul Lien : {t.get('liens')}")
    echecs += check(t["liens"][0]["cible"] == {"type": "page", "page_id": "751173657",
                                               "titre": "SA-NOTE-CREER"}, f"{t['liens'][0]}")
    formes = {(c["type"], c["code"]): c["forme"] for c in t.get("citations", [])}
    echecs += check(formes.get(("SA", "SA-NOTE-CREER")) == "lien", f"SA en lien : {formes}")
    echecs += check(formes.get(("RG", "RG-NOTE-X")) == "gras", f"RG en gras : {formes}")
    echecs += check(formes.get(("MSG", "MSG-NOTE-INTROUVABLE")) == "code",
                    f"MSG en code, tiret replie dans le code : {formes}")
    echecs += check(formes.get(("HAB", "note:gerer")) == "prose", f"habilitation : {formes}")
    echecs += check("barre" not in t and "couleur" not in t, "ni barre ni couleur partiels")

    barre = lecteur.texte(para(txt("GET /notes", "strike", couleur="#ff5630")))
    echecs += check(barre.get("barre") is True and barre.get("couleur") == "#ff5630",
                    f"tout barre et colore : {barre}")
    partiel = lecteur.texte(para(txt("GET /notes", "strike"), txt(" en cours")))
    echecs += check("barre" not in partiel, "barre seulement si TOUT est barre")
    return echecs


def verifie_liens():
    echecs = 0
    lecteur = fx.Lecteur(fx.charge_config(), "100", "PAGE-TEST")
    base = "https://sinapse-gie-nc.atlassian.net"
    cas = {
        f"{base}/wiki/pages/resumedraft.action?draftId=123": ("page", "brouillon"),
        f"{base}/wiki/spaces/SINAPSE/pages/edit-v2/380567556": ("page", "edition"),
        f"{base}/browse/REC-2231": ("jira", None),
        "https://www.example.org/x": ("externe", None),
    }
    for url, (type_, etat) in cas.items():
        lien = lecteur.lien(url, "t", "lien")
        echecs += check(lien["cible"]["type"] == type_ and lien.get("etat") == etat,
                        f"{url} -> {lien}")
    court = lecteur.lien(f"{base}/wiki/x/KwCcL", None, "carte")
    echecs += check(court["cible"].get("page_id") == "748421163",
                    f"lien court de 5 caracteres decode : {court}")
    echecs += check(court["texte"] == f"{base}/wiki/x/KwCcL",
                    "carte vers une page hors inventaire : le texte est l'URL")
    return echecs


def verifie_absent_et_vide():
    """Section absente = cle absente ; section presente sans contenu = liste vide."""
    echecs = 0
    adf = doc(titre(1, "1. But & scénarios"), titre(2, "1.2 Scénarios"),
              titre(1, "2. Contrat d'entrée"),
              table(["Attribut", "Description", "Obligatoire"], ["id", "Identifiant", "Oui"]),
              titre(1, "3. Contrat de sortie"), titre(2, "3.2 Codes retours"),
              titre(1, "4. Traitement"), para(txt("Contrôles", "strong")),
              para(txt("Retourner MSG-X-VALIDATION-A")),
              titre(1, "5. Règles de gestion"))
    faits = collecte(adf, "SA", "SA-TEST-CREER")
    echecs += check(faits.get("scenarios") == [], f"section presente vide : {faits.get('scenarios')}")
    echecs += check(faits.get("codes") == [], "codes : section presente, sans tableau")
    echecs += check("objet_restitue" not in faits, "3.1 absent : cle absente")
    echecs += check(faits["contrat_entree"][0]["cellules"]["obligatoire"]["texte"] == "Oui",
                    f"{faits['contrat_entree']}")
    etapes = faits["traitement"].get("etapes", [])
    echecs += check([e["titre"] for e in etapes] == ["Contrôles"], f"etapes : {etapes}")
    echecs += check(etapes and etapes[0]["texte"]["citations"][0]["code"] == "MSG-X-VALIDATION-A",
                    f"citation MSG de l'etape : {etapes}")
    echecs += check(faits["page"]["parse_status"] == "ok", f"{faits['inconnus']}")
    echecs += check(nulls(faits) == [], f"aucun null : {nulls(faits)}")
    return echecs


def verifie_inconnus():
    """Rien ne disparait en silence : colonne, section et section manquante signalees."""
    echecs = 0
    adf = doc(titre(1, "Description"), para(txt("Un CU.")),
              titre(1, "Fonctionnement nominal"),
              table(["N°", "Activité élémentaire", "Commentaire libre"], ["1", "Ouvrir", "x"]),
              titre(1, "Variantes exotiques"))
    faits = collecte(adf, "CU", "CU-TEST")
    quoi = sorted((i["quoi"], i["valeur"]) for i in faits["inconnus"])
    echecs += check(("colonne", "Commentaire libre") in quoi, f"colonne inconnue : {quoi}")
    echecs += check(("section", "Variantes exotiques") in quoi, f"section inconnue : {quoi}")
    echecs += check(("section_manquante", "ihm") in quoi and ("section_manquante", "regles") in quoi,
                    f"sections attendues manquantes : {quoi}")
    echecs += check(faits["page"]["parse_status"] == "partial", "partial si inconnus")
    ligne = faits["nominal"][0]
    echecs += check(ligne["autres"]["Commentaire libre"]["texte"] == "x",
                    f"la cellule d'une colonne inconnue est gardee : {ligne}")
    return echecs


def verifie_cartouche():
    echecs = 0
    adf = doc(colonnes([para(txt("Quartier : Q-SERV")), para(txt("Service fonctionnel : SF-NOTE")),
                        para(txt("Lien vers la tâche de test",
                                 href="https://sinapse-gie-nc.atlassian.net/browse/REC-95"))],
                       [para(txt("Habilitation :"))], [para(txt("note:gerer"))]),
              titre(1, "Description"))
    faits = collecte(adf, "CU", "CU-TEST")
    cartouche = faits.get("cartouche", {})
    echecs += check(cartouche.get("quartier", {}).get("texte") == "Q-SERV", f"{cartouche}")
    echecs += check(cartouche.get("sf", {}).get("texte") == "SF-NOTE", f"{cartouche}")
    echecs += check(cartouche.get("habilitation", {}).get("texte") == "note:gerer",
                    f"valeur dans la colonne suivante : {cartouche}")
    echecs += check(cartouche.get("lien_test", {}).get("cible", {}).get("ticket") == "REC-95",
                    f"{cartouche}")
    return echecs


def verifie_inclusions_et_definitions():
    echecs = 0
    adf = doc(titre(1, "Règles"), table(["Description"], [inclusion(" RG-A", "SF-X: Règles", "l1")],
                                        [inclusion("RG-B", "SF-X: Règles", "l2")]))
    resolver = [{"statut": "resolue", "page_id": "100", "local_id": "l1"},
                {"statut": "definition_absente", "page_id": "100", "local_id": "l2"},
                {"statut": "resolue", "page_id": "999", "local_id": "l2"}]
    faits = collecte(adf, "CU", "CU-TEST", faits_resolver=resolver)
    inclusions = {i["nom"]: i for i in faits["inclusions"]}
    echecs += check(inclusions["RG-A"]["nom_brut"] == " RG-A", "nom brut garde l'espace (K55)")
    echecs += check(inclusions["RG-A"]["statut"] == "resolue", f"{inclusions['RG-A']}")
    echecs += check(inclusions["RG-B"]["statut"] == "definition_absente",
                    "jointure par (page_id, local_id) : le fait d'une autre page est ignore")
    echecs += check(faits["regles"][0]["cellules"]["regle"]["texte"] == "{inclusion:RG-A}",
                    f"{faits['regles'][0]}")

    rg = doc(titre(2, "Persistance"), titre(3, "RG-X-PERSISTANCE-CREATION"),
             definition("RG-X-PERSISTENCE-CREATION",
                        para(txt("Règle", "strong"), txt(" RG-X-PERSISTANCE-CREATION concernant la création")),
                        para(txt("Retourner MSG-X-CONFLIT-A"))))
    faits = collecte(rg, "RG", "SF-X: Règles de gestion consolidées")
    regle = faits["regles"][0]
    echecs += check(regle["nom"] == "RG-X-PERSISTENCE-CREATION"
                    and regle["code_titre"] == "RG-X-PERSISTANCE-CREATION"
                    and regle["titre_section"] == "RG-X-PERSISTANCE-CREATION"
                    and regle["groupe"] == "Persistance", f"nom, titre et code distincts : {regle}")
    echecs += check(regle["titre_gras"] == "Règle" and regle["concernant"] == "la création",
                    f"gras partiel, titre lu dans le paragraphe : {regle}")
    echecs += check(any(c["code"] == "MSG-X-CONFLIT-A" for c in regle["corps"].get("citations", [])),
                    "citations MSG du corps (K29)")
    echecs += check("tableaux" not in regle["corps"], "corps sans tableau : cle absente")
    echecs += check(faits["definitions"][0]["titre_section"] == "RG-X-PERSISTANCE-CREATION",
                    f"{faits['definitions']}")

    rg = doc(titre(3, "RG-X-FILTRE"),
             definition("RG-X-FILTRE", para(txt("Règle RG-X-FILTRE concernant le filtre", "strong")),
                        table(["Attributs du DTO XRequete", "Alimentation"], ["XRequete.page", "15"])),
             para(txt("Voir RG-PATTERN.BARRE-Highlight.Actif. Puis la suite.")))
    faits = collecte(rg, "RG", "SF-X: Règles de gestion consolidées")
    tableaux = faits["regles"][0]["corps"].get("tableaux")
    echecs += check(tableaux == [{"rang": 1, "entetes": ["Attributs du DTO XRequete", "Alimentation"],
                                  "lignes": [["XRequete.page", "15"]]}], f"tableaux du corps (K65) : {tableaux}")
    codes = {c["code"] for t in faits["textes"] for c in t.get("citations", []) if c["type"] == "RG"}
    echecs += check("RG-PATTERN.BARRE-Highlight.Actif" in codes,
                    f"code de RG a casse mixte lu en entier, sans le point final : {codes}")
    return echecs


def verifie_api():
    echecs = 0
    adf = doc(titre(1, "1. Inventaire des routes"),
              table(["Route", "Objet", "SA associés", "Habilitation requise"],
                    ["PUT /admin/actualites/{id}", "Modifier", "SA-X.MODIFIER", "actualite:gerer"]),
              titre(1, "2. Catalogue DTO"),
              table(["Attribut (nom court)", "ActualiteRequete", "ActualiteReponse"],
                    ["titre", "R", "✓"], ["data", "O", "R - ActualiteReponse[]"]),
              titre(1, "3. Mapping DTO ↔ contrat d’entrée SA"),
              table(["Élément du DTO", "SA-X.MODIFIER", "Nature de l'écart"],
                    ["ActualiteRequete", "Correspondance 1 - 1", "-"],
                    ["version", "version", "Optionnel dans le DTO, obligatoire dans le SA"]))
    faits = collecte(adf, "API", "API-X")
    route = faits["routes"][0]
    echecs += check((route.get("verbe"), route.get("chemin")) == ("PUT", "/admin/actualites/{id}"),
                    f"{route}")
    dtos = {d["nom"]: d for d in faits["dtos"]}
    echecs += check(sorted(dtos) == ["ActualiteReponse", "ActualiteRequete"], "DTO = colonnes")
    data = dtos["ActualiteReponse"]["attributs"][1]
    echecs += check(data["marqueur"] == "R" and data["precision"] == "ActualiteReponse[]", f"{data}")
    mapping = faits["mappings"][0]
    echecs += check(mapping["un_pour_un"] == ["ActualiteRequete"] and len(mapping["lignes"]) == 2
                    and mapping["sa"]["texte"] == "SA-X.MODIFIER", f"{mapping}")
    echecs += check(faits["page"]["parse_status"] == "ok", f"{faits['inconnus']}")
    return echecs


def verifie_mcd():
    echecs = 0
    relations = para(txt("Utilisateur(1,1) ↔︎ (0,N) Favoris"), {"type": "hardBreak"},
                     txt("Utilisateur (1,1) <-> (0,N) Recent (0,N) ↔ (0,1) Personne, lien \"vu\""),
                     {"type": "hardBreak"},
                     txt("La relation Recent ↔ Personne est conceptuelle"))
    adf = doc(titre(1, "Modélisation des données"), relations,
              titre(1, "Inventaire des données"), titre(2, "Propriétés de Favoris"),
              para(txt("Objet permettant de mémoriser les favoris d'un utilisateur.")),
              table(["Nom du champ", "Désignation", "Format", "Lg"],
                    ["Favoris.id", "Identifiant", "UUID", ""],
                    ["Favoris.ordre", "Ordre", "Entier", "3"]),
              titre(2, "Sans préfixe"), table(["Nom du champ", "Désignation"], ["a", "b"]))
    faits = collecte(adf, "MDD", "SF-X: Modélisation des données")
    echecs += check(faits["page"]["type"] == "MCD", "alias MDD -> MCD")
    paires = [(r["de"], r["card_de"], r["card_vers"], r["vers"]) for r in faits["relations"]]
    echecs += check(paires == [("Utilisateur", "1..1", "0..N", "Favoris"),
                               ("Utilisateur", "1..1", "0..N", "Recent"),
                               ("Recent", "0..N", "0..1", "Personne")],
                    f"chainage, cardinalites, dedoublonnage : {paires}")
    echecs += check(faits["relations"][2].get("libelle") == "vu", f"{faits['relations']}")
    entite = faits["entites"][0]
    echecs += check(entite["nom"] == "Favoris" and [a["attribut"] for a in entite["attributs"]]
                    == ["id", "ordre"], f"{entite}")
    echecs += check(entite.get("description", {}).get("texte")
                    == "Objet permettant de mémoriser les favoris d'un utilisateur.",
                    f"description de l'entite, hors tableau (K104) : {entite.get('description')}")
    echecs += check(any(i["valeur"] == "entité sans préfixe commun" for i in faits["inconnus"]),
                    "tableau sans prefixe : inconnu, pas d'entite fausse")
    return echecs


def verifie_tri():
    echecs = 0
    echecs += check(fx._whitelist("Attribut de tri - whitelist : nom, description. Préfixe -") == ["nom", "description"],
                    "whitelist : liste, arret au point")
    echecs += check(fx._whitelist("n’appartient pas à la whitelist (date, auteur)") == ["date", "auteur"],
                    "whitelist entre parentheses")
    echecs += check(fx._whitelist("whitelist dateDebut / dateFin") == ["dateDebut", "dateFin"], "barre oblique")
    echecs += check(fx._whitelist("hors whitelist de RG-COMPTE.UTILISATEUR-FILTRAGE-TRI") is None,
                    "renvoi a une RG : non releve")
    echecs += check(fx._whitelist("n'appartient pas à la whitelist") is None, "whitelist sans liste")
    adf = doc(titre(1, "2. Contrat d'entrée"),
              table(["Attribut", "Description"], ["q", "Recherche libre"],
                    ["sort", "Attribut de tri - whitelist : date, auteur"]),
              titre(1, "4. Traitement"),
              para(txt("Si sort est renseigné et n’appartient pas à la whitelist (date)")))
    faits = collecte(adf, "SA", "SA-X-RECHERCHER")
    tri = faits.get("tri", {})
    echecs += check(tri.get("contrat", {}).get("valeurs") == ["date", "auteur"]
                    and tri.get("traitement", {}).get("valeurs") == ["date"]
                    and tri["traitement"]["ou"] == {"section": "4. Traitement"}, f"tri du SA (K39) : {tri}")
    return echecs


def verifie_fixtures():
    """Pages reelles figees : CU-NOTE-CREER et SF-NOTE RG."""
    echecs = 0
    collecteur = fx.Collecteur()
    adf = json.loads((FIXTURES / "28344321.json").read_text(encoding="utf-8"))
    faits = collecteur.collecte(adf, {"id": "28344321", "titre": "CU-NOTE-CREER", "type": "CU"})
    echecs += check(faits["page"]["parse_status"] == "ok", f"{faits['inconnus']}")
    # Fixture du 4 aout 2026 : l'habilitation etait encore au format HAB-…, gardee brute.
    echecs += check(faits["cartouche"]["habilitation"]["texte"] == "HAB-NOTE-GERER",
                    f"{faits['cartouche']}")
    echecs += check(len(faits["regles"]) == 6 and all(l["cellules"]["regle"].get("inclusions")
                                                      for l in faits["regles"]),
                    "6 regles, chacune par inclusion")
    echecs += check(nulls(faits) == [], f"aucun null : {nulls(faits)[:3]}")

    adf = json.loads((FIXTURES / "180256775.json").read_text(encoding="utf-8"))
    faits = collecteur.collecte(adf, {"id": "180256775", "type": "RG",
                                      "titre": "SF-NOTE: Règles de gestion consolidées"})
    noms = {r["nom"]: r for r in faits["regles"]}
    echecs += check(len(faits["regles"]) == len(faits["definitions"]),
                    "une regle par definition d'extrait")
    # Seul ecart nom / titre de cette version : un nom d'extrait numerote (cas K54).
    ecarts = [(r["nom"], r.get("code_titre")) for r in faits["regles"]
              if r.get("code_titre") and r["nom"] != r["code_titre"]]
    echecs += check(ecarts == [("RG-NOTE.TYPENOTE-7", "RG-NOTE-TYPENOTE-MODIFICATION")],
                    f"ecart nom / code du titre : {ecarts}")
    echecs += check(" RG-NOTE-TRI" not in noms and any(r["nom_brut"].startswith(" ")
                                                      for r in faits["regles"]),
                    "espace de tete : dans nom_brut, pas dans nom")
    return echecs


def verifie_ecriture():
    echecs = 0
    faits = collecte(doc(titre(1, "Description")), "CU", "CU-TEST")
    with tempfile.TemporaryDirectory() as dossier:
        echecs += check(fx.ecrit_faits(faits, dossier) is True, "premiere ecriture")
        faits["genere_le"] = "2026-10-23T00:00:00Z"
        echecs += check(fx.ecrit_faits(faits, dossier) is False,
                        "write-if-changed : genere_le seul ne reecrit pas")
        faits["page"]["confluence_version"] = 2
        echecs += check(fx.ecrit_faits(faits, dossier) is True, "contenu change : reecrit")
        echecs += check(not list(Path(dossier).glob("*.tmp")), "aucun temporaire restant")
    return echecs


VERIFICATIONS = (verifie_normalisation, verifie_texte, verifie_liens, verifie_absent_et_vide,
                 verifie_inconnus, verifie_cartouche, verifie_inclusions_et_definitions,
                 verifie_api, verifie_mcd, verifie_tri, verifie_fixtures, verifie_ecriture)


def test_faits():
    echecs = sum(v() for v in VERIFICATIONS)
    assert echecs == 0, f"{echecs} echec(s) : {ECHECS}"


if __name__ == "__main__":
    total = sum(v() for v in VERIFICATIONS)
    if total:
        print(f"ECHEC - {total} verification(s) en echec")
        sys.exit(1)
    print("OK - toutes les verifications du collecteur passent")
