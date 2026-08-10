# Table de normalisation ADF

Ce que le pipeline fait de chaque nœud ADF du corpus SINAPSE.

**État : table de normalisation complète.** Les **36 types de nœuds du corpus
complet** sont couverts : contenu réutilisé (§1), `nested-table` (§2), nettoyage
des noms (§3), seconde famille de macros (§1.8), marqueur de réutilisation (§1.9),
mise en page (§4), médias (§5 et §5.1), cartes (§6), `status` / `taskList` /
`mention` / `date` / `emoji` (§7), marks (§8), nœuds structurels (§9). Le §10
distingue **deux** listes : les types absents du corpus complet, qui lèvent, et ceux
qui sont couverts sans être exercés par les 9 fixtures. Les points encore ouverts,
listés en §11, ne portent plus sur la normalisation elle-même mais sur ses
prérequis — slugification, resolver, arbitrage du mécanisme de réutilisation.

Base factuelle : 248 fixtures ADF pour §1 à §3 ; les 9 fixtures du corpus doré,
8288 nœuds, pour §4 à §10. Trois types — `date`, `emoji`, `mediaInline` — ne
figurent dans aucune des 9 fixtures et sont documentés depuis le corpus complet.

**Règle qui domine tout le reste** : aucun nœud n'est ignoré silencieusement. Un nœud
non couvert par cette table remonte en erreur au rapport de run.

### Deux niveaux de signalement — `incident` et `constat`

« Lève » désigne dans ce document le comportement du **nœud**, jamais celui de la page.
Le nœud fautif ne produit rien, le parcours se poursuit, et la page sort avec ce qui a
pu être rendu.

| Niveau | Effet sur `parse_status` | Ce qu'il signale |
|---|---|---|
| **incident** | `partial` | du contenu manque dans le `.md` — la page n'est plus scorable |
| **constat** | aucun, la page reste `ok` | un fait à consigner au rapport, sans perte de contenu |

Le renderer **collecte** les incidents au lieu de s'arrêter au premier. Motif : en
tout-ou-rien, le premier type inconnu masque tous les suivants, et il faut un run complet
par type à découvrir. En collecte, un seul run donne la liste entière.

Le parcours ne rattrape que l'exception typée du renderer. **Toute autre exception
remonte** : c'est un défaut du code, pas un fait du corpus, et l'absorber en incident le
rendrait indiscernable d'un nœud Confluence inattendu.

Sont des **incidents** : un type de nœud non couvert, un mark hors de la liste blanche,
un mark à rendu sur un porteur qui ne l'admet pas (§8), un `nested-table` sans `adf`
exploitable (§2.2), une `mention` sans `text` ni `id` (§7.3), un `blockCard` sans
`datasource` ni `url` (§6.2), un type sans règle de rendu HTML rencontré dans une cellule
de tableau HTML (§9.1).

Sont des **constats** : un JQL contenant `{{` (§6.1), un identifiant de page absent de
`pages_inventory.json` (§6.3), une URL d'édition `edit-v2` (§6.3), deux nœuds `text`
adjacents portant le même jeu de marks (§8.3), un mark enveloppant appliqué à un nœud
autre que `text` (§8), un `heading` sans `attrs.level` (§9).

---

## 1. Contenu réutilisé — trois mécanismes, deux formes de clé

Le corpus porte **trois** mécanismes de réutilisation, et non un seul : deux familles
de macros — `multiexcerpt` et `excerpt`, comparées en **§1.8** — et le mécanisme
`syncBlock`. Ils se traitent dans **le même visiteur** — un seul parcours de l'arbre —
mais **jamais avec la même clé**.

Le tableau ci-dessous oppose la famille `multiexcerpt` à `syncBlock`, les deux
mécanismes connus au 4 août. La famille `excerpt`, relevée le 6 août, partage la
colonne `multiexcerpt` sur **tous** ces points sauf un : le paramètre qui porte la
page source. C'est précisément ce qui en fait un piège — voir §1.8.

| | multiexcerpt | syncBlock |
|---|---|---|
| Nœuds | `extension`, `bodiedExtension`, `inlineExtension` | `syncBlock`, `bodiedSyncBlock` |
| Désignation de la source | **titre** de page | **identifiant** de page |
| Clé de résolution | `(page, nom)` | `(page_id, uuid)` |
| Résolution | index des définitions du space | `GET /pages/{id}` direct |
| Dépend de `pages_inventory.json` | oui | **non** |
| Sensible au renommage | oui — voir §1.4 | **non** |
| Occurrences | 908 | 4 inclusions, 5 définitions |

### 1.1 Ces deux mécanismes relèvent du resolver, pas du rendu

La résolution du contenu réutilisé précède la normalisation dans la chaîne :

```
ADF brut → résolution du contenu réutilisé → normalisation → rendu markdown
```

Étendre le rendu aux `syncBlock` serait une erreur d'étage : le renderer aplatit des
nœuds dont il a le contenu sous la main, alors qu'ici **le contenu est absent de la page
consommatrice** et exige un appel réseau. C'est la définition même du travail du
resolver.

**Un visiteur limité aux nœuds `Extension` manquerait les syncBlock en silence** : ce ne
sont pas des extensions, ce sont des types de nœuds à part entière. Le point d'entrée
unique du visiteur est `classify_reuse_node()`, qui rend l'une de **six** natures :
`multiexcerpt_definition`, `multiexcerpt_include`, `excerpt_definition`,
`excerpt_include`, `sync_definition`, `sync_include` — deux familles de macros
(§1.8) et le mécanisme `syncBlock`.

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

La résolution est faite. `multiexcerpt.py` v1.1 porte la couche déterministe — clés des
trois mécanismes, classification en six natures, extraction de paramètres, garde-fou de
cycle, 77 contrôles. `resolver.py` v1.0 porte le parcours et la récupération : une
descente unique qui injecte les tables imbriquées et résout les inclusions, les pages
sources étant fournies par un objet extérieur, jamais par un appel direct à Confluence.
117 contrôles. L'arbitrage « réutiliser ou réécrire » a conclu à réécrire ; motifs en
§5 du document de référence.

### 1.8 Une seconde famille de macros — `excerpt` natif

*Relevé le 6 août 2026 sur `180256775` et `27787265`.*

Le corpus porte désormais **deux familles de macros** de réutilisation, en plus du
mécanisme `syncBlock` du §1. Elles se traitent dans le même visiteur, avec la même
forme de clé `(page, nom)`, mais **la page source ne se lit pas au même endroit**.

| | famille `multiexcerpt` | famille `excerpt` |
|---|---|---|
| Origine | app Marketplace (Appfire) | macro native Confluence |
| Nœuds | `extension`, `bodiedExtension`, `inlineExtension` | idem |
| Clé de résolution | `(page, nom)` | `(page, nom)` |
| Nom | `macroParams.name.value` | `macroParams.name.value` |
| **Page source** | `macroParams.page.value` | **`macroParams[""].value`** |
| Sensible au renommage | oui | oui |
| Dépend de `pages_inventory.json` | oui | oui |

#### Reconnaissance — par sous-chaîne, jamais par énumération

- `multiexcerpt` dans `extensionKey` → famille `multiexcerpt` ;
- sinon `excerpt` dans `extensionKey` → famille `excerpt` ;
- corps présent → définition ; corps absent → inclusion.

**L'ordre des deux tests est impératif** : `multiexcerpt-fast-block-macro`
contient `excerpt`. Tester `excerpt` en premier classerait toute la famille
historique dans la nouvelle.

L'énumération des variantes est proscrite. Le corpus en comptait six le 4 août ;
deux de plus sont apparues le 5. Une liste `VARIANTES_OBSERVEES` peut être tenue à
titre documentaire, mais elle ne participe à aucun appariement.

#### La clé de paramètre vide n'est pas un accident

`macroParams[""]` est l'héritage du **paramètre positionnel** du wiki markup :
`{excerpt-include:Nom De La Page|nopanel=true}`. Confluence a conservé cette
sérialisation, et un paramètre sans nom se range sous la clé vide. C'est stable,
pas fortuit.

**C'est aussi le piège le plus dangereux du dossier.** Un resolver qui cherche
`page` ne trouve rien sur un `excerpt-include`, conclut « page courante », et
résout contre une définition locale de même nom. Le contenu produit est faux,
plausible, et **muet** — ni trou ni message. Cas réel : sur `27787265`,
`habilitation` est défini localement **et** inclus depuis `CU-NOTE-CREER`.

Page absente ou vide → page courante, dans les deux familles.

#### Les index de définitions restent séparés par famille

Une inclusion ne résout **jamais** que contre une définition de sa propre famille,
dans les deux sens. Confluence ne croise pas les deux mécanismes ; un pipeline qui
les croiserait produirait un `.md` **plus complet que la page réelle** et
masquerait un affichage cassé que les rédacteurs voient à l'écran sans que le
rapport de run ne le signale jamais.

#### Unicité de clé — levée obligatoire

Si une clé `(page, nom)` apparaît deux fois dans la même famille, la construction
de l'index **lève**, avec les deux emplacements dans le message. Cas réel :
`27787265` définit `habilitation` deux fois, avec un contenu identique
aujourd'hui — donc sans effet visible, jusqu'au jour où les deux divergeront.
C'est la même mécanique que la collision de `resourceId` du §1.3.

#### Les deux familles cohabitent sur une même page

`180256775` porte 25 définitions `excerpt` **et** 2 multiexcerpts résiduels. Le
resolver ne peut donc pas choisir un mécanisme par page : il classe nœud par
nœud.

#### Statut de cette section

Elle décrit ce que le corpus contient et ce que le code reconnaît. **Elle ne vaut
pas adoption** : le sort de l'essai du 5 août — conservé, annulé ou généralisé —
reste ouvert (§11). Documenter la famille est indépendant de la décision, au même
titre que le §10 énumère les types absents du corpus complet pour que leur
apparition ne passe pas inaperçue.

### 1.9 Le marqueur de contenu réutilisé — visible, pas commenté

*Décision du 11 août 2026, qui en corrige une antérieure.*

Le contenu résolu est encadré de deux marqueurs, **rendus visibles par un lecteur
markdown**. Ils répondent à une question que le lecteur d'une spec se pose en
permanence : *puis-je corriger cette phrase ici, ou dois-je aller sur la page source ?*

| Position | Rendu |
|---|---|
| ouverture | `*↳ inclusion : {nom} — source : {page}*` |
| fermeture | `*↳ fin inclusion : {nom}*` |

Pour un `syncBlock`, `{nom}` vaut `bloc synchronisé {8 premiers caractères de l'UUID}`
et `{page}` le titre de la page source.

**Le resolver émet un `paragraph` portant un nœud `text` marqué `em`** — jamais des
astérisques littérales. C'est ce qui fait que le marqueur suit la machinerie déjà en
place sans aucun cas particulier : `*…*` en markdown, `<em>…</em>` dans une cellule de
tableau HTML. Des astérisques écrites en clair s'afficheraient telles quelles à
l'intérieur d'une balise.

**Le libellé ne contient ni `|`, ni `<`, ni `>`** — les trois caractères que ce document
échappe (§9.1). Un marqueur qui en porterait serait déformé en cellule, et l'on
retomberait sur le défaut que cette section supprime. `↳` passe dans les deux modes.

**Aucune décision ne se prend sur le texte du marqueur.** Le libellé est fabriqué au
rendu à partir du mécanisme, du nom et de la page source ; il peut être reformulé sans
qu'aucune règle en dépende. C'est la contrepartie de la règle générale du §5 du document
de référence — un fait dont une décision dépend vit dans un champ structuré, pas dans
une phrase.

**Le marqueur est un `paragraph`.** Une cellule portant une inclusion en compte donc au
moins deux, ce qui la rend complexe au sens du §9.1 et fait basculer son tableau en HTML.
C'est assumé : le contenu inclus apporte de toute façon le plus souvent une liste.

#### Ce que cette décision corrige

Le marqueur était auparavant un commentaire HTML — `<!-- inclusion : … -->`. Il
satisfaisait la décision « contenu réutilisé marqué visiblement » **au sens du fichier
brut**, et la contredisait au sens de l'usage : un lecteur markdown ne l'affiche pas, et
c'est avec un lecteur markdown que les specs sont lues. La décision était bonne, sa
transcription trahissait le besoin.

Elle produisait en outre un défaut mesuré à 30 occurrences : en cellule de tableau HTML,
l'échappement de `<` et `>` transformait le commentaire en texte affiché
`&lt;!-- inclusion : … --&gt;`. Ce défaut n'existe plus, non parce qu'on l'a réparé, mais
parce que le marqueur est désormais du texte que l'on veut voir.

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

### 2.3 Les autres macros `extension` — `toc`

Un nœud `extension` peut porter une macro qui n'est **ni** de la réutilisation (§1)
**ni** un `nested-table` (§2). Le corpus en compte une seule à ce jour : `toc`, la
table des matières, **8 occurrences sur 8 des 9 fixtures** — c'est un élément de
cartouche, pas une exception.

| `extensionKey` | Occ. | Rendu |
|---|---|---|
| `toc` | 8 | `<!-- toc -->` |

Un sommaire Confluence est **généré à l'affichage** à partir des titres de la page :
il n'a aucun contenu propre à convertir, et un lecteur de `.md` reconstruit la même
information depuis les `#`. Le commentaire HTML conserve la trace de la macro sans
polluer le rendu.

**Ordre de reconnaissance des `extension`**, à respecter strictement :

1. `extensionKey == "nested-table"` → §2 ;
2. `multiexcerpt` en sous-chaîne de `extensionKey` → famille `multiexcerpt`, §1 ;
3. sinon `excerpt` en sous-chaîne → famille `excerpt`, §1.8 ;
4. sinon, clé présente dans la table ci-dessus → rendu indiqué ;
5. sinon → **lève**, conformément à la règle dominante.

Cette table est une **liste blanche**, au même titre que celle des marks (§8.2) :
une macro non listée lève, elle ne passe pas en silence. C'est ce qui a permis de
découvrir `toc`, resté invisible tant que rien ne l'exigeait.

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

Base factuelle : `recensement/inventaire_fixtures_20260806.md` — 9 fixtures,
8045 nœuds, 33 types distincts, inventaire exhaustif.

---

## 4. Conteneurs transparents

Un conteneur transparent ne produit aucune syntaxe markdown propre : ses enfants
sont émis à sa place, dans l'ordre du document. Ses `attrs` de présentation sont
jetés — ils décrivent un rendu d'écran que le `.md` n'a pas vocation à reproduire.

### 4.1 `layoutSection` / `layoutColumn`

7 `layoutSection` (3 à deux colonnes, 4 à trois), 18 `layoutColumn`, toutes au
chemin `doc > layoutSection`. Aucune autre imbrication.

```json
{"type": "layoutColumn",
 "attrs": {"width": 50.0, "localId": "39c1f5970d12"},
 "content": [ ... ]}
```

| Élément | Traitement |
|---|---|
| `layoutSection` | transparent |
| `layoutColumn` | transparent ; **une ligne vide entre deux colonnes** |
| `attrs.width`, `attrs.localId` | jetés |
| mark `breakout` porté par la section | jeté — voir §8 |

La ligne vide n'est pas décorative : sans elle, le dernier paragraphe d'une
colonne et le premier de la suivante fusionneraient en un seul bloc markdown.
Elle sépare, elle ne signale pas.

Aucun marqueur de colonne n'est écrit. La mise en page en colonnes des cartouches
est de la présentation ; l'information qu'elle porte est dans les paragraphes
eux-mêmes. L'index croisé étant construit depuis l'ADF, rien n'est perdu pour les
skills.

Une colonne vide — cas rencontré : un `layoutColumn` ne contenant qu'un
`paragraph` sans `content` — ne produit rien.

### 4.2 `expand`

7 occurrences, toutes au chemin `doc`, **toutes titrées `EVOLUTIONS`**, toutes
contenant exactement un nœud `table`.

```json
{"type": "expand",
 "attrs": {"title": "EVOLUTIONS"},
 "marks": [{"type": "breakout", "attrs": {"mode": "wide", "width": 1800}}],
 "content": [{"type": "table", ...}]}
```

Rendu :

```
**{title}**

{contenu}
```

**Le titre n'est jamais rendu en titre markdown (`##`).** Le niveau correct ne
s'infère pas de l'ADF : `expand` est un nœud de bloc, pas un nœud de hiérarchie.
Émettre `## EVOLUTIONS` au milieu d'une page dont le plan est en `h2` insérerait
une section fantôme dans l'index et déplacerait tout ce qui suit. Le gras est
neutre de ce point de vue, et reste une ancre stable pour les skills.

Si `attrs.title` est absent ou vide, seul le contenu est émis.

### 4.3 Ce que l'`expand` EVOLUTIONS n'est pas

Le tableau contenu dans l'`expand` est un **`table` ADF ordinaire**, saisi à la
main, aux colonnes `Version | Description de la mise à jour | Ref JIRA | Date` :
c'est le journal de version de la page.

**Il ne faut pas le confondre avec le `blockCard` à `datasource` du §6.1**, qui
est un nœud distinct, placé à la racine `doc`, en dehors de l'`expand`. Les deux
coexistent sur une même page et n'ont aucun rapport structurel :

| | `expand` EVOLUTIONS | `blockCard` à datasource |
|---|---|---|
| Nature | `table` ADF saisi à la main | table Jira interrogée par JQL |
| Emplacement | dans l'`expand` | racine `doc` |
| Contenu | Version, Description, Ref JIRA, Date | issues renvoyées par la requête |
| Occurrences | 7 | 5 |

Le premier porte l'historique figé des évolutions déjà intégrées à la spec ; le
second la vue vivante de celles qui ne le sont pas encore. Chacun suit sa propre
règle de rendu, sans traitement conjoint.

---

## 5. Médias

21 `mediaSingle`, chacun contenant exactement un `media`, plus 4 `caption`.

```json
{"type": "media",
 "attrs": {"id": "18f44d75-3f1e-4cf9-ab9f-379e7ddd5aef",
           "collection": "contentId-109543425",
           "type": "file",
           "alt": "image-20250716-200316.png",
           "width": 543, "height": 254}}
```

| Élément | Traitement |
|---|---|
| `mediaSingle` | transparent |
| `media` | `![{alt}](adf-media://{id}?collection={collection})` |
| `caption` | ligne en italique immédiatement sous l'image |
| `attrs.width`, `height`, `layout`, `widthType`, `localId` | jetés |
| mark `border` | jeté — voir §8 |

**Aucun binaire n'est téléchargé.** Le pipeline produit des `.md` de
spécification, pas une copie de l'espace Confluence. Le marqueur retenu est de la
syntaxe markdown d'image valide, donc inoffensif au rendu, et conserve `id` et
`collection` : si une étape ultérieure devait rapatrier les pièces jointes, elle
aurait de quoi les retrouver sans re-parcourir l'ADF.

`alt` est systématiquement le nom de fichier généré par Confluence
(`image-20260513-003643.png`) : il ne décrit rien, il est conservé tel quel sans
interprétation.

Ce choix est sans effet sur le scoring : les captures d'écran ne sont jamais
pénalisées par les skills de validation.

### 5.1 `mediaInline` — image au fil du texte

6 occurrences au corpus complet, 3 pages, **aucune dans les 9 fixtures**.

```json
{"type": "mediaInline",
 "attrs": {"id": "d73b9bbd-bafe-4209-95fa-bd3d96738e23",
           "collection": "contentId-428113938",
           "localId": "662318527c9f"}}
```

| Élément | Traitement |
|---|---|
| `mediaInline` | `![](adf-media://{id}?collection={collection})` |
| `attrs.localId` | jeté — absent d'une occurrence sur six, ne sert à rien |

**Nœud inline**, contrairement au `mediaSingle` du §5 qui est un bloc : il se rend dans
la chaîne inline de son paragraphe, sans ligne vide autour.

**Le marqueur ne porte pas d'`alt`, parce que le nœud n'en a pas.** Le §5 conserve `alt`
là où il existe ; en fabriquer un ici — l'identifiant recopié, un mot générique — serait
inventer une description. Un `alt` vide est de la syntaxe markdown légale, et la
traçabilité voulue par le §5 tient déjà dans `id` et `collection`.

`mediaGroup` : absent du corpus complet — voir §10.

---

## 6. Cartes

Trois cas distincts : le `blockCard` porteur d'un `datasource` (requête Jira), le
`blockCard` sans `datasource` (simple lien), et l'`inlineCard` (renvoi entre
pages).

### 6.1 `blockCard` à `datasource` — la requête Jira du cartouche

5 occurrences sur 5 `blockCard` du corpus, toutes au chemin `doc`.

**La détection se fait sur la présence de `attrs.datasource`, exclusivement.** Le
libellé du tableau n'est pas dans ce nœud — voir §4.3.

Le JQL se lit dans `attrs.datasource.parameters.jql`, présent sur les 5
occurrences ; `parameters` y contient exactement `cloudId` et `jql`. `attrs.url`
porte la même requête encodée en URL : c'est un doublon, ignoré. Si
`parameters.jql` venait à manquer, la requête est décodée depuis le paramètre
`jql` de `attrs.url` ; si les deux manquent, le nœud lève.

Les colonnes déclarées se lisent dans
`attrs.datasource.views[0].properties.columns[*].key`. Relevé : 10 colonnes sur
4 fixtures, 9 sur `380567556` (pas de `issuekey`).

Rendu :

```
**Requête Jira (cartouche)**

- vue : `table`
- colonnes : issuetype, issuekey, summary, status, resolution, customfield_10061,
  customfield_10060, fixVersions, customfield_10058, key
- JQL :

    (id in linkedIssues(REC-35,"réfère") or "Specs[URL Field]" = "…") and …
```

**Aucun appel Jira n'est fait.** Le pipeline remet la macro en clair et s'arrête
là ; l'interrogation de Jira reste dans le skill `confluence-outil-lien-jira`, qui
trouvera dans le `.md` la requête exacte dont il a besoin — notamment la liaison
`"Specs[URL Field]" = "<url de la page>"`.

**Gabarit non substitué.** La fixture `380567556` porte
`"Specs[URL Field]" = "{{page.url}}"` : la requête ne cible aucune page réelle. Un
JQL contenant `{{` est **remonté comme fait au rapport de run**, pas comme
erreur : la page est parsée correctement, c'est son contenu qui est fautif.

### 6.2 `blockCard` sans `datasource`

Aucune occurrence dans le corpus, mais la forme est légale. Traitement :
`[{attrs.url}]({attrs.url})`. Un `blockCard` sans `datasource` **ni** `url` lève.

### 6.3 `inlineCard` — renvois entre pages

69 occurrences, dont 53 hors tables imbriquées. La ventilation ci-dessous porte sur ces
53 : elle a été relevée par un parcours qui n'entrait pas dans `parameters.adf`. **La
répartition des 16 autres reste à mesurer** — elle n'est pas extrapolée ici, la règle de
traitement étant de toute façon la même pour les trois familles.

| Famille | Occ. | Forme |
|---|---|---|
| page Confluence en clair | 42 | `…/wiki/spaces/{SPACE}/pages/{ID}` |
| lien court Confluence | 10 | `…/wiki/x/{SUFFIXE}` |
| ticket Jira | 1 | `…/browse/REC-342` |

**52 sur 53 sont des renvois vers des pages Confluence dont l'identifiant est
récupérable** — directement dans l'URL longue, ou par décodage du lien court.
C'est la matière des renvois entre specs : rendus en URL brute, ils deviendraient
illisibles dans le `.md`.

Le suffixe d'un lien court encode l'identifiant de page :

```python
def page_id_depuis_lien_court(suffixe: str) -> int:
    s = suffixe.replace("_", "/").replace("-", "+")
    s += "=" * (-len(s) % 4)
    octets = base64.b64decode(s).ljust(8, b"\x00")
    return struct.unpack("<Q", octets)[0]
```

Entier 8 octets **little-endian**, octets nuls de fin tronqués, base64 avec
alphabet URL-safe, bourrage `=` supprimé.

**Vérifié sur trois paires du corpus**, sans aucun appel réseau :

| Lien court | Décodage | Corroboration |
|---|---|---|
| `AYCwAQ` | `28344321` | présent dans le JQL de la page `28344321` elle-même |
| `LYBJDg` | `239697965` | même page citée ailleurs en URL longue |
| `NoC3AQ` | `28803126` | même page citée ailleurs en URL longue |

Traitement, dans cet ordre :

| Cas | Rendu |
|---|---|
| ID extrait (URL longue ou lien court décodé) **et** présent dans `pages_inventory.json` | `[{titre}]({chemin relatif})` — voir ci-dessous |
| ID extrait, **absent** de l'inventaire | `[{url}]({url})` + fait au rapport de run |
| Suffixe non décodable, ou URL d'une autre nature (ticket Jira) | `[{url}]({url})` |

**Le chemin est relatif au fichier porteur, pas à `local_path`.** La cible est
`os.path.relpath(md_path_cible, os.path.dirname(md_path_source))`, séparateurs
`/` quelle que soit la plateforme :

```
[CU-PERSONNE-MODIFIER](../SF-PERSONNE-gestion-des-personnes/CU-PERSONNE-MODIFIER.md)
```

Aucun encodage n'est nécessaire : la liste blanche de `contracts/slugification.md`
§4 garantit que le chemin ne porte ni espace, ni parenthèse, ni caractère
réservé de la syntaxe Markdown. C'est la raison d'être de cette liste blanche
autant que la compatibilité Windows.

**Conséquence de séquencement** : le normalizer dépend de `pages_inventory.json`
pour une **seconde** raison, après la résolution du contenu réutilisé par titre
(§1) — et il en dépend pour `md_path` des deux extrémités du lien, source
comprise. Il ne peut donc pas tourner page par page en ignorant l'inventaire.

Un ID absent de l'inventaire n'est pas une erreur de parsing : c'est un renvoi
vers une page hors périmètre d'export, fait à consigner.

**Anomalie relevée dans le corpus** : `380567556` porte un `inlineCard` vers
`…/wiki/spaces/SINAPSE/pages/edit-v2/380567556#IHM-concernant-la-gestion-du-profil…`
— une URL **d'édition**, avec ancre, pointant vers la page elle-même. L'extraction
d'identifiant doit tolérer le segment `edit-v2/` sans le confondre avec un
identifiant, et le fait est à remonter au rapport de run.

`embedCard` : absent du corpus complet — voir §10.

---

## 7. `status`, `taskList`, `mention`

### 7.1 `status`

1 occurrence, en cellule de tableau.

```json
{"type": "status",
 "attrs": {"color": "yellow", "style": "bold", "text": "A VALIDER",
           "localId": "81ea2c78-…"}}
```

Rendu : **le texte nu**, `A VALIDER`, sans décoration.

`color` et `style` sont jetés : la couleur redouble le texte. Inventer une syntaxe
(`[A VALIDER]`, `` `A VALIDER` ``) créerait une ambiguïté avec les liens ou avec le
mark `code`, massivement utilisé par ailleurs, pour ne rien ajouter au sens.

### 7.2 `taskList` / `taskItem`

1 `taskList` portant 10 `taskItem`, tous à l'état `TODO`.

| Élément | Rendu |
|---|---|
| `taskList` | transparent |
| `taskItem` avec `attrs.state == "DONE"` | `- [x] {contenu inline}` |
| `taskItem`, tout autre état | `- [ ] {contenu inline}` |
| `attrs.localId` | jeté |

### 7.3 `mention`

1 occurrence. Rendu : `attrs.text` s'il est présent (forme `@Prénom Nom`), sinon
`@{attrs.id}`. **Si ni l'un ni l'autre n'est présent, le nœud lève** — plutôt que
d'émettre une mention vide qui passerait pour du texte manquant.

### 7.4 `date`

47 occurrences au corpus complet, **une seule page** — `298385410`, type DOCUMENTATION,
exportée non scorée. Aucune dans les 9 fixtures. Les 47 sont les cellules d'un même
tableau de planning, toutes au chemin `tableCell > paragraph`.

```json
{"type": "date",
 "attrs": {"localId": "8adb9609-4552-4fe8-b854-2c8fd2803296",
           "timestamp": "1776816000000"}}
```

Deux clés, jamais plus. `timestamp` est un epoch en **millisecondes**, encodé en chaîne.

**Rendu : `2026-04-22` — ISO 8601.** Le nœud ne porte aucun attribut de format : la forme
d'affichage n'existe pas dans l'ADF, Confluence la calcule à l'écran. Le choix est donc
une décision, pas une transcription. `22/04/2026` et `04/22/2026` sont indiscernables sur
une valeur isolée ; l'ISO est trié, non ambigu, indépendant de la locale, et se relit
aussi bien par un skill que par un humain.

**La conversion se fait en UTC explicite** —
`datetime.fromtimestamp(ms / 1000, tz=timezone.utc)`. La forme naïve emploie le fuseau de
la machine : sans effet à Nouméa, où minuit UTC reste le même jour, mais un exécutant
placé dans un fuseau négatif décalerait les 47 dates d'un jour, sans un mot. Le défaut ne
se voit jamais sur le poste où il a été écrit.

`timestamp` absent, vide ou non numérique → **incident**.

**Nœud inline.** Il ne vit pas seul dans son paragraphe : les 47 occurrences sont suivies
d'un `text` valant une espace. Un renderer qui jetterait le nœud laisserait 47 cellules
ne contenant qu'une espace — perte muette, et le tableau resterait en pipes puisque la
cellule n'a qu'un `paragraph`.

### 7.5 `emoji`

21 occurrences au corpus complet, 7 pages, dont **une seule scorée** — `120160278`
API-COMPTE-UTILISATEUR.IMPORT. Aucune dans les 9 fixtures.

```json
{"type": "emoji",
 "attrs": {"id": "atlassian-warning", "text": ":warning:",
           "shortName": ":warning:", "localId": "3b0be13ae440"}}
```

Quatre clés, toujours les quatre. Deux familles : `id` préfixé `atlassian-` (19
occurrences, `text` vaut le shortcode) ou codepoint hexadécimal (2 occurrences, `text`
porte le vrai caractère).

**Rendu : `attrs.text`, sans distinguer les deux familles.** Repli sur `attrs.shortName`
s'il est absent ; ni l'un ni l'autre → **incident**.

Conséquence assumée : sur 19 des 21 occurrences, le `.md` porte `:warning:` et non le
caractère. C'est un **shortcode GitHub Flavored Markdown valide**, rendu comme emoji par
les moteurs visés — de la syntaxe, pas un artefact. L'alternative serait une table
`atlassian-* → caractère`, c'est-à-dire l'interprétation figée que ce document refuse
déjà pour les couleurs (§8.1) ; elle imposerait en outre de décider du sort d'un
`atlassian-` inconnu, et faire partir une page en `partial` pour un emoji décoratif
serait hors de proportion.

*Si un jour un `.md` affiche `:warning:` littéralement chez un consommateur, c'est cette
décision qui se rouvre — et elle se rouvre en une ligne.*

**Nœud inline.** Une occurrence vit dans un corps de définition multiexcerpt : le
resolver la recopie à chaque inclusion, une source unique peut donc produire plusieurs
occurrences au rendu.

`decisionList`, `decisionItem` : absents du corpus complet — voir §10.

---

## 8. Marks

**15 marks couverts** : les 14 relevés dans les 9 fixtures, plus `fontSize`, qui n'existe
que sur le corpus complet (§8.2). C'est le compte de la liste blanche — un mark absent des
quinze lève. Six ont un rendu direct :

**Le renderer lit `marks` sur tous les nœuds, sans exception** — et non sur les seuls
nœuds `text`. Mesuré sur les 9 fixtures : 89 marks portés par un nœud autre que `text`,
sur 10 couples (mark, porteur). `breakout` se porte sur six types différents, dont `rule`
et `codeBlock` ; s'en tenir aux conteneurs en manquerait 18 sur 36. Et `annotation` se
porte sur un `inlineCard`, qui est inline : **« porteur autre que `text` » n'est pas
synonyme de « nœud de bloc »**, et une règle écrite sur cette équivalence serait fausse.

La règle se lit par **porteur**, en quatre lignes :

| Cas | Traitement |
|---|---|
| mark hors des 15 | **incident**, quel que soit le porteur |
| un des 7 marks jetés (§8.2) | jeté, quel que soit le porteur ; le contenu est intact |
| `strong`, `em`, `strike`, `underline`, `backgroundColor`, `textColor` sur `text`, `paragraph`, `heading`, `inlineCard`, `status` ou `mention` | **enveloppe le contenu rendu une seule fois** ; sur un porteur autre que `text`, **constat** |
| tout autre couple (mark à rendu, porteur) | **incident** |

**« Une seule fois » n'est pas un détail de forme.** Sur un `paragraph`, le mark
enveloppe le paragraphe **rendu**, pas chacun de ses nœuds `text` :

```
correct  : <mark …>La date **doit être** de la forme JJ/MM/AAAA</mark>
faux     : <mark …>La date</mark><mark …> doit être </mark><mark …>de la forme…</mark>
```

**Pourquoi ces six-là et pas les huit.** Un paragraphe entier surligné est le cas le plus
probable, et le §8.1 lui donne un sens métier : le jeter ou le fragmenter perdrait
l'information. `strike` relève du même registre en sens inverse. En revanche `code` et
`link` **lèvent sur tout porteur autre que `text`** : une portion de code ne peut contenir
aucun autre balisage, l'appliquer à un paragraphe avalerait en silence son gras, ses liens
et son surlignage ; et un lien ne peut pas en contenir un autre, donc la règle ne
marcherait que selon le contenu du paragraphe — c'est-à-dire qu'elle échouerait un jour
sans prévenir.

**Un mark à rendu porté par un conteneur de blocs — `table`, `bulletList`, `expand`,
`layoutSection`, `panel`, `blockquote` — est un incident**, y compris parmi les six. Un
mark inline ne franchit pas une frontière de bloc : `**` ne traverse pas une ligne vide et
laisserait des marqueurs orphelins, et `<mark>` est du contenu de phrasé, auquel HTML
interdit de contenir un `<ul>`.

| Mark | Rendu | Note |
|---|---|---|
| `strong` | `**texte**` | |
| `em` | `*texte*` | |
| `code` | `` `texte` `` | |
| `link` | `[texte]({href})` | `attrs.href` ; les liens vers des pages du périmètre suivent §6.3 |
| `underline` | `<u>texte</u>` | pas d'équivalent markdown |
| `strike` | `~~texte~~` | GitHub Flavored Markdown — supporté par les moteurs visés, mais **hors markdown de base** : si un consommateur ne le rend pas, le repli est `<del>texte</del>`, jamais la perte du texte |

### 8.1 Marks conservés — les couleurs portent du sens métier

`backgroundColor` et `textColor` **ne sont pas de l'habillage**. Le surlignage
signale les évolutions à venir, non encore développées ; le code couleur fait la
jointure avec le journal de version de l'`expand` (§4.3), où figurent la tâche
Jira, l'objet de l'évolution et sa couleur.

Les jeter perdrait l'information « ce passage décrit du futur, pas de
l'existant » — exactement ce qui ferait qu'un skill score une spec sur du contenu
non encore vrai.

| Mark | Occ. | Valeurs distinctes | Rendu |
|---|---|---|---|
| `backgroundColor` | 167 | 5 | `<mark style="background:{color}">…</mark>` |
| `textColor` | 7 | 1 (`#bf2600`) | `<span style="color:{color}">…</span>` |

**Le hex est conservé brut, sans table de correspondance couleur → sens.** Le
pipeline produit un fait ; l'interprétation reste aux skills et aux BA. Une table
figée dans le pipeline se périmerait au premier changement de convention.

Valeurs relevées, pour mémoire et sans valeur normative : `#dfd8fd`, `#fedec8`,
`#d3f1a7`, `#c6edfb`, `#f8e6a0` en fond ; `#bf2600` en texte, sur des libellés de
contrainte du type « La date doit être de la forme "JJ/MM/AAAA" ».

**Ventilation par couleur à remesurer.** Le décompte du 9 août — 47 / 46 / 40 / 9 / 5,
somme 147 — a été pris par un parcours de `content` seul, qui n'entre pas dans
`parameters.adf`. Le total corrigé étant 167, il ne somme plus et n'est donc pas repris
ici. À remesurer au premier balayage entrant dans les tables imbriquées ; les cinq valeurs
distinctes, elles, sont confirmées.

**Le barré pose la même question, en sens inverse.** Le surlignage signale du
futur non encore développé ; un passage barré signale vraisemblablement du
passé — « ceci n'est plus d'actualité ». Si la convention se confirme, un skill
qui score une CU ne doit pas compter le barré comme du contenu actif, au même
titre qu'il ne doit pas scorer un passage surligné comme de l'existant.

**Le pipeline ne change rien pour autant** : il conserve le fait (`~~…~~`),
l'interprétation reste aux skills et aux BA. Une table figée dans le pipeline
« barré → à ignorer » se périmerait au premier changement de convention, comme
le ferait une table couleur → sens.

Convention à confirmer auprès des BA — voir
`docs/reference-pipeline-sinapse.md` §7.

### 8.2 Marks jetés

| Mark | Occ. | `attrs` typiques | Motif |
|---|---|---|---|
| `breakout` | 36 | `{"mode": "wide", "width": 1800}` | largeur d'affichage |
| `alignment` | 32 | `{"align": "end"}` | alignement |
| `fragment` | 19 | `{"name": "Table 2", "localId": "…"}` | identité interne Confluence |
| `annotation` | 23 | `{"annotationType": "inlineComment", "id": "…"}` | commentaire dont le corps n'est pas dans l'ADF — 21 sur `text`, 2 sur `inlineCard` |
| `border` | 2 | `{"size": 2, "color": "#091e4224"}` | bordure d'image |
| `subsup` | 1 | `{"type": "sup"}` | exposant, sans équivalent markdown |
| `fontSize` | 0 (3 au corpus) | `{"fontSize": "small"}` | taille d'affichage — mise en forme, pas un fait |

Le texte porté est conservé intact dans tous les cas — **pour ces sept marks-là**. Un
mark à rendu posé sur un porteur qui ne l'admet pas est un incident (§8), et le nœud
concerné ne produit alors rien.

**Aucun mark ne fait échouer une page.** Mais la liste des marks traités est une
**liste blanche explicite** : un mark absent des quinze lève, conformément à la
règle qui domine ce document.

`fontSize` a été arbitré le 10 août : jeté, texte conservé. Le critère est celui
qui sépare un fait d'une forme — le surlignage des BA signale une évolution non
encore développée, donc un fait ; une taille de police est de la mise en forme.

**Un point de vigilance, qui ne relève pas du renderer.** Si un rédacteur a
agrandi du texte pour simuler un titre au lieu d'employer un `heading`, jeter le
mark fait perdre cette hiérarchie : le texte survit et se lit comme un paragraphe
ordinaire. Le rendu reste le bon — aucun skill ne peut déduire une structure d'une
taille de police, et une exception dans le renderer ne ferait que déplacer le
problème. Le geste correct est une entrée dans `docs/anomalies-confluence.md`, à
poser si la mesure montre que le cas existe.

**Mesuré le 10 août sur le corpus complet : le cas n'existe pas.** Les 3
occurrences valent toutes `small` — du texte **réduit**, jamais agrandi — et
portent la même légende de statuts sur trois pages UX (`521142301`, `521797667`,
`522092547`). Aucune entrée au registre d'anomalies. À noter pour le renderer :
ce mark est porté par un `paragraph`, pas par un nœud `text` ; le jeter laisse
donc le paragraphe et tout son contenu intacts, `status` compris.

`annotation` signale qu'un commentaire en ligne existe, mais son contenu se
récupère par une API distincte, hors périmètre. Le nombre d'annotations
rencontrées peut être consigné au rapport de run.

### 8.3 Pas de passe de fusion des nœuds `text`

Sur **804 paires de nœuds `text` adjacents** examinées, **aucune** ne porte le
même jeu de marks. L'ADF rendu par l'API est déjà normalisé de ce point de vue :
Confluence fusionne à la source les textes contigus de même formatage. Le risque
`**a****b**` n'existe pas sur ce corpus.

**Aucune passe de fusion n'est donc écrite** — mais le renderer **contrôle** cette
propriété à chaque rendu plutôt que de s'y fier tacitement : rien ne la garantit
contractuellement du côté d'Atlassian, et sa violation produirait un balisage cassé
silencieux.

La violation est un **constat**, pas un incident : le balisage sort laid, aucun contenu
n'est perdu, et la page reste scorable. Faire échouer une page pour un défaut cosmétique
serait hors de proportion.

---

## 9. Nœuds structurels

Les types suivants n'appellent pas d'arbitrage : leur rendu markdown est direct.
Ils figurent ici pour que la table du document soit **exhaustive**.

**Portée de l'exhaustivité : le document entier, pas la seule table ci-dessous.** Les
36 types du corpus complet sont couverts, 16 ici et 20 dans les sections précédentes —
les nœuds de réutilisation en §1 (`extension`, `bodiedExtension`, `inlineExtension`,
`syncBlock`, `bodiedSyncBlock`), la mise en page en §4 (`layoutSection`,
`layoutColumn`, `expand`), les médias en §5 et §5.1 (`media`, `mediaSingle`,
`caption`, `mediaInline`), les cartes en §6 (`blockCard`, `inlineCard`), et
`status` / `taskList` / `taskItem` / `mention` / `date` / `emoji` en §7. **Un type que
ne couvre aucune section lève** ; le §10 énumère d'une part ceux qu'on sait absents du
corpus complet, d'autre part ceux qui sont couverts sans être exercés par les 9
fixtures.

| Type | Occ. | Rendu |
|---|---|---|
| `doc` | 9 | racine, transparent |
| `text` | 2869 | texte, marks appliqués selon §8 |
| `paragraph` | 2271 | bloc, ligne vide de séparation |
| `heading` | 96 | `#` répété `attrs.level` fois |
| `bulletList` / `listItem` | 188 / 445 | `- ` avec indentation par niveau |
| `orderedList` | 3 | `1. ` avec indentation par niveau |
| `blockquote` | 2 | `> ` en préfixe de chaque ligne |
| `codeBlock` | 1 | bloc clôturé, langage depuis `attrs.language` si présent |
| `rule` | 39 | `---`, **précédé d'une ligne vide obligatoire** |
| `hardBreak` | 34 | `<br>` |
| `panel` | 7 | voir §9.2 |
| `table` / `tableRow` / `tableHeader` / `tableCell` | 58 / 387 / 216 / 1417 | voir §9.1 |

**`rule`** : sans la ligne vide qui le précède, `---` placé sous un paragraphe est
interprété comme un titre setext de niveau 2 par la plupart des moteurs markdown.
Le paragraphe précédent deviendrait un titre.

**`hardBreak`** : `<br>` plutôt que deux espaces en fin de ligne. Les deux espaces
sont supprimés par la plupart des éditeurs et des linters, et ne fonctionnent pas
dans une cellule de tableau.

**`heading` sans `attrs.level`** : rendu au niveau 1, et **constat** au rapport de run.
Le niveau ne se devine pas, et aucune occurrence n'existe au corpus. Perdre un niveau de
titre est bénin ; faire partir la page en `partial` pour un attribut manquant ne l'est
pas.

### 9.1 Tableaux — deux rendus selon le contenu des cellules

Un tableau markdown en pipes ne peut contenir que de l'inline. Or le corpus porte
des cellules à contenu de bloc : listes à puces, tableaux imbriqués (§2),
paragraphes multiples, images.

**Règle : si une seule cellule du tableau contient du contenu de bloc ou porte une
fusion, le tableau entier est rendu en HTML.** Sinon, tableau en pipes.

Est du contenu de bloc, dans une cellule : `bulletList`, `orderedList`, `table`,
`panel`, `codeBlock`, `blockquote`, `mediaSingle`, `rule`, `heading`, ou plus d'un
`paragraph`.

`rule` et `heading` ont été ajoutés le 11 août : sans eux, une cellule n'en contenant
qu'un est jugée simple et son `---` ou son `## x` sort au milieu d'une ligne de pipes,
qu'il rompt. Le corpus doré compte un `rule` en cellule, qui ne bascule en HTML que parce
que son tableau hôte est complexe pour un autre motif — la couverture y était fortuite.

Est une fusion : `attrs.colspan > 1` (fusion horizontale) ou `attrs.rowspan > 1`
(fusion verticale). Un tableau markdown en pipes n'a **aucune syntaxe** pour les
exprimer : un en-tête fusionné sur trois colonnes ne peut qu'être remis dans la
première, les deux autres vides, et la fusion disparaît sans trace. En HTML,
`colspan` et `rowspan` sont rendus tels quels, et aucune logique de grille n'est à
écrire. Volume : 6 `colspan` et 10 `rowspan` au corpus complet, **zéro dans les 9
fixtures** — la règle ne sera donc pas exercée par le corpus doré, elle demande un
test dédié.

**Un tableau rendu en HTML rend aussi ses cellules en HTML.** À l'intérieur d'une
balise, le markdown n'est plus interprété : `<th>**Libellé**</th>` affiche deux
astérisques, et une liste à puces sort en tirets non rendus. Le contenu d'une
cellule suit donc une seconde table de rendu :

| Nœud ou mark | Rendu HTML |
|---|---|
| `strong` / `em` / `code` | `<strong>` / `<em>` / `<code>` |
| `underline` / `strike` | `<u>` / `<del>` |
| `link` | `<a href>` |
| `paragraph` | `<p>` |
| `bulletList` / `orderedList` | `<ul><li>` / `<ol><li>` |
| `blockquote` / `codeBlock` | `<blockquote>` / `<pre><code>` |
| `rule` | `<hr>` |
| `heading` | `<h{level}>` |
| `media` / `mediaInline` | `<img>` |
| `caption` | `<em>` |
| `hardBreak` | `<br>` |
| `inlineCard` | `<a href="{cible §6.3}">{titre}</a>` — même résolution qu'en markdown |
| `status` / `date` / `emoji` | texte nu, comme en markdown |
| `mention` | `@…`, comme en markdown |
| `taskList` / `taskItem` | `<ul>` / `<li>` ; l'état se rend `[x]` ou `[ ]` en tête du texte du `taskItem` |
| `panel` | transparent, comme au §9.2 |
| `table` imbriqué | `<table>` complet, mêmes règles, récursivement |

`&`, `<` et `>` sont échappés dans le texte, `&` en premier. Les marks conservés du §8.1
gardent leur forme, qui est déjà du HTML.

Structure émise : `<table>`, `<tr>`, `<th>` et `<td>`. Ni `<thead>` ni `<tbody>` — rien
ne les consomme. `colspan` et `rowspan` ne sont émis que s'ils valent plus de 1.

**Aucun repli sur le rendu markdown.** Un type rencontré dans une cellule de tableau HTML
sans règle HTML est un **incident** ; il ne retombe pas sur le rendu markdown. Le repli
est tentant parce qu'il produit toujours quelque chose — mais ce quelque chose est
`**Libellé**` affiché avec ses astérisques, c'est-à-dire le défaut même que cette section
existe pour supprimer, revenu par la porte de derrière et invisible autrement qu'en
ouvrant le fichier.

**Les deux modes couvrent le même ensemble de types**, et cette égalité est vérifiée par
une assertion, en forme positive : c'est la seule forme qui reste rouge quand un type est
ajouté d'un côté et oublié de l'autre. La duplication markdown / HTML est le vrai risque
structurel de ce renderer ; elle n'est pas évitable, elle est surveillée.

Mesuré : 58 cellules des 9 fixtures portaient du markdown non interprété avant que
cette règle ne soit posée. Le défaut est silencieux et ne se voit qu'au rendu.

Le tout-ou-rien est délibéré : un tableau à moitié en pipes et à moitié en HTML
n'est valide dans aucun des deux formats. Le HTML est verbeux mais sans perte, et
tous les moteurs markdown le laissent passer.

#### Ordonnancement — l'évaluation vient en dernier

**La complexité d'une cellule s'évalue après la résolution du contenu réutilisé
(§1) et après l'injection des `nested-table` (§2), jamais sur l'ADF brut.**

Les deux opérations injectent du contenu dans des cellules qui paraissaient
simples : une inclusion multiexcerpt peut apporter une liste à puces, un
`nested-table` apporte par construction un `table`. Évaluée trop tôt, la cellule
passe pour simple, le tableau reste en pipes, et le contenu injecté le casse au
rendu. Le défaut n'apparaîtrait que sur les pages concernées, donc tard et une à
la fois.

#### Ampleur mesurée

Mesuré le 9 août 2026, **après injection des `nested-table`** — c'est le seul
décompte qui vaut, l'ordonnancement ci-dessus l'impose : **15 tableaux sur 58**
portent au moins une cellule complexe, soit 84 cellules complexes sur 1633 (5 %).
Motifs, en occurrences de nœud : `bulletList` (74, réparties sur 69 cellules), plus
d'un `paragraph` (18), `mediaSingle` (15, sur 13 cellules), `table` (2), `rule` (1).

**Méthode du décompte** : chaque cellule est rattachée à son `table` le plus proche et
comptée une seule fois ; le parcours entre dans `parameters.adf`. La précision n'est pas
ornementale — une remesure du 11 août, collectant les cellules sur tout le sous-arbre de
chaque tableau, a compté deux fois les 34 cellules des deux tableaux injectés et conclu
à 1667 cellules dont 97 complexes. Les chiffres ci-dessus ont été rétablis. **Un nombre
mesuré n'entre dans ce contrat qu'avec la façon dont il a été compté.**

Les 9 fixtures ne contiennent que **2** `nested-table` ; les 11 relevées au §2.2
portent sur les 248 fixtures du corpus complet. Un décompte antérieur annonçait
« environ 24 sur 56 » en extrapolant depuis ces 11 — il est corrigé ici.

La répartition est très inégale : `28344321` a 4 tableaux complexes sur 6,
`380567556` 3 sur 5, tandis que `241532980` n'en a aucun sur 10 et `560201732`
un seul sur 19.

Deux lectures de « la cellule contient » ont été calculées — enfants directs, ou
sous-arbre entier : elles donnent le même résultat. Aucun bloc ne se cache en
profondeur sans être visible au premier niveau ; la lecture directe suffit.

**Ces 26 % justifient à eux seuls la décision « index croisé construit depuis
l'ADF, pas depuis le `.md` ».** Il suffit d'une cellule à liste pour qu'un
tableau ne survive pas à un aller-retour par le markdown — et deux des CU
analysées sont largement dans ce cas : `28344321` porte 4 tableaux complexes sur
6, `28344344` 2 sur 4.

#### Cellules restant en pipes

`tableHeader` produit la ligne d'en-tête ; un tableau sans `tableHeader` reçoit
une ligne d'en-tête vide, faute de quoi la syntaxe en pipes est invalide.

**Une ligne d'en-tête mixte fait basculer le tableau en HTML** — troisième déclencheur,
après le contenu de bloc et la fusion. Est mixte une première ligne qui n'est pas
composée à 100 % de `tableHeader`, ou un tableau portant un `tableHeader` hors de sa
première ligne. Les 60 tableaux du corpus doré ont une première ligne homogène et aucun
`tableHeader` ailleurs : la règle n'y est pas exercée, elle demande un test dédié. Sans
elle, le cas dégrade en silence — tout l'en-tête passe en corps et une ligne d'en-tête
vide est émise. En HTML, `<th>` et `<td>` cohabitent sans contrainte et il n'y a rien à
réparer.

**Tout caractère `|` présent dans le contenu d'une cellule est échappé en `\|`.**
Sans cet échappement, un `|` rompt la structure du tableau : notations `R/O/P` des
tableaux de contrats DTO, expressions logiques dans les règles. Le défaut est
silencieux et ne se voit qu'au rendu, sur une page à la fois.

#### Aucun autre échappement

**Le texte n'est jamais échappé, hors les deux cas ci-dessus** : le `|` d'une cellule en
pipes, et `&` `<` `>` dans une cellule en HTML. Les caractères actifs du markdown —
`*`, `_`, `[`, `!`, `#`, `` ` `` — sortent tels quels.

La règle n'est pas une négligence, c'est une condition de fonctionnement. Le pipeline
**fabrique** de la syntaxe markdown, y compris à l'intérieur du contenu qu'il injecte :
un échappement générique transformerait `![alt](adf-media://…)` en `!\[alt\](…)`, affiché
littéralement. C'est l'un des motifs pour lesquels `marklas` a été écarté le 9 août — son
renderer échappait la syntaxe injectée.

Elle est écrite ici parce qu'un lecteur qui découvre du texte non échappé y verra un
oubli, ajoutera une protection générique, et cassera le rendu sans qu'aucune fixture ne
change de forme visible.

### 9.2 `panel` — conteneur transparent

7 occurrences, sur 7 fixtures — c'est un élément récurrent des cartouches, pas une
exception.

```json
{"type": "panel", "attrs": {"panelType": "info"}, "content": [ ... ]}
```

**Rendu : transparent.** Le contenu est émis à la place du nœud, comme au §4 ; le
contenant disparaît. `attrs.panelType` est jeté, ainsi que `panelIcon`,
`panelIconId`, `panelIconText` et `panelColor` s'ils sont présents.

Une version antérieure de ce contrat rendait le panel en citation étiquetée
(`> **[INFO]**`) pour « donner une ancre aux skills ». Le besoin réel est le
**contenu** du panel, pas la connaissance du contenant : aucun contrôle de
validation ne dépend de savoir qu'une donnée était dans un panel. Deux mesures ont
appuyé l'abandon : les 7 panels du corpus doré sont **tous** en `panelType: info`
— l'étiquette ne distinguait donc rien — et le corpus ne compte que 2 `blockquote`,
dont le panel était censé se distinguer.

**Un `panelType` inconnu ne lève pas** : il est jeté comme les autres, le contenu
sort intact.

**Conséquence sur le §9.1** : `panel` reste dans la liste des contenus de bloc qui
font basculer un tableau en HTML. Un panel en cellule porte des paragraphes, donc
du bloc ; c'est le contenu qui commande, pas le contenant. Aucune occurrence dans
les fixtures.

---

## 10. Types non exercés — deux listes à ne pas confondre

**Deux listes, et non une.** Le titre de cette section a longtemps dit « absents du
corpus » alors qu'elle ne mesurait que les 9 fixtures. L'imprécision a produit une
erreur : `mediaInline` y figurait comme absent, alors qu'il compte 6 occurrences au
corpus complet. La distinction est désormais explicite.

**Absents du corpus complet — aucune règle, ils lèvent** : `nestedExpand`,
`mediaGroup`, `embedCard`, `decisionList`, `decisionItem`. Écrire une règle spéculative
reviendrait à faire passer leur apparition inaperçue, ce que la règle dominante du
document interdit. Le renderer les traite comme n'importe quel type non couvert :
incident, la page part en `parse_status: partial` avec son motif, et le rapport de run le
signale.

**Couverts, mais absents des 9 fixtures — donc non exercés par le corpus doré** :
`date` (§7.4), `emoji` (§7.5), `mediaInline` (§5.1), `fontSize` (§8.2), et la fusion de
cellules `colspan` / `rowspan` (§9.1). Cette liste **est** la liste des tests dédiés à
écrire : rien dans le corpus de non-régression ne les éprouvera tant que le
rafraîchissement prévu n'y aura pas versé une page porteuse.

Avec `date`, `emoji` et `mediaInline`, le contrat couvre **les 36 types du corpus
complet** : les 33 des 9 fixtures et ces trois-là. Aucun type connu ne peut plus faire
partir une page en `partial` au premier run complet.

**Quatre types à occurrence unique** méritent une vigilance particulière —
`codeBlock`, `mention`, `status`, `taskList` : leur règle est écrite sur un seul
exemple, et une erreur ne se verrait qu'en production sur le corpus complet.

---

## 11. Ce qui reste à trancher

- **Le sort de l'essai « Extrait natif »** du 5 août sur `180256775` et
  `27787265` : conservé, annulé, ou généralisé.
- Le sort de `API-COMPTE-USER.REINIT.PSW` (`110231568`) — voir
  `contracts/classification_pages.md` §5.
