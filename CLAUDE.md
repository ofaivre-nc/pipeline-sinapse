# SINAPSE — Pipeline Confluence → Markdown

Dépôt du pipeline Python qui exporte les pages Confluence SINAPSE en `.md` + caches JSON,
et des skills Claude qui exploitent ces fichiers.

**Document de référence : `docs/reference-pipeline-sinapse.md`.** Il porte les décisions et
leurs justifications ; le dépôt porte le détail technique.

**Règle d'arbitrage** : si ce dépôt et le document de référence divergent sur un **fait
technique**, le dépôt a raison. S'ils divergent sur une **décision ou sa justification**,
le document de référence a raison.

`docs/archive/brief-pipeline-sinapse-v3.md` est la version antérieure, conservée pour la
formulation d'origine des décisions. Ne pas s'y référer comme source active.

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
config.ini.example     gabarit de configuration ; à copier en pipeline/config.ini
.claude/rules/         règles ciblées par chemin (python.md)
.claude/skills/        LES SKILLS SINAPSE — source de vérité
contracts/             LE CONTRAT pipeline ↔ skills
  classification_pages.md          groupe, type, module, exclusions, 3 attributs
  normalisation_adf.md             table de normalisation ADF
  slugification.md                 règle de fabrication de `md_path`
  frontmatter.md                   métadonnées des .md exportés
  pages_inventory.schema.json      inventaire et delta
  reused_content_cache.schema.json multiexcerpt + syncBlock, deux clés
  index_croise.schema.json         agrégation par module
  mcd_sinapse_data.schema.json     données MCD — PROVISOIRE, voir le fichier
pipeline/src/          main, confluence_client, inventory, multiexcerpt, normalizer,
                       renderer, index_builder, mcd, report
pipeline/tests/        rejouent les fixtures
pipeline/fixtures/     5-10 ADF figés + .md attendus
pipeline/config.ini    NON VERSIONNÉ
tools/                 outils autonomes (restitution PUF, présentation MCD…)
build/                 make_skill_zip.py
docs/                  document de référence, guides
docs/skills/           READMEs utilisateurs des skills
docs/archive/          documents remplacés, conservés pour mémoire
```

Règle de rangement : `.claude/skills/` = ce que Claude exécute ; `docs/skills/` = ce que les
humains lisent ; `contracts/` = ce qui lie les deux.

### Distribution des skills

Deux canaux **indépendants** — une session Claude Code ne lit que le disque, elle ne voit
pas l'espace GIE de claude.ai.

| Canal | Public | Mécanisme |
|---|---|---|
| Dépôt `.claude/skills/` | Olivier, devs, BAs sur Claude Code | `git pull` |
| Espace GIE claude.ai | BAs sur l'interface web | zip produit par `build/make_skill_zip.py`, importé manuellement |

Le dépôt est la source de vérité ; l'espace GIE est une cible de déploiement.

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
conflits de synchronisation OneDrive. Migration GitLab différée, réversible en une commande.

```bash
git init --bare "<SharePoint>\sinapse\sinapse.git"
git remote add origin "<SharePoint>\sinapse\sinapse.git"
```

Aucun remote n'est configuré à ce jour : le chemin SharePoint sera renseigné le jour où le
travail à domicile devient nécessaire.

Avant le premier `push` : vérifier ce qui part (`git status`, `git diff --cached`).

## État d'avancement — mis à jour le 7 août 2026

Séquencement, position détaillée et questions ouvertes : sections 2 et 7 du document de
référence. Position en bref :

- **Étape 0d close.** `recense_adf.py` (v1.2) a couvert le corpus : 246 pages sur 247,
  36 types de nœuds, 12 macros, 15 marks. Sorties dans `recensement/` (non versionné,
  régénérable). **`marklas` confirmé contre `pyadf`** : `layoutSection` (112),
  `layoutColumn` (290), `bodiedExtension` (260) sont tous présents, `pyadf` les jetterait.
- **`contracts/normalisation_adf.md` est complet** : les 33 types de nœuds du corpus sont
  couverts, un type non couvert lève. Seul `fontSize` reste non arbitré — relevé dans le
  corpus complet, absent des 9 fixtures.
- **Slugification close** — `contracts/slugification.md`. Liste blanche `[A-Za-z0-9._-]`,
  point conservé, accents repliés, casse conservée, collisions détectées sur `casefold()`
  et levées au niveau du groupe de pages. Mesuré : 0 collision sur les 246 pages.
- **Étape 3 en cours** — `inventory.py` (v1.2) classifie les 246 pages et produit
  `slugify()` + la détection de collision. Restent l'**assemblage de
  `pages_inventory.json`** (carte indexée par identifiant, `md_path`, `last_exported`)
  et le **delta par `version.number`**.
- **Resolver** — `multiexcerpt.py` (v1.1) fournit les clés des trois mécanismes de
  réutilisation et le garde-fou de cycle, 75 tests. Le parcours récursif reste à écrire,
  avec l'arbitrage réutiliser/réécrire.
- `.claude/rules/skills.md` n'existe pas encore : il accueillera les conventions de nommage
  des skills, la limite des 500 lignes et le barème, au moment du rapatriement des skills
  (étape 10).
- `docs/anomalies-confluence.md` n'existe pas encore : il accueillera les anomalies à
  remonter aux BA, listées en section 8 du document de référence.
