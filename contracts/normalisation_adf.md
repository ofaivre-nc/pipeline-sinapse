# Table de normalisation ADF

Ce que le pipeline fait de chaque nœud ADF du corpus SINAPSE.

**État : table de normalisation complète.** Les 33 types de nœuds relevés dans
le corpus sont couverts : contenu réutilisé (§1), `nested-table` (§2),
nettoyage des noms (§3), seconde famille de macros (§1.8), mise en page (§4),
médias (§5), cartes (§6), `status` / `taskList` / `mention` (§7), marks (§8),
nœuds structurels (§9). Les types absents du corpus sont énumérés en §10 et
lèvent. Les points encore ouverts, listés en §11, ne portent plus sur la
normalisation elle-même mais sur ses prérequis — slugification, resolver,
arbitrage du mécanisme de réutilisation.

Base factuelle : 248 fixtures ADF pour §1 à §3 ; les 9 fixtures du corpus doré,
8045 nœuds, inventaire exhaustif de 33 types, pour §4 à §10.

**Règle qui domine tout le reste** : aucun nœud n'est ignoré silencieusement. Un nœud
non couvert par cette table remonte en erreur au rapport de run.

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

Le parcours récursif complet attend l'arbitrage **réutiliser ou réécrire le resolver**
multiexcerpt (question ouverte n°3 du brief) et la couche de récupération des pages.
`multiexcerpt.py` v1.0 ne contient que ce qui est indépendant de cet arbitrage : clés,
extraction de paramètres, garde-fou de cycle.

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
titre que le §10 énumère les nœuds absents pour que leur apparition ne passe pas
inaperçue.

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

`mediaGroup`, `mediaInline` : absents du corpus — voir §10.

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

53 occurrences, réparties en trois familles :

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
| ID extrait (URL longue ou lien court décodé) **et** présent dans `pages_inventory.json` | `[{titre}]({md_path})` |
| ID extrait, **absent** de l'inventaire | `[{url}]({url})` + fait au rapport de run |
| Suffixe non décodable, ou URL d'une autre nature (ticket Jira) | `[{url}]({url})` |

**Conséquence de séquencement** : le normalizer dépend de `pages_inventory.json`
pour une **seconde** raison, après la résolution du contenu réutilisé par titre
(§1). Et il dépend de `md_path`, donc de la règle de slugification. Tant que
celle-ci n'est pas arrêtée, la première ligne est inapplicable et le rendu se
replie sur `[{url}]({url})`.

Un ID absent de l'inventaire n'est pas une erreur de parsing : c'est un renvoi
vers une page hors périmètre d'export, fait à consigner.

**Anomalie relevée dans le corpus** : `380567556` porte un `inlineCard` vers
`…/wiki/spaces/SINAPSE/pages/edit-v2/380567556#IHM-concernant-la-gestion-du-profil…`
— une URL **d'édition**, avec ancre, pointant vers la page elle-même. L'extraction
d'identifiant doit tolérer le segment `edit-v2/` sans le confondre avec un
identifiant, et le fait est à remonter au rapport de run.

`embedCard` : absent du corpus — voir §10.

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

`decisionList`, `decisionItem` : absents du corpus — voir §10.

---

## 8. Marks

14 marks distincts. Six ont un rendu markdown direct : `strong`, `em`, `code`,
`link`, `underline` (`<u>`), `strike`.

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
| `backgroundColor` | 147 | 5 | `<mark style="background:{color}">…</mark>` |
| `textColor` | 7 | 1 (`#bf2600`) | `<span style="color:{color}">…</span>` |

**Le hex est conservé brut, sans table de correspondance couleur → sens.** Le
pipeline produit un fait ; l'interprétation reste aux skills et aux BA. Une table
figée dans le pipeline se périmerait au premier changement de convention.

Valeurs relevées, pour mémoire et sans valeur normative :
`#dfd8fd` (47), `#fedec8` (46), `#d3f1a7` (40), `#c6edfb` (9), `#f8e6a0` (5) en
fond ; `#bf2600` (7) en texte, sur des libellés de contrainte du type « La date
doit être de la forme "JJ/MM/AAAA" ».

### 8.2 Marks jetés

| Mark | Occ. | `attrs` typiques | Motif |
|---|---|---|---|
| `breakout` | 36 | `{"mode": "wide", "width": 1800}` | largeur d'affichage |
| `alignment` | 32 | `{"align": "end"}` | alignement |
| `fragment` | 19 | `{"name": "Table 2", "localId": "…"}` | identité interne Confluence |
| `annotation` | 8 | `{"annotationType": "inlineComment", "id": "…"}` | commentaire dont le corps n'est pas dans l'ADF |
| `border` | 2 | `{"size": 2, "color": "#091e4224"}` | bordure d'image |
| `subsup` | 1 | `{"type": "sup"}` | exposant, sans équivalent markdown |

Le texte porté est conservé intact dans tous les cas.

**Aucun mark ne fait échouer une page.** Mais la liste des marks traités est une
**liste blanche explicite** : un mark absent des quatorze lève, conformément à la
règle qui domine ce document. `fontSize`, relevé ailleurs dans le corpus complet
mais absent des 9 fixtures, en fait partie tant qu'il n'a pas été arbitré.

`annotation` signale qu'un commentaire en ligne existe, mais son contenu se
récupère par une API distincte, hors périmètre. Le nombre d'annotations
rencontrées peut être consigné au rapport de run.

### 8.3 Pas de passe de fusion des nœuds `text`

Sur **804 paires de nœuds `text` adjacents** examinées, **aucune** ne porte le
même jeu de marks. L'ADF rendu par l'API est déjà normalisé de ce point de vue :
Confluence fusionne à la source les textes contigus de même formatage. Le risque
`**a****b**` n'existe pas sur ce corpus.

**Aucune passe de fusion n'est donc écrite** — mais le renderer porte une
**assertion** sur cette propriété plutôt qu'une confiance tacite : rien ne la
garantit contractuellement du côté d'Atlassian, et sa violation produirait un
balisage cassé silencieux.

---

## 9. Nœuds structurels

Les types suivants n'appellent pas d'arbitrage : leur rendu markdown est direct.
Ils figurent ici pour que la table du document soit **exhaustive**.

**Portée de l'exhaustivité : le document entier, pas la seule table ci-dessous.** Les
33 types du corpus sont couverts, 16 ici et 17 dans les sections précédentes — les
nœuds de réutilisation en §1 (`extension`, `bodiedExtension`, `inlineExtension`,
`syncBlock`, `bodiedSyncBlock`), la mise en page en §4 (`layoutSection`,
`layoutColumn`, `expand`), les médias en §5 (`media`, `mediaSingle`, `caption`), les
cartes en §6 (`blockCard`, `inlineCard`), et `status` / `taskList` / `taskItem` /
`mention` en §7. **Un type que ne couvre aucune section lève** ; ceux qu'on sait
absents du corpus sont énumérés en §10.

| Type | Occ. | Rendu |
|---|---|---|
| `doc` | 9 | racine, transparent |
| `text` | 2791 | texte, marks appliqués selon §8 |
| `paragraph` | 2218 | bloc, ligne vide de séparation |
| `heading` | 96 | `#` répété `attrs.level` fois |
| `bulletList` / `listItem` | 175 / 413 | `- ` avec indentation par niveau |
| `orderedList` | 3 | `1. ` avec indentation par niveau |
| `blockquote` | 2 | `> ` en préfixe de chaque ligne |
| `codeBlock` | 1 | bloc clôturé, langage depuis `attrs.language` si présent |
| `rule` | 39 | `---`, **précédé d'une ligne vide obligatoire** |
| `hardBreak` | 34 | `<br>` |
| `panel` | 7 | voir §9.2 |
| `table` / `tableRow` / `tableHeader` / `tableCell` | 56 / 370 / 212 / 1387 | voir §9.1 |

**`rule`** : sans la ligne vide qui le précède, `---` placé sous un paragraphe est
interprété comme un titre setext de niveau 2 par la plupart des moteurs markdown.
Le paragraphe précédent deviendrait un titre.

**`hardBreak`** : `<br>` plutôt que deux espaces en fin de ligne. Les deux espaces
sont supprimés par la plupart des éditeurs et des linters, et ne fonctionnent pas
dans une cellule de tableau.

### 9.1 Tableaux — deux rendus selon le contenu des cellules

Un tableau markdown en pipes ne peut contenir que de l'inline. Or le corpus porte
des cellules à contenu de bloc : listes à puces, tableaux imbriqués (§2),
paragraphes multiples, images.

**Règle : si une seule cellule du tableau contient du contenu de bloc, le tableau
entier est rendu en HTML.** Sinon, tableau en pipes.

Est du contenu de bloc, dans une cellule : `bulletList`, `orderedList`, `table`,
`panel`, `codeBlock`, `blockquote`, `mediaSingle`, ou plus d'un `paragraph`.

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

Sur les 9 fixtures, **13 des 56 tableaux** portent au moins une cellule complexe,
soit 630 cellules dont 71 réellement complexes (11 %). Motifs : `bulletList` (56
cellules), plus d'un `paragraph` (18), `mediaSingle` (13).

Ce décompte est **sous-estimé** : il porte sur l'arbre principal, avant injection.
Les 11 tableaux logés dans `parameters.adf` des nœuds `nested-table` sont par
construction des tableaux dans des cellules ; après injection, leurs tableaux
hôtes basculent aussi. Le total réel approche 24 tableaux sur 56.

La concentration est extrême : une seule fixture (`10485761`) porte 49 des 71
cellules complexes dans 2 tableaux, tandis que `560201732`, avec 19 tableaux, n'en
a qu'une.

Deux lectures de « la cellule contient » ont été calculées — enfants directs, ou
sous-arbre entier : elles donnent le même résultat. Aucun bloc ne se cache en
profondeur sans être visible au premier niveau ; la lecture directe suffit.

**Ces 23 % justifient à eux seuls la décision « index croisé construit depuis
l'ADF, pas depuis le `.md` ».** Il suffit d'une cellule à liste pour qu'un
tableau ne survive pas à un aller-retour par le markdown — et deux des CU
analysées, `28344321` et `28344344`, sont dans ce cas.

#### Cellules restant en pipes

`tableHeader` produit la ligne d'en-tête ; un tableau sans `tableHeader` reçoit
une ligne d'en-tête vide, faute de quoi la syntaxe en pipes est invalide.

**Tout caractère `|` présent dans le contenu d'une cellule est échappé en `\|`.**
Sans cet échappement, un `|` rompt la structure du tableau : notations `R/O/P` des
tableaux de contrats DTO, expressions logiques dans les règles. Le défaut est
silencieux et ne se voit qu'au rendu, sur une page à la fois.

### 9.2 `panel`

7 occurrences, sur 7 fixtures — c'est un élément récurrent des cartouches, pas une
exception.

```json
{"type": "panel", "attrs": {"panelType": "info"}, "content": [ ... ]}
```

Rendu : citation markdown précédée d'une ligne d'étiquette.

```
> **[INFO]**
> {contenu}
```

L'étiquette reprend `attrs.panelType` en capitales. Elle distingue un `panel` d'un
`blockquote` ordinaire (§9), que le préfixe `>` seul confondrait, et donne une
ancre aux skills. Un `panelType` inconnu est repris tel quel en capitales — il ne
lève pas, contrairement à un type de nœud inconnu.

---

## 10. Nœuds absents du corpus

`nestedExpand`, `mediaGroup`, `mediaInline`, `embedCard`, `decisionList`,
`decisionItem` : zéro occurrence sur les 9 fixtures.

**Aucune règle n'est écrite pour eux.** Le normalizer les traite comme n'importe
quel type non couvert : il lève, la page part en `parse_status: partial` avec son
motif, et le rapport de run le signale. Écrire une règle spéculative reviendrait à
faire passer leur apparition inaperçue, ce que la règle dominante du document
interdit.

**Quatre types à occurrence unique** méritent une vigilance particulière —
`codeBlock`, `mention`, `status`, `taskList` : leur règle est écrite sur un seul
exemple, et une erreur ne se verrait qu'en production sur le corpus complet.

---

## 11. Ce qui reste à trancher

- **La règle de slugification**, verrou de `md_path`, prérequis de §6.3. Le
  corpus emploie `-` et `.` dans les titres : la réduction du point en tiret
  fabriquerait des collisions (`CU-NOTE-TYPENOTE.CREER` contre
  `CU-NOTE-TYPENOTE-CREER`). Une désambiguïsation est nécessaire.
- **`fontSize`**, relevé dans le corpus complet mais absent des 9 fixtures.
- **L'arbitrage réutiliser ou réécrire le resolver** multiexcerpt (question
  ouverte n°3 du brief), désormais élargi : le corpus porte **deux familles de
  macros** de réutilisation (§1.8) en plus du mécanisme `syncBlock`.
- **Le sort de l'essai « Extrait natif »** du 5 août sur `180256775` et
  `27787265` : conservé, annulé, ou généralisé.
- Le sort de `API-COMPTE-USER.REINIT.PSW` (`110231568`) — voir
  `contracts/classification_pages.md` §5.
