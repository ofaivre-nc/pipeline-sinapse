#!/usr/bin/env python3
"""
Delta entre deux inventaires — dernier verrou de l'etape 3.

VERSION : 1.0

Decide, a partir de deux `pages_inventory.json`, ce qu'un run doit reexporter et
ce qu'il doit detruire. `compare()` est PURE : elle ne lit ni n'ecrit aucun
fichier, ne joint pas Confluence, et ne supprime rien sur disque. Elle rend un
PLAN — l'appelant l'execute.

Module separe d'inventory.py : le delta ne depend pas de la classification, il
prend deux inventaires et rend un plan.

Contrats de reference : contracts/pages_inventory.schema.json pour la forme des
entrees, contracts/slugification.md §9 pour les collisions.
"""

VERSION = "1.0"

# Etats qui appellent une reecriture du .md en mode incremental.
# `retrait` en est absent : une page qui n'a plus de fichier n'a rien a ecrire.
ETATS_A_EXPORTER = frozenset({
    "creation", "retour", "modification", "deplacement", "modification_deplacement",
})

# Etats qui cassent un lien relatif entrant : un fichier cesse d'exister a son
# ancien chemin. Ce sont eux, et les suppressions, qui forcent le run complet.
ETATS_DEPLACEMENT = frozenset({"deplacement", "modification_deplacement"})


def etat_page(avant, apres):
    """Etat d'une page entre deux inventaires. Voir §2 de l'instruction du delta.

    `avant` vaut None si la page est absente de l'inventaire precedent.

    `retrait` et `retour` l'emportent sur `modification` : une page qui n'a pas de
    fichier n'a rien a dire sur son contenu.

    Un passage a None n'est PAS un deplacement. C'etait le decoupage initial et il
    est faux : il declenchait un re-rendu complet pour une page entree en
    collision, alors que son .md reste en place et qu'aucun lien entrant ne casse.
    `deplacement` exige DEUX chemins non nuls.
    """
    if avant is None:
        return "creation"

    chemin_avant, chemin_apres = avant.get("md_path"), apres.get("md_path")
    if chemin_avant and not chemin_apres:
        return "retrait"
    if not chemin_avant and chemin_apres:
        return "retour"

    version_changee = avant.get("version") != apres.get("version")
    deplacee = bool(chemin_avant) and bool(chemin_apres) and chemin_avant != chemin_apres
    if version_changee and deplacee:
        return "modification_deplacement"
    if deplacee:
        return "deplacement"
    if version_changee:
        return "modification"
    return "inchangee"


def _protegees(courant):
    """Identifiants qu'aucune suppression ne doit toucher.

    Deux origines, qui se declenchent dans DEUX BRANCHES differentes :

      collisions    la page est PRESENTE dans courant["pages"], md_path a None.
                    Branche « page sans chemin ».
      unclassified  la page a QUITTE la carte. Branche « page absente ». Sans
                    cette protection, une page dont le titre s'est vide voit son
                    .md efface.

    L'union suffit puisqu'une page ne peut relever que d'une seule des deux, mais
    les deux sources sont lues explicitement : en oublier une n'effacerait des
    fichiers que dans un cas de figure rare, donc tard.
    """
    ids = set()
    for groupe in courant.get("collisions") or ():
        ids.update(groupe.get("page_ids") or ())
    for entree in courant.get("unclassified") or ():
        if entree.get("id"):
            ids.add(entree["id"])
    return ids


def compare(precedent, courant):
    """Plan de run entre deux inventaires. Fonction pure : ne mute ni ses entrees
    ni le disque.

    `precedent` vaut None au premier run — pas un dictionnaire vide : l'absence
    d'inventaire precedent est un fait, et elle se dit.

    Rend un dict :
      run_complet            bool
      raisons_run_complet    liste de motifs en clair, pour le rapport
      a_exporter             identifiants a (re)ecrire, tries
      suppressions           [{page_id, md_path}] a effacer
      suppressions_retenues  [{page_id, md_path}] qu'on s'est INTERDIT d'effacer
                             faute de `complete` — pour le rapport
      etats                  {page_id: etat}, une entree par page de courant
      precedent_ignore       bool, vrai si schema_version differe
    """
    pages_courant = courant.get("pages") or {}
    raisons = []

    # --- Garde-fou (c) : schema_version different => precedent non fiable.
    # Deviner la semantique de champs d'une autre version est pire que tout
    # reexporter. Les DECISIONS se prennent alors comme sans precedent — aucune
    # suppression, run complet — mais les ETATS restent calcules par paires : ils
    # ne servent qu'au rapport, et dire « creation » de 246 pages qui existaient
    # deja serait faux.
    precedent_ignore = bool(
        precedent is not None
        and precedent.get("schema_version") != courant.get("schema_version"))
    if precedent_ignore:
        raisons.append(
            f"schema_version different : {precedent.get('schema_version')!r} "
            f"puis {courant.get('schema_version')!r}")

    pages_precedent = (precedent or {}).get("pages") or {}

    # --- Les sept etats, une entree par page PRESENTE dans courant.
    etats = {}
    for page_id, apres in pages_courant.items():
        etats[page_id] = etat_page(pages_precedent.get(page_id), apres)

    # --- Suppressions candidates, deux branches.
    protegees = _protegees(courant)
    candidates = []
    if precedent is not None and not precedent_ignore:
        # Branche A : la page est la, elle n'a plus de chemin.
        for page_id, etat in etats.items():
            if etat == "retrait" and page_id not in protegees:
                candidates.append({"page_id": page_id,
                                   "md_path": pages_precedent[page_id]["md_path"]})
        # Branche B : la page a quitte la carte.
        for page_id, avant in pages_precedent.items():
            if page_id in pages_courant or page_id in protegees:
                continue
            if avant.get("md_path"):
                candidates.append({"page_id": page_id, "md_path": avant["md_path"]})
    candidates.sort(key=lambda s: s["page_id"])

    # --- Garde-fou (a) : `complete` est la SEULE autorisation de detruire. Une
    # collecte partielle doit dire ce qu'elle s'est interdit, sinon personne ne
    # saura qu'un incident a eu lieu.
    if courant.get("complete"):
        suppressions, retenues = candidates, []
    else:
        suppressions, retenues = [], candidates
        if retenues:
            raisons.append(
                f"{len(retenues)} suppression(s) retenue(s) : collecte incomplete")

    # --- Run complet : le critere est « un fichier cesse d'exister a son ancien
    # chemin », pas « un chemin a change ». C'est la seule chose qui casse un lien
    # relatif entrant.
    if precedent is None:
        raisons.insert(0, "aucun inventaire precedent")
    deplacements = sorted(i for i, e in etats.items() if e in ETATS_DEPLACEMENT)
    if deplacements:
        raisons.append(f"{len(deplacements)} deplacement(s) : "
                       f"{', '.join(deplacements[:5])}")
    if suppressions:
        raisons.append(f"{len(suppressions)} suppression(s) retenue(s) dans le plan")

    run_complet = bool(precedent is None or precedent_ignore
                       or deplacements or suppressions)

    # --- Ce qu'il faut ecrire.
    if run_complet:
        a_exporter = {i for i, f in pages_courant.items()
                      if f.get("exported") and f.get("md_path")}
    else:
        a_exporter = {i for i, f in pages_courant.items()
                      if etats[i] in ETATS_A_EXPORTER
                      and f.get("exported") and f.get("md_path")}

    # --- Garde-fou (d) : troisieme entree du delta, `last_exported`. Une page
    # exportable jamais ecrite est la signature d'un run interrompu : l'inventaire
    # s'ecrit APRES l'export. Sans cette entree, un plantage a mi-export laisse
    # des pages definitivement manquantes — rien ne bougera plus jamais chez elles.
    jamais_ecrites = {i for i, f in pages_courant.items()
                      if f.get("exported") and f.get("md_path")
                      and f.get("last_exported") is None}
    a_exporter |= jamais_ecrites

    return {
        "delta_version": VERSION,
        "run_complet": run_complet,
        "raisons_run_complet": raisons if run_complet else [],
        "a_exporter": sorted(a_exporter),
        "suppressions": suppressions,
        "suppressions_retenues": retenues,
        "etats": etats,
        "precedent_ignore": precedent_ignore,
        "jamais_ecrites": sorted(jamais_ecrites),
    }
