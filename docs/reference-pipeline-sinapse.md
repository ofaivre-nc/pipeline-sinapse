# Pipeline SINAPSE — document de référence

*Document unique de la conversation de conception. Remplace `brief-pipeline-sinapse-v3.md`, archivé dans `docs/archive/`. Il succède aussi à un document de reprise de contexte antérieur, qui n'a vécu que dans l'espace de conversation : il n'en existe aucune trace dans le dépôt, inutile de l'y chercher.*
*Mis à jour le 7 août 2026 — étape 3 : slugification close, reste l'assemblage et le delta.*

---

## 0. Comment lire ce document, et où vit le reste

Ce document porte **ce qui a été décidé et pourquoi**. Il n'est vérifiable contre aucun fichier : si son contenu se perd, il se perd définitivement et les arbitrages sont à refaire.

Le détail technique — **ce qui existe** — vit dans le dépôt, maintenu par Claude Code et vérifiable contre le code :

```
C:\dev\sinapse-claude\
├── CLAUDE.md                    instructions de session
├── CLAUDE.local.md              spécificités machine — non versionné
├── config.ini.example           gabarit ; pipeline/config.ini non versionné
├── .gitignore
│
├── .claude/
│   ├── rules/python.md          règles Python, robustesse du run
│   ├── settings.json            permissions du projet — versionné
│   ├── settings.local.json      préférences du poste — non versionné
│   └── skills/                  vide — rapatriement à l'étape 10
│
├── contracts/                   LE CONTRAT pipeline ↔ skills
│   ├── classification_pages.md
│   ├── normalisation_adf.md
│   ├── slugification.md
│   ├── frontmatter.md
│   ├── pages_inventory.schema.json
│   ├── reused_content_cache.schema.json
│   ├── index_croise.schema.json
│   └── mcd_sinapse_data.schema.json     PROVISOIRE
│
├── docs/
│   ├── reference-pipeline-sinapse.md    ce document
│   ├── guide_implementation_skills_sinapse_v4.md
│   └── archive/                         brief v3, première séance
│
├── pipeline/
│   ├── src/
│   │   ├── recense_adf.py       v1.2 — porte la couche HTTP en attendant
│   │   │                        confluence_client
│   │   ├── inventory.py         v1.2 — classification + slugification
│   │   └── multiexcerpt.py      v1.1 — clés des 3 mécanismes
│   ├── tests/
│   │   ├── test_inventory.py        `python pipeline/tests/test_inventory.py`
│   │   └── test_multiexcerpt.py     ou `python -m pytest` ; sans dépendance
│   └── fixtures/
│       ├── 9 fixtures ADF figées (.json)
│       ├── pages_classification_20260805.json   corpus de non-régression
│       └── README.md
│
├── build/                       vide — make_skill_zip.py à venir
├── tools/                       vide
└── recensement/                 NON VERSIONNÉ, ~37 Mo, régénérable en 93 s
                                 sert aussi de boîte de dépôt — voir §9
```

Les modules annoncés par le brief archivé et encore absents — `main`, `confluence_client`, `normalizer`, `renderer`, `index_builder`, `mcd`, `report` — sont tous en aval de l'étape 3. `pipeline/CLAUDE.md`, prévu par l'arborescence du brief, n'a jamais été créé : `.claude/rules/python.md`, ciblé par chemin, remplit le même rôle.

**Règle** : si ce document et le dépôt divergent sur un fait technique, le dépôt a raison. S'ils divergent sur une décision ou sa justification, ce document a raison.

À joindre à une nouvelle conversation : ce document, plus `guide_implementation_skills_sinapse_v4.md` (cartographie des 31 skills, février 2026, partiellement périmé) et les `contracts/` concernés par le sujet.

**Convention de la ligne de date**, en tête : à chaque mise à jour, elle porte **la date et la dernière décision consignée** — « Mis à jour le 5 août 2026 — organisation des `.md` exportés ». Une date seule ne dit pas si l'on a devant soi la version qui tranche la question du jour ; le nom de la décision, si. Une modification qui ne consigne aucune décision ne touche pas cette ligne.

### Message d'amorçage suggéré

> Je construis un pipeline Python qui exporte les pages Confluence SINAPSE en `.md` + caches JSON, pour que mes skills Claude de validation de specs travaillent sur des fichiers locaux au lieu d'interroger Confluence à chaque session.
>
> Le document de référence joint décrit le projet, l'état d'avancement et les décisions prises : lis-le en premier. Le développement se fait en **Claude Code** sur mon PC ; toi, tu es mon interlocuteur de conception — tu m'aides à arbitrer, à rédiger les instructions à donner à Claude Code, et à relire ce qu'il produit. Tu n'as accès ni à Confluence ni à ma machine.
>
> Je débute sur Claude Code et sur Git : explique-moi ce que je fais quand ce n'est pas évident.

---

## 1. Pourquoi ce pipeline

### Les quatre phases

- **Phase 1 — prompts ad hoc** : aucune persistance.
- **Phase 2 — skills monolithiques** : séquencement non garanti, la résolution multiexcerpt pouvait être sautée. **C'est la cause racine des résultats aléatoires.**
- **Phase 3 — script + appels API Claude externes** : séquencement fiable, mais la mémoire de conversation devait être réimplémentée (mémoire JSON, `config_loader.py`). Abandonnée pour cette raison.
- **Phase 4 (actuelle)** — skills unitaires + orchestrateur. Python pour le déterministe, Claude en conversation pour le sémantique.

Le pipeline étend la Phase 4 : le fetch Confluence passe par l'API REST directe parce qu'il tourne hors session Claude. **Aucun LLM dans le pipeline** — donc aucun retour à la mécanique de la Phase 3.

### Le problème résolu

Les pages SINAPSE réutilisent du contenu : une règle définie une fois sur une page source est incluse ailleurs. L'API Confluence retourne ces inclusions vides en markdown. Le skill `confluence-outil-resolve-multiexcerpt` résout le problème en session, mais le résultat est local et éphémère : chaque BA, chaque conversation, doit recommencer.

### La solution cible

Un script Python autonome, planifié quotidiennement à 7h, qui établit l'inventaire des pages et détecte les changements, résout le contenu réutilisé, normalise les nœuds ADF spécifiques à Confluence, exporte chaque page en `.md` dans le SharePoint synchronisé, met à jour les caches JSON, et produit un rapport d'exécution `.md` + `.json`. Les skills Claude opèrent ensuite sur ces fichiers au lieu de lire Confluence.

### Environnement

- Atlassian Cloud : `sinapse-gie-nc.atlassian.net`, API REST v2 (`/wiki/api/v2`)
- Auth Basic (email + token API), token en variable d'environnement — **jamais versionné, jamais transmis en conversation**
- Python 3.11+, point d'entrée `.venv\Scripts\python.exe` (`requests` absent du Python système)
- Conversion ADF → MD : `marklas`

### Périmètre Confluence

**Groupe A — specs fonctionnelles** : contenu réutilisé résolu, index croisé produit, soumis aux validations.

| Page racine | ID |
|---|---|
| Spécifications fonctionnelles | `1474581` |
| Référentiels du projet | `1277977` |

**Groupe B — documentation** : export `.md` simple, sans résolution ni index.

| Page racine | ID |
|---|---|
| Analyse de l'existant | `1245499` |
| Documentations | `1310723` |
| Skills claude | `219086849` |

Export récursif, profondeur illimitée. 247 pages au total.

---

## 2. Où on en est

| Étape | État |
|---|---|
| 0a — accès REST | ✅ |
| 0b — resolver : réutiliser ou réécrire | 🟡 à trancher en écrivant le parcours récursif — **trois mécanismes** à couvrir désormais |
| 0c — environnement | ✅ |
| **0d — recensement + table de normalisation** | ✅ les 33 types du corpus sont couverts ; un type non couvert lève |
| 0e — inventaire du space | ✅ |
| 1, 2 — export d'une page, puis une par type | ⬜ |
| 2bis — corpus doré | 🟡 9 fixtures figées ; `.md` attendus manquants |
| **3 — inventaire et delta** | 🟡 classification ✅, slugification ✅ ; restent l'assemblage de `pages_inventory.json` et le delta |
| 4 — cache du contenu réutilisé | ⬜ |
| 5 — index croisé (module PERSONNE) | ⬜ |
| 6 — `mcd_sinapse_data` | ⬜ |
| 7 à 9 — run complet, incrémental, planification | ⬜ |
| 10 — adaptation des skills | ⬜ |
| 11 — run à la demande | ⬜ |

Deux étapes ouvertes en parallèle (0d et 3) : la classification a été anticipée parce qu'elle était devenue prérequis du resolver.

**Étape 3 — l'inventaire n'est pas encore assemblé.** `inventory.py` v1.1 émet un **tableau de pages à plat**, alors que `contracts/pages_inventory.schema.json` décrit une **carte indexée par identifiant** — la forme utile au delta. Ni `md_path` ni `last_exported` ne sont renseignés. L'assemblage arrive **avec la slugification et le delta**, qui closent l'étape ; ce qui existe aujourd'hui est un dump de classification, pas `pages_inventory.json`.

### Critères de validation par étape

Récupérés du brief archivé. Ce sont des **tests d'acceptation fondés sur une connaissance du corpus** : les perdre reviendrait à valider chaque étape à vue.

| Étape | Critère |
|---|---|
| **4** — cache du contenu réutilisé | sur `RG-PERSONNE-CARACTERES.AUTORISES`, les **3 consommateurs connus** sont listés |
| **5** — index croisé (module PERSONNE) | nombre de règles cohérent avec le RG ; **une règle orpheline connue apparaît** ; habilitations CU↔API conformes aux cartouches ; `parse_status` correct sur une page **volontairement dégradée** |
| **6** — `mcd_sinapse_data` | validation par **modification d'un attribut MDD** |
| **7** — run complet | mesure du temps, vérification du rapport, **contrôle manuel de 5 pages** |
| **8** — runs incrémentaux | tester les 4 cas : page modifiée, **source de contenu réutilisé modifiée**, suppression, renommage |

Le critère de l'étape 8 est à étendre : « source de multiexcerpt modifiée » date d'avant la découverte des `syncBlock`, puis de la famille `excerpt`. Les **trois** mécanismes doivent être testés, l'invalidation transitive valant pour chacun.

### Environnement en place

Claude Code opérationnel, dépôt `C:\dev\sinapse-claude`. Token Atlassian en variables `ATLASSIAN_EMAIL` / `ATLASSIAN_API_TOKEN`. **Aucun remote configuré** — le chemin SharePoint sera renseigné le jour où le travail à domicile devient nécessaire. `recensement/` non versionné (37 Mo, régénérable en 93 s).

### Prochaines étapes

1. **Assembleur de `pages_inventory.json`** — carte indexée par identifiant (la sortie actuelle d'`inventory.py` est un tableau à plat, dump de mise au point), `md_path`, `unclassified`, `last_exported`. Il appelle `slugify()` et `meres_exportantes()`.

   **Contrainte de conception arbitrée** : le calcul du chemin doit être une fonction pure d'`inventory.py`, prenant une page et rendant un `md_path`, sans dépendance à Confluence ni à un fichier de configuration — **pour que `pipeline/tests/test_inventory.py` l'appelle au lieu d'en recopier la logique**. `_md_path()` disparaît du fichier de tests le jour où l'assembleur existe. Ce n'est pas un nettoyage à prévoir après : conçu sans cette contrainte, l'assembleur sera inappelable depuis un test et la copie survivra. Elle a déjà piégé deux fois cette semaine — le chiffre 78 dupliqué entre contrat et commentaire, et la définition de « page avec filles » dupliquée entre `mesures_corpus()` et son propre test de non-régression, qui restait vert quand on annulait la correction. **Un test ne vaut que par ce qu'il partage avec le code qu'il surveille.**

2. **Delta à deux entrées — décision arbitrée.** `version.number` détecte modifications, suppressions et renommages de contenu. Il ne détecte **pas** les déplacements de fichier, parce que ceux-ci découlent de NOS règles de nommage et non d'un événement Confluence : quand une page reçoit sa première fille exportée, son `.md` passe de `{slug}.md` à `{slug}/{slug}.md` alors que **personne ne l'a touchée** — Confluence n'a rien enregistré à son sujet, ni version ni date.

   **Le delta compare donc deux champs** : `version.number` pour savoir si le contenu a changé, et le `md_path` calculé face à celui du `pages_inventory.json` du run précédent pour savoir si le fichier doit déménager. Un écart de chemin déclenche un **déplacement**, signalé comme tel au rapport, jamais une suppression suivie d'une création.

   **Coût nul** : comparer des `version.number` suppose déjà de connaître ceux de la veille, donc de relire l'inventaire précédent. C'est un champ de plus dans une boucle qui tourne de toute façon.

   **Pourquoi comparer le résultat et non les causes.** Déduire le déplacement de son déclencheur — « une page apparaît, donc sa mère descend d'un cran » — obligerait à écrire un détecteur par cause : première fille exportée, dernière fille archivée, page renommée, **ancêtre renommé (tout le sous-arbre bouge)**, changement de parent, exclusion posée ou levée, collision apparue ou résolue. Sept causes, dont une en cascade, et une huitième le jour où la règle de nommage évoluera — avec, à chaque oubli, des fichiers silencieusement au mauvais endroit. La comparaison des `md_path` les attrape toutes d'un coup, et les suivantes aussi, parce qu'elle porte sur la sortie.

3. **Test de conversion `marklas`** sur les 9 fixtures, warnings confrontés à `contracts/normalisation_adf.md`.
4. Puis étapes 1 et 2 (export de pages), 2bis (corpus doré complété), 4, 5…

#### La slugification — arrêtée le 7 août

Détail dans `contracts/slugification.md`. Trois décisions portent le reste :

- **Le point n'est pas touché.** La crainte d'origine — réduire `.` en `-` ferait entrer en collision `CU-NOTE-TYPENOTE.CREER` et `CU-NOTE-TYPENOTE-CREER` — supposait qu'il fallait le réduire. Le point est légal dans un nom de fichier Windows sauf en dernière position. Aucune désambiguïsation n'est nécessaire, et l'identifiant SINAPSE reste lisible tel que les BA l'écrivent.
- **Liste blanche `[A-Za-z0-9._-]`, pas liste noire.** Une liste noire des caractères interdits sous Windows laisserait passer parenthèses, espaces et esperluettes, tous légaux sous Windows et tous nuisibles ailleurs : les parenthèses cassent la syntaxe d'un lien Markdown. La liste blanche donne un `md_path` qui s'écrit tel quel dans un lien, sans encodage — c'est ce qui rend `normalisation_adf.md` §6.3 applicable.
- **Accents repliés, casse conservée.** Le slug est une clé d'adressage, le titre exact vit dans l'inventaire et le frontmatter. La détection de collision se fait sur `casefold()` : Windows, SharePoint et Git sur Windows sont insensibles à la casse.

Mesuré sur les 246 pages du recensement du 5 août : **0 collision**, `md_path` médian à 89 caractères, le plus long à **131**, **164** si l'on provisionne un niveau d'arborescence supplémentaire. Il reste donc **96 caractères** pour le préfixe SharePoint sous le plafond Windows de 260 — un chemin de synchronisation OneDrive courant en consomme 70 à 90. La marge est réelle et mince : le chemin SharePoint doit être choisi court.

Une piste a été mesurée puis fermée : tronquer le titre à son préfixe d'identifiant (`SF-COMPTE: Modélisation des données` → `SF-COMPTE`) produit **7 collisions entre frères** sur le corpus.

---

## 3. Ce qui a été établi

### Recensement ADF — corpus complet

247 pages, 498 appels API, 93 s : 36 types de nœuds, 12 macros, 15 marks, 3 formes de liens Jira. `recense_adf.py` v1.2. 9 fixtures dans `pipeline/fixtures/` couvrant 33 des 36 types.

- **`marklas` retenu** pour la conversion. `layoutSection`, `layoutColumn`, `bodiedExtension`, `expand`, `media`, `rule` sont tous présents dans le corpus ; `pyadf` les perdrait silencieusement.
- **Trois formes de liens Jira** : `blockCard` avec table JQL (82), `inlineCard` (6), macro historique `extension :: jira` (8). 64 tickets REC-* cartographiés page ↔ ticket **sans aucun appel Jira** — la décision tient.
- **`colspan` (6) et `rowspan` (10) existent**, plus 467 cellules à liste ou tableau imbriqué. Confirme « index croisé depuis l'ADF, pas depuis le `.md` ».
- **Décodage générique obligatoire** : `html.unescape()` — le corpus contient `&period;` et `&lowbar;`.
- **Marks à traiter** : `fragment`, `breakout`, `textColor`, `backgroundColor`, `alignment`, `annotation`, `subsup`, `border`, `fontSize`.

### Réutilisation de contenu — trois mécanismes, deux formes de clé

Deux familles de macros — `multiexcerpt` et `excerpt` natif, clé `(page, nom)` — et le
mécanisme `syncBlock`, clé `(page_id, uuid)`. Détail dans
`contracts/normalisation_adf.md` §1 ; les circonstances de la découverte de la seconde
famille sont en §5 de ce document.

**Multiexcerpt** — 6 variantes, 908 occurrences : 3 formes de définition (`bodiedExtension`, sans paramètre `page` : elles définissent sur leur propre page) et 3 formes d'inclusion.

- **Règle de reconnaissance** : `multiexcerpt` dans la clé → c'est un multiexcerpt ; corps présent → définition, absent → inclusion. **Ne jamais énumérer les variantes.**
- Clé de résolution : **`(page, nom)`** — le nom n'est pas unique globalement (`habilitation` défini 5 fois).
- La source est désignée **par titre**. Confluence maintient ce titre à jour côté serveur au renommage, sans incrémenter la version de la consommatrice. REST v2 et connecteur MCP concordent. **Aucun repli par ID nécessaire.**
- Nettoyage obligatoire : `html.unescape()` **puis** `.strip()` des deux côtés. 10 occurrences portent un espace de tête, cohérent des deux côtés aujourd'hui — la jointure marche par chance, une retouche d'un seul côté casserait 4 inclusions en silence. Vérifié : aucun couple de noms ne fusionne après nettoyage.
- L'inclusion **inline** se substitue dans un paragraphe : le remplacement doit produire des nœuds inline.

**`excerpt` natif** — 2 variantes relevées le 6 août, `excerpt` (définition) et `excerpt-include` (inclusion), sur `180256775` et `27787265`.

- Même forme de clé que le multiexcerpt, **`(page, nom)`**, et même désignation de la source **par titre** : aucun gain sur le renommage ni sur la dépendance à l'inventaire.
- **La page source se lit dans `macroParams[""]`**, la clé vide — pas dans `macroParams.page`. C'est le piège le plus dangereux du dossier : chercher `page` ne trouve rien, fait conclure « page courante », et résout contre une définition locale de même nom, sans erreur.
- **Reconnaissance par sous-chaîne**, `multiexcerpt` testé **avant** `excerpt` — le premier contient le second.
- **Index séparé du multiexcerpt** : Confluence ne croise pas les deux familles, le pipeline non plus.

**syncBlock** — mécanisme distinct, absent de l'échantillon initial. Un visiteur limité aux nœuds `Extension` le manquerait **en silence**.

```
bodiedSyncBlock (définition)  attrs.resourceId = "{UUID}"                           content = [...]
syncBlock       (inclusion)   attrs.resourceId = "confluence-page/{PAGE_ID}/{UUID}"  content = []
```

- Le contenu est **absent** de la page consommatrice → résolution nécessaire, ce n'est pas de la normalisation.
- Clé : **`(page_id, uuid)`**. Ce n'est pas une précaution théorique — le corpus contient déjà un `resourceId` défini sur **deux pages CU vivantes et scorées** (`CU-NOTE-CREER` 28344321 et `CU-NOTE-TYPENOTE.CREER` 396361729), avec des contenus divergents. Une indexation par UUID seul aurait choisi arbitrairement et produit du contenu faux sans lever d'erreur.
- Les inclusions restent non ambiguës : chacune porte son `confluence-page/{id}/`.
- Les 4 inclusions du corpus trouvent toutes leur définition, aucune orpheline.
- Enjeu mesuré : sans résolution, `CU-NOTE-MODIFIER` sort sans aucun de ses tableaux IHM, et `structure-cu` la validerait comme une CU sans frames.

**Les trois mécanismes cohabitent dans la même pile de récursion**, clés préfixées par leur mécanisme pour interdire toute collision — y compris entre une clé `multiexcerpt` et une clé `excerpt` de forme identique. `CycleGuard` implémenté dans `pipeline/src/multiexcerpt.py` v1.1, 75 tests. Le parcours récursif reste à écrire.

### `nested-table` — pas un échec de conversion

Le nœud porte `parameters.adf`, chaîne JSON contenant le document ADF complet de la table imbriquée : contenu intégralement récupérable par un second `json.loads()`. **Aucun `parse_status: partial`.** Vérifié sur les 248 fixtures : les 11 occurrences portent toutes `adf`, `cxhtml` et `reason`.

Le champ `reason` décrit une limitation de l'éditeur Confluence, et il est **localisé** (anglais et français observés sur le même module) — ne jamais matcher dessus. `cxhtml` coexiste avec `adf` : utiliser `adf`.

*Cette conclusion annule une décision antérieure fondée sur la seule lecture de `reason`.*

### Classification des pages

`pipeline/src/inventory.py` v1.1, 56 tests. La chaîne `parent_id` est complète sur 246/246 et aboutit toujours à une des 5 racines : l'appartenance groupe A/B est **dérivable localement**, sans appel API. L'endpoint ancêtres ne servira jamais.

232 exportées · 196 sources de contenu · 101 scorées · 14 exclues (5 directes, 9 héritées).

| Type | Pages | exported | content_source | scored |
|---|---|---|---|---|
| CU | 59 | ✅ | ✅ | ✅ |
| API | 23 | ✅ | ✅ | ✅ |
| MDD | 20 | ✅ | ✅ | ✅ |
| RG | 7 | ✅ | ✅ | ✅ |
| JOB | 6 | ✅ | ✅ | ✅ |
| MODULE (SF-*) | 38 | ✅ | ✅ | — |
| DOMAINE (Q-*) | 12 | ✅ | ✅ | — |
| UX | 12 | ✅ | ✅ | — |
| A_QUALIFIER | 7 | ✅ | ✅ | — |
| GENERIQUE | 5 | ✅ | ✅ | — |
| REFERENTIEL | 4 | ✅ | ✅ | — |
| SA | 3 | ✅ | ✅ | — |
| DOCUMENTATION | 50 | ✅ | — | — |
| HORS_PERIMETRE | 0 | — | — | — |

**14 valeurs de type**, et non 13 : `HORS_PERIMETRE` complète l'énumération sans avoir aucune occurrence dans le corpus — les 246 chaînes d'ascendance aboutissent toutes à une des 5 racines. Elle existe pour qu'une page rattachée hors périmètre ne puisse pas emprunter un type de spec par défaut.

**Règles acquises** — détail dans `contracts/classification_pages.md` :

- **Toute page du groupe A est `content_source`**, quel que soit son type. Une source peut vivre n'importe où dans l'arbre des specs ; un faux négatif casse une inclusion en silence. *Confirmé : une CU peut être source d'une autre CU.*
- **Aucun type partagé entre groupes A et B** — permet l'invariante : toute page du groupe A en `A_QUALIFIER` est une anomalie, le compteur doit tendre vers zéro.
- **Normalisation des titres avant matching** : `html.unescape()`, puis repli des tirets Unicode (U+2010–U+2015, U+2212, U+FE58, U+FF0D) vers l'ASCII. NFKC seul ne suffit pas. A permis de récupérer `CU-PERSONNE-RECHERCHER`, invisible à l'œil.
- **Préfixe d'exclusion retiré avant le typage**, jamais par désancrage des motifs — sinon `Archive CU-…` deviendrait une spec fantôme scorée.
- **L'exclusion est héritée par tout le sous-arbre.** Règle les doublons `(version avant API)` sans intervention des BA ; `exclude_page_ids` reste vide.
- **Module dérivé de l'ascendance** (ancêtre `SF-*`) en priorité, du titre à défaut.
- `DOC-*` et `TAB-*` : types réservés, non implémentés.

---

## 4. Impact sur les skills

### Supprimés

| Skill | Raison |
|---|---|
| `confluence-outil-analyse-module` | remplacé par `index_croise_{MODULE}.json` |
| `confluence-validation-coherence-mdd-openapi` | OpenAPI hors périmètre |
| `confluence-validation-coherence-api-openapi` | idem |

> **Conséquence assumée** : le contrôle **maxLength** (MDD ↔ DTO, sévérité CRITIQUE) disparaît. Deux actions obligatoires à l'étape 10 : **repondérer** l'orchestrateur (les poids 30/30/25/15 et les seuils 95/90 avaient été calibrés avec ce contrôle bloquant), et **documenter** dans le README de `confluence-validation-module` que la cohérence des longueurs n'est plus vérifiée.

### Modifiés — lecture sur `.md` local

`confluence-outil-lien-jira` (macros en clair depuis le `.md`, appels Jira conservés), `coherence-rg-cu-api`, `coherence-cu-api`, `coherence-codes-http` (partie OpenAPI retirée), `habilitations`, `completude`, `qualite-mdd`, `qualite-cu`, `validation-module` (phase 1 supprimée, phase 2 remplacée par l'index).

**Deux règles transverses à inscrire dans chaque SKILL.md** : afficher `exported_at` en tête du compte-rendu ; ne pas scorer une page dont `parse_status ≠ ok`.

### `confluence-mcd-sync`

Bloc A absorbé par le pipeline. Bloc B (injection planning) reste un skill manuel.

### Distribution

Deux canaux **indépendants** — une session Claude Code ne lit que le disque, elle ne voit pas l'espace GIE de claude.ai.

| Canal | Public | Mécanisme |
|---|---|---|
| Dépôt `.claude/skills/` | Olivier, devs, BAs sur Claude Code | `git pull` |
| Espace GIE claude.ai | BAs sur l'interface web | zip produit par `build/make_skill_zip.py`, importé manuellement |

Le dépôt est la source de vérité ; l'espace GIE est une cible de déploiement. La version en tête de chaque compte-rendu (`Skill : nom-du-skill vX.Y`) permet de repérer un décalage.

---

## 5. Décisions arbitrées — ne pas rouvrir sans raison

**Architecture**
- Tout Python — **aucun LLM dans le pipeline**, sinon retour à la mécanique abandonnée en Phase 3.
- Le pipeline produit des **faits** ; verdicts, sévérités et scores restent dans les skills — sinon changer un seuil impose de redéployer le pipeline.
- **Un seul chemin de lecture** pour les skills : les `.md` locaux, jamais Confluence.
- **Aucun appel Jira dans le pipeline** — données plus volatiles que les specs ; macros remises en clair, appels dans le skill `confluence-outil-lien-jira`.

**Données**
- **Delta par `version.number`**, jamais par date : `lastmodified` est à la minute, sensible au fuseau, et ne bouge pas sur certains déplacements. Le diff de versions donne en prime suppressions, renommages et déplacements.
- **Index croisé construit depuis l'ADF**, pas depuis le `.md` : les tableaux markdown perdent leur structure dès qu'une cellule contient une liste ou un saut de ligne — précisément le cas des tableaux IHM 5 colonnes et MDD 9 colonnes. **Mesuré le 6 août** : 13 des 56 tableaux des 9 fixtures portent au moins une cellule à contenu de bloc, et jusqu'à ~24 après injection des `nested-table`. Deux des CU analysées (`28344321`, `28344344`) en font partie.
- **`parse_status` obligatoire par page** : sans lui, un skill lisant `regles: []` ne peut pas distinguer « aucune règle » de « le parser a échoué », et produit un rapport entièrement faux. Une page en `parse_status ≠ ok` n'est pas scorée, elle est signalée.
- **Pas de cache ADF brut global** — seulement `pipeline/fixtures/` pour les tests. Une évolution du convertisseur implique un run complet depuis Confluence.
- **Aucun nœud ADF ignoré silencieusement** : tout nœud non couvert remonte en erreur au rapport. Un warning résiduel de la lib = un bug du normalizer.
- **`marklas`** pour la conversion ADF → Markdown.
- **Trois mécanismes de contenu réutilisé, deux formes de clé** : par titre pour les macros `multiexcerpt` **et** `excerpt` natif — clé `(page, nom)` ; par identifiant pour le `syncBlock` — clé `(page_id, uuid)`. Les index de définitions restent **séparés par mécanisme** : les croiser produirait un `.md` plus complet que la page réelle, et masquerait un affichage cassé que les rédacteurs voient à l'écran.
- **Le slug est une clé d'adressage, pas un libellé** : liste blanche `[A-Za-z0-9._-]`, point conservé, accents repliés, casse conservée, collisions détectées sur `casefold()`. Une collision **lève au niveau du groupe de pages, pas du run** : les pages concernées ne sont pas exportées, leurs `.md` antérieurs ne sont pas supprimés, et le fait ouvre le rapport. Aucune désambiguïsation automatique — un suffixe renommerait silencieusement une spec qui n'a pas bougé. Contrat : `contracts/slugification.md`.
- **OpenAPI hors périmètre** → maxLength abandonné assumé.

**Exécution**
- Cadence quotidienne, 7h. First run avec `last_run = 2020-01-01`, puis delta.
- Écriture atomique (temporaire + rename) ; **write-if-changed**, sinon SharePoint resynchronise tout chaque jour.
- Une page en échec n'interrompt pas le run : listée au rapport, retentée au run suivant.
- Frontmatter YAML visible ; contenu réutilisé marqué visiblement dans le `.md`.
- `exported_at` affiché dans l'en-tête de **tous** les comptes-rendus de skills.

**Organisation**
- Git avec dépôt nu sur le SharePoint comme remote ; GitLab différé, réversible en une commande.
- Sorties du pipeline sur le SharePoint d'équipe.
- **Aucun skill SINAPSE dans `~/.claude/skills/`** : le personnel l'emporte sur le projet, une copie oubliée gagnerait silencieusement sur celle du dépôt.
- Skills Claude Code et espace GIE claude.ai : deux stocks séparés.
- Le token Atlassian n'est jamais versionné ni transmis en conversation.
- **`contracts/` est la source de vérité technique** ; ce document ne le duplique pas.

### Organisation des `.md` exportés — l'arborescence Confluence est reproduite

*Décision prise le 5 août 2026. Elle n'avait jamais été arbitrée explicitement : le brief v3 impliquait un **répertoire plat** sous `specs/` et `docs/`, par le seul exemple `md_path: "specs/CU-PERSONNE-MODIFIER.md"`. Ce n'était pas un choix, c'était un exemple qu'on aurait fini par prendre pour une règle.*

Les `.md` reproduisent **la hiérarchie des pages Confluence**. Un BA qui connaît l'arbre Confluence retrouve un fichier sans consulter d'index, et un module se lit comme un tout au lieu d'être dispersé dans une liste de 232 fichiers.

**Les deux racines sont conservées** : `specs/` pour le groupe A, `docs/` pour le groupe B.

| Cas | Forme |
|---|---|
| Page **avec** filles | un répertoire `{slug}/`, contenant son propre contenu dans `{slug}/{slug}.md`, puis les fichiers et répertoires de ses filles |
| Page **sans** fille | un simple `{slug}.md` — **pas de répertoire à fichier unique** |

```
specs/
├── Q-IDENTITE-gestion-des-identites/
│   ├── Q-IDENTITE-gestion-des-identites.md
│   └── SF-PERSONNE-gestion-des-personnes/
│       ├── SF-PERSONNE-gestion-des-personnes.md
│       ├── SF-PERSONNE-Modelisation-des-donnees.md
│       └── CU-PERSONNE-MODIFIER.md
└── ...
```

**Conséquence à signaler au rapport** : l'ajout d'une première fille **déplace le `.md` de la page parente**, de `{slug}.md` vers `{slug}/{slug}.md`, alors que **son contenu n'a pas changé** et que sa `version.number` n'a pas bougé. Ce n'est ni une suppression ni une création : le rapport doit le nommer comme un déplacement, sinon le run se lit comme une anomalie inexpliquée. Le cas inverse — suppression de la dernière fille — vaut aussi.

**`md_path` dans `pages_inventory.json` reste la référence unique du chemin.** Les skills le **lisent depuis le cache** et ne le recalculent **jamais** depuis le titre : la profondeur, le slug du parent et la forme fichier-ou-répertoire ne sont pas dérivables d'un titre de page. Un skill qui reconstruirait un chemin le perdrait au premier déplacement.

### Le contenu réutilisé — trois mécanismes, et un incident qui en a révélé un

*Décision du 6 août 2026.*

Le 5 août, l'endpoint REST v1 « Convert content body » de Confluence a atteint sa
date de suppression définitive. La macro **MultiExcerpt Advanced** (app
Marketplace Appfire) l'utilisait en interne : elle a cessé de restituer le
contenu. Le service est revenu à la normale le 6 après mise à jour du plugin.

**Le pipeline n'a jamais été menacé** : il lit l'ADF brut et résout lui-même. Ce
qui a cassé, c'est l'affichage pour les rédacteurs. Cette indépendance est un
acquis de conception, pas une chance.

Pendant l'incident, un BA a testé la macro **Extrait native** de Confluence comme
contournement, sur `180256775` (25 définitions) et `27787265` (8 inclusions). La
limite historique d'un extrait par page **n'existe plus** : les extraits natifs
sont nommés, comme les multiexcerpts.

Décisions :

- **Le contrat documente la famille `excerpt` sans l'adopter**
  (`normalisation_adf.md` §1.8). Documenter n'est pas encourager : la famille est
  présente dans Confluence aujourd'hui, le code doit la reconnaître.
- **Aucune contrainte technique n'impose de choisir un mécanisme.** Les deux
  familles cohabitent déjà sur une même page — `180256775` porte 25 `excerpt`
  **et** 2 multiexcerpts résiduels. Le resolver classe nœud par nœud, jamais page
  par page.
- **Reconnaissance par sous-chaîne dans `extensionKey`, jamais par énumération**,
  avec `multiexcerpt` testé **avant** `excerpt` — le premier contient le second.
  Le corpus comptait six variantes le 4 août, deux de plus le 5 : une liste
  figée vieillit, une sous-chaîne non.
- **La page source ne se lit pas au même endroit** : `macroParams.page` pour le
  multiexcerpt, `macroParams[""]` pour l'`excerpt` natif — héritage du paramètre
  positionnel du wiki markup `{excerpt-include:Page|name=X}`. Un resolver qui
  chercherait `page` conclurait « page courante » et résoudrait contre une
  définition locale de même nom : contenu faux, plausible, **muet**. Cas réel sur
  `27787265`.
- **L'`excerpt` natif désigne sa source par titre**, comme le multiexcerpt : il
  n'apporte aucun gain sur la sensibilité au renommage ni sur la dépendance à
  `pages_inventory.json`. Seul le `syncBlock` règle ce point.
- **L'unité de migration est une définition et toutes ses inclusions**, jamais
  une page : convertir une source sans ses consommatrices casse l'affichage. Sur
  908 occurrences, c'est un travail de coordination — que l'index croisé sait
  produire. D'où l'ordre : **construire l'inventaire et l'index croisé, puis
  migrer avec**, et non l'inverse.

---

## 6. Exigences à porter dans le code

> **Backoff** — `confluence_client.py` doit couvrir `requests.exceptions.Timeout` et `ConnectionError`, pas seulement le HTTP 429. Le run complet du 4 août a perdu une page sur un timeout transitoire (elle repasse en 0,3 s au réessai) — page qui, de ce fait, n'est pas classée. À raison d'un run quotidien, ce sont des pages qui disparaissent des specs sans que personne ne le remarque.

> **Rangement** — `build_report()` vit provisoirement dans `inventory.py` ; sa place est dans `report.py` quand ce module existera.

> **Nommage des fichiers** — règle arrêtée, `contracts/slugification.md`. **Les collisions lèvent à la construction de l'inventaire**, elles ne sont pas seulement signalées : un fichier écrasé silencieusement fait disparaître une spec du corpus. Elles lèvent **au niveau du groupe de pages concerné**, le run se poursuit sur le reste, et la phase de nettoyage des orphelins doit ignorer ces pages — sinon une collision efface deux specs au lieu d'en manquer une.

> **Horodatage des sorties** — un run partiel ne doit pas pouvoir écraser le rapport d'un run complet du même jour.

---

## 7. Ce qui reste ouvert

**Technique**
- **réutiliser ou réécrire le resolver** (étape 0b) — deux voies : injecter des fonctions `requests` en place des fonctions connecteur dans `confluence_adf_multiexcerpt_resolver.py`, **ou** réimplémenter comme visiteur de l'AST. **Ne pas maintenir deux logiques.** Les clés, le `CycleGuard` et la classification en six natures sont faits ; le parcours récursif reste à écrire, et il doit couvrir **trois mécanismes**, ce que le resolver d'origine n'en couvre qu'un ;
- `fontSize` — relevé dans le corpus complet, absent des 9 fixtures : seul mark non arbitré. Il lève tant qu'il n'est pas tranché ;
- **forme inline de l'Extrait natif** — le corpus compte 53 inclusions inline en multiexcerpt (`…-include-inline-macro` ×50, `multiexcerpt-include-macro` ×3). L'essai du 5 août n'a produit que des nœuds `extension` de bloc, y compris en cellule de tableau où un bloc paraît en ligne. À vérifier par une insertion **au milieu d'une phrase, hors tableau** : si Confluence l'accepte, le nœud doit être un `inlineExtension` ;
- sort de `confluence-outil-resolve-multiexcerpt` (retiré ou conservé en secours) — dépend de la fiabilité du pipeline en production ;
- emplacement des 3 outils existants (`tools/` ou skill) : artefact autonome → `tools/` ; déclenché en conversation → skill.

**Périmètre**
- classification des 7 pages `A_QUALIFIER` (notes de cadrage, à qualifier une par une) ;
- **`-NEW- CU-COMPTE-PROFIL.GEST` est exclue, et son ancienne version l'est par héritage → cette spec disparaît entièrement du corpus.** Seul trou connu ;
- format des pages `SA-*` (services applicatifs) — typées, exportées, non scorées en attendant validation du principe ;
- exclusions de pages ;
- **chemin SharePoint réel** — devenu chiffré, et contraint : `md_path` mesure au plus 131 caractères aujourd'hui, 164 en provisionnant un niveau d'arborescence de plus. Il reste **96 caractères** de préfixe sous le plafond Windows de 260, quand un chemin de synchronisation OneDrive courant en consomme 70 à 90. Le chemin doit être choisi court, et mesuré avant le premier run complet ; le pipeline avertit à 200 caractères de chemin complet et lève à 250.

**Déploiement**
- repondération de l'orchestrateur après abandon d'OpenAPI (étape 10) ;
- accès des BAs sur claude.ai aux `.md` : miroir SharePoint conservé, ou passage des BAs sur Claude Code (étape 10) ;
- mécanisme de run à la demande : Python portable + `.bat`, ou CI (étape 11) ;
- distribution des skills aux BAs sur Claude Code — le dépôt suffit tant qu'Olivier est seul ;
- migration GitLab + CI, après l'étape 9 ou à l'arrivée d'un 2ᵉ contributeur ;
- **runner CI capable de joindre `atlassian.net`** — question longue à obtenir, à poser tôt en parallèle.

Côté **périmètre**, s'ajoutent :

- **sort de l'essai « Extrait natif »** du 5 août sur `180256775` et `27787265` : conservé, annulé, ou généralisé. Deux pages sont dans un état que personne n'a validé, et les rédacteurs ne savent pas quoi utiliser. Le pipeline n'impose rien — c'est une décision d'équipe ;
- **convention de couleurs des BA** — 5 valeurs de `backgroundColor` relevées, le surlignage signalant les évolutions à venir non encore développées. Le pipeline conserve le hex sans l'interpréter ; si une convention existe, elle est à documenter côté skills ;
- **sens du texte barré** — le mark `strike` est présent au corpus et conservé en `~~…~~`. Reste à confirmer ce qu'il signifie dans une spec : s'il marque du contenu périmé, il est le symétrique du surlignage et les skills de validation ne doivent pas le scorer comme du contenu actif. Question de convention BA, à poser avec celle des couleurs — le pipeline conserve le fait dans les deux cas ;
- **rafraîchir le corpus de non-régression** — `334888965` (`SF-COORDONNEE: Règles de gestion consolidées`, page RG) manque au recensement du 4 août, perdue sur un timeout ; s'y ajoutent `180256775` et `27787265`, modifiées le 5 août. À rejouer **dans un commit dédié**, où seul le jeu de données change : régénérer le dump, re-dériver **délibérément** les sept mesures du §11 de `contracts/slugification.md`, mettre à jour la fixture versionnée. Jamais en même temps que du code ;
- **coordination avec les BA pendant l'écriture du normalizer** — éviter qu'une conversion de masse se poursuive pendant que le pipeline se construit.

---

## 8. Anomalies Confluence à remonter aux BA

À tenir dans `docs/anomalies-confluence.md` :

- **`CU-NOTE-TYPENOTE.CREER` (396361729) est une copie de `CU-NOTE-CREER` (28344321) qui a hérité de ses identifiants de bloc** — même `resourceId`, même `localId`, contenus divergents. Deux specs vivantes prétendent définir le même bloc. Le pipeline s'en sort par la clé `(page_id, uuid)`, mais l'édition de l'une des deux réserve des surprises ;
- 5 requêtes JQL avec gabarit `{{page.url}}` non substitué — ces tables Jira ne ciblent aucune page réelle ;
- 3 `blockCard` sans datasource, en fait des liens SharePoint — **sur le corpus complet des 246 pages** ; les 9 fixtures du corpus doré n'en contiennent aucun, leurs 5 `blockCard` portent tous un `datasource` ;
- **`habilitation` défini deux fois sur `27787265`** — deux `bodiedExtension :: excerpt` de même nom, contenu identique à ce jour. Sans effet visible jusqu'au jour où les deux divergeront ; ni le plugin ni la macro native ne disent laquelle gagne. Le pipeline lève à la construction de l'index ;
- **`380567556` porte un `inlineCard` vers une URL d'édition** — `…/pages/edit-v2/380567556#IHM-concernant-la-gestion-du-profil…`, pointant vers la page elle-même. Un lien d'édition n'a rien à faire dans une spec ;
- `Règles génériques utilisables pour les recherches` (28803126) rangée sous `4. Patterns`, au milieu du sous-arbre Design System, alors que ses quatre sœurs sont directement sous la racine ;
- écart module titre/ascendance sur `SF-DOCUMENT` et `ARCHIVE_CU-DOSS-CONSULT` (titre annonce DOSS, arbre dit PERSONNE) ;
- `-NEW- CU-COMPTE-PROFIL.GEST` — préfixe à retirer si c'est la version vivante ;
- spécifications archivées encore rattachées à la racine `Spécifications fonctionnelles` (1474581) — leur déplacement hors du périmètre serait le geste propre, l'héritage d'exclusion en tient lieu en attendant.

*Non retenu comme anomalie : l'emplacement de `SF-DOSS: Messages système consolidés` sous « 2. Fondation et tokens » est volontaire (multiexcerpt source à terme).*

---

## 9. Contraintes de la relation de travail

- **L'interlocuteur de conception n'a accès ni à Confluence ni à la machine.** Son bac à sable ne peut pas joindre `atlassian.net`. Tout ce qui touche à Confluence passe par un script exécuté en local — ou par un partage de fixtures JSON en pièce jointe, qui s'est révélé efficace.
- **Le token Atlassian n'est jamais transmis en conversation** ni écrit dans un fichier versionné.
- Le développement se fait en Claude Code ; cette conversation sert à concevoir, arbitrer et relire.

### Échange de fichiers entre la conversation et le dépôt

**Les documents de référence vivent dans le dépôt.** La conversation ne régénère jamais un fichier existant : elle produit un **patch en blocs avant/après**, que Claude Code applique. Régénérer un document depuis la conversation efface silencieusement ce que Claude Code y a écrit entre-temps, et fait perdre l'historique Git de la modification réelle.

Deux natures de fichiers descendent de la conversation vers le dépôt, et elles ne se déposent pas au même endroit :

| Nature | Destination | Versionné |
|---|---|---|
| **Livrable** — contrat, code, schéma | sa place définitive (`contracts/`, `pipeline/src/`…) | oui |
| **Document de travail** — patch, note d'arbitrage, brouillon | `recensement/` | non |

**Un patch nomme sa cible par son chemin complet dans le dépôt** (`docs/…`,
`contracts/…`, `pipeline/src/…`). Un patch dont la cible n'existe pas n'est jamais
appliqué par interprétation : Claude Code s'arrête et demande.

`recensement/` sert de boîte de dépôt parce qu'il figure déjà au `.gitignore` : 37 Mo régénérables en 93 s, rien de ce qu'il contient n'a vocation à survivre. **C'est aussi sa limite** — un nouveau run de `recense_adf.py` peut le vider. Un patch en attente d'application ne doit pas y séjourner d'un jour à l'autre.

**Un patch se supprime une fois appliqué.** Le laisser en place fait courir le risque qu'il soit réappliqué sur un document qui a déjà bougé, ou lu comme l'état courant d'une décision qu'il ne fait que proposer.

**Dans l'autre sens**, la conversation n'a accès ni à Confluence ni à la machine : tout fichier du dépôt dont l'interlocuteur de conception a besoin — fixture ADF, cache JSON, module Python à relire — lui est **joint directement** en pièce jointe. L'aller-retour descriptif s'est révélé bien moins efficace, et ces pièces jointes sont aussi ce qui permet de mesurer une décision sur le corpus réel au lieu de l'arbitrer à vue.

**Ce qui ne transite jamais** : le token Atlassian, sous aucune forme.
