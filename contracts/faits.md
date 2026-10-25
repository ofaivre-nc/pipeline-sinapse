# Contrat de faits (v2)

Ce que le pipeline garantit aux skills de validation de `sinapse-skills` : les **faits** d'une spec, extraits de l'ADF, rangés pour que chaque contrôle du catalogue les désigne par un chemin stable.

*Rédigé le 22 octobre 2026, avant le code (étape 7 de la feuille de route de `sinapse-skills`). Remplace `index_croise.schema.json` v1, jamais implémenté, et le « format normalisé » prévu côté skills. Le JSON carto et le JSON MCD deviennent des **projections** de ces faits (§7).*

**État : proposition.** Les noms de champs sont ceux que le catalogue utilisera ; les changer après l'écriture du catalogue coûte une passe sur tous ses contrôles.

---

## 1. Principes

1. **Des faits, jamais un verdict.** Le collecteur relève ce qui est écrit, avec son emplacement. Il ne dit pas si c'est conforme : c'est le rôle du catalogue. Changer un seuil ou une sévérité ne doit jamais toucher au pipeline.
2. **Trois entrées, pas de réseau :**
   - l'**ADF brut** de la page, et non l'ADF résolu. Le brut garde les noms d'extraits tels qu'écrits (K55 en a besoin) et montre les inclusions comme des références, sans recopier le contenu des autres pages ;
   - les **faits du resolver** (`resolver.py`), qui donnent le statut de chaque inclusion (`resolue`, `definition_absente`, `page_source_absente`). La jointure se fait par `localId` ;
   - l'**inventaire** (`pages_inventory.json`), qui donne le type, le module, la page parente et le quartier.
3. **Nom brut et nom normalisé.** Tout nom (extrait, titre, cible de lien) est donné deux fois : `brut`, tel qu'écrit, et normalisé, après `html.unescape()`, `.strip()` et repli des tirets Unicode (contrat `normalisation_adf.md` §3). La normalisation se fait **une seule fois, ici**. Un contrôle compare toujours les noms normalisés, sauf ceux qui portent justement sur l'écriture brute (K55).
4. **Tout fait porte son emplacement** (`ou`, §3.5). Sans lui, le compte-rendu ne peut pas dire où commenter.
5. **Absent n'est pas vide.**
   - Une **section absente** de la page : la clé est absente.
   - Une **section présente mais sans contenu** : liste vide `[]` ou texte vide `""`.
   - Jamais `null`.

   Les deux cas comptent pour le catalogue : K24 distingue « §3 manquant » de « §3 vide ». Les projections appliquent ensuite leur propre règle (le JSON carto omet les listes vides).
6. **La structure vient d'une configuration par type, pas du code** (`pipeline/config/faits_types.json`, §8). Elle donne les titres de section et les en-têtes de colonnes reconnus, avec leurs synonymes. Les vraies pages ne suivent pas toutes le template : cartouche en tableau dans le template et en colonnes dans les pages, « Evolutions » en titre ou en bloc repliable, « SA appelés » ou « SA associés ».
7. **Rien ne disparaît en silence.** Une section, une colonne ou un tableau que la configuration ne reconnaît pas va dans `inconnus[]` (§4.6), avec son emplacement. C'est un fait comme un autre : il signale soit une page hors template, soit une configuration à compléter.
8. **Barré et coloré sont des attributs, pas des filtres.** Le texte barré (évolution à venir) n'est pas retiré : il est marqué `barre: true`. Un contrôle de présence ne compte pas une ligne entièrement barrée (décision du 2026-10-21). Le texte coloré porte sa couleur ; aucun contrôle n'en dépend en v1.

## 2. Fichiers

| Fichier | Contenu | Réécrit quand |
|---|---|---|
| `faits/{page_id}.json` | faits d'une page (§4 et §5) | la version Confluence de la page change, ou la version du collecteur ou de sa configuration change |
| `faits/graphe.json` | couche graphe de tout le corpus exporté (§6) | à chaque run, à partir de tous les fichiers de page : c'est rapide et cela évite tout état caché |
| `faits/rapport_collecte.json` | pages relues (avec le motif), inchangées, partielles, en échec, sans ADF | à chaque run |
| `carto_sinapse_data_{perimetre}_{AAAAMMJJHHMM}.json` | projection carto (§7.1) | sur demande |
| `mcd_sinapse_data_{AAAAMMJJHHMM}.json` | projection MCD (§7.2) | sur demande ; l'ancien fichier est conservé |

Chaque fichier porte en tête :

```json
{
  "schema_version": 2,
  "collecteur_version": "1.0",
  "config_version": "1.0",
  "genere_le": "2026-10-22T09:00:00Z"
}
```

Un lecteur qui trouve une autre `schema_version` s'arrête au lieu de deviner.

**Mode incrémental.** Un run sur un SF ne relit que les pages dont `confluence_version` a changé depuis le fichier de faits existant. Le graphe, lui, est toujours reconstruit en entier : une page inchangée peut devenir incohérente parce que sa voisine a changé.

## 3. Types de base

### 3.1 `Texte`

La forme de toute valeur rédigée : une cellule, un paragraphe, une section.

```json
{
  "texte": "Si la personne personneId n'est pas trouvée (cf RG-NOTE-ASSOCIATION-PERSONNE)",
  "liens": [ { "...": "Lien, §3.2" } ],
  "inclusions": [ { "...": "Inclusion, §3.3" } ],
  "citations": [ { "...": "Citation, §3.4" } ],
  "barre": true,
  "couleur": "#ff5630"
}
```

- `texte` : le texte à plat, espaces normalisés. Une inclusion y apparaît sous la forme `{inclusion:NOM}`, pour que le texte reste lisible sans être confondu avec la prose.
- `barre` : présent et vrai seulement si **tout** le texte est barré. `couleur` : présent seulement si tout le texte porte la même couleur.
- `liens`, `inclusions`, `citations` : présents seulement s'ils ne sont pas vides.

### 3.2 `Lien`

```json
{
  "texte": "SA-NOTE-CREER",
  "url": "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/751173657",
  "forme": "lien",
  "cible": { "type": "page", "page_id": "751173657", "titre": "SA-NOTE-CREER" },
  "etat": "brouillon"
}
```

- `forme` : `lien` (mark `link`), `carte` (`inlineCard`) ou `bloc` (`blockCard`).
- `cible.type` : `page`, `jira` (avec `ticket`), `externe`.
  - Pour une page, `page_id` vient de l'URL, y compris d'un lien court `…/x/{suffixe}` (décodé sans réseau, comme le fait `renderer.py`).
  - `titre` est le titre de la page cible **si elle est dans l'inventaire** ; sinon la clé est absente, et le graphe la range parmi les références hors corpus.
- `etat` : présent seulement si le lien vise une page non publiée ou en édition : `brouillon` (`resumedraft.action`, `draftId=`) ou `edition` (`/edit-v2/`). C'est le fait de K53.

### 3.3 `Inclusion`

```json
{
  "mecanisme": "excerpt",
  "nom_brut": " RG-NOTE-ASSOCATION-TYPENOTE",
  "nom": "RG-NOTE-ASSOCATION-TYPENOTE",
  "page_source": "SF-NOTE: Règles de gestion consolidées",
  "statut": "resolue",
  "forme": "inline",
  "local_id": "4963a47a44dd"
}
```

`mecanisme` : `multiexcerpt`, `excerpt` ou `sync`. `statut` vient du resolver, joint par `page_id` et `local_id` (resolver 1.4) ; `hors_corpus: true` quand la page source n'est pas dans le corpus exporté, ce que K56 ne signale pas. Pour un extrait natif sans nom, `nom` vaut `""` (extrait par défaut, `normalisation_adf.md` §1.8). Pour un syncBlock, `nom` est l'UUID du bloc.

### 3.4 `Citation`

Un code reconnu dans le texte, par motif. Les motifs sont dans la configuration (§8), pas dans le code.

```json
{ "type": "RG", "code": "RG-NOTE-ASSOCIATION-PERSONNE", "forme": "gras" }
```

- `type` : `RG`, `MSG`, `IHM`, `SA`, `CU`, `API`, `ROUTE`, `HAB` (habilitation `ressource:action` ou `HAB-…`), `CHAMP` (`Entite.attribut`), `TICKET`.
- `forme` : `prose`, `gras`, `code`, `lien` (le code est le texte d'un lien) ou `inclusion` (le code est le nom d'une inclusion).

**Une citation en prose n'est jamais l'identité d'une RG** (règle de lecture de `CLAUDE.md`) : le graphe prend ses arêtes dans les inclusions et les liens. Les citations servent aux contrôles qui comparent la prose à la macro : K02 (nom en prose ≠ nom de l'extrait) et K34 (RG citées au §4 d'un SA ≠ RG du §5).

### 3.5 `Emplacement` (`ou`)

```json
{ "section": "1. Inventaire des routes", "tableau": 1, "ligne": 3, "colonne": "habilitation" }
```

- `section` : titre de la section, tel qu'écrit, ou `cartouche`, `evolutions`.
- `tableau` : rang du tableau dans la section (à partir de 1).
- `ligne` : rang de la ligne, en-tête exclu (à partir de 1).
- `colonne` : nom **canonique** de la colonne (§8), pas l'en-tête brut.
- `local_id` : quand le nœud ADF en porte un.

### 3.6 `Ligne`

Une ligne de tableau : `{ "ou": {…}, "cellules": { "<colonne canonique>": Texte } }`. Une colonne absente du tableau est absente de `cellules`. La ligne entière porte `barre: true` si toutes ses cellules non vides sont barrées.

- Une **ligne de regroupement** (une seule cellule sur toute la largeur : « Tri et pagination », « Authentification », un sous-objet « Habilitations listeHabilitations[] ») n'est pas une ligne : son texte est porté par les lignes suivantes, dans `groupe`. K35 s'en sert pour écarter les attributs d'authentification.
- Une ligne entièrement vide est omise.
- Les cellules d'une colonne non reconnue vont dans `autres`, sous leur en-tête brut (§8).

## 4. Socle commun à toute page

### 4.1 `page`

```json
"page": {
  "id": "751173657",
  "titre": "SA-NOTE-CREER",
  "titre_brut": "SA‑NOTE-CREER",
  "type": "SA",
  "module": "NOTE",
  "quartier": "Q-IDENTITE",
  "parent_id": "12976129",
  "url": "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/751173657",
  "confluence_version": 17,
  "version_date": "2026-10-10T08:12:00Z",
  "exporte_le": "2026-10-22T00:01:05Z",
  "parse_status": "ok"
}
```

- `titre_brut` : présent seulement s'il diffère de `titre`.
- `module` vient de l'ascendance (ancêtre `SF-*`, inventaire) ; `quartier` aussi (page parente du SF, décision du 2026-10-22). Les valeurs écrites dans le cartouche sont relevées à part (§4.2) : K58 compare les deux.
- `parse_status` : `ok`, `partial` (au moins un `inconnus[]` ou une section attendue manquante) ou `failed`. Un contrôle ne score pas une page `failed`.

### 4.2 `cartouche`

| Champ | Type | Source |
|---|---|---|
| `quartier` | `Texte` | « Quartier : … » |
| `sf` | `Texte` | « Service fonctionnel : … » |
| `habilitation` | `Texte` | « Habilitation : … » (CU) |
| `cus_lies` | `Texte` | « CUs liés : … » (API, SA) |
| `lien_test` | `Lien` | « Lien vers la tâche de test » |

Le cartouche est lu dans la première `layoutSection` de la page, ou dans le premier tableau de la section « Cartouche d'identification » pour une page au format du template. La valeur brute de l'habilitation n'est jamais normalisée (`HAB-XXX` et `ressource:action` coexistent).

### 4.3 `jira` et `evolutions`

```json
"jira": { "ticket_test": "REC-2231", "jql": "id in linkedIssues(REC-2231,\"réfère\") and …" },
"evolutions": [
  { "ou": {…}, "version": "1", "description": Texte, "tickets": ["REC-900"], "date": "17/08/2026" }
]
```

- `jira` : relevé dans le `blockCard` du cartouche. Le pipeline n'appelle pas Jira.
- `evolutions` : lignes du tableau du bloc repliable « EVOLUTIONS » (ou de la section « Evolutions »). `tickets` : codes trouvés dans la colonne Ref JIRA, texte ou lien. `date` : telle qu'écrite.

### 4.4 `sections`

Liste ordonnée des titres : `{ "niveau": 1, "titre": "2. Contrat d'entrée", "numero": "2", "canonique": "contrat_entree" }`. `canonique` est absent si la configuration ne reconnaît pas le titre. Sert à K17 (titres de niveau 1 du CU) et aux contrôles de présence de section.

### 4.5 Index de la page

Pour les contrôles qui portent sur toute la page, quel que soit l'endroit :

| Champ | Contenu | Contrôles |
|---|---|---|
| `textes` | tous les blocs de texte de la page (paragraphes, cellules, éléments de liste, titres), chacun avec `ou` et un `Texte` ; **y compris les paramètres des macros** (un placeholder peut s'y cacher) | K05, K06, K32, K33, K38, K40, K41 |
| `liens` | tous les `Lien` de la page, avec `ou` | K07, K08, K53, K56 |
| `inclusions` | toutes les `Inclusion`, avec `ou` | K01, K03, K56 |
| `definitions` | toutes les définitions d'extrait de la page : `mecanisme`, `nom_brut`, `nom`, `ou`, `titre_section` (le titre sous lequel elle est rangée) | K55, K57 |

`textes` duplique ce que portent les champs par type : c'est voulu. Un contrôle « nulle part dans la page » lit l'index ; un contrôle « dans la colonne Habilitation » lit le champ typé.

### 4.6 `inconnus`

`[{ "ou": {…}, "quoi": "colonne", "valeur": "Habilitation (cible)" }]`. `quoi` : `section`, `colonne`, `tableau`, `macro`.

## 5. Faits par type

Les noms de colonnes ci-dessous sont les noms **canoniques**. Les en-têtes réels, avec leurs synonymes, sont dans la configuration (§8).

### 5.1 CU

| Champ | Contenu | Contrôles |
|---|---|---|
| `description` | `Texte` de la section « Description » | K50 (revue) |
| `nominal` | `Ligne[]` : `numero`, `activite`, `description` | K50 |
| `alternatif` | idem, section « Fonctionnement alternatif » | — |
| `processus` | `{ "texte": Texte, "diagramme": true }` ; `diagramme` si la section contient une image ou un média | K18 |
| `ihm` | liste de blocs IHM : `{ "titre": "Frame 1 : …", "lignes": Ligne[] }` ; colonnes `libelle`, `composant`, `nom_champ`, `mapping_dto`, `saisie`, `obligatoire`, `description` | K04, K09, K11, K14, K15, K16, K19, K60, K62 |
| `regles` | `Ligne[]` du tableau de la section « Règles » ; colonne `regle` | K01, K03, K13, K62 |

### 5.2 API

| Champ | Contenu | Contrôles |
|---|---|---|
| `routes` | `Ligne[]` de l'inventaire ; colonnes `route`, `objet`, `sa`, `cus`, `habilitation`, `dto_requete`, `dto_reponse`. Chaque ligne porte en plus `verbe` et `chemin`, décomposés depuis `route` | K13, K20, K21, K22, K26, K27, K47 |
| `dtos` | catalogue §2 : `{ "nom": "ActualiteReponse", "ou": {…}, "attributs": [ { "nom": "data", "marqueur": "R", "precision": "ActualiteReponse[]" } ] }`. Les DTO sont les **colonnes** des matrices (en-tête = nom du DTO), les attributs sont les lignes. Une cellule « R - ActualiteReponse[] » donne le marqueur `R` et la `precision` | K09, K10, K23, K25, K60, K61 |
| `mappings` | §3 : `{ "sa": Texte, "ou": {…}, "un_pour_un": ["ActualiteRequete"], "lignes": Ligne[] }` ; `sa` vient de l'en-tête de la 2ᵉ colonne (souvent un lien) ; colonnes `element`, `contrat_sa`, `ecart`. `un_pour_un` : les DTO des lignes dont `contrat_sa` vaut « Correspondance 1 - 1 » ; les autres lignes sont les **écarts déclarés** (paramètre d'URL, contexte d'authentification, optionnel dans le DTO et obligatoire dans le SA…) | K24, K61 |

**Le §3 ne liste que les écarts** : sur API-PORTAIL-ACTUALITES, une ligne « ActualiteRequete | Correspondance 1 - 1 » dit que les attributs du DTO et ceux du contrat d'entrée se correspondent par nom, puis chaque ligne suivante déclare une exception. K61 rapproche donc les attributs par nom et ne signale pas un écart déclaré.

**Renvoi API → SA** (décision du 2026-10-21) : la cellule `sa` d'une route porte le nom du SA et, en général, son lien. Les deux sont gardés : le texte dans `texte`, la cible dans `liens`. La concordance des deux est un contrôle (K08), pas une correction faite par le collecteur.

### 5.3 SA

| Champ | Contenu | Contrôles |
|---|---|---|
| `objet` | `Texte` de « 1. But & scénarios » ou « 1.1 Objet » | K37, K49 |
| `scenarios` | `Ligne[]` (`scenario`, `declencheur`, `resultat`) si la section porte un tableau | — |
| `contrat_entree` | `Ligne[]` ; colonnes `attribut`, `description`, `obligatoire` ; la forme d'un sous-objet reste à relever (§10) | K28, K35, K36, K39, K61 |
| `objet_restitue` | `Texte` de 3.1 | — |
| `codes` | `Ligne[]` de 3.2 ; colonnes `code`, `message` | K29, K30, K31, K32 |
| `traitement` | `Texte` de toute la section 4, avec ses `citations` et ses `liens` ; plus `etapes` : `[{ "titre": "Contrôles", "texte": Texte }]`, découpées sur les titres et les paragraphes entièrement en gras | K28, K29, K34, K37, K52 |
| `regles` | `Ligne[]` du tableau de la section 5 ; colonne `regle` (la colonne « N° », si elle existe, donne `numero`) | K29, K34 |
| `tri` | whitelist de tri d'un SA de recherche : `{ "contrat": { "valeurs": ["date", "auteur"], "ou": {…} }, "traitement": { "valeurs": […], "ou": {…} } }`. `contrat` : la description de la ligne `sort` du §2 ; `traitement` : la première ligne du §4 qui cite `sort` et nomme les attributs après « whitelist ». Une whitelist donnée par renvoi (« hors whitelist de RG-… ») n'est pas relevée ; clé absente si aucun des deux côtés n'en nomme | K39 |

Les **RG du §4 sont des citations** (en gras dans la prose), celles du **§5 sont des inclusions**. K34 compare les deux ensembles, par nom normalisé.

### 5.4 RG et GENERIQUE

Une page RG (règles de gestion consolidées d'un SF) et une page générique (règles réutilisables) ont la même forme : une suite de définitions d'extrait.

```json
"regles": [
  {
    "ou": { "section": "RG-NOTE-PERSISTANCE-CREATION", "local_id": "…" },
    "groupe": "Persistance",
    "titre_section": "RG-NOTE-PERSISTANCE-CREATION",
    "mecanisme": "excerpt",
    "nom_brut": "RG-NOTE-PERSISTENCE-CREATION",
    "nom": "RG-NOTE-PERSISTENCE-CREATION",
    "titre": "Règle RG-NOTE-PERSISTANCE-CREATION concernant la création d'une note",
    "titre_gras": "Règle RG-NOTE-PERSISTANCE-CREATION concernant la création d'une note",
    "code_titre": "RG-NOTE-PERSISTANCE-CREATION",
    "concernant": "la création d'une note",
    "corps": Texte
  }
]
```

- `groupe` : le titre de niveau 2 qui précède ; `titre_section` : le titre de niveau 3 juste au-dessus de la définition.
- `titre` : le premier paragraphe du corps, quand il commence en gras ou par « Règle » (convention TEMPLATE_RG : « Règle RG-X concernant … »). `titre_gras` : le premier passage en gras ; sur SF-NOTE, il ne couvre parfois que le mot « Règle », d'où les deux champs. `code_titre` : le code RG cité dans `titre`. `concernant` : ce qui suit « concernant » dans `titre`.
- Le nom, le titre de section et le code du titre peuvent **tous trois différer** : sur SF-NOTE, `RG-NOTE-PERSISTENCE-CREATION` (nom) est rangé sous `RG-NOTE-PERSISTANCE-CREATION` (titre et code). Le collecteur relève les trois ; K54 et K02 les comparent.
- `corps` porte ses `citations` : les `MSG-` d'une RG incluse au §5 d'un SA comptent pour K29, les `IHM_…` et les libellés d'une RG incluse par un CU pour K62. Le contrôle passe de l'inclusion à la définition par la jointure du resolver (§2), pas par le texte affiché dans la page qui inclut.
- `corps.tableaux` (clé absente sans tableau) : les tableaux du corps, en texte, `[{ "rang": 1, "entetes": ["Attributs du DTO X", "Alimentation"], "lignes": [["X.page", "…"]] }]`. Une cellule garde ses retours à la ligne (plusieurs attributs par cellule). Sert à K65.

### 5.5 MCD

```json
"entites": [
  {
    "nom": "Favoris",
    "libelle": "Propriétés de Favoris",
    "ou": {…},
    "agregat": { "ou": {…}, "texte": Texte, "type": "entite_interne", "racine": "Utilisateur" },
    "description": Texte,
    "attributs": [
      { "ou": {…}, "champ_brut": "Favoris.auteurId", "attribut": "auteurId",
        "designation": Texte, "format": "Entier36", "longueur": "", "commentaire": Texte,
        "valeurs": Texte }
    ]
  }
],
"relations": [
  { "ou": {…}, "de": "Personne", "vers": "CompteTI", "card_de": "0..N", "card_vers": "0..1", "libelle": "…" }
]
```

Règles reprises du skill legacy `confluence-mcd-sync`, qui les a éprouvées sur tout le corpus :

- **Entité** : déduite du **préfixe commun** de la colonne « Nom du champ » (`Favoris.id`, `Favoris.ordre` → `Favoris`), pas du titre de section, qui ne sert qu'au `libelle`. Sans préfixe commun, le tableau va dans `inconnus[]` plutôt que de produire une entité fausse. Plusieurs tableaux de même préfixe forment une seule entité.
- **Description** : la prose placée sous le titre de l'entité, hors tableaux (« Objet permettant de représenter une Note… », TEMPLATE_MCD). Clé absente si le titre n'est suivi que du tableau. Sert à K104. Depuis le TEMPLATE_MCD du 2026-10-23, elle commence par le libellé « **Description** : », que le collecteur retire ; ce qui précède ce paragraphe est le texte d'agrégat.
- **Agrégat** (collecteur 1.2, configuration 1.4) : le texte placé entre le titre de l'entité et le paragraphe « Description » (TEMPLATE_MCD : « racine de l'agrégat », « entité interne à l'agrégat » ou « objet valeur », et la racine associée). Clé absente sans paragraphe « Description » (ancien format) ou sans texte avant lui. `type` : `racine`, `entite_interne` ou `objet_valeur`, reconnu par les synonymes de `faits_types.json` (`MCD.entite.agregat`), clé absente si aucun ne figure. `racine` : pour une entité interne ou un objet valeur, l'entité de la même page citée dans le texte (la première après le mot « racine »), clé absente sinon ; une racine définie dans un autre MCD reste dans `texte`. Le collecteur ne juge pas : un type non reconnu ou une racine manquante sont l'affaire du catalogue.
- **Ancien format** `MODULE.ENTITE.champ` (SF-DOCUMENT) : relevé tel quel dans `champ_brut`. K43 le signale ; le collecteur ne le corrige pas.
- **Relations** : texte de la forme `Entite (card) <-> (card) Entite`, flèche ASCII `<->` ou `↔` (U+2194, avec ou sans U+FE0E). Une ligne peut enchaîner plusieurs relations. Un libellé `, lien "…"` en fin de ligne va dans `libelle`. Cardinalités normalisées en `0..N`, `1..1`, `1..N`, `0..1`. Une relation barrée porte `barre: true`.
- La **clé étrangère** n'est pas déduite : K44 rapproche lui-même `auteurId` de l'entité visée et de son format.

### 5.6 TEMPLATE

Une page de template ne reçoit que le socle (§4). Elle sert de référence à la configuration, pas de cible aux contrôles.

### 5.7 ASYNC et JOB

Hors du catalogue v1. Une page ASYNC ou JOB reçoit le socle et `parse_status: partial`. Le jour où leur template est stable, on ajoute une section ici et une entrée à la configuration, sans changer le reste.

## 6. Couche graphe (`graphe.json`)

Construite à partir des fichiers de page, sans relire l'ADF. Elle reprend le modèle du JSON carto (notice de cartographie §4 et §8), dont les décisions ne sont pas rouvertes : **toute relation est une arête**, un appel entre SA passe par la RG qui le porte (`RG → SA`), et un nœud n'existe que si sa page a été lue.

**Nœuds** : `cu`, `api`, `endpoint` (`id` = `VERBE /chemin`), `sa`, `async`, `rg`, `entite`. Chacun porte `id`, `sf`, `page_id` et `url`. L'`id` d'une RG est le **nom normalisé de son extrait**, jamais une variante vue en prose.

**Arêtes** : `{ "de", "vers", "type", "source": { "page_id", "ou" }, "confiance" }`.

| Type | De → vers | Pris dans |
|---|---|---|
| `appelle` | RG → endpoint | lien `VERBE /route` dans le corps de la RG |
| `appelle` | RG → SA | lien vers une page SA dans le corps de la RG |
| `appelle` | CU → endpoint | lien `VERBE /route` écrit dans la page CU elle-même, s'il y en a. **Sur les CU de SF-NOTE, il n'y en a aucun** : les 15 liens de route sont dans le corps des RG que les CU incluent. Le « CU appelle telle route » se lit donc en composant `CU → RG (reference)` et `RG → endpoint (appelle)`, comme « SA1 appelle SA2 » |
| `expose` | endpoint → SA | colonne `sa` de l'inventaire des routes (cible du lien, à défaut le texte) |
| `reference` | CU → RG, SA → RG | inclusions du tableau des règles (CU) ou du §5 (SA) |
| `inclut` | page → définition | toute inclusion, y compris non résolue : c'est le fait de K56 |
| `lien` | page → page | tout lien vers une page du corpus |
| `emet`, `consomme` | SA → ASYNC, ASYNC → SA | v2, avec le template ASYNC |
| `lecture`, `ecriture`, `lecture_critere` | RG → entité | **non produites ici** : heuristique, voir §7.1 |

Une cible absente du corpus exporté reste une chaîne dans `vers`, et va dans `hors_corpus[]` avec la page qui la cite. **Elle n'est pas une anomalie** (décision du 2026-10-21) : K56 ne signale que les cibles du corpus qui n'existent pas, ou les inclusions dont la définition manque.

## 7. Projections

Condition posée par Olivier le 2026-10-21 : les deux JSON se déduisent **facilement** des faits, par un script court et sans heuristique cachée. **Critère d'acceptation du contrat** : régénérer `fixtures/carto/carto_sinapse_data_sfnote_202610181200_v4.json` et la partie entités et relations de `fixtures/carto/mcd_sinapse_data_202610012100.json` (dépôt `sinapse-skills`), puis expliquer chaque écart (erreur des faits, ou erreur de la référence, faite en partie à la main).

**Vérifié le 2026-10-22** sur les 27 pages de test : code `pipeline/src/projections.py`, bilan dans `sinapse-skills/docs/analyse/acceptation-contrat-faits.md`. Tous les écarts s'expliquent (références plus anciennes, faites en partie à la main, de périmètre plus étroit, titres des pages hors corpus inconnus), sans champ à ajouter aux faits.

### 7.1 JSON carto

| Champ carto (notice §8) | Pris dans |
|---|---|
| Pages retenues | pages CU, SA et API du périmètre, sauf (`_meta.pages_ecartees`, avec le motif) : une **annexe** (titre « code : sous-titre », ex. « CU-NOTE-CONSULTER: Matrice de passage specs-tests ») et une **page chapeau** (CU ou SA sans aucune section du modèle et mère de pages du même type, ex. SA-NOTE). Une page squelette ou vide sans fille reste un nœud |
| `nodes.cu[]` : `id`, `sf`, `url`, `description`, `habilitation` | nœud `cu` ; `cu.description.texte` ; `cartouche.habilitation.texte` |
| `edges[]` `appelle` CU → endpoint | composition `CU → RG (reference)` + `RG → endpoint (appelle)` du graphe (§6), plus les liens directs du CU s'il y en a |
| `nodes.api[]` : `id`, `sf`, `url`, `tickets` | nœud `api` ; `evolutions[].tickets` |
| `nodes.endpoint[]` : `id`, `api`, `sa`, `description`, `habilitation`, `confiance` | nœud `endpoint` et arête `expose` ; `routes[].cellules.objet` et `.habilitation` (une cellule faite de l'extrait « habilitation » d'un CU prend `cartouche.habilitation.texte` de ce CU) ; `confiance` = `lien_brouillon_non_resolu` si le lien `sa` a `etat: brouillon` |
| `nodes.sa[]` : `id`, `sf`, `url`, `description`, `tickets` | nœud `sa` ; `sa.objet.texte` ; `evolutions[].tickets` |
| `nodes.rg[]` : `id`, `sf`, `url`, `description`, `extrait` | nœud `rg` ; `regles[].concernant`. Quand le nom d'extrait n'est pas un code RG (`recherche_pagination`), `id` = `regles[].code_titre` (`RG-RECH-6`) et `extrait` garde le nom ; les arêtes suivent |
| `nodes.rg[].categorie`, `confiance` | **heuristique de la projection**, reprise de la procédure carto §2.6 ; jamais un fait, jamais un score |
| `edges[]` `appelle`, `expose`, `reference` | arêtes du graphe, à l'identique |
| `edges[]` `lecture`, `ecriture`, `lecture_critere` | **heuristique de la projection** (`confiance: heuristique_v0`) : motif `Entite.attribut` dans `regles[].corps`, entité validée contre les `entites` des faits MCD. La cible `to` s'écrit **`SF.ENTITE` en capitales** (`NOTE.NOTE`, `NOTE.TYPENOTE`) : c'est la forme de la référence du 18 octobre, la seule que l'outil de visualisation reconnaît comme entité, et qu'il rapproche du JSON MCD par `(sf + '.' + id).upper()` |
| `_meta.references_non_resolues` | `hors_corpus[]` |
| `_meta.pages_connues` | `page.id`, `type`, `module`, `titre`, `confluence_version` des fichiers de faits |
| `_meta.anomalies_detectees` | **pas une projection** : c'est la sortie d'une validation. Le skill « valider » peut l'écrire |
| `jira{}`, `tickets` | `tickets` vient des faits ; `jira{}` de l'étape Jira (à la demande, hors pipeline) |

### 7.2 JSON MCD

| Champ du JSON MCD (v2.0) | Pris dans |
|---|---|
| `entities[]` : `id`, `label`, `sf`, `attrs[]` (`nom`, `designation`, `format`, `commentaire`) | `entites[]` des pages MCD, attributs non barrés ; `sf` = `page.module` ; `label` = nom de l'entité ; `format` sans la longueur et `commentaire` pris dans « Valeurs possibles », comme le legacy `confluence-mcd-sync` |
| `relations[]` : `from`, `to`, `cardFrom`, `cardTo`, `name` | `relations[]` des pages MCD, dédupliquées par `min(de,vers)\|max(de,vers)` |
| `quartiers[].sfs[].confluencePage` | `page.titre` et `page.url` de la page MCD du SF |
| `quartiers[]` | `page.quartier` (page parente du SF) |
| `quartiers[].sfs[].jiraTickets`, `paliers` | étape Jira (Epic parente des tickets des tableaux EVOLUTIONS, palier et incrément tirés de la version souhaitée MOA) ; à défaut, repris du fichier précédent |
| `paliers[]` (libellés, couleurs) | configuration de présentation, repris du fichier précédent |

Cette projection remplace `mcd_sinapse_data.schema.json` (provisoire), dont le format ne correspond pas au fichier réellement utilisé : c'est le fichier réel qu'on garde.

## 8. Configuration par type

`pipeline/config/faits_types.json`. En JSON et non en YAML : le pipeline n'a pas d'autre dépendance d'exécution que `requests` (`CLAUDE.md` du dépôt). Une entrée par type de page : sections reconnues, tableaux attendus par section, colonnes avec leurs synonymes, sections attendues (`attendues`). Exemple pour la section 1 de l'API :

```json
"API": {
  "sections": {
    "routes": {
      "titres": ["Inventaire des routes"],
      "tableau": { "colonnes": {
        "route": ["Route"],
        "sa": ["SA associés", "SA appelés", "SA associé", "SA"],
        "habilitation": ["Habilitation requise", "Habilitation"]
      } }
    }
  },
  "attendues": ["routes", "dtos", "mappings"]
}
```

- **Comparaison** : sur une forme réduite (minuscules, sans accents, apostrophes unifiées, ponctuation et espaces normalisés), après retrait de la numérotation de tête (« 3.2 Codes retours » → `numero` 3.2, titre « Codes retours »). Un synonyme terminé par `*` reconnaît tout en-tête qui commence par lui (« Message (à revoir, … ) »).
- **Motifs de citation** (clé `citations`) : un motif par type de citation (§3.4). Les codes `RG-` et `MSG-` acceptent le tiret bas, les `IHM_` les minuscules (`IHM_FAVORI_BoutonMonter`), pour que le code relevé soit entier et que les contrôles de format (K30) le voient tel qu'écrit.
- **Alias de type** : l'inventaire classe les MCD en `MDD` ; `alias_types` les ramène à `MCD`.
- **Sous-section** : une section reconnue rangée sous une autre (« Règles » en titre de niveau 2 sous « IHM ») garde ses faits pour elle ; ses tableaux ne sont pas comptés dans la section englobante.

Les synonymes de départ viennent des 27 pages de `sinapse-skills/fixtures/confluence/` et des templates ; toute nouvelle variante rencontrée apparaît d'abord dans `inconnus[]`, avec `quoi` : `section` (titre de niveau 1 non reconnu), `section_manquante` (section de `attendues` absente), `tableau` (aucun en-tête reconnu, ou entité MCD sans préfixe commun), `colonne`. La cellule d'une colonne non reconnue n'est pas perdue : elle va dans `autres` de sa ligne, sous son en-tête brut.

## 9. Ce que le catalogue lit : exemples de sélecteurs

Le catalogue désigne un fait par un chemin. Quelques exemples, pour vérifier que le contrat suffit :

| Contrôle | Mécanisme | Sélecteur |
|---|---|---|
| K20 Habilitation de chaque route renseignée | `presence` | `API: routes[].cellules.habilitation` (lignes non barrées) |
| K21 Habilitation au format `ressource:action` | `motif_requis` | `API: routes[].cellules.habilitation.texte` |
| K01 RG citée existe dans la page RG | `reference_resolue` | `*: inclusions[]` dont `statut` ≠ `resolue` et cible du corpus |
| K34 RG du §4 = RG du §5 | `ensembles_egaux` | `SA: traitement.citations[type=RG].code` et `SA: regles[].cellules.regle.inclusions[].nom` |
| K29 codes du §3.2 = codes du §4, des RG du §5 et des SA appelés | `ensembles_egaux` | `SA: codes[].cellules.code.texte` et l'union de `SA: traitement.citations[type=MSG].code`, de `RG: regles[nom ∈ SA: regles[].cellules.regle.inclusions[].nom].corps.citations[type=MSG].code` et des `codes` de chaque SA visé par une arête `appelle` de ces RG ou par un lien du §4 (un niveau, SA du corpus seulement) |
| K61 attribut `R` du DTO = obligatoire du SA | `concordance` (jointure) | `API: dtos[].attributs[].marqueur` et `SA: contrat_entree[].cellules.obligatoire`, joints par `API: mappings[].un_pour_un` puis par nom d'attribut, hors `mappings[].lignes` |
| K22 habilitation route = habilitation CU | `concordance` | arête `appelle` CU → endpoint : `cartouche.habilitation.texte` et `routes[].cellules.habilitation.texte` |
| K55 nom d'extrait bien formé | `motif_requis` | `*: definitions[].nom_brut` et `inclusions[].nom_brut` |
| K58 module du titre = module de l'arborescence | `concordance` | `page.titre` (segment module) et `page.module` |

La table complète K01 → K58 fera partie du catalogue lui-même, pas de ce contrat.

## 10. Points ouverts

1. **Synonymes à compléter** : CU, RG et MCD n'ont été observés que sur SF-NOTE, SF-PORTAIL et SF-DOCUMENT. La première passe du collecteur sur le corpus complet remplira `inconnus[]` : c'est elle qui fixera la configuration v1.
2. **Découpage des étapes du traitement SA** (§5.3) : sur des titres et des paragraphes en gras. À vérifier sur plus de SA que les dix exportés.
3. **ASYNC et JOB** : à ajouter avec leur template (§5.7).
4. **Schéma JSON** (`contracts/faits.schema.json`) : à écrire une fois les noms du §5 validés, à partir de ce document et des faits produits.
5. **`index_croise.schema.json` v1** et **`mcd_sinapse_data.schema.json`** : à retirer quand le collecteur sera en place, ou à marquer remplacés dès maintenant.
6. ~~**Jointure avec les faits du resolver**~~ : fait le 2026-10-22, `resolver.py` 1.4 donne `page_id` et `local_id` en champs.
8. **Sous-objets du contrat d'entrée d'un SA** : ils sont écrits comme une ligne de regroupement (« Habilitations listeHabilitations[] ») suivie de leurs attributs. Le collecteur donne le texte du regroupement dans `groupe` (§3.6), sans en extraire le nom du sous-objet : à faire si K35 ou K61 en ont besoin au calibrage.
7. **Composition CU → endpoint** (§6) : le JSON carto de référence porte 5 arêtes CU → endpoint, de confiance `prose`. Deux visent `PUT /notes/{id}` et `DELETE /notes/{id}`, alors que les liens de la page RG s'affichent `PUT /notes` et `DELETE /notes`, sans `{id}`. La référence a donc été corrigée à la main, ou bien le texte des liens est faux (cas K08 ou K13). À trancher au moment du critère d'acceptation (§7).
