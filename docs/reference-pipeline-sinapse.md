# Pipeline SINAPSE — document de référence

*Document unique de la conversation de conception. Remplace `brief-pipeline-sinapse-v3.md`, archivé dans `docs/archive/`. Il succède aussi à un document de reprise de contexte antérieur, qui n'a vécu que dans l'espace de conversation : il n'en existe aucune trace dans le dépôt, inutile de l'y chercher.*
*Mis à jour le 11 août 2026 — contrat de rendu : marqueur de réutilisation rendu visible, marks lus par porteur, `date` / `emoji` / `mediaInline` couverts, `normalizer` fondu dans `renderer`.*

---

## 0. Comment lire ce document, et où vit le reste

Ce document porte **ce qui a été décidé et pourquoi**. Il n'est vérifiable contre aucun fichier : si son contenu se perd, il se perd définitivement et les arbitrages sont à refaire.

Le détail technique — **ce qui existe** — vit dans le dépôt, maintenu par Claude Code et vérifiable contre le code :

```
C:\dev\pipeline-sinapse\         (C:\dev\sinapse-claude\ jusqu'au 2026-10-23)
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
│   │   ├── inventory.py         v1.4 — classification, slugification, md_path,
│   │   │                        assemblage de pages_inventory.json
│   │   ├── multiexcerpt.py      v1.1 — clés des 3 mécanismes
│   │   └── delta.py             v1.0 — plan de run entre deux inventaires
│   ├── tests/
│   │   ├── test_inventory.py        stdlib pure : tournent sur un dépôt
│   │   ├── test_multiexcerpt.py     fraîchement cloné, sans rien installer
│   │   ├── test_delta.py
│   │   └── test_contracts.py        exige `jsonschema` — voir §9
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

Les modules annoncés par le brief archivé et encore absents — `main`, `confluence_client`, `renderer`, `index_builder`, `mcd`, `report` — sont tous en aval de l'étape 3. **`normalizer` a été retiré de cette liste le 11 août** : normalisation et rendu ne se coupent pas sans inventer un nœud marqueur pour la séparation des colonnes (§4.1 du contrat) ni sans risquer de décider du mode d'un tableau après avoir aplati ses `panel` (§9.1 / §9.2). Un seul module, `renderer.py`, avec le mode de sortie — markdown ou HTML — en paramètre. `pipeline/CLAUDE.md`, prévu par l'arborescence du brief, n'a jamais été créé : `.claude/rules/python.md`, ciblé par chemin, remplit le même rôle.

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
- Conversion ADF → MD : **aucune bibliothèque** — `renderer.py`, écrit sur l'ADF brut

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
| **0b — resolver** | ✅ réécrit — `resolver.py` v1.0, les trois mécanismes, 117 contrôles |
| 0c — environnement | ✅ |
| **0d — recensement + table de normalisation** | ✅ les 33 types du corpus sont couverts ; un type non couvert lève |
| 0e — inventaire du space | ✅ |
| 1, 2 — export d'une page, puis une par type | ⬜ |
| 2bis — corpus doré | 🟡 9 fixtures figées ; `.md` attendus manquants |
| **3 — inventaire et delta** | ✅ classification, slugification, assemblage, delta |
| 4 — cache du contenu réutilisé | ⬜ |
| 5 — index croisé (module PERSONNE) | ⬜ |
| 6 — `mcd_sinapse_data` | ⬜ |
| 7 à 9 — run complet, incrémental, planification | ⬜ |
| 10 — adaptation des skills | ⬜ |
| 11 — run à la demande | ⬜ |

Deux étapes ouvertes en parallèle (0d et 3) : la classification a été anticipée parce qu'elle était devenue prérequis du resolver.

**Étape 3 close.** `inventory.py` v1.4 assemble `pages_inventory.json` — carte indexée par identifiant, `md_path`, `collisions`, `complete`, `unclassified`, `last_exported` — et `delta.py` v1.0 en dérive le plan d'un run. Le dump de classification à plat subsiste sous `--dump` : il produit la fixture de non-régression, et son nom dit désormais ce qu'il est. Reste à écrire `main.py`, qui exécutera le plan que `compare()` décide.

**Étape 0b close.** `resolver.py` v1.0 couvre les trois mécanismes en un parcours unique, sur l'ADF brut. 117 contrôles, verts au point d'entrée autonome comme sous `pytest`. Le resolver d'origine n'a pas été porté : voir §5. Restent, avant l'étape 4, la remise de `renderer.py` et l'écriture de `main.py`.

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

Claude Code opérationnel, dépôt `C:\dev\pipeline-sinapse` (nommé `C:\dev\sinapse-claude` jusqu'au 2026-10-23). Token Atlassian en variables `ATLASSIAN_EMAIL` / `ATLASSIAN_API_TOKEN`. Remote : dépôt GitHub privé `ofaivre-nc/pipeline-sinapse` depuis le 2026-10-21, à la place du dépôt nu SharePoint prévu au départ ; il synchronise le poste pro et le poste perso. `recensement/` non versionné (37 Mo, régénérable en 93 s).

### Prochaines étapes

1. **Remise de `pipeline/src/renderer.py`** et de ses tests, transcription de `contracts/normalisation_adf.md` sur l'ADF brut. L'essai de conversion du 9 août tient lieu de prototype : 9 fixtures sur 9, 394 lignes, aucune dépendance. Restent à écrire les tests de non-régression, dont ceux des cas absents du corpus doré — cellules fusionnées, famille `excerpt`, `fontSize`.
2. **Étapes 1 et 2** — export d'une page CU, puis une par type. `main.py` exécute le plan que `compare()` décide : `compare()` ne touche ni Confluence ni le disque, et instancie le resolver **une fois** pour tout le run — c'est ce qui rend l'index des pages sources réutilisable d'une page à l'autre.
3. **Remesurer le §9.1 de `contracts/normalisation_adf.md` au premier run complet.** Les comptes y sont désormais donnés à deux stades, et le stade qui fait foi — après injection des `nested-table` et résolution — reste un plancher sur le corpus doré : 12 de ses 32 inclusions s'y résolvent, 19 visent des pages absentes des 9 fixtures, et la 32ᵉ est orpheline pour de bon (sa page source est présente, sa définition n'existe pas). Les chiffres eux-mêmes vivent au §9.1 et nulle part ailleurs.
4. Puis 2bis — **le corpus doré complété de ses `.md` attendus**, dans un **commit dédié** où seuls ces fichiers changent. Les générer avec le renderer qu'on vient d'écrire ne prouve rien : tant qu'ils ne sont pas relus, ils ne sont pas une référence. **La relecture est le test d'acceptation de l'étape**, au même titre que le contrôle manuel de 5 pages l'est pour l'étape 7.
5. Puis 4, 5…

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

- **Aucune bibliothèque ADF.** Le recensement portait sur la couverture de parsing — `layoutSection`, `layoutColumn`, `bodiedExtension`, `expand`, `media`, `rule` sont tous présents dans le corpus, et `pyadf` comme `atlas-doc-parser` les perdraient. `marklas` passait ce critère, mais l'essai du 9 août a montré qu'il n'émet aucun warning et que son renderer échappe la syntaxe markdown injectée : il ne peut produire ni les tableaux HTML du §9.1, ni le marqueur d'image du §5, et il perd le JQL et les couleurs. Le rendu est propre à SINAPSE ; il est écrit dans `pipeline/src/renderer.py`, mesuré à 394 lignes pour les 9 fixtures.
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

**Les trois mécanismes cohabitent dans la même pile de récursion**, clés préfixées par leur mécanisme pour interdire toute collision — y compris entre une clé `multiexcerpt` et une clé `excerpt` de forme identique. `CycleGuard` implémenté dans `pipeline/src/multiexcerpt.py` v1.1, 77 tests. Le parcours récursif reste à écrire.

### `nested-table` — pas un échec de conversion

Le nœud porte `parameters.adf`, chaîne JSON contenant le document ADF complet de la table imbriquée : contenu intégralement récupérable par un second `json.loads()`. **Aucun `parse_status: partial`.** Vérifié sur les 248 fixtures : les 11 occurrences portent toutes `adf`, `cxhtml` et `reason`.

Le champ `reason` décrit une limitation de l'éditeur Confluence, et il est **localisé** (anglais et français observés sur le même module) — ne jamais matcher dessus. `cxhtml` coexiste avec `adf` : utiliser `adf`.

*Cette conclusion annule une décision antérieure fondée sur la seule lecture de `reason`.*

### Classification des pages

`pipeline/src/inventory.py` v1.4, 166 tests. La chaîne `parent_id` est complète sur 246/246 et aboutit toujours à une des 5 racines : l'appartenance groupe A/B est **dérivable localement**, sans appel API. L'endpoint ancêtres ne servira jamais.

232 exportées · 196 sources de contenu · 101 scorées · 14 exclues (5 directes, 9 héritées).

**Méthode** : mesuré sur `recensement/pages_classification_20260805.json`, soit 246 pages classées moins 14 exclues. `334888965` manque à ce dump et n'est donc dans aucun des quatre comptes — le périmètre d'export **réel** en compte 233, voir §7.

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
- **`version.number` jamais la date** : `lastmodified` est à la minute, sensible au fuseau, et ne bouge pas sur certains déplacements. Le diff de versions donne en prime suppressions et renommages. Mais `version.number` **ne suffit pas** : le delta compare trois champs, voir « L'étape 3 » ci-dessous.
- **Index croisé construit depuis l'ADF**, pas depuis le `.md` : les tableaux markdown perdent leur structure dès qu'une cellule contient une liste ou un saut de ligne — précisément le cas des tableaux IHM 5 colonnes et MDD 9 colonnes. Un quart des tableaux du corpus doré sont concernés, dont ceux de deux CU analysées. Décompte tenu à un seul endroit, `contracts/normalisation_adf.md` §9.1 : un chiffre recopié ici divergerait à la première remesure, ce qui s'est produit le 9 août.
- **`parse_status` obligatoire par page** : sans lui, un skill lisant `regles: []` ne peut pas distinguer « aucune règle » de « le parser a échoué », et produit un rapport entièrement faux. Une page en `parse_status ≠ ok` n'est pas scorée, elle est signalée.
- **Pas de cache ADF brut global** — seulement `pipeline/fixtures/` pour les tests. Une évolution du convertisseur implique un run complet depuis Confluence.
- **Aucun nœud ADF ignoré silencieusement** : tout nœud non couvert remonte en erreur au rapport. Un warning résiduel de la lib = un bug du normalizer.
- **Aucune bibliothèque ADF en exécution.** `requests` reste la seule dépendance du run. Le rendu ADF → Markdown transcrit `contracts/normalisation_adf.md` dans `pipeline/src/renderer.py`. Motif : les règles de rendu sont des décisions métier SINAPSE, qu'aucune bibliothèque ne peut connaître ; et le seul candidat qui passait le critère de parsing (`marklas`) n'émet aucun warning, ce qui prive la règle « aucun nœud ignoré silencieusement » de tout appui.
- **Trois mécanismes de contenu réutilisé, deux formes de clé** : par titre pour les macros `multiexcerpt` **et** `excerpt` natif — clé `(page, nom)` ; par identifiant pour le `syncBlock` — clé `(page_id, uuid)`. Les index de définitions restent **séparés par mécanisme** : les croiser produirait un `.md` plus complet que la page réelle, et masquerait un affichage cassé que les rédacteurs voient à l'écran.
- **Le slug est une clé d'adressage, pas un libellé** : liste blanche `[A-Za-z0-9._-]`, point conservé, accents repliés, casse conservée, collisions détectées sur `casefold()`. Une collision **lève au niveau du groupe de pages, pas du run** : les pages concernées ne sont pas exportées, leurs `.md` antérieurs ne sont pas supprimés, et le fait ouvre le rapport. Aucune désambiguïsation automatique — un suffixe renommerait silencieusement une spec qui n'a pas bougé. Contrat : `contracts/slugification.md`.
- **OpenAPI hors périmètre** → maxLength abandonné assumé.

**Exécution**
- Cadence quotidienne, 7h. First run avec `last_run = 2020-01-01`, puis delta.
- Écriture atomique (temporaire + rename) ; **write-if-changed**, sinon SharePoint resynchronise tout chaque jour.
- Une page en échec n'interrompt pas le run : listée au rapport, retentée au run suivant.
- Frontmatter YAML visible ; **contenu réutilisé encadré de marqueurs visibles dans un lecteur markdown**, et non d'un commentaire HTML — forme en `contracts/normalisation_adf.md` §1.9.
- `exported_at` affiché dans l'en-tête de **tous** les comptes-rendus de skills.

**Organisation**
- Git avec dépôt nu sur le SharePoint comme remote ; GitLab différé, réversible en une commande. *Remplacé le 2026-10-21 par un dépôt GitHub privé.*
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

### Le resolver — réécrit, parce que l'original n'était pas réparable

*Décision du 9 août 2026. `resolver.py` v1.0, 117 contrôles.*

La question posée était « réutiliser ou réécrire ». Elle s'est tranchée en lisant le
resolver d'origine : ses quatre défauts ne sont pas des bugs, ce sont ses fondations.

- **Sa clé de résolution est le nom seul.** `habilitation` est défini sur 3 des 9
  fixtures ; l'injection se faisant par `str.replace()` sur le markdown déjà produit,
  le dernier contenu lu est recopié dans **tous** les emplacements. Aucune erreur n'est
  levée : trois habilitations différentes deviennent la même.
- **Il injecte après avoir converti**, quand la chaîne du contrat résout avant de
  normaliser. Le contenu injecté sort donc d'un convertisseur qui n'est pas celui qui
  produit le `.md`.
- **Il ne décode pas les entités HTML.** ` RG-NOTE-ASSOCATION&period;PERSONNE` ne joint
  jamais sa définition, et l'échec est imputé à une page source introuvable.
- **Il ne redescend pas dans ce qu'il injecte**, et n'a pas de garde-fou de cycle. Deux
  des 32 inclusions du corpus doré sont pourtant logées dans un corps de définition.

Ce qui en a été gardé : la **forme du compte-rendu** — un statut par inclusion, qui
alimente `parse_status` — et ses quatre défauts, devenus les quatre premiers tests.
C'est sa vraie valeur : la spécification empirique du problème, découverte en usage.

**Trois décisions de structure en découlent.**

- **Un parcours unique** traite l'injection des tables imbriquées et la résolution de
  la réutilisation à la même descente. Chacune peut révéler du travail pour l'autre —
  une table imbriquée peut contenir une inclusion, un corps de définition peut contenir
  une table imbriquée — et tout ordre séquentiel laisse un cas dehors. Aucun de ces deux
  croisements n'a d'occurrence dans les 9 fixtures : le parcours unique est une
  précaution gratuite, pas une nécessité mesurée.
- **`resolver.py` n'appelle jamais Confluence.** Il reçoit un fournisseur à deux
  méthodes, `par_titre()` et `par_identifiant()`. C'est ce qui rend les tests
  exécutables hors réseau : celui des tests lit `pipeline/fixtures/`. Sans cette
  séparation, éprouver la résolution imposerait de joindre Confluence, donc de ne plus
  l'éprouver.
- **Une définition est indexée puis traversée, jamais remplacée.** Une définition
  s'affiche aussi là où elle est écrite : la page RG montre ses propres règles. La
  remplacer viderait les pages sources de leur contenu.

**Une page source hors périmètre est lue, pas exportée.** Le titre est d'abord cherché
dans la carte titre → identifiant bâtie depuis `pages_inventory.json` — gratuite, aucun
appel ; à défaut seulement, un appel par titre exact. Les définitions de la page trouvée
sont alors indexées **d'un coup** : on paie un appel par page source distincte, pas un
par inclusion. Mesuré sur le corpus doré : `241532980` porte 7 inclusions pour 3 appels.
Deux pages du périmètre de même titre, ou deux réponses à une recherche par titre,
**lèvent** — contrôle à la construction de l'index, comme la détection de collision de
slug.

**La carte indexe les deux formes du titre, `title` et `title_raw`.** Motif mesuré :
`299499522` (`CU-PERSONNE-RECHERCHER`) porte un tiret insécable U+2011 que la
slugification replie et que `clean_page_title()` ne replie pas. Un seul cas sur 246,
mais il suffit à rendre la page introuvable par titre. La leçon dépasse le cas : deux
normalisations indépendantes de la même chaîne divergent, et la divergence ne se voit
que là où les deux se rencontrent.

**Deux assertions écrites pour ce module ont d'abord survécu à la régression qui aurait
dû les tuer**, et c'est le seul motif pour lequel elles ont été trouvées : dix
régressions ont été injectées dans une copie du dépôt, pas dans les fichiers réels.
L'une comparait deux injections par leur seule racine — or le parcours reconstruit les
dictionnaires qu'il traverse, donc deux injections partageant tout leur sous-arbre ont
malgré tout des racines distinctes. L'autre éprouvait une collision de `resourceId` sur
une page source vide, où les deux résolutions échouaient pareillement.

**Une consigne de cette instruction était elle-même fausse** : elle annonçait des
contenus différents pour `habilitation` sur `28344321` et `28344344`. Ils sont
identiques au `localId` près. Suivie à la lettre, elle produisait une assertion de
différence verte grâce à un identifiant interne — un contrôle qui ne mesure rien. Le
couple `28344321` / `380567556`, dont les contenus diffèrent réellement, porte
l'assertion. Une consigne ne dispense pas de vérifier la donnée qu'elle invoque.

### L'étape 3 — inventaire assemblé et delta à trois entrées

*Décisions des 8 et 9 août 2026. `inventory.py` v1.4, `delta.py` v1.0.*

- **Le delta compare trois champs, pas un.** `version.number` dit si le contenu a changé. Le `md_path` calculé, face à celui du run précédent, dit si le fichier doit déménager — un déplacement ne découle pas d'un événement Confluence mais de **nos** règles de nommage : quand une page reçoit sa première fille exportée, son `.md` bouge alors que personne ne l'a touchée et que Confluence n'a rien enregistré. `last_exported` à `null` sur une page exportable dit qu'elle **n'a jamais été écrite** — l'inventaire s'écrivant après l'export, c'est la signature d'un run interrompu. Sans cette troisième entrée, un plantage à mi-export laisse des pages définitivement manquantes.
- **Comparer le résultat, non les causes.** Déduire un déplacement de son déclencheur imposerait un détecteur par cause — première fille exportée, dernière fille archivée, page renommée, ancêtre renommé (tout le sous-arbre bouge), changement de parent, exclusion posée ou levée, collision apparue ou résolue. Sept causes, dont une en cascade, et une huitième à la prochaine évolution de la règle. Comparer les `md_path` les attrape toutes, et les suivantes aussi.
- **`complete` est la seule autorisation de détruire.** Une collecte partielle ne supprime rien, et **dit ce qu'elle s'est interdit** : les suppressions écartées partent au rapport, sinon personne ne saura qu'un incident a eu lieu. Motif : une page absente de l'inventaire courant est indistinguable d'une page supprimée, et le cas s'est produit — `334888965` perdue sur un timeout le 4 août.
- **Le ré-rendu complet se déclenche sur « un fichier cesse d'exister à son ancien chemin »**, pas sur « un chemin a changé ». C'est la seule chose qui casse un lien relatif entrant. Trois exclusions en découlent, toutes délibérées : une collision n'en déclenche pas — son `.md` reste en place ; une collecte incomplète non plus — elle ne détruit rien ; une **création** non plus, et l'asymétrie se démontre : pour pointer vers une page neuve, il faut avoir édité la page pointeuse, dont la `version` a donc bougé.
- **`schema_version` différent ⟹ le précédent est remplacé par `None`.** Aucun de ses champs n'est lu, ni pour les états ni pour les suppressions : « traité comme absent » ne veut dire quelque chose que si rien n'est lu. Conséquence assumée — des `.md` devenus orphelins survivent à ce run, faute de précédent pour les repérer. Le sens de l'erreur est le bon : un orphelin se rattrape au run suivant, une spec supprimée à tort ne se rattrape pas. Et un changement de `schema_version` est un acte délibéré de développement, pas un événement de production.

### Un fait de décision ne se lit jamais dans un message destiné à l'humain

**Motif récurrent, rencontré deux fois en cinq jours** — le `reason` d'un `nested-table`, et le `warnings` d'une page en collision. À reconnaître avant de le reproduire une troisième.

`md_path: null` était ambigu entre « page non exportée » et « page en collision ». Les deux portent aussi `exported: false` : le seul discriminant restant était le **texte d'un `warnings`**. Or la différence décide de l'effacement d'un fichier — dans un cas le `.md` antérieur est un orphelin à supprimer, dans l'autre il doit être **conservé**. D'où le tableau `collisions` de premier niveau dans `pages_inventory.json`, avec ses trois consommateurs : le delta, le nettoyage des orphelins, le rapport de run.

C'est exactement la faute que `contracts/normalisation_adf.md` §2.1 interdit déjà pour `nested-table`, dont le champ `reason` est **localisé** — anglais et français observés sur le même module : détecter le cas dessus aurait marché jusqu'à la première page rédigée dans l'autre langue.

**La règle générale** : un message en clair est écrit pour être lu par quelqu'un. Il est traduit, reformulé, enrichi d'un détail — sans que personne n'imagine qu'une décision en dépendait. Tout fait dont une décision dépend se porte dans un champ structuré, dédié, et dont l'absence est détectable.

### Un test ne vaut que par ce qu'il partage avec le code qu'il surveille

**Cinq instances en une semaine.** Le motif est toujours le même : un contrôle qui paraît protéger quelque chose, et qui reste vert quand ce qu'il surveille casse.

1. **La copie de `_md_path()`.** L'assemblage du chemin vivait dans le fichier de tests, faute d'équivalent dans le module : le test vérifiait donc une seconde implémentation au lieu de la vraie. La contrainte de conception a été **tenue par anticipation** — le calcul du chemin devait être une fonction pure d'`inventory.py`, prenant une page et rendant un `md_path`, sans dépendance à Confluence ni à un fichier de configuration, précisément pour que `pipeline/tests/test_inventory.py` l'appelle au lieu d'en recopier la logique. `md_path()` est descendu dans le module **avant** l'assembleur, et non après : conçu plus tard, il aurait été inappelable depuis un test et la copie aurait survécu. Ce n'était pas un nettoyage à prévoir ensuite, c'était une contrainte à poser d'abord.
2. **Une valeur mesurée dupliquée entre contrat et commentaire.** Le contrat annonçait un slug maximal de 78 — valeur héritée d'une règle candidate abandonnée, en liste noire, qui conservait la virgule. Corrigé en 77 dans le contrat, il est resté 78 dans le commentaire du code : un fait dupliqué en deux endroits diverge dès la première correction. C'est précisément le mode de défaillance que `contracts/` existe pour empêcher.
3. **La définition de « page avec filles » dupliquée** entre `mesures_corpus()` et son propre test de non-régression. Le test calculait lui-même son ensemble de mères : il restait vert quand on annulait la correction dans le code mesuré. Une fonction unique et partagée l'a réglé — et la régression simulée fait désormais échouer deux vérifications sur six.
4. **La vérification de nommage née vide.** À son premier essai, elle a rapporté `collectees == []` : le bloc `__main__` était placé avant la définition du point d'entrée, et elle inspectait un namespace où il n'existait pas encore. Elle a trouvé son propre défaut parce qu'elle est écrite en **assertion positive** — la liste doit valoir exactement le point d'entrée attendu. Un contrôle qui n'échouerait que sur un coupable identifié aurait été vert.
5. **Le nom du fichier, angle mort de cette même vérification.** Renommé hors de `test_*.py` / `*_test.py`, un fichier n'est plus collecté du tout par pytest — en silence — pendant que le point d'entrée autonome continue d'afficher `OK`. La vérification de namespace ne voyait rien : elle inspecte un module que pytest ne visite jamais.

S'y ajoute un cas voisin, qui n'est pas une duplication mais la même famille de silence : **le test de contrat qui aurait pu se sauter**. `test_contracts.py` dépend de `jsonschema` ; son absence le fait **échouer**, avec le message d'installation, jamais passer. Un test de contrat qui se saute quand son outil manque est vert partout où l'outil manque — c'est-à-dire exactement là où on aurait besoin de lui.

**Deux règles en découlent**, toutes deux inscrites dans `CLAUDE.md` parce qu'elles doivent être lues à chaque session : la forme durable d'un contrôle est l'**assertion positive** — dire ce qu'on a trouvé, pas qu'on n'a rien trouvé de coupable — et **commiter avant d'injecter une régression de contrôle**, la remise en état ayant détruit du travail non enregistré deux fois le 8 août.

### Un nombre mesuré entre dans un contrat avec sa méthode

*11 août 2026. Le patch de contrat de ce jour a remplacé des chiffres justes par des faux.*

Une remesure a annoncé 1667 cellules et 97 complexes là où le contrat portait 1633 et 84. L'écart — exactement 34 et 13 — a été lu comme du contenu jusque-là non compté, celui des tables imbriquées. C'était l'inverse : les 34 cellules des deux tableaux injectés étaient comptées **deux fois**, une fois pour le tableau interne et une fois pour son hôte. Les deux hypothèses produisent le même écart, et rien dans le nombre transmis ne permettait de les départager.

**« 1633 cellules » ne veut rien dire ; « 1633 cellules, chacune rattachée à son `table` le plus proche, comptée une fois, parcours entrant dans `parameters.adf` » se vérifie et se rejoue.** Toute valeur mesurée inscrite dans un contrat porte désormais sa méthode. Et une remesure qui contredit un chiffre existant doit expliquer **l'écart**, pas seulement produire le nouveau nombre — c'est l'explication, pas le résultat, qui distingue une correction d'une erreur.

Le motif est voisin des cinq de la section précédente sans s'y confondre : ce n'est pas un fait dupliqué qui diverge, c'est un fait transmis sans ce qui permettrait de le vérifier.

### Une décision formulée pour un usage se vérifie contre la façon dont cet usage a lieu

*11 août 2026, découvert en relisant la décision « contenu réutilisé marqué visiblement ».*

La décision était bonne : un lecteur doit voir qu'un passage vient d'ailleurs, faute de quoi il tenterait de le corriger sur la mauvaise page. Sa transcription — un commentaire HTML `<!-- inclusion : … -->` — a rendu le marqueur **invisible dans un lecteur markdown**, c'est-à-dire dans le seul mode où les specs sont lues. Le dispositif satisfaisait le mot « visiblement » au sens du fichier brut, que personne n'ouvre.

Le mot juste dans une décision ne garantit rien : il faut le confronter à la manière dont le résultat sera consommé. La question qui manquait tenait en six mots — **avec quel outil vas-tu lire ?**

Corollaire opérationnel : le défaut a été trouvé en projetant un cas concret sous les yeux de celui qui lira, pas en relisant la décision. Une décision de rendu se valide sur un extrait rendu.

---

## 6. Exigences à porter dans le code

> **Backoff** — `confluence_client.py` doit couvrir `requests.exceptions.Timeout` et `ConnectionError`, pas seulement le HTTP 429. Le run complet du 4 août a perdu une page sur un timeout transitoire (elle repasse en 0,3 s au réessai) — page qui, de ce fait, n'est pas classée. À raison d'un run quotidien, ce sont des pages qui disparaissent des specs sans que personne ne le remarque.

> **Rangement** — `build_report()` vit provisoirement dans `inventory.py` ; sa place est dans `report.py` quand ce module existera.

> **L'ADF résolu doit survivre à l'export de sa page** — `main.py` le remet à une liste de collecteurs avant de passer à la page suivante. **La liste est vide aujourd'hui : c'est une porte, pas une fonctionnalité.** Motif : l'index croisé (étape 5) et `mcd_sinapse_data` (étape 6) se construisent depuis l'ADF résolu et non depuis le `.md`, et il n'existe **aucun cache d'ADF brut global** — décision arrêtée au §5. Le seul moment où cette donnée existe est pendant le run. Un `main.py` qui résout, rend, écrit et jette imposerait un second run complet sur le réseau pour reconstruire une donnée qu'on avait eue en main. La contrainte se pose avant d'écrire le module, comme `md_path()` est descendu dans `inventory.py` **avant** l'assembleur : conçue après, elle aurait été inatteignable.

> **Nommage des fichiers** — règle arrêtée, `contracts/slugification.md`. **Les collisions lèvent à la construction de l'inventaire**, elles ne sont pas seulement signalées : un fichier écrasé silencieusement fait disparaître une spec du corpus. Elles lèvent **au niveau du groupe de pages concerné**, le run se poursuit sur le reste, et la phase de nettoyage des orphelins doit ignorer ces pages — sinon une collision efface deux specs au lieu d'en manquer une.

> **Horodatage des sorties** — un run partiel ne doit pas pouvoir écraser le rapport d'un run complet du même jour.

---

## 7. Ce qui reste ouvert

**Technique**
- **croisement réutilisation ↔ table imbriquée** — le parcours unique de `resolver.py` le traite, mais le corpus doré ne l'exerce pas : aucune inclusion dans une table imbriquée, aucune table imbriquée dans un corps de définition. Deux tests synthétiques en tiennent lieu. À reprendre sur le corpus complet, où les 11 tables imbriquées offrent plus de matière que les 2 des fixtures ;
- **`fontSize` — arbitré le 10 août (jeté, texte conservé) et mesuré le même jour** : 3 occurrences sur le corpus complet, toutes `{"fontSize": "small"}`, portées par un `paragraph` et non par un nœud `text`, sur trois pages UX (`521142301`, `521797667`, `522092547`) où elles réduisent la même légende de statuts. Le cas du titre simulé — texte agrandi en place d'un `heading` — **n'existe pas dans le corpus** : aucune entrée au registre d'anomalies. Ce qui reste ouvert n'est plus la décision mais la couverture : `fontSize` est absent des 9 fixtures, donc aucun test de non-régression ne l'exerce tant que le corpus doré n'accueille pas une de ces trois pages ;
- **forme inline de l'Extrait natif** — le corpus compte 53 inclusions inline en multiexcerpt (`…-include-inline-macro` ×50, `multiexcerpt-include-macro` ×3). L'essai du 5 août n'a produit que des nœuds `extension` de bloc, y compris en cellule de tableau où un bloc paraît en ligne. À vérifier par une insertion **au milieu d'une phrase, hors tableau** : si Confluence l'accepte, le nœud doit être un `inlineExtension` ;
- sort de `confluence-outil-resolve-multiexcerpt` (retiré ou conservé en secours) — dépend de la fiabilité du pipeline en production ;
- emplacement des 3 outils existants (`tools/` ou skill) : artefact autonome → `tools/` ; déclenché en conversation → skill ;
- **option `--tout` de `main.py`** — un changement du **rendu** produit des `.md` différents à partir d'ADF identiques, et aucun des trois champs comparés par le delta ne le voit : ni la version Confluence, ni le chemin, ni `last_exported`. Il faudra pouvoir forcer un ré-rendu sans attendre qu'une page bouge ;
- **index des liens entrants — optimisation, pas correction.** Le ré-rendu complet est **correct par construction** : il réécrit tout dès qu'un fichier cesse d'exister à son ancien chemin, donc aucun lien relatif ne reste cassé. Un index des liens entrants ne rendrait pas le résultat plus juste, il éviterait seulement de réécrire **un fichier par page exportée** quand une seule page bouge. Ce compte vaut 232 aujourd'hui, et c'est le **même nombre** qu'au §3, par la même origine : le run écrit un `.md` par page exportée, y compris pour une page à filles, qui donne un seul `{slug}/{slug}.md`. **L'égalité ne survivra pas à la reclassification de `334888965`** : le compte de fichiers suit le périmètre d'export réel (233), celui de la classification suit le dump (232) — un 233 qui apparaîtra ici ne sera pas une erreur. À n'ouvrir que si le coût d'un run complet devient mesurable — et **jamais comme la correction d'un défaut**, il n'y en a pas.
- **résidus de `normalizer` dans la documentation** — le module a été fondu dans `renderer.py` le 11 août, et cinq documents portent encore son nom. `.claude/rules/python.md` en compte cinq occurrences, dont une règle écrite deux fois et une mention de « la bibliothèque de conversion », qui n'existe plus ; `contracts/slugification.md` une ; ce document deux — « un warning résiduel de la lib = un bug du normalizer » au §5, et « coordination avec les BA pendant l'écriture du normalizer » ci-dessous. Différés et connus : à reprendre dans un **commit de nettoyage dédié**, jamais mêlé à du code. Les numéros de ligne ne sont pas donnés, ils seraient faux au premier patch ;
- **`localId` n'identifie pas un tableau** — piège pour l'index croisé, à ne pas découvrir en l'écrivant. Un même `localId` porte trois tableaux distincts au corpus doré, et la résolution d'un `syncBlock` en duplique un quatrième. Seule la paire `(page, localId)` est unique, et seulement dans un document donné : vérifié aux deux stades du §9.1, 58 puis 60 clés distinctes. Un `localId` seul ne peut servir de clé nulle part ;
- **une page du périmètre est absente du dump de classification** — `334888965` (SF-COORDONNEE: Règles de gestion consolidées), la page RG perdue sur un timeout au recensement du 4 août et jamais reclassée. Elle n'est pas exclue : elle manque. Toute mesure qui définit son périmètre en écartant « les pages absentes du dump » l'écarte avec les vraies exclusions, sans le dire — le périmètre d'export compte 232 pages classées, 233 en la comptant. Vérifié le 11 août : elle ne porte aucune inclusion inline, donc aucun chiffre du §1.9 n'en dépend. À reclasser au premier rafraîchissement du recensement ;

**Périmètre**
- **réorganisation des specs autour des services applicatifs** — les pages `SA` deviennent le point d'exposition, et les fiches API se simplifient en renvoyant systématiquement vers une SA. Rien n'est à défaire : le type `SA` existe déjà dans la classification, et l'index croisé est arbitré comme construit depuis l'ADF résolu. Trois décisions en découlent, toutes à prendre **avant l'étape 5**, aucune avant : la **convention de rédaction du renvoi API → SA** — lien `inlineCard` (§6.3 du contrat) ou multiexcerpt, jamais les deux, une pratique mixte rendant l'index faux à moitié sans le signaler, et le geste est à figer avec les BA avant que vingt pages soient écrites dans les deux styles ; le **format du graphe SA → SA / API / JOB**, qui traverse les modules et ne rentre donc pas tel quel dans un `index_croise_{MODULE}.json` par module — ou l'on duplique les arêtes, ou l'on porte des références pendantes ; l'entrée au corpus doré d'une **première SA et d'une première API du nouveau format**, dans le commit dédié où seul le jeu de données change, sans quoi ni le renderer ni l'index ne seront éprouvés sur la nouvelle organisation ;
- **extension de `mcd_sinapse_data`** — relier attribut, DTO, entité et champ demande de croiser MDD, API et SA. Le schéma est déjà marqué PROVISOIRE et rien n'est à défaire : ce sont des tableaux 9 et 4 colonnes, précisément le cas qui a motivé « depuis l'ADF, pas depuis le `.md` ». Exigence à tenir dès la première ligne : **un lien qui ne s'établit pas est un fait, pas une erreur** — un attribut de DTO sans correspondant au MDD se consigne avec sa cause, et c'est au skill de décider si c'est grave. À l'étape 6 ;
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

**Tenues dans `docs/anomalies-confluence.md`**, seul endroit où cette liste vit. Le
registre a été ouvert le 10 août ; la liste ci-dessous **en a été retirée** — elle n'est
conservée ici sous aucune forme, y compris abrégée. Deux entrées neuves l'ont rejointe :
deux règles incluses et jamais définies, sorties du premier passage de `resolver.py`.

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
