# SINAPSE — Pipeline Confluence → Markdown

Dépôt du pipeline Python qui exporte les pages Confluence SINAPSE en `.md` + caches JSON,
et des skills Claude qui exploitent ces fichiers.

**Document de référence : `docs/brief-pipeline-sinapse-v3.md`.** En cas de contradiction
entre ce fichier et le brief, le brief fait foi — et ce fichier doit être corrigé.

`docs/guide_implementation_skills_sinapse_v4.md` (février 2026) cartographie les 31 skills,
leurs sources et leurs stratégies de reprise. Certains ont évolué depuis. En cas de
contradiction, le brief v3 et l'état réel des skills font foi.

## Architecture

Deux espaces distincts, à ne pas confondre :

| Espace | Contenu | Versionné |
|---|---|---|
| `C:\dev\sinapse-claude\` | le **code** : pipeline, skills, contrats | oui (Git) |
| `{local_path}\` (SharePoint) | les **sorties** : `specs/`, `docs/`, `cache/`, `reports/` | non |

```
CLAUDE.md              ce fichier
CLAUDE.local.md        spécificités de la machine courante — non versionné
.claude/rules/         règles ciblées par chemin (python.md)
.claude/skills/        LES SKILLS SINAPSE — source de vérité
contracts/             LE CONTRAT pipeline ↔ skills (schémas JSON, frontmatter, normalisation)
pipeline/src/          main, confluence_client, inventory, multiexcerpt, normalizer,
                       renderer, index_builder, mcd, report
pipeline/tests/        rejouent les fixtures
pipeline/fixtures/     5-10 ADF figés + .md attendus
pipeline/config.ini    NON VERSIONNÉ
tools/                 outils autonomes (restitution PUF, présentation MCD…)
build/                 make_skill_zip.py
docs/                  briefs, guides
docs/skills/           READMEs utilisateurs des skills
```

Règle de rangement : `.claude/skills/` = ce que Claude exécute ; `docs/skills/` = ce que les
humains lisent ; `contracts/` = ce qui lie les deux.

## Chaîne de traitement

```
ADF brut (API v2, body-format=atlas_doc_format)
  → résolution du contenu réutilisé (multiexcerpt + syncBlock)
  → normalisation Confluence        (aplatissement des nœuds spécifiques)
  → rendu markdown
  → frontmatter YAML + écriture atomique du .md
```

**Le corpus contient deux mécanismes de réutilisation de contenu**, et non un seul :
les multiexcerpts, portés par des nœuds `Extension` (6 variantes : trois de définition,
trois d'inclusion, dont la forme historique `multiexcerpt-include-macro`), et les
`syncBlock` / `bodiedSyncBlock`, qui **ne sont pas des nœuds `Extension`** — un visiteur
limité aux Extension les manquerait silencieusement. La clé de résolution d'un multiexcerpt
est le couple **(page, nom)**, jamais le nom seul : `habilitation` est défini sur plusieurs
pages différentes. Les noms sont encodés en entités HTML (`&period;`, `&lowbar;`) : décoder
par `html.unescape()`, sinon les identifiants de règles écrits dans le `.md` et l'index
croisé sont faux.

En parallèle : `pages_inventory.json`, `multiexcerpt_cache.json`,
`index_croise_{MODULE}.json`, `mcd_sinapse_data_YYYYMMDD.json`, puis le rapport de run.

## Décisions arrêtées — ne pas les rouvrir sans raison explicite

- **Aucun LLM dans le pipeline.** Tout est déterministe. Python pour le mécanique,
  Claude en conversation pour le sémantique.
- **Aucun appel Jira dans le pipeline.** Les liens Jira sont remis en clair dans le `.md` ;
  les appels restent dans le skill `confluence-outil-lien-jira`. Le corpus en contient
  **trois formes** : la macro historique `extension :: jira`, les `blockCard` portant une
  table via `attrs.datasource.parameters.jql`, et les `inlineCard` vers `/browse/REC-xxx`.
  En Confluence Cloud un lien Jira n'est le plus souvent **pas** une macro. Le JQL donne
  l'ancrage page ↔ ticket sans appeler Jira : `linkedIssues(REC-xxx,"réfère")` et le champ
  `Specs[URL Field]`.
- **Delta par `version.number`**, jamais par date : `lastmodified` est à la minute, sensible
  au fuseau, et ne bouge pas sur certains déplacements.
- **Index croisé construit depuis l'ADF résolu, pas depuis le `.md`.** Un tableau markdown
  perd sa structure dès qu'une cellule contient une liste — le cas des tableaux IHM
  (5 colonnes) et MDD (9 colonnes).
- **`parse_status` obligatoire par page.** Sans lui, un skill ne distingue pas « aucune règle »
  de « le parser a échoué ». Une page en `parse_status ≠ ok` n'est pas scorée, elle est signalée.
- **Le pipeline produit des faits.** Verdicts, sévérités et scores restent dans les skills —
  sinon changer un seuil impose de redéployer le pipeline.
- **Pas de cache ADF brut global** : seulement `fixtures/` pour les tests. Faire évoluer le
  convertisseur implique un run complet depuis Confluence.
- **Un seul chemin de lecture pour les skills : les `.md` locaux, jamais Confluence.**
- **Aucun nœud ADF ignoré silencieusement** — tout nœud non couvert remonte en erreur.
- **Aucun skill SINAPSE dans `~/.claude/skills/`.** Le personnel l'emporte sur le projet :
  une copie oubliée gagnerait silencieusement sur celle du dépôt.
- Écriture atomique + write-if-changed ; frontmatter YAML visible ; multiexcerpts marqués
  visiblement dans le `.md`.

## Sécurité

- Auth Basic : `ATLASSIAN_EMAIL` + `ATLASSIAN_API_TOKEN` en variables d'environnement
  (prioritaires) ou `config.ini` non versionné.
- **Le token n'est jamais écrit dans un fichier versionné ni cité en conversation.**
  Ne pas l'afficher, même pour le vérifier : tester l'accès par un appel API.
- `config.ini` et `CLAUDE.local.md` sont dans le `.gitignore` depuis le premier commit.

## Périmètre Confluence

Instance `sinapse-gie-nc.atlassian.net`, space `SINAPSE`, export récursif, profondeur illimitée.

| Groupe | Traitement | Pages racines |
|---|---|---|
| **A** — specs fonctionnelles | multiexcerpts résolus + index croisé | `1474581`, `1277977` |
| **B** — documentation | export `.md` simple | `1245499`, `1310723`, `219086849` |

## Conventions

- Python 3.11+, stdlib + `requests` ; toute autre dépendance se justifie.
  Les règles détaillées sont dans `.claude/rules/python.md` (chargé sur `pipeline/**/*.py`).
- Markdown et documentation en **français accentué**.
  Dans le code Python : commentaires et docstrings en français sans accents, ainsi que tout
  ce qui part vers `print()` — la console Windows en cp1252 casse l'affichage. En revanche
  le contenu écrit dans un fichier est accentué, avec `encoding="utf-8"` explicite à chaque
  ouverture.
- Commits en français, à l'impératif : `ajoute le normalizer des nœuds expand`.
- Chaque skill affiche `exported_at` en tête de son compte-rendu, et sa propre version
  (`Skill : nom-du-skill vX.Y`) pour repérer un décalage avec l'espace GIE claude.ai.

## Git

Pour l'instant, pas de GitHub ni de GitLab : le remote est un **dépôt nu déposé sur le
SharePoint GIE**. On n'y édite rien, on ne fait que `push` / `pull` — c'est ce qui évite les
conflits de synchronisation OneDrive. Migration GitLab différée (question ouverte n°11).

Avant le premier `push` : vérifier ce qui part (`git status`, `git diff --cached`).

## État d'avancement — mis à jour le 4 août 2026

Séquencement complet en section 7 du brief, questions ouvertes en section 8. Position actuelle :

- **Étape 0d terminée** — recensement ADF. `pipeline/src/recense_adf.py` (v1.1) a couvert
  le corpus complet : 246 pages sur 247, 36 types de nœuds, 12 macros, 15 marks.
  La page manquante est tombée sur un timeout transitoire et n'apporte aucun nœud inédit.
  Sorties dans `recensement/` (non versionné, régénérable).
- **`marklas` confirmé contre `pyadf`.** Les trois inconnues du bake-off sont toutes
  présentes dans le corpus — `layoutSection` (112 occurrences), `layoutColumn` (290),
  `bodiedExtension` (260) — et `pyadf` les jetterait.
- **Prochaine étape : la table de normalisation** (`contracts/normalisation_adf.md`),
  puis l'arbitrage réutiliser/réécrire le resolver multiexcerpt.
  **Ne pas écrire de code de conversion avant.**
- Restent à trancher, révélés par le recensement : la règle pour `syncBlock` /
  `bodiedSyncBlock`, celle pour `extension :: nested-table` (le marqueur que Confluence
  pose lui-même sur un contenu qu'il n'a pas su convertir — son paramètre `reason` est à
  remonter au rapport), et la classification des pages : 129 des 247 tombent en `AUTRE`,
  les `TYPE_PATTERNS` ne reconnaissant ni les pages `Q-*` ni la documentation du groupe B.
- `.claude/rules/skills.md` n'existe pas encore : il accueillera les conventions de nommage
  des skills, la limite des 500 lignes et le barème, au moment du rapatriement des skills
  (étape 10).
