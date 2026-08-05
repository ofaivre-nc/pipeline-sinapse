# Table de normalisation ADF

Ce que le pipeline fait de chaque nœud ADF du corpus SINAPSE.

**État : partiel.** Trois mécanismes sont tranchés et implémentés côté clés de
résolution (`pipeline/src/multiexcerpt.py`, verrouillé par
`pipeline/tests/test_multiexcerpt.py`). Le reste de la table — `expand`,
`layoutSection` / `layoutColumn`, `media`, les `card` Jira, `status`, `taskList` — reste
à arrêter à partir du recensement du 4 août 2026 (`recensement/recensement_adf_20260804.md`).

Base factuelle : 248 fixtures ADF balayées, dont les deux fixtures d'analyse
`CU-NOTE-CREER` (`28344321`) et `CU-NOTE-MODIFIER` (`28344344`).

**Règle qui domine tout le reste** : aucun nœud n'est ignoré silencieusement. Un nœud
non couvert par cette table remonte en erreur au rapport de run.

---

## 1. Contenu réutilisé — deux mécanismes, deux clés

Le corpus porte **deux** mécanismes de réutilisation, et non un seul. Ils se traitent
dans **le même visiteur** — un seul parcours de l'arbre — mais **jamais avec la même
clé**.

| | multiexcerpt | syncBlock |
|---|---|---|
| Nœuds | `extension`, `bodiedExtension`, `inlineExtension` | `syncBlock`, `bodiedSyncBlock` |
| Désignation de la source | **titre** de page | **identifiant** de page |
| Clé de résolution | `(page, nom)` | `(page_id, uuid)` |
| Résolution | index des définitions du space | `GET /pages/{id}` direct |
| Dépend de `pages_inventory.json` | oui | **non** |
| Sensible au renommage | oui — voir §1.4 | **non** |
| Occurrences | 908 | 4 inclusions, 5 définitions |

### 1.1 Ces deux mécanismes relèvent du resolver, pas du normalizer

La résolution du contenu réutilisé précède la normalisation dans la chaîne :

```
ADF brut → résolution du contenu réutilisé → normalisation → rendu markdown
```

Étendre le normalizer aux `syncBlock` serait une erreur d'étage : le normalizer aplatit
des nœuds dont il a le contenu sous la main, alors qu'ici **le contenu est absent de la
page consommatrice** et exige un appel réseau. C'est la définition même du travail du
resolver.

**Un visiteur limité aux nœuds `Extension` manquerait les syncBlock en silence** : ce ne
sont pas des extensions, ce sont des types de nœuds à part entière. Le point d'entrée
unique du visiteur est `classify_reuse_node()`, qui rend l'une de quatre natures :
`multiexcerpt_definition`, `multiexcerpt_include`, `sync_definition`, `sync_include`.

### 1.2 syncBlock — forme exacte, relevée sur les deux fixtures

Sur la page **consommatrice** (`CU-NOTE-MODIFIER`), le nœud est vide :

```json
{"type": "syncBlock",
 "attrs": {"resourceId": "confluence-page/28344321/fb607b8e-c344-4322-93eb-6e86a5304bc8",
           "localId": "495b88f2-b0e1-43ca-a83f-f4e5bb599a8b"},
 "content": []}
```

Sur la page **source** (`CU-NOTE-CREER`), la définition porte le **même UUID sans le
préfixe de chemin**, et le contenu réel :

```json
{"type": "bodiedSyncBlock",
 "attrs": {"resourceId": "fb607b8e-c344-4322-93eb-6e86a5304bc8",
           "localId": "e1231288-0b9d-431e-b239-7fb1e6108d96"},
 "content": [ ... 2 nœuds ... ]}
```

D'où deux formes de `resourceId`, à ne jamais confondre — une forme inattendue lève, elle
ne se devine pas :

| Rôle | `resourceId` |
|---|---|
| inclusion | `confluence-page/{PAGE_ID}/{UUID}` |
| définition | `{UUID}` |

`localId` ne sert pas à la résolution : il identifie l'instance de nœud dans le document.

### 1.3 L'UUID seul ne suffit pas — cas réel de collision

**C'est la raison d'être de la clé `(page_id, uuid)`.** Le corpus contient le même
`resourceId` défini en `bodiedSyncBlock` sur **deux pages différentes** :

| Page | UUID | Contenu |
|---|---|---|
| `28344321` CU-NOTE-CREER | `2342b419-9e51-43bd-81f4-c45e0ca27d9b` | 3 nœuds |
| `396361729` CU-NOTE-TYPENOTE.CREER | `2342b419-9e51-43bd-81f4-c45e0ca27d9b` | 2 nœuds |

`CU-NOTE-TYPENOTE.CREER` est une copie de `CU-NOTE-CREER` : elle a hérité du
`resourceId` **et** du `localId`, puis les deux contenus ont divergé. Les quatre pages
concernées sont des specs `CU` vivantes et scorées du module `NOTE`, pas des archives.

Une résolution par UUID seul choisirait l'une des deux définitions arbitrairement et
produirait un contenu faux sur l'une des deux pages consommatrices, **sans aucune
erreur**. Les inclusions, elles, sont non ambiguës : `confluence-page/28344321/…` et
`confluence-page/396361729/…` désignent chacune sa page.

### 1.4 Ce que syncBlock gagne sur multiexcerpt

La source étant désignée par identifiant :

- résolution par `GET /pages/{id}` **direct**, sans consulter `pages_inventory.json` ;
- **insensible au renommage** de la page source.

Le multiexcerpt vise un titre, donc dépend de la réécriture de `macroParams.page.value`
par Confluence lors d'un renommage. Vérifié le 5 août 2026 sur la page de test
`586416131` : le REST v2 retourne bien le **nouveau** titre après renommage, comme le
connecteur MCP. Ça fonctionne, mais ça repose sur un comportement serveur qu'on ne
maîtrise pas — d'où l'obligation de remonter toute inclusion non résolue en erreur.

### 1.5 Les 6 variantes de macro multiexcerpt

Relevé du 4 août 2026. **Trois définitions** (`bodiedExtension`, paramètres
`fallback` / `hidden` / `name`, pas de `page`) et **trois inclusions** (paramètres
`name` / `page` / `macro_uuid`) :

| Variante | Nœud | Rôle | Occurrences |
|---|---|---|---|
| `multiexcerpt-fast-include-block-macro` | `extension` | inclusion | 595 |
| `multiexcerpt-fast-block-macro` | `bodiedExtension` | définition | 190 |
| `multiexcerpt-macro` | `bodiedExtension` | définition | 69 |
| `multiexcerpt-fast-include-inline-macro` | `inlineExtension` | inclusion | 50 |
| `multiexcerpt-include-macro` | `inlineExtension` | inclusion (forme historique) | 3 |
| `multiexcerpt-fast-inline-macro` | `bodiedExtension` | définition | 1 |

Une **définition ne porte aucun paramètre `page`** : elle définit sur sa propre page. Sa
clé se construit donc avec le titre de la page hôte, fourni par l'appelant. Une
inclusion dont `page` est vide vise la page courante.

### 1.6 Récursion et cycles

Aucune imbrication dans les deux fixtures analysées, **mais rien ne l'interdit** : une
définition peut contenir une inclusion, d'un mécanisme comme de l'autre. La résolution
est donc récursive, avec détection de cycle (`CycleGuard`) et plafond de profondeur.

Les clés des deux mécanismes cohabitent dans la même pile, **préfixées par leur
mécanisme** : sans ce préfixe, un `(page_id, uuid)` pourrait collisionner avec un
`(page, nom)` de même forme. Un cycle et un dépassement de profondeur lèvent tous deux,
et remontent au rapport.

### 1.7 Ce qui reste à écrire

Le parcours récursif complet attend l'arbitrage **réutiliser ou réécrire le resolver**
multiexcerpt (question ouverte n°3 du brief) et la couche de récupération des pages.
`multiexcerpt.py` v1.0 ne contient que ce qui est indépendant de cet arbitrage : clés,
extraction de paramètres, garde-fou de cycle.

---

## 2. `extension :: nested-table` — contenu intégralement récupérable

**Ce nœud ne déclasse pas la page en `parse_status: partial`.**

C'est un marqueur que Confluence pose lui-même sur un contenu que **son éditeur** ne sait
pas éditer — une table dans une cellule de table. Le champ `reason` décrit cette
limitation de l'éditeur, **pas un échec de conversion**. Et le contenu est là :

| Paramètre | Contenu | Usage |
|---|---|---|
| `adf` | **chaîne JSON** portant un document ADF complet | **à utiliser** |
| `cxhtml` | la même table en XHTML de stockage | à ignorer |
| `reason` | message d'éditeur, **localisé** | à ne jamais tester |

Traitement : second `json.loads()` sur `parameters.adf` — même double parsing que
`body.atlas_doc_format.value` — puis **injection des nœuds obtenus à la place de
l'extension**. La table imbriquée réintègre l'arbre et suit ensuite les règles normales
de rendu des tableaux.

### 2.1 Deux précautions

**`reason` est localisé — ne jamais s'en servir pour détecter le cas.** Les deux langues
sont présentes dans le corpus, sur deux pages du même module :

- `28344321` : `"A table in a table cell can't be created or edited in the new editor."`
- `28344344` : `"Il est impossible de créer ou de modifier un tableau dans une cellule de tableau dans le nouvel éditeur."`

La détection se fait sur `extensionKey == "nested-table"`, exclusivement. Un
`nested-table` sans `reason` du tout doit rester détecté et exploité.

**`cxhtml` coexiste avec `adf`** dans les 11 occurrences du corpus. On utilise `adf` et
on ignore `cxhtml` : ce serait un second convertisseur à écrire et à maintenir, pour le
même contenu.

### 2.2 Balayage du corpus : aucun cas ne justifie un `partial`

Les **11** occurrences de `nested-table` des 248 fixtures portent **toutes** le même jeu
de paramètres `('adf', 'cxhtml', 'reason')`. **Zéro occurrence sans champ `adf`.**

Le seul cas qui justifierait `parse_status: partial` serait donc un `nested-table` dont
`adf` est absent ou illisible : `nested_table_content()` lève alors une
`ResolutionError`, et la page part en `partial` avec son motif. **Aucune occurrence à ce
jour** — le cas est couvert par un test, pas par une observation.

---

## 3. Nettoyage des noms de multiexcerpt

Avant **toute** jointure, des **deux côtés** — définition comme inclusion :

```python
html.unescape(nom).strip()
```

Dans cet ordre. Les noms sont encodés en entités HTML (`&period;`, `&lowbar;`) : sans le
décodage, les identifiants de règles écrits dans le `.md` et dans l'index croisé sont
faux. Le même traitement s'applique au titre de page cible d'une inclusion.

### 3.1 Le cas du corpus

**10 occurrences** portent un espace de tête, pour **3 noms distincts**, tous du module
`NOTE` :

| Nom brut | Définition | Inclusions |
|---|---|---|
| `" RG-NOTE-ASSOCATION&period;PERSONNE"` | `180256775` | `180944899`, `28344321` |
| `" RG-NOTE-TRI"` | `180256775` | `180944899`, `27787265`, `29032449` |
| `" RG-NOTE-IMPRESSION"` | `180256775` | `180944899`, `27787265` |

**L'espace est présent des deux côtés de façon cohérente** : la jointure fonctionne donc
aujourd'hui — par chance. Le `strip()` est une **précaution**, pas une réparation : il
protège du cas où un seul des deux côtés serait corrigé dans Confluence, ce qu'une
retouche du titre de la définition suffirait à provoquer. Une inclusion non résolue est
un contenu manquant dans le `.md`, pas une erreur bruyante — d'où la précaution.

**Le `strip()` ne fait perdre aucune distinction** : sur les 300 définitions relevées,
aucun couple de noms ne fusionne après nettoyage. Vérifié avant d'appliquer la règle.

---

## 4. Ce qui reste à trancher

- le reste de la table de normalisation : `expand` / `nestedExpand`,
  `layoutSection` / `layoutColumn`, `media*`, `blockCard` / `inlineCard`, `status`,
  `taskList`, `decisionList` ;
- l'arbitrage réutiliser / réécrire le resolver multiexcerpt (question ouverte n°3) ;
- le sort de `API-COMPTE-USER.REINIT.PSW` (`110231568`), page vraisemblablement mal
  rangée sous une archive — voir `contracts/classification_pages.md` §5.
