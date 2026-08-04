#!/usr/bin/env python3
"""
Recensement des noeuds ADF du corpus Confluence SINAPSE — etape 0d du pipeline.

VERSION : 1.1 — inventaire des types de noeuds, des macros (extensionKey), des marks et
                des cards (liens Jira et Confluence) presents dans un echantillon de pages.
                Aucune conversion, aucune dependance a une bibliotheque ADF->MD.

Objectif : fermer le perimetre du normalizer avant d'ecrire une seule ligne de conversion.

Sorties (dans --out, par defaut ./recensement/) :
  - recensement_adf_YYYYMMDD.json   donnees brutes exploitables
  - recensement_adf_YYYYMMDD.md     rapport lisible a relire
  - fixtures/{page_id}.json         ADF brut des pages echantillonnees (jeu de tests)

Authentification :
  ATLASSIAN_EMAIL et ATLASSIAN_API_TOKEN en variables d'environnement,
  ou --email / --token en ligne de commande.

Exemples :
  python recense_adf.py --sample
  python recense_adf.py --roots 1474581,1277977 --max-pages 40
  python recense_adf.py --pages 329318407,265453570
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

VERSION = "1.1"
BASE_URL = "https://sinapse-gie-nc.atlassian.net"
API_V2 = f"{BASE_URL}/wiki/api/v2"

# Racines par defaut : groupe A (specs) puis groupe B (documentation)
DEFAULT_ROOTS_A = ["1474581", "1277977"]
DEFAULT_ROOTS_B = ["1245499", "1310723", "219086849"]

# Classification par titre, pour echantillonner tous les types de specs
TYPE_PATTERNS = [
    ("CU", re.compile(r"^CU[-_ ]", re.I)),
    ("API", re.compile(r"^API[-_ ]", re.I)),
    ("JOB", re.compile(r"^(JOB|BATCH)[-_ ]", re.I)),
    ("MDD", re.compile(r"mod[ée]lisation des donn[ée]es", re.I)),
    ("RG", re.compile(r"r[èe]gles de gestion", re.I)),
    ("GENERIQUE", re.compile(r"g[ée]n[ée]rique|r[ée]f[ée]rentiel", re.I)),
]


# --------------------------------------------------------------------------
# Client HTTP
# --------------------------------------------------------------------------

class Confluence:
    def __init__(self, email, token):
        self.auth = HTTPBasicAuth(email, token)
        self.session = requests.Session()
        self.calls = 0

    def _get(self, url, params=None):
        for attempt in range(5):
            resp = self.session.get(
                url, params=params, auth=self.auth,
                headers={"Accept": "application/json"}, timeout=30,
            )
            self.calls += 1
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                print(f"    429 recu, pause {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Echec apres 5 tentatives : {url}")

    def get_page_adf(self, page_id):
        """Retourne (metadonnees, corps ADF). Double parsing obligatoire sur .value."""
        data = self._get(f"{API_V2}/pages/{page_id}",
                         params={"body-format": "atlas_doc_format"})
        raw = data.get("body", {}).get("atlas_doc_format", {}).get("value")
        adf = json.loads(raw) if raw else None
        meta = {
            "id": str(data.get("id")),
            "title": data.get("title"),
            "version": (data.get("version") or {}).get("number"),
            "parent_id": data.get("parentId"),
        }
        return meta, adf

    def list_children(self, page_id):
        """Enfants directs (pagination v2)."""
        out, url, params = [], f"{API_V2}/pages/{page_id}/children", {"limit": 250}
        while url:
            data = self._get(url, params=params)
            out.extend(data.get("results", []))
            nxt = (data.get("_links") or {}).get("next")
            url = f"{BASE_URL}{nxt}" if nxt else None
            params = None
        return out

    def list_descendants(self, root_id, max_pages=None):
        """Parcours recursif en largeur, profondeur illimitee."""
        found, queue, seen = [], [root_id], set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for child in self.list_children(current):
                cid = str(child.get("id"))
                if cid in seen:
                    continue
                found.append({"id": cid, "title": child.get("title")})
                queue.append(cid)
                if max_pages and len(found) >= max_pages:
                    return found
        return found


# --------------------------------------------------------------------------
# Parcours ADF
# --------------------------------------------------------------------------

def classify(title):
    for name, pattern in TYPE_PATTERNS:
        if pattern.search(title or ""):
            return name
    return "AUTRE"


def walk(node, stats, page_meta, path=()):
    """Parcours recursif d'un noeud ADF, alimente les compteurs."""
    if not isinstance(node, dict):
        return
    ntype = node.get("type")
    if not ntype:
        return

    stats["node_types"][ntype] += 1
    stats["node_types_by_page_type"][page_meta["spec_type"]][ntype] += 1
    stats["pages_by_node_type"][ntype].add(page_meta["title"])

    if ntype not in stats["examples"]:
        stats["examples"][ntype] = {
            "page": page_meta["title"],
            "page_id": page_meta["id"],
            "chemin": " > ".join(path[-4:]),
            "extrait": json.dumps(node, ensure_ascii=False)[:400],
        }

    # Macros Confluence : c'est ici que se joue le perimetre du normalizer
    if ntype in ("extension", "bodiedExtension", "inlineExtension"):
        attrs = node.get("attrs", {}) or {}
        key = attrs.get("extensionKey", "?")
        etype = attrs.get("extensionType", "?")
        params = attrs.get("parameters", {}) or {}
        signature = f"{ntype} :: {key}"
        stats["extensions"][signature] += 1
        stats["extension_details"][signature] = {
            "extension_type": etype,
            "parametres": sorted(_param_keys(params))[:20],
            "a_un_corps": bool(node.get("content")),
            "page_exemple": page_meta["title"],
        }
        stats["pages_by_extension"][signature].add(page_meta["title"])
        if "multiexcerpt" in key.lower():
            name = _multiexcerpt_name(params)
            stats["multiexcerpts"][f"{key} :: {name}"] += 1

    # Cards : en Confluence Cloud les liens Jira ne sont pas des macros mais des cards.
    # blockCard porte une table Jira via datasource.parameters.jql, inlineCard un lien simple.
    if ntype in ("blockCard", "inlineCard", "embedCard"):
        attrs = node.get("attrs", {}) or {}
        url = attrs.get("url")
        jql = ((attrs.get("datasource") or {}).get("parameters") or {}).get("jql")
        nature = _classe_card(url, jql)
        signature = f"{ntype} :: {nature}"
        stats["cards"][signature] += 1
        stats["pages_by_card"][signature].add(page_meta["title"])
        if signature not in stats["card_examples"]:
            stats["card_examples"][signature] = {
                "page": page_meta["title"],
                "url": url,
                "jql": jql,
            }
        if jql:
            stats["card_jql"][jql] += 1
            for cle in _jira_keys(jql):
                stats["jira_tickets"][cle] += 1
            cible = _specs_url(jql)
            if cible:
                stats["card_specs_url"][cible] += 1
                # Un gabarit non substitue signale une macro copiee-collee sans reglage
                if "{{" in cible:
                    stats["anomalies"]["cards_gabarit_non_resolu"] += 1
        elif ntype == "blockCard":
            stats["anomalies"]["blockcard_sans_datasource"] += 1
        if url:
            stats["card_urls"][f"{ntype} :: {url}"] += 1

    # Marks (gras, liens, couleurs...) — impactent le rendu markdown
    for mark in node.get("marks", []) or []:
        if isinstance(mark, dict) and mark.get("type"):
            stats["marks"][mark["type"]] += 1

    # Tableaux : colspan/rowspan cassent le parsing des tableaux MDD et IHM
    if ntype in ("tableCell", "tableHeader"):
        attrs = node.get("attrs", {}) or {}
        if (attrs.get("colspan") or 1) > 1:
            stats["anomalies"]["cellules_colspan"] += 1
        if (attrs.get("rowspan") or 1) > 1:
            stats["anomalies"]["cellules_rowspan"] += 1
        if any(_child_types(node) & {"bulletList", "orderedList", "table"}):
            stats["anomalies"]["cellules_structurees"] += 1

    for child in node.get("content", []) or []:
        walk(child, stats, page_meta, path + (ntype,))


def _child_types(node):
    return {c.get("type") for c in (node.get("content") or []) if isinstance(c, dict)}


def _param_keys(params):
    keys = set()
    for k, v in (params or {}).items():
        keys.add(k)
        if isinstance(v, dict):
            keys |= {f"{k}.{sk}" for sk in v.keys()}
    return keys


def _macro_param(params, nom):
    """Valeur d'un parametre de macro : parameters.macroParams.<nom>.value."""
    val = (params.get("macroParams") or {}).get(nom)
    if isinstance(val, dict):
        val = val.get("value")
    return val


def _multiexcerpt_name(params):
    return str(_macro_param(params, "name") or "?")


# Une cle Jira ne peut pas etre confondue avec un type d'issue ("Sub-task") : elle
# se termine par un tiret suivi de chiffres.
RE_JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9_]*-\d+\b")
RE_SPECS_URL = re.compile(r'"Specs\[URL Field\]"\s*=\s*"([^"]*)"')
RE_BROWSE = re.compile(r"/browse/[A-Z][A-Z0-9_]*-\d+")


def _classe_card(url, jql):
    """Nature d'une card, pour savoir quelle regle de normalisation lui appliquer."""
    if jql:
        return "table Jira (JQL)"
    if not url:
        return "sans url"
    if RE_BROWSE.search(url):
        return "ticket Jira"
    if "/issues/?jql=" in url or "/issues/?filter=" in url:
        return "recherche Jira"
    if "/wiki/spaces/" in url or "/wiki/x/" in url:
        return "page Confluence"
    return "autre"


def _jira_keys(jql):
    return sorted(set(RE_JIRA_KEY.findall(jql or "")))


def _specs_url(jql):
    """Page cible du champ Specs[URL Field] : c'est l'ancrage page <-> ticket."""
    found = RE_SPECS_URL.search(jql or "")
    return found.group(1) if found else None


def new_stats():
    return {
        "node_types": Counter(),
        "node_types_by_page_type": defaultdict(Counter),
        "pages_by_node_type": defaultdict(set),
        "extensions": Counter(),
        "extension_details": {},
        "pages_by_extension": defaultdict(set),
        "multiexcerpts": Counter(),
        "cards": Counter(),
        "pages_by_card": defaultdict(set),
        "card_examples": {},
        "card_jql": Counter(),
        "card_urls": Counter(),
        "card_specs_url": Counter(),
        "jira_tickets": Counter(),
        "marks": Counter(),
        "anomalies": Counter(),
        "examples": {},
    }


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

def build_report(stats, pages, errors, elapsed, calls):
    L = []
    add = L.append
    add(f"# Recensement ADF — corpus SINAPSE\n")
    add(f"*Script recense_adf.py v{VERSION} — {datetime.now():%d/%m/%Y %H:%M}*\n")
    add(f"- Pages analysees : **{len(pages)}**")
    add(f"- Appels API : {calls} — duree : {elapsed:.1f}s")
    add(f"- Types de noeuds distincts : **{len(stats['node_types'])}**")
    add(f"- Macros distinctes : **{len(stats['extensions'])}**")
    add(f"- Tickets Jira references : **{len(stats['jira_tickets'])}**")
    if errors:
        add(f"- ⚠️ Pages en echec : **{len(errors)}**")
    add("")

    add("## 1. Pages analysees\n")
    add("| Type | Titre | ID | Version |")
    add("|---|---|---|---|")
    for p in sorted(pages, key=lambda x: (x["spec_type"], x["title"] or "")):
        add(f"| {p['spec_type']} | {p['title']} | {p['id']} | {p.get('version')} |")
    add("")

    add("## 2. Types de noeuds ADF rencontres\n")
    add("Colonne *pages* = nombre de pages distinctes ou le noeud apparait.\n")
    add("| Noeud | Occurrences | Pages | A traiter dans le normalizer |")
    add("|---|---|---|---|")
    a_traiter = {
        "extension": "OUI — multiexcerpt, TOC",
        "bodiedExtension": "OUI — corps a conserver",
        "inlineExtension": "OUI",
        "expand": "OUI — sinon section perdue",
        "nestedExpand": "OUI",
        "layoutSection": "OUI — cartouches en colonnes",
        "layoutColumn": "OUI",
        "media": "OUI — placeholder",
        "mediaSingle": "OUI — placeholder",
        "mediaGroup": "OUI — placeholder",
        "mediaInline": "OUI — placeholder",
        "embedCard": "A verifier — voir section 5",
        "inlineCard": "OUI — lien a remettre en clair, voir section 5",
        "blockCard": "OUI — table Jira par JQL, voir section 5",
        "status": "A verifier",
        "taskList": "A verifier",
        "decisionList": "A verifier",
    }
    for ntype, count in stats["node_types"].most_common():
        nb = len(stats["pages_by_node_type"][ntype])
        add(f"| `{ntype}` | {count} | {nb} | {a_traiter.get(ntype, '')} |")
    add("")

    add("## 3. Macros Confluence (extensionKey)\n")
    add("**C'est la section decisive** : chaque ligne doit avoir une regle de normalisation.\n")
    if not stats["extensions"]:
        add("*Aucune macro rencontree.*")
    else:
        add("| Macro | Occurrences | Pages | Corps | Parametres |")
        add("|---|---|---|---|---|")
        for sig, count in stats["extensions"].most_common():
            d = stats["extension_details"][sig]
            nb = len(stats["pages_by_extension"][sig])
            corps = "oui" if d["a_un_corps"] else "non"
            params = ", ".join(f"`{p}`" for p in d["parametres"][:8]) or "—"
            add(f"| `{sig}` | {count} | {nb} | {corps} | {params} |")
    add("")

    add("## 4. Multiexcerpts identifies\n")
    if not stats["multiexcerpts"]:
        add("*Aucun multiexcerpt dans l'echantillon — elargir l'echantillon.*")
    else:
        add("| Macro :: nom | Occurrences |")
        add("|---|---|")
        for name, count in stats["multiexcerpts"].most_common(60):
            add(f"| {name} | {count} |")
    add("")

    add("## 5. Liens Jira et Confluence (cards)\n")
    add("En Confluence Cloud, un lien Jira n'est **pas** une macro : c'est une *card*. "
        "Une `blockCard` porte une table Jira via `attrs.datasource.parameters.jql`, "
        "une `inlineCard` un simple lien via `attrs.url`.\n")
    if not stats["cards"]:
        add("*Aucune card rencontree.*")
    else:
        add("| Card | Nature | Occurrences | Pages |")
        add("|---|---|---|---|")
        for sig, count in stats["cards"].most_common():
            ntype, nature = sig.split(" :: ", 1)
            nb = len(stats["pages_by_card"][sig])
            add(f"| `{ntype}` | {nature} | {count} | {nb} |")
    add("")

    add("### 5.1 Tickets Jira references\n")
    if not stats["jira_tickets"]:
        add("*Aucun ticket Jira reference.*")
    else:
        add("Extraits des requetes JQL. Le ticket cite dans `linkedIssues(...)` est "
            "l'ancrage entre la page de spec et Jira.\n")
        add("| Ticket | Occurrences |")
        add("|---|---|")
        for ticket, count in stats["jira_tickets"].most_common():
            add(f"| {ticket} | {count} |")
    add("")

    add("### 5.2 Pages cibles du champ `Specs[URL Field]`\n")
    if not stats["card_specs_url"]:
        add("*Aucun champ `Specs[URL Field]` dans les requetes.*")
    else:
        add("| Cible | Occurrences |")
        add("|---|---|")
        for cible, count in stats["card_specs_url"].most_common():
            add(f"| `{cible}` | {count} |")
    add("")

    add("### 5.3 Requetes JQL distinctes\n")
    if not stats["card_jql"]:
        add("*Aucune requete JQL.*")
    else:
        add(f"{len(stats['card_jql'])} requetes distinctes. "
            "Tronquees a 300 caracteres ; les requetes completes sont dans le `.json`.\n")
        add("| Occurrences | JQL |")
        add("|---|---|")
        for jql, count in stats["card_jql"].most_common():
            propre = " ".join(jql.split())[:300].replace("|", "\\|")
            add(f"| {count} | `{propre}` |")
    add("")

    add("## 6. Marks (mise en forme du texte)\n")
    add("| Mark | Occurrences |")
    add("|---|---|")
    for mark, count in stats["marks"].most_common():
        add(f"| `{mark}` | {count} |")
    add("")

    add("## 7. Points de vigilance\n")
    labels = {
        "cellules_colspan": "Cellules fusionnees horizontalement (colspan)",
        "cellules_rowspan": "Cellules fusionnees verticalement (rowspan)",
        "cellules_structurees": "Cellules contenant une liste ou un tableau imbrique",
        "cards_gabarit_non_resolu": "Card Jira avec un gabarit `{{...}}` non substitue",
        "blockcard_sans_datasource": "blockCard sans datasource (donc sans JQL)",
    }
    if not stats["anomalies"]:
        add("*Aucun point de vigilance detecte.*")
    else:
        add("| Point | Occurrences | Consequence |")
        add("|---|---|---|")
        consequences = {
            "cellules_colspan": "Decalage de colonnes en markdown — parser l'ADF, pas le .md",
            "cellules_rowspan": "Idem",
            "cellules_structurees": "Contenu aplati en markdown — perte d'information",
            "cards_gabarit_non_resolu": "La requete ne cible aucune page reelle — lien Jira a verifier dans Confluence",
            "blockcard_sans_datasource": "Nature de la card a determiner avant de figer sa regle",
        }
        for key, count in stats["anomalies"].most_common():
            add(f"| {labels.get(key, key)} | {count} | {consequences.get(key, '')} |")
    add("")

    add("## 8. Exemple pour chaque type de noeud\n")
    for ntype in sorted(stats["examples"]):
        ex = stats["examples"][ntype]
        add(f"### `{ntype}`")
        add(f"Page : {ex['page']} ({ex['page_id']}) — chemin : `{ex['chemin']}`")
        add("```json")
        add(ex["extrait"])
        add("```")
        add("")

    if errors:
        add("## 9. Pages en echec\n")
        add("| Page | Erreur |")
        add("|---|---|")
        for pid, err in errors:
            add(f"| {pid} | {err} |")
        add("")

    return "\n".join(L)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def select_sample(client, roots, max_pages, per_type):
    """Echantillon equilibre : au plus per_type pages par type de spec."""
    candidates = []
    for root in roots:
        print(f"  exploration de la racine {root}...")
        for page in client.list_descendants(root):
            page["spec_type"] = classify(page["title"])
            candidates.append(page)
    print(f"  {len(candidates)} pages descendantes trouvees")

    buckets = defaultdict(list)
    for page in candidates:
        buckets[page["spec_type"]].append(page)

    sample = []
    for spec_type in sorted(buckets):
        sample.extend(buckets[spec_type][:per_type])
    return sample[:max_pages]


def main():
    ap = argparse.ArgumentParser(description="Recensement des noeuds ADF SINAPSE")
    ap.add_argument("--pages", help="IDs de pages explicites, separes par des virgules")
    ap.add_argument("--roots", help="IDs de pages racines (defaut : groupes A et B du brief)")
    ap.add_argument("--sample", action="store_true", help="Echantillonnage automatique par type")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--per-type", type=int, default=5)
    ap.add_argument("--out", default="recensement")
    ap.add_argument("--email", default=os.environ.get("ATLASSIAN_EMAIL"))
    ap.add_argument("--token", default=os.environ.get("ATLASSIAN_API_TOKEN"))
    args = ap.parse_args()

    if not args.email or not args.token:
        sys.exit("ERREUR : renseigner ATLASSIAN_EMAIL et ATLASSIAN_API_TOKEN "
                 "(variables d'environnement) ou --email / --token.")

    out_dir = Path(args.out)
    fixtures = out_dir / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)

    client = Confluence(args.email, args.token)
    started = time.time()

    # --- Selection des pages
    if args.pages:
        targets = [{"id": pid.strip(), "title": None} for pid in args.pages.split(",")]
    else:
        roots = (args.roots.split(",") if args.roots
                 else DEFAULT_ROOTS_A + DEFAULT_ROOTS_B)
        print("Selection de l'echantillon...")
        targets = select_sample(client, [r.strip() for r in roots],
                                args.max_pages, args.per_type)

    print(f"\n{len(targets)} pages a analyser\n")

    stats = new_stats()
    pages, errors = [], []

    for i, target in enumerate(targets, 1):
        pid = target["id"]
        try:
            meta, adf = client.get_page_adf(pid)
            if not adf:
                errors.append((pid, "corps ADF vide"))
                continue
            meta["spec_type"] = classify(meta["title"])
            print(f"  [{i}/{len(targets)}] {meta['spec_type']:10s} {meta['title']}")
            (fixtures / f"{pid}.json").write_text(
                json.dumps(adf, ensure_ascii=False, indent=2), encoding="utf-8")
            walk(adf, stats, meta)
            pages.append(meta)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(targets)}] ECHEC {pid} : {exc}", file=sys.stderr)
            errors.append((pid, str(exc)))

    elapsed = time.time() - started
    stamp = datetime.now().strftime("%Y%m%d")

    payload = {
        "script_version": VERSION,
        "generated_at": datetime.now().isoformat(),
        "pages_analysees": pages,
        "erreurs": errors,
        "node_types": dict(stats["node_types"]),
        "node_types_par_type_de_page": {k: dict(v) for k, v in stats["node_types_by_page_type"].items()},
        "extensions": dict(stats["extensions"]),
        "extension_details": stats["extension_details"],
        "multiexcerpts": dict(stats["multiexcerpts"]),
        "cards": dict(stats["cards"]),
        "cards_exemples": stats["card_examples"],
        "cards_jql": dict(stats["card_jql"]),
        "cards_urls": dict(stats["card_urls"]),
        "cards_specs_url": dict(stats["card_specs_url"]),
        "jira_tickets": dict(stats["jira_tickets"]),
        "marks": dict(stats["marks"]),
        "points_de_vigilance": dict(stats["anomalies"]),
        "exemples": stats["examples"],
    }
    json_path = out_dir / f"recensement_adf_{stamp}.json"
    md_path = out_dir / f"recensement_adf_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_report(stats, pages, errors, elapsed, client.calls), encoding="utf-8")

    print(f"\nTermine en {elapsed:.1f}s — {client.calls} appels API")
    print(f"  rapport  : {md_path}")
    print(f"  donnees  : {json_path}")
    print(f"  fixtures : {fixtures}/ ({len(pages)} fichiers ADF)")


if __name__ == "__main__":
    main()
