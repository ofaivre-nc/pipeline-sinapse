> # ⚠ DOCUMENT ARCHIVÉ — NE PAS UTILISER COMME SOURCE
>
> **Remplacé le 5 août 2026 par `docs/reference-pipeline-sinapse.md`.**
>
> Ce brief est conservé pour une seule raison : il porte la **formulation d'origine** de
> décisions qu'on voudra peut-être relire. Il n'est plus tenu à jour et contient des
> éléments désormais **faux**.
>
> **Où est passé son contenu :**
>
> | Section du brief | Destination |
> |---|---|
> | §1 contexte, §6 impact skills, §7 séquencement, §8 questions ouvertes, §9 décisions | `docs/reference-pipeline-sinapse.md` |
> | §2 organisation du code, arborescence, transport Git | `CLAUDE.md` |
> | §2 `config.ini` | `config.ini.example` |
> | §3 chaîne de conversion et table de normalisation | `contracts/normalisation_adf.md` |
> | §4.1 `pages_inventory.json` | `contracts/pages_inventory.schema.json` |
> | §4.2 `multiexcerpt_cache.json` | `contracts/reused_content_cache.schema.json` *(renommé : deux mécanismes)* |
> | §4.3 `index_croise_{MODULE}.json` | `contracts/index_croise.schema.json` |
> | §4.4 `mcd_sinapse_data` | `contracts/mcd_sinapse_data.schema.json` *(provisoire)* |
> | §4.5 métadonnées des `.md` | `contracts/frontmatter.md` |
> | §5 robustesse du run | `.claude/rules/python.md` |
>
> **Points de ce document devenus faux** — la liste complète des divergences est dans le
> compte-rendu de redistribution ; les principaux :
>
> - §4.1 « module et type sont déduits du titre » : le **module** vient de l'ascendance,
>   le titre n'est qu'un repli. Le bac `unclassified` est largement remplacé par le type
>   `A_QUALIFIER`.
> - §4.2 le cache indexé par **nom seul** : le nom n'est pas unique dans le space
>   (`habilitation` défini 5 fois). Clé `(page, nom)`.
> - §4.2 ne connaît qu'un mécanisme de réutilisation : le corpus en porte **deux**, le
>   second (`syncBlock`) avec la clé `(page_id, uuid)`.
> - §3 « `extension` TOC → supprimé » et le traitement de `nested-table` : ce nœud est
>   **intégralement récupérable** via `parameters.adf`, il ne déclasse pas la page.
> - §5 backoff sur le seul HTTP 429 : `Timeout` et `ConnectionError` sont obligatoires.
> - §1 et §2 « multiexcerpt » partout : le terme est trop étroit depuis la découverte des
>   `syncBlock`.

# Brief — Pipeline Python SINAPSE : export Confluence → .md + caches JSON

**Version 3** — 2 août 2026
*Document de contexte pour le développement. Remplace la v2.*

---

## 1. Contexte

### Historique — pourquoi ce pipeline

- **Phase 1 — Prompts ad hoc** : aucune persistance.
- **Phase 2 — Skills monolithiques** : séquencement non garanti, la résolution multiexcerpt pouvait être sautée.
- **Phase 3 — Script + appels API Claude externes** : séquencement fiable, mais la mémoire de conversation devait être réimplémentée (mémoire JSON, `config_loader.py`).
- **Phase 4 (actuelle)** : skills unitaires + orchestrateur. Python pour le déterministe, Claude en conversation pour le sémantique.

Le pipeline étend la Phase 4 : le fetch Confluence passe par l'API REST directe (token Atlassian) parce qu'il tourne hors session Claude. **Aucun LLM dans le pipeline** — donc aucun retour à la mécanique de la Phase 3.

### Problème résolu

Les pages SINAPSE utilisent le plugin **multiexcerpt** : des règles définies une fois sur une page source sont incluses par macro ailleurs. L'API Confluence retourne ces macros vides en markdown. Le skill `confluence-outil-resolve-multiexcerpt` résout le problème en session, mais le résultat est local et éphémère : chaque BA, chaque conversation, doit recommencer.

### Solution cible

Un script Python autonome, planifié quotidiennement à 7h, qui :

1. établit l'inventaire des pages du périmètre et détecte les changements ;
2. résout les multiexcerpts ;
3. normalise les nœuds ADF spécifiques à Confluence ;
4. exporte chaque page en `.md` dans le répertoire SharePoint synchronisé ;
5. met à jour les caches JSON (inventaire, multiexcerpts, index croisé par module, données MCD) ;
6. produit un rapport d'exécution `.md` + `.json`.

Les skills Claude opèrent ensuite sur ces fichiers au lieu de lire Confluence.

### Environnement

- Atlassian Cloud : `sinapse-gie-nc.atlassian.net`
- Auth : Basic Auth (email + token API). **Token en variable d'environnement ou `config.ini` non versionné. Jamais en dur, jamais transmis en conversation.**
- API REST Confluence v2 : `/wiki/api/v2`
- Python 3.11+
- Conversion ADF → MD : `marklas` pressenti, à confirmer (voir §3)

### Périmètre Confluence

**Groupe A — Specs fonctionnelles** : multiexcerpts résolus, index croisé produit, soumis aux validations.

| Page racine | ID |
|---|---|
| Spécifications fonctionnelles | `1474581` |
| Référentiels du projet | `1277977` |

**Groupe B — Documentation** : export `.md` simple, sans résolution ni index.

| Page racine | ID |
|---|---|
| Analyse de l'existant | `1245499` |
| Documentations | `1310723` |
| Skills claude | `219086849` |

Export récursif, profondeur illimitée.

---

## 2. Organisation du code et des fichiers

### Deux espaces distincts

**Le code** — dépôt Git, copie de travail locale sur chaque poste :

```
C:\dev\sinapse-claude\
├── CLAUDE.md                     instructions Claude Code, chargées à chaque session
├── CLAUDE.local.md               chemins propres à CETTE machine (non versionné)
├── config.ini.example
├── .gitignore
│
├── .claude/
│   ├── rules/                    règles ciblées par chemin (python.md, skills.md)
│   └── skills/                   LES SKILLS SINAPSE — source de vérité
│
├── contracts/                    LE CONTRAT entre pipeline et skills
│   ├── index_croise.schema.json
│   ├── mcd_sinapse_data.schema.json
│   ├── frontmatter.md
│   └── normalisation_adf.md
│
├── pipeline/
│   ├── CLAUDE.md
│   ├── src/                      main, confluence_client, inventory, multiexcerpt,
│   │                             normalizer, renderer, index_builder, mcd, report
│   ├── tests/
│   ├── fixtures/                 5-10 ADF figés + .md attendus
│   └── config.ini                NON VERSIONNÉ
│
├── tools/                        outils autonomes (restitution PUF, présentation MCD…)
├── build/                        make_skill_zip.py
└── docs/                         briefs, guides, READMEs utilisateurs des skills
```

Règle de rangement : `.claude/skills/` = ce que Claude exécute ; `docs/skills/` = ce que les humains lisent ; `contracts/` = ce qui lie les deux.

**Transport entre postes** : dépôt Git nu déposé dans le SharePoint GIE, servant de *remote*. Aucune édition dedans, uniquement `push` / `pull` — donc aucun conflit de synchronisation.

```bash
git init --bare "<SharePoint>\sinapse\sinapse.git"
git remote add origin "<SharePoint>\sinapse\sinapse.git"
```

**Les sorties du pipeline** restent dans le SharePoint d'équipe, comme aujourd'hui :

```
{SHAREPOINT_LOCAL_PATH}\
├── specs\        .md du groupe A
├── docs\         .md du groupe B
├── cache\        pages_inventory, multiexcerpt_cache, index_croise_*, mcd_sinapse_data
└── reports\      sync_report_*.md et .json
```

> Phase de test : `C:\sinapse-specs-test\`, créé automatiquement au premier run. Seul `local_path` change au retour au bureau.

### Distribution des skills

Deux canaux **indépendants** — une session Claude Code ne lit que le disque, elle ne voit pas l'espace GIE de claude.ai.

| Canal | Public | Mécanisme |
|---|---|---|
| Dépôt `.claude/skills/` | Toi, devs, BAs sur Claude Code | `git pull` |
| Espace GIE claude.ai | BAs sur l'interface web | Zip produit par `build/make_skill_zip.py`, importé manuellement |

Le dépôt est la source de vérité ; l'espace GIE est une cible de déploiement. La version affichée en tête de chaque compte-rendu (`Skill : nom-du-skill vX.Y`) permet de repérer un décalage.

**Règle d'hygiène** : aucun skill SINAPSE dans `~/.claude/skills/`. Le personnel l'emporte sur le projet — une copie oubliée gagnerait silencieusement sur celle du dépôt.

### `config.ini`

```ini
[confluence]
base_url = https://sinapse-gie-nc.atlassian.net
space_key = SINAPSE
email = olivier@...
; token : variable ATLASSIAN_API_TOKEN (prioritaire) ou clé ci-dessous
api_token =

specs_root_page_ids = 1474581,1277977
doc_root_page_ids = 1245499,1310723,219086849
exclude_page_ids =

[storage]
local_path = C:\sinapse-specs-test

[convert]
library = marklas            ; marklas | pyadf
strict_unknown_nodes = true  ; tout nœud non couvert par le normalizer = erreur au rapport

[run]
schema_version = 1
last_run = 2020-01-01T00:00:00Z
```

---

## 3. Chaîne de conversion ADF → Markdown

### Bibliothèques évaluées

| Lib | Version | Nœuds Confluence spécifiques |
|---|---|---|
| `pyadf` | 0.5.2 (juin 2026), Rust | `expand`, `extension`, `media`, `embedCard` **explicitement non rendus** → perte silencieuse |
| **`marklas`** | 0.8.6 (juil. 2026) | `Expand`, `Extension`, `Media` sont des nœuds de premier ordre ; API `Transformer` ; bidirectionnel ; `plain=True` |
| `atlas-doc-parser` | 1.0.1 (janv. 2026) | documentation insuffisante — recours de 3ᵉ rang |

`marklas` est pressenti : il modélise les nœuds Confluence au lieu de les jeter, son API `Transformer` permet d'implémenter la résolution multiexcerpt comme un visiteur typé sur l'AST, et sa bidirectionnalité servira au Bloc 6 (génération de pages).

Inconnues à lever : `layoutSection` / `layoutColumn` (cartouches en colonnes) et `bodiedExtension`, non documentés.

### Pipeline de conversion

```
ADF brut
  → résolution multiexcerpts     (visiteur sur les nœuds Extension)
  → normalisation Confluence     (aplatissement des nœuds spécifiques)
  → rendu markdown
  → frontmatter YAML + écriture .md
```

Table de normalisation — à compléter à l'issue de l'étape 0d, puis figée dans `contracts/normalisation_adf.md` :

| Nœud ADF | Transformation |
|---|---|
| `extension` multiexcerpt-include | contenu résolu, encadré de balises de traçabilité |
| `extension` macro Jira | paramètres remis en clair (clé de test, JQL) |
| `expand` / `nestedExpand` | titre en heading + contenu déplié |
| `layoutSection` / `layoutColumn` | sections séquentielles |
| `bodiedExtension` | corps conservé, macro signalée en commentaire |
| `media` / `mediaSingle` | placeholder `![screenshot: nom]` |
| `extension` TOC | supprimé |

**Règle stricte** : tout nœud non couvert est remonté en erreur dans le rapport, jamais ignoré. Un warning résiduel de la lib = un bug du normalizer.

---

## 4. Fichiers de cache

### 4.1 `pages_inventory.json`

Inventaire complet du périmètre, base de la détection de delta. Construit en début de run via `/wiki/api/v2/pages` paginé.

**Delta par `version.number`, pas par date** : `lastmodified` est à la minute, sensible au fuseau, et ne bouge pas sur certains déplacements. Le diff de numéros de version est exact et donne en prime les **suppressions**, les **renommages** (sinon un `.md` orphelin subsiste et sera lu comme une spec valide) et les **déplacements**.

```json
{
  "generated_at": "2026-08-02T07:00:00Z",
  "schema_version": 1,
  "pages": {
    "329318407": {
      "title": "CU-PERSONNE-MODIFIER", "version": 47, "parent_id": "265453569",
      "group": "A", "module": "PERSONNE", "type": "CU",
      "md_path": "specs/CU-PERSONNE-MODIFIER.md",
      "last_exported": "2026-08-02T07:03:12Z"
    }
  },
  "unclassified": [
    {"id": "331122334", "title": "Brouillon reprise", "reason": "titre non conforme"}
  ]
}
```

Module et type sont déduits du titre. Toute page non classifiable part dans `unclassified` **et figure au rapport** — c'est un signal de non-conformité, et ça évite qu'une spec disparaisse du radar.

**Nommage des fichiers** : les titres contiennent des caractères interdits sous Windows (`SF-PERSONNE: …`). Slugification obligatoire, collisions détectées et signalées.

### 4.2 `multiexcerpt_cache.json`

Index des multiexcerpts du space : contenu, hash, pages consommatrices. Si le hash d'une source change, toutes ses consommatrices sont regénérées (invalidation transitive).

```json
{
  "multiexcerpts": {
    "RG-PERSONNE-CARACTERES.AUTORISES": {
      "source_page_id": "265453570",
      "source_page_title": "SF-PERSONNE: Règles de gestion consolidées",
      "content_hash": "sha256:a3f4b2...",
      "content_md": "Les caractères autorisés sont : ...",
      "last_changed": "2026-06-15T10:22:00Z",
      "consumers": [
        {"page_id": "329318407", "page_title": "CU-PERSONNE-MODIFIER"},
        {"page_id": "242221060", "page_title": "CU-PERSONNE-PP.CREER"}
      ]
    }
  }
}
```

À traiter : multiexcerpts imbriqués (récursion + détection de cycle), variantes de macro, inclusions non résolues → erreurs.

### 4.3 `index_croise_{MODULE}.json`

Agrégation structurée d'un module, permettant aux skills de travailler sans relire Confluence ni reparser les pages.

**Construit depuis l'ADF résolu, pas depuis le `.md`.** Les tableaux markdown perdent leur structure dès qu'une cellule contient une liste ou un saut de ligne — précisément le cas des tableaux IHM 5 colonnes et MDD 9 colonnes.

**`parse_status` obligatoire par page.** Sans lui, un skill lisant `regles: []` ne peut pas distinguer « aucune règle » de « le parser a échoué », et produit un rapport entièrement faux. **Règle imposée aux skills : une page en `parse_status ≠ ok` n'est pas scorée, elle est signalée.**

```json
{
  "module": "PERSONNE", "schema_version": 1, "pipeline_version": "1.0",
  "pages": {
    "MDD": {"id": "265453570", "md_path": "specs/SF-PERSONNE-MDD.md",
            "parse_status": "ok", "warnings": []},
    "RG":  {"id": "265453571", "md_path": "specs/SF-PERSONNE-RG.md",
            "parse_status": "partial",
            "warnings": ["tableau §3 : 6 colonnes trouvées, 5 attendues (ligne 12)"]},
    "CU":  [{"id": "329318407", "md_path": "...", "parse_status": "ok"}],
    "API": [{"id": "329023489", "md_path": "...", "parse_status": "ok"}]
  },
  "entites": [{"id": "PERSONNE.PP", "attributs": ["nom", "prenom", "dateNaissance"]}],
  "regles": [
    {"code": "RG-PERSONNE.PP-001", "categorie": "Saisie", "codes_erreur": ["PERS-001"],
     "existe_dans_rg": true, "citee_dans_cu": ["CU-PERSONNE-MODIFIER"],
     "citee_dans_api": ["API-PERSONNE"]}
  ],
  "regles_orphelines": ["RG-PERSONNE.PP-015"],
  "codes_erreur": ["PERS-001", "PERS-002"],
  "habilitations": {"CU-PERSONNE-MODIFIER": "ROLE_PERSONNE_WRITE"},
  "endpoints": [{"methode": "GET", "path": "/personnes/{id}", "statut_attendu": 200}],
  "champs_ihm": [{"page": "CU-PERSONNE-MODIFIER", "frame": "4.2",
                  "champ": "_IHM_PERSONNE_PP_Nom_", "mdd_ref": "PERSONNE.PP.nom"}],
  "rg_api_globales": {"API-PERSONNE": {"RG-API-1": true, "RG-API-2": true, "RG-API-3": true}}
}
```

**Frontière** : le pipeline produit des **faits** et des recoupements mécaniques. Les **verdicts, sévérités et scores** restent dans les skills — sinon changer un seuil impose de redéployer le pipeline.

### 4.4 `mcd_sinapse_data_YYYYMMDD.json` + `mcd_diff_YYYYMMDD.md`

Remplace le Bloc A de `confluence-mcd-sync`. Reconstruit depuis les pages MDD modifiées ; l'ancien fichier est conservé. Consommé par `qualite-mdd`, l'outil MCD HTML et les skills de génération.

### 4.5 Métadonnées des `.md`

```yaml
---
page_id: "329318407"
page_title: "CU-PERSONNE-MODIFIER"
page_url: "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/329318407"
confluence_version: 47
version_date: "2026-06-15T10:22:00Z"
exported_at: "2026-08-02T07:03:12Z"
pipeline_version: "1.0"
schema_version: 1
module: "PERSONNE"
type: "CU"
parse_status: "ok"
jira_test_key: "REC-95"
jira_jql: "id in linkedIssues(REC-95,\"réfère\") or \"Specs[URL Field]\" = \"...\""
---
```

`exported_at` est affiché dans l'en-tête de **tous** les comptes-rendus de skills.

Multiexcerpts résolus, marqués visiblement :

```markdown
> 📎 *Multiexcerpt **RG-PERSONNE-CARACTERES.AUTORISES** — source : [SF-PERSONNE: Règles de gestion consolidées](https://.../265453570)*

Les caractères autorisés sont : ...

> *(fin multiexcerpt RG-PERSONNE-CARACTERES.AUTORISES)*
```

Macros Jira remises en clair. **Le pipeline n'appelle pas Jira** : ces données sont plus volatiles que les specs et n'ont pas leur place dans une page de spec. Les appels Jira restent dans le skill `confluence-outil-lien-jira`, au moment de la validation.

---

## 5. Robustesse du run

| Sujet | Règle |
|---|---|
| Écriture | Atomique (temporaire + rename) — jamais de `.md` partiel visible |
| Fichiers inchangés | **Write-if-changed**, sinon SharePoint resynchronise tout chaque jour |
| Verrous OneDrive | `PermissionError` retenté |
| Rate limit | HTTP 429 avec backoff exponentiel, concurrence plafonnée |
| Reprise | Une page en échec n'interrompt pas le run ; listée au rapport, retentée au run suivant |
| Rapport | `.md` humain + `.json` machine : exportées / ignorées / en échec avec motif, multiexcerpts non résolus, nœuds non couverts, avertissements de parsing, pages non classifiées, durée |
| Tests | `fixtures/` rejouées à chaque modification du normalizer |

---

## 6. Impact sur les skills

### Supprimés

| Skill | Raison |
|---|---|
| `confluence-outil-analyse-module` | Remplacé par `index_croise_{MODULE}.json` |
| `confluence-validation-coherence-mdd-openapi` | OpenAPI hors périmètre |
| `confluence-validation-coherence-api-openapi` | Idem |

> **Conséquence assumée** : le contrôle **maxLength** (MDD ↔ DTO, sévérité CRITIQUE) disparaît. Deux actions obligatoires : **repondérer** l'orchestrateur (les poids 30/30/25/15 et les seuils 95/90 avaient été calibrés avec ce contrôle bloquant), et **documenter** dans le README de `confluence-validation-module` que la cohérence des longueurs n'est plus vérifiée.

### Modifiés — lecture sur `.md` local

`confluence-outil-lien-jira` (macros en clair depuis le `.md`, appels Jira conservés), `coherence-rg-cu-api`, `coherence-cu-api`, `coherence-codes-http` (partie OpenAPI retirée), `habilitations`, `completude`, `qualite-mdd`, `qualite-cu`, `validation-module` (phase 1 supprimée, phase 2 remplacée par l'index).

**Deux règles transverses dans chaque SKILL.md** : afficher `exported_at` en tête du compte-rendu ; ne pas scorer une page dont `parse_status ≠ ok`.

### `confluence-mcd-sync`

Bloc A absorbé par le pipeline. Bloc B (injection planning) reste un skill manuel.

---

## 7. Séquencement

### Étape 0 — Préliminaires

- **0a** Accès API REST depuis le poste : `GET /pages/{id}?body-format=atlas_doc_format`, double parsing de `.value`, listing des filles, recherche CQL.
- **0b** Réutilisation de `confluence_adf_multiexcerpt_resolver.py` — injection de fonctions `requests` en place des fonctions connecteur, **ou** réimplémentation comme visiteur de l'AST. À arbitrer au vu de 0d. Ne pas maintenir deux logiques.
- **0c** Environnement : Python 3.11+, `marklas` et `pyadf` installés.
- **0d** **Recensement ADF + bake-off** sur ~30 pages représentatives : inventaire des types de nœuds et des `extensionKey` ; conversion des mêmes 5 pages par les deux libs ; production de la table de normalisation définitive.
- **0e** Inventaire du space : nombre de pages, profondeur, volumétrie.

### Étape 1 — Export d'une page CU
`CU-PERSONNE-MODIFIER.md`, multiexcerpts résolus, macros Jira en clair. Validation par comparaison avec la page Confluence.

### Étape 2 — Une page par type
RG, MDD, API, JOB.

### Étape 2bis — Corpus doré
5-10 ADF + `.md` attendus figés dans `fixtures/`, avec les tests associés.

### Étape 3 — Inventaire et delta
Classification module/type, suppressions, renommages, slugification.

### Étape 4 — `multiexcerpt_cache.json`
Validation : sur `RG-PERSONNE-CARACTERES.AUTORISES`, les 3 consommateurs connus sont listés.

### Étape 5 — Index croisé sur le module PERSONNE
Validation : nombre de règles cohérent avec le RG ; une règle orpheline connue apparaît ; habilitations CU↔API conformes aux cartouches ; `parse_status` correct sur une page volontairement dégradée.

### Étape 6 — `mcd_sinapse_data`
Absorption du Bloc A. Validation par modification d'un attribut MDD.

### Étape 7 — Run complet
Mesure du temps, vérification du rapport, contrôle manuel de 5 pages.

### Étape 8 — Runs incrémentaux
Tester : page modifiée, source de multiexcerpt modifiée, suppression, renommage.

### Étape 9 — Planification Windows
Tâche quotidienne 7h, mode delta.

### Étape 10 — Adaptation des skills
Skill par skill, sur un module validé.

### Étape 11 — Run à la demande
Resynchronisation complète, sans argument de périmètre. En attendant : attendre le run du lendemain ou demander un lancement manuel.

---

## 8. Questions ouvertes et point de décision

| # | Question | À trancher | Comment |
|---|---|---|---|
| 1 | Bibliothèque de conversion : `marklas` ou `pyadf` | **Étape 0d** | Bake-off sur 5 pages réelles |
| 2 | Table de normalisation ADF définitive | **Étape 0d** | Sortie du recensement → `contracts/normalisation_adf.md` |
| 3 | Réutiliser ou réécrire le resolver multiexcerpt | **Étape 0b/0d** | Selon l'API de la lib retenue |
| 4 | Chemin SharePoint réel et exclusions de pages | **Étape 3** | `config.ini` |
| 5 | Repondération de l'orchestrateur après abandon d'OpenAPI | **Étape 10** | Recalcul des poids et des seuils |
| 6 | Sort de `confluence-outil-resolve-multiexcerpt` (retiré ou conservé en secours) | **Étape 10** | Dépend de la fiabilité du pipeline en production |
| 7 | Emplacement des 3 outils existants (`tools/` ou skill) | Au moment de les rapatrier | Artefact autonome → `tools/` ; déclenché en conversation → skill |
| 8 | Comment les BAs sur claude.ai accèdent aux `.md` | **Étape 10** | Miroir SharePoint conservé, ou passage des BAs sur Claude Code |
| 9 | Mécanisme de run à la demande | **Étape 11** | Python portable + `.bat`, ou CI |
| 10 | Distribution des skills aux BAs sur Claude Code (projet / plugin / entreprise) | Quand un 2ᵉ contributeur arrive | Le dépôt suffit tant qu'Olivier est seul |
| 11 | Migration du dépôt vers GitLab + CI planifiée | Après l'étape 9, ou à l'arrivée d'un 2ᵉ contributeur | `git remote set-url` — réversible pour rien |
| 12 | Runner CI capable de joindre `atlassian.net` | **À poser tôt, en parallèle** | Question longue à obtenir ; ne bloque rien mais conditionne la CI |

---

## 9. Décisions arrêtées

- Tout Python — aucun LLM dans le pipeline
- **Cadence quotidienne** (7h)
- Un seul `multiexcerpt_cache.json` global
- First run avec `last_run = 2020-01-01`, puis delta
- **Delta par `version.number`**, pas par date
- **Index croisé construit depuis l'ADF**, pas depuis le `.md`
- **`parse_status` obligatoire** ; les skills ne scorent pas une page non parsée
- **Pas de cache ADF brut global** — seulement `fixtures/` pour les tests. Une évolution du convertisseur implique un run complet depuis Confluence
- **Pas d'appel Jira dans le pipeline** — macros remises en clair, appels dans le skill
- **Un seul chemin de lecture** pour les skills : les `.md`, jamais Confluence
- **maxLength abandonné assumé**, avec repondération et mention au README
- Le pipeline produit des faits ; verdicts et scores restent dans les skills
- Écriture atomique + write-if-changed ; nœuds ADF non couverts remontés en erreur
- Frontmatter YAML visible ; multiexcerpts marqués visiblement
- **Git avec dépôt nu sur SharePoint comme remote** ; GitLab différé
- **Sorties du pipeline sur SharePoint d'équipe**, inchangé
- Aucun skill SINAPSE dans `~/.claude/skills/`
- Le token Atlassian n'est jamais versionné ni transmis en conversation
