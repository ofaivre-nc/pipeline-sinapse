# Slugification et fabrication de `md_path`

Comment le pipeline dérive un nom de fichier d'un titre de page Confluence, et
comment il assemble `md_path`.

**État : règle arrêtée, mesurée sur les 246 pages du recensement du 5 août 2026.**
Zéro collision, `md_path` le plus long à 131 caractères. Consommé par
`pipeline/src/inventory.py` (assemblage de `pages_inventory.json`), par
l'exportateur, et par le normalizer pour les renvois entre pages
(`normalisation_adf.md` §6.3).

**Règle qui domine tout le reste** : le slug est une **clé d'adressage**, pas un
libellé. Le titre exact vit dans `pages_inventory.json` et dans le frontmatter du
`.md` ; rien n'est perdu quand le slug abîme un titre. En revanche, deux pages
qui produisent le même chemin font disparaître une spec du corpus — la perte est
irréversible et muette. Toute la règle est écrite dans cet ordre de priorité :
**unicité et prévisibilité d'abord, lisibilité ensuite.**

---

## 1. Entrée et sortie

L'entrée est le champ `title` de `pages_inventory.json`, **déjà normalisé** par
`inventory.py` : `html.unescape()` puis repli des tirets Unicode
(U+2010–U+2015, U+2212, U+FE58, U+FF0D) vers l'ASCII, décrit dans
`classification_pages.md`.

`slugify()` **ne refait pas cette normalisation** et ne consomme jamais
`title_raw`. Un seul endroit normalise les titres ; le dupliquer garantirait une
divergence le jour où l'un des deux évoluerait.

La sortie est un segment de chemin unique parmi les frères, exploitable sous
Windows, dans une URL relative de lien Markdown et dans un `.bat`, sans
échappement ni encodage.

---

## 2. La règle

```python
KEEP = re.compile(r"[^A-Za-z0-9._-]")
RESERVED = {"CON","PRN","AUX","NUL"} | {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)}
SEGMENT_MAX = 80

def slugify(title: str, page_id: str) -> str:
    s = unicodedata.normalize("NFD", title)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")   # 3. repli des accents
    s = unicodedata.normalize("NFC", s)
    s = KEEP.sub("-", s)                                           # 4. liste blanche
    s = re.sub(r"-{2,}", "-", s).strip("-._ ")                     # 5. compactage et rognage
    if len(s) > SEGMENT_MAX:                                       # 6. plafond
        s = s[:SEGMENT_MAX].rstrip("-._") + "~" + page_id
    if s.split(".")[0].upper() in RESERVED:                        # 7. noms réservés
        s = "_" + s
    return s or f"page-{page_id}"                                  # 8. repli
```

### 3. Repli des accents

`NFD` puis retrait des marques combinantes (`Mn`), puis `NFC`. `Réflexion` →
`Reflexion`.

Motif : Git et les clients de synchronisation ne s'accordent pas sur la forme
Unicode d'un nom de fichier accentué — un dépôt partagé entre Windows et macOS
voit apparaître des fichiers « modifiés » que personne n'a touchés. S'y ajoute
la page de code `cp1252` de `cmd.exe`, qui reste le terrain d'un `.bat` de
lancement (étape 11). Le corpus porte 111 caractères accentués sur 246 titres :
le problème est certain, pas hypothétique.

Effet de bord recherché : deux titres qui ne diffèrent que par un accent —
`Réflexion` et `Reflexion`, coquille éditoriale plausible — produisent le même
slug et **lèvent en collision** au lieu de produire deux fichiers voisins que
personne ne rapprochera jamais.

### 4. Liste blanche `[A-Za-z0-9._-]`, jamais liste noire

Tout le reste devient `-`. Une liste noire des caractères interdits sous Windows
(`<>:"/\|?*`) laisserait passer les parenthèses, l'esperluette, la virgule,
l'apostrophe et l'espace, tous légaux sous Windows et tous nuisibles ailleurs :

| Caractère | Occ. corpus | Pourquoi il ne peut pas rester |
|---|---|---|
| `(` `)` | 16 / 16 | **cassent la syntaxe d'un lien Markdown** `[titre](chemin)` — le rendu des renvois §6.3 exigerait un encodage `%28` que personne ne relira |
| espace | 415 | même raison ; impose `%20` dans les liens et des guillemets partout en ligne de commande |
| `&` | 1 | séparateur de commandes de `cmd.exe` |
| `'` `’` | 3 / 1 | délimiteur de chaîne des shells |
| `,` | 3 | séparateur d'arguments de plusieurs outils Windows |
| `:` | 70 | interdit sous Windows |
| `/` | 2 | interdit sous Windows |

La conséquence à retenir : **un `md_path` produit par cette règle s'écrit tel
quel dans un lien Markdown, sans aucun encodage.** C'est ce qui rend §6.3
applicable.

Une liste blanche a par ailleurs une propriété qu'une liste noire n'aura jamais :
elle couvre d'avance le caractère qu'un rédacteur emploiera pour la première fois
dans six mois.

### 5. Compactage et rognage

Runs de `-` compactés en un seul ; `-`, `.`, `_` et espace retirés en tête et en
queue. Un nom Windows ne peut se terminer ni par un point ni par un espace.
`-NEW- CU-COMPTE-PROFIL.GEST` → `NEW-CU-COMPTE-PROFIL.GEST`.

### 6. Plafond de segment

80 caractères, puis `~{page_id}`. Aucun slug du corpus ne l'atteint — le plus
long fait **77** caractères
(`Referentiel-definissant-les-types-de-donnees-utilises-dans-les-differents-MCD`,
d'un titre de 77). C'est un garde-fou contre un titre pathologique futur,
pas un mécanisme actif : le fixer à 80 garantit **zéro renommage aujourd'hui**,
donc zéro brassage de fichiers sur le SharePoint.

`~` n'appartient pas à la liste blanche : sa seule origine possible est cette
troncature, ce qui rend un slug tronqué reconnaissable à l'œil. L'identifiant est
repris **entier** — un suffixe court ne garantit pas l'unicité.

Le plafond porte sur la **partie dérivée du titre**, pas sur le segment rendu :
celui-ci peut atteindre 80 + 1 + longueur de l'identifiant, soit 90 caractères
pour un identifiant à 9 chiffres. C'est voulu — un identifiant tronqué ne
garantirait plus l'unicité — mais c'est cette valeur, et non 80, qu'il faut
retenir pour le budget de chemin du §11.

### 7. Noms réservés

`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, comparés sur la partie
qui précède le premier point et sans tenir compte de la casse : Windows refuse
`NUL.md` comme `nul`. Aucune occurrence au corpus. Préfixe `_` si le cas se
présente.

---

## 8. Ce que la règle ne fait pas — et pourquoi

**Le point n'est pas touché.** C'était la crainte initiale : réduire `.` en `-`
ferait entrer en collision `CU-NOTE-TYPENOTE.CREER` et `CU-NOTE-TYPENOTE-CREER`.
Or le point est **légal dans un nom de fichier Windows** partout sauf en dernière
position. Il n'y a aucune raison de le réduire, et donc aucune désambiguïsation à
inventer : `CU-NOTE-TYPENOTE.CREER.md` est un nom valide. Le point est
significatif dans la nomenclature SINAPSE — il distingue deux modules
(`SF-COMPTE` et `SF-COMPTE.INTERNET`) et deux entités — le préserver conserve
l'identifiant lisible tel que les BA l'écrivent.

*Conséquence à connaître : un nom de fichier peut porter deux points
(`CU-NOTE-TYPENOTE.CREER.md`). Un outil qui couperait à la première occurrence
pour trouver l'extension se tromperait. `pathlib.Path.suffix` coupe à la
dernière, correctement.*

**La casse est conservée.** `CU-PERSONNE-MODIFIER` reste en capitales : c'est la
forme de l'identifiant SINAPSE, la mettre en minuscules la rendrait
méconnaissable. En contrepartie, **toute détection de collision se fait sur
`casefold()`** — Windows, SharePoint et Git sur Windows sont insensibles à la
casse, deux slugs qui ne diffèrent que par elle désignent le même fichier.

**Le nom n'est pas dérivé de l'identifiant de page.** `120127489.md` réglerait
tout, et annulerait la décision du 5 août de reproduire l'arborescence
Confluence : un BA doit retrouver un fichier sans consulter d'index.

**Le titre n'est pas tronqué à son préfixe d'identifiant.** Réduire
`SF-COMPTE: gestion des comptes utilisateurs` à `SF-COMPTE` a été mesuré :
**7 collisions entre frères** sur le corpus, parce que `SF-COMPTE: Modélisation
des données`, `SF-COMPTE: Règles de gestion consolidées` et `SF-COMPTE: Contrat
OpenAPI` partagent le même préfixe. Piste fermée.

---

## 9. Collisions

Deux pages en collision, c'est un `.md` écrasé et une spec disparue du corpus
sans trace. La détection est donc **exhaustive et systématique**, à la
construction de l'inventaire.

**Périmètre** : chaque page alimente **deux clés dans un seul et même espace de
noms**, sur `slug.casefold()` — `(parent_id, slug)`, parce que son fichier vit
dans le répertoire de sa mère, et `(page_id, slug)`, parce qu'il vit dans son
propre répertoire si elle a des filles. Les deux clés sont posées pour toute
page, sans condition : une page sans fille réserve une entrée que rien ne peut
heurter, le cas est inoffensif et la règle reste uniforme.

Le cas `X/X.md` se détecte alors de lui-même : une fille dont le slug égale
celui de sa mère porte la clé `(id de la mère, slug)`, qui tombe exactement sur
l'entrée que la mère s'est réservée. **Séparer les deux natures de clé en deux
espaces distincts fait disparaître ce cas** — la mère et la fille ne sont plus
jamais comparées — et produit en prime des groupes en double sur les collisions
entre frères.

**Mesure au corpus du 5 août : 0 collision**, tous cas confondus, sur les 246
pages. Il n'existe par ailleurs aucun doublon de titre exact, ni global ni entre
frères : les collisions ne peuvent naître que de la règle elle-même.

**Traitement** — un groupe en collision :

- ne produit **aucun** `.md` ce run ;
- garde son entrée dans `pages`, avec `md_path: null`, `exported: false` et un
  `warnings` nommant les pages concernées ;
- **n'entraîne pas la suppression** des `.md` produits par les runs précédents :
  la phase de nettoyage des orphelins ignore les pages en collision. Sans cette
  précaution, une collision effacerait deux specs au lieu d'en manquer une ;
- figure **en tête du rapport de run**, comme anomalie bloquante à corriger dans
  Confluence.

Le reste du run se poursuit. C'est l'application de la règle « une page en échec
n'interrompt pas le run » : la collision lève au niveau du groupe, pas du run.
Interrompre l'inventaire entier priverait le lendemain d'un delta sur 244 pages
saines à cause de deux titres mal choisis.

*Il n'y a pas de désambiguïsation automatique par suffixe. Elle renommerait
silencieusement des specs — y compris celle qui n'a pas bougé — et laisserait le
corpus dans un état que personne n'a validé. Une collision est une anomalie
éditoriale : elle se corrige dans Confluence.*

---

## 10. Assemblage de `md_path`

`md_path` est relatif à `local_path`. Racine `specs/` pour le groupe A, `docs/`
pour le groupe B.

| Cas | Forme |
|---|---|
| Page ayant au moins une fille **exportée** | `{…ancêtres}/{slug}/{slug}.md` |
| Page sans fille exportée | `{…ancêtres}/{slug}.md` |
| Ancêtre, quel qu'il soit | contribue **un** segment `{slug}/` |

**« Avec filles » signifie « avec au moins une fille exportée ».** Une page dont
toutes les filles sont exclues n'a pas de répertoire : il ne contiendrait que
son propre fichier. Le cas existe — `CU-PERSONNE-CONSULTER` n'a qu'une fille,
archivée.

**Conséquence à signaler au rapport, au même titre que l'arrivée d'une première
fille** : préfixer une fille unique par `Archive` dans Confluence ramène le
`.md` de sa mère de `{slug}/{slug}.md` à `{slug}.md`, alors que la mère n'a pas
bougé. C'est un déplacement, pas une suppression suivie d'une création.

Aucune des sept mesures du §11 ne dépend de ce choix : elles sont identiques
dans les deux lectures. C'est ce qui rend le point dangereux — il ne se signale
nulle part et se recopie tel quel dans l'assembleur.

Les segments d'ancêtres ne sont **jamais** doublés : le doublement ne concerne
que le fichier propre d'une page mère.

```
specs/Q-IDENTITE-gestion-des-identites/
├── Q-IDENTITE-gestion-des-identites.md
└── SF-PERSONNE-gestion-des-personnes/
    ├── SF-PERSONNE-gestion-des-personnes.md
    ├── SF-PERSONNE-Modelisation-des-donnees.md
    └── CU-PERSONNE-MODIFIER.md
```

Les 5 racines de périmètre ne sont pas des pages exportées : elles ne
contribuent aucun segment.

`md_path` est **la référence unique du chemin**. Les skills le lisent dans
`pages_inventory.json` et ne le recalculent jamais.

---

## 11. Longueurs

Mesures sur les 232 pages exportées du corpus du 5 août :

| Mesure | Valeur |
|---|---|
| `md_path` médian | 89 car. |
| `md_path` le plus long | **131 car.** |
| `md_path` le plus long si chaque feuille gagnait une fille | **164 car.** |
| Slug le plus long | **77** car. |
| Profondeur maximale sous `specs/` | 4 niveaux |

Mesures établies sur **246 pages**. Le corpus du 5 août en compte une de moins
que le périmètre réel : `334888965` a été perdue sur un timeout au recensement.
Aucune des sept valeurs n'a été recalculée avec elle.

Le plus long aujourd'hui :

```
specs/Q-ADMINISTRATION/SF-PARAMETRE-gestion-des-parametres-de-l-application/SF-PARAMETRE-gestion-des-parametres-de-l-application.md
```

**Budget pour le préfixe SharePoint** : le plafond Windows est de 260 caractères
pour le chemin complet. Il reste **129 caractères** de préfixe avec le corpus
d'aujourd'hui, **96** si l'on provisionne un niveau d'arborescence
supplémentaire. Un chemin de synchronisation OneDrive courant
(`C:\Users\{compte}\{Organisation}\{Bibliothèque} - Documents\`) consomme 70 à
90 caractères : la marge est réelle mais pas confortable. **Le chemin
SharePoint doit être choisi court, et mesuré avant tout run complet.**

Contrôle à l'exécution, sur le chemin **complet** (`local_path` + `md_path`) —
`md_path` seul ne veut rien dire :

| Seuil | Traitement |
|---|---|
| ≥ 200 car. | avertissement au rapport de run |
| ≥ 250 car. | la page lève, elle n'est pas exportée |

---

## 12. Liens Markdown entre pages — conséquence pour §6.3

`normalisation_adf.md` §6.3 prévoit de rendre un `inlineCard` en
`[{titre}]({md_path})`. **Cette forme est fausse depuis que l'arborescence est
reproduite** : `md_path` est relatif à `local_path`, alors qu'un lien Markdown se
résout relativement au fichier qui le porte.

La cible est `os.path.relpath(md_path_cible, os.path.dirname(md_path_source))`,
avec des séparateurs `/` quelle que soit la plateforme. D'une CU à une autre :

```
[CU-PERSONNE-MODIFIER](../SF-PERSONNE-gestion-des-personnes/CU-PERSONNE-MODIFIER.md)
```

Aucun encodage n'est nécessaire : la liste blanche du §4 garantit que le chemin
ne contient ni espace, ni parenthèse, ni caractère réservé de la syntaxe
Markdown.

---

## 13. Tests attendus

| Cas | Attendu |
|---|---|
| `CU-NOTE-TYPENOTE.CREER` | `CU-NOTE-TYPENOTE.CREER` — point préservé |
| `CU-NOTE-TYPENOTE-CREER` | `CU-NOTE-TYPENOTE-CREER` — distinct du précédent |
| `SF-COMPTE: gestion des comptes utilisateurs` | `SF-COMPTE-gestion-des-comptes-utilisateurs` |
| `Archive CU-COMPTE (version monolithique, sans API)` | `Archive-CU-COMPTE-version-monolithique-sans-API` |
| `IV. Les Assurés Obligatoires Étudiants/Élèves (AOEE)` | `IV.-Les-Assures-Obligatoires-Etudiants-Eleves-AOEE` |
| `Guide d’utilisation du BPMN` | `Guide-d-utilisation-du-BPMN` |
| `-NEW- CU-COMPTE-PROFIL.GEST` | `NEW-CU-COMPTE-PROFIL.GEST` |
| `Bonnes pratiques RGAA 4.1.2 - Guide opérationnel BA & DEV` | `Bonnes-pratiques-RGAA-4.1.2-Guide-operationnel-BA-DEV` |
| `  ` (titre de blancs) | `page-{id}` |
| `NUL` | `_NUL` |
| titre de 120 caractères | tronqué à 80 + `~{page_id}` |
| `Réflexion` et `Reflexion` frères | collision détectée, ni l'une ni l'autre exportée |
| `A` et `a` frères | collision détectée (`casefold`) |
| page mère `X` avec une fille `X` | collision détectée (cas `X/X.md`) |
| corpus complet du 5 août | 232 pages exportées, 0 collision, slug max 77, `md_path` médian 89 et max 131, 164 en forçant le doublement de chaque feuille, profondeur 4 |

Cette dernière ligne est un **test de non-régression sur le dump de
recensement**, pas une note. Les mesures du §11 ne sont vérifiables que par
elle ; sans elle, une évolution de la règle les périme en silence. Le dump est
versionné dans `pipeline/fixtures/` — 143 Ko de métadonnées, sans contenu de
page — et son absence fait **échouer** le test : pointer sur `recensement/`,
non versionné, rendait la vérification verte pour toujours ailleurs que sur le
poste qui l'avait produite.

**Cas choisis et invariants de corpus ne se remplacent pas.** Les premiers
pincent la règle sur des formes que le corpus ne porte pas ; les seconds pincent
tout le corpus sur une propriété. La préservation du point l'illustre : réduire
`.` en `-` ne fait bouger **aucune** des sept mesures, parce qu'aucune paire de
frères ne diffère que par là — seuls les deux cas `CU-NOTE-TYPENOTE.CREER` et
`CU-NOTE-TYPENOTE-CREER` tiennent alors la règle. L'invariant
« un titre et son slug portent le même nombre de points » la tient, lui, sur les
63 titres pointés du corpus.
