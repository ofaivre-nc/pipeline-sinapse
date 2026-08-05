# Contrat de classification des pages

Ce que le pipeline garantit aux skills sur le classement d'une page Confluence.
Implémenté par `pipeline/src/inventory.py` (v1.1, étape 3), verrouillé par
`pipeline/tests/test_inventory.py`.

**Règle de synchronisation** : le bloc de constantes en tête de `inventory.py` et ce
fichier disent la même chose. Modifier l'un sans l'autre est un bug.

> **Précision par rapport au brief v3 §4.1**, qui indique « module et type sont déduits
> du titre » : le **type** l'est toujours, mais le **module** est désormais déduit de
> l'ascendance, le titre ne servant que de repli. Le brief est antérieur au recensement
> du 4 août 2026, qui a montré que des pages de specs réelles ne portent aucun code
> module dans leur titre (`Réflexion Document`, `Briques techniques`).

---

## 1. Normalisation du titre — avant tout filtrage

Aucun motif n'est appliqué au titre brut. `normalize_title()` fait deux choses, dans
cet ordre :

1. **`html.unescape()`** — les noms Confluence sont encodés en entités
   (`&period;`, `&lowbar;`). Sans ce décodage, les identifiants de règles écrits dans
   le `.md` et dans l'index croisé sont faux.
2. **Repli des tirets Unicode sur le tiret ASCII `-`** : U+2010 à U+2015, U+2212,
   U+FE58, U+FF0D.

**NFKC ne suffit pas** et n'est donc pas utilisé : de tout ce jeu, **seul U+FF0D**
atteint le tiret ASCII par NFKC. U+2011 se replie sur U+2010 et U+FE58 sur U+2014 —
c'est-à-dire sur d'autres tirets non-ASCII, ce qui ne règle rien ; U+2010,
U+2012 à U+2015 et U+2212 traversent NFKC inchangés. La table explicite est le seul
moyen fiable.

Le corpus contient un cas réel : `CU‑PERSONNE-RECHERCHER` (`299499522`) sépare `CU` de
`PERSONNE` par un **U+2011** (tiret insécable). Indiscernable à l'œil, il rendait la
page invisible au motif `^CU-` — une spec de cas d'utilisation hors radar de l'index
croisé. C'est aussi l'illustration la plus nette de la limite de NFKC : ce caractère
précis *est* replié par NFKC, mais sur U+2010, et `^CU-` échoue toujours.

---

## 2. Groupe et périmètre

Le groupe vient de l'**ascendance**, jamais du titre : on remonte les `parent_id`
jusqu'à l'une des 5 racines du brief §2.

| Groupe | Racines | Traitement | Type résiduel |
|---|---|---|---|
| **A** — specs | `1474581`, `1277977` | multiexcerpts résolus + index croisé | `REFERENTIEL` ou `A_QUALIFIER` |
| **B** — documentation | `1245499`, `1310723`, `219086849` | export `.md` simple | `DOCUMENTATION` |
| **hors périmètre** | aucune racine connue atteinte | rien : ni export, ni index, ni score | `HORS_PERIMETRE` |

La détection de cycle interrompt la remontée sur un parent déjà vu, au lieu de boucler.

**Aucun type résiduel n'est partagé entre deux groupes.** Un type `AUTRE` commun aux
deux ferait passer un résidu de specs pour de la documentation libre, c'est-à-dire pour
une situation normale — alors qu'une spec non classée est une anomalie. La distinction
se fait par **ascendance**, jamais par motif de titre :

| Type résiduel | Condition | Statut |
|---|---|---|
| `REFERENTIEL` | groupe A, racine A2 `1277977`, hors sous-arbre UX | assumé — règles transverses |
| `A_QUALIFIER` | groupe A, racine A1 `1474581` | **anomalie à résorber** |
| `DOCUMENTATION` | groupe B | normal |
| `HORS_PERIMETRE` | aucune racine connue | rien produit |

Une racine du groupe A qui serait ajoutée sans entrée dans `RESIDUAL_TYPE_BY_ROOT`
tombe en `A_QUALIFIER` **avec un avertissement** : le défaut est bruyant, pas silencieux.

**Une page non classifiable reste dans l'inventaire.** Le brief v3 prévoyait un bac
`unclassified` qui la sortait de la liste des pages ; c'est désormais le type
`A_QUALIFIER` qui joue ce rôle, **sans la sortir**. La raison est le delta : `pages` est
la base de la comparaison par `version.number`, et une page qui en disparaît est
indistinguable d'une page supprimée — son `.md` serait effacé, puis recréé au run suivant.
`unclassified` est réduit aux pages dont les métadonnées sont inexploitables (titre
absent, ascendance rompue), les seules qu'on ne sait même pas suivre. Voir
`contracts/pages_inventory.schema.json`.

**Une page du groupe B ne reçoit jamais un type de spec.** Le type suggéré par son titre
est conservé comme fait, en avertissement au rapport, mais il n'est pas appliqué. Cas
réel : `VII. Règles de gestion` (`306839565`) est un chapitre du guide CAFAT, sous la
racine B `1245499`. La typer `RG` la ferait scorer comme une page de règles de gestion
consolidées et produirait un rapport entièrement faux.

---

## 3. Types de pages

### Ordre de test — il est porteur de sens

`TYPE_PATTERNS` est une séquence, pas un dictionnaire. Deux précédences sont imposées
par le corpus réel ; les inverser casse la classification en silence.

| # | Type | Motif | Ancré |
|---|---|---|---|
| 1 | `CU` | `^CU-` | oui |
| 2 | `API` | `^API-` | oui |
| 3 | `JOB` | `^(JOB\|BATCH)-` | oui |
| 4 | `SA` | `^SA-` | oui |
| 5 | `MDD` | `modélisation des données` | non |
| 6 | `RG` | `règles de gestion` | non |
| 7 | `DOMAINE` | `^Q-` | oui |
| 8 | `MODULE` | `^SF-` | oui |
| 9 | `GENERIQUE` | `générique\|référentiel` | non |
| 10 | `UX` | *aucun motif de titre* — appartenance à un sous-arbre | — |
| 11 | résiduel | *aucun motif* — par ascendance, voir §2 | — |

**Précédence 1 — MDD et RG passent avant `^SF-`.** Les 27 pages de modélisation et de
règles du corpus s'appellent toutes `SF-XXX: Modélisation des données` ou
`SF-XXX: Règles de gestion consolidées`. Tester `^SF-` d'abord les reclasserait en
`MODULE` et leur retirerait l'attribut `scored` — 27 specs sorties du champ des skills
de validation, sans aucune erreur levée.

**Précédence 2 — `^Q-` passe avant `GENERIQUE`.** `Q-REFERENTIEL` contient le mot
« référentiel » : sans cette précédence, une page de domaine est classée comme
référentiel générique.

**Les préfixes restent ancrés en début de titre.** Les désancrer ferait matcher un
titre comme « Liste des CU-PERSONNE à reprendre ». Les titres masqués par un préfixe
parasite sont traités par les exclusions (§5), qui retirent le préfixe avant le typage.

### `UX` — par sous-arbre, pas par titre

Les pages du référentiel de conception n'ont aucun code dans leur titre (`4. Patterns`,
`Modale de confirmation`, `Sous-patterns`). Elles sont reconnues par leur ascendance :
`UX_SUBTREE_ROOTS = ("519897125",)` — la page « Design System portail agent » et sa
descendance. **La page racine du sous-arbre en fait partie** : elle est `UX`, pas
`REFERENTIEL`.

Le reste de la racine A2 — `Urbanisation du SI`, `Guide d'utilisation du BPMN`,
`Organisation des menus de l'application`, `Bonnes pratiques RGAA 4.1.2` — n'est pas de
l'UX au sens strict et tombe en `REFERENTIEL` : des règles transverses assumées, pas un
résidu à qualifier.

Un motif de titre l'emporte toujours sur l'appartenance au sous-arbre : les 5 pages
`GENERIQUE` situées sous `1277977` restent `GENERIQUE`, et `SF-DOSS: Messages système
consolidés` reste `MODULE`.

### Types réservés, non implémentés

`DOC-*` et `TAB-*` sont **réservés** : aucune page du corpus ne les porte au 5 août
2026. Aucun motif ne leur est associé dans le code, volontairement — un motif pour un
type inexistant est un faux positif silencieux qui attend son heure. `TYPES_RESERVES`
les déclare pour mémoire, et un test vérifie qu'ils restent absents de
`TYPE_PATTERNS`. Le jour où une page `DOC-…` ou `TAB-…` apparaît : ajouter le motif ici
et dans le code, et décider de ses trois attributs.

---

## 4. Trois attributs indépendants

Un seul axe ne suffisait pas : une page chapeau de module doit sortir en `.md` pour la
navigation, sans être soumise aux skills de validation qui n'y trouveraient aucune
règle. Chaque page porte donc trois booléens indépendants.

| Attribut | Signification |
|---|---|
| `exported` | la page part en `.md` dans `specs/` (groupe A) ou `docs/` (groupe B) |
| `content_source` | son ADF est parsé et indexable comme source de multiexcerpt ou de `syncBlock` |
| `scored` | elle est soumise aux skills de validation |

| Type | `exported` | `content_source` | `scored` |
|---|---|---|---|
| `CU`, `RG`, `MDD`, `API`, `JOB` | oui | oui | oui |
| `UX`, `GENERIQUE`, `SA`, `MODULE`, `DOMAINE`, `REFERENTIEL`, `A_QUALIFIER` | oui | oui | non |
| `DOCUMENTATION` (groupe B) | oui | non | non |
| `HORS_PERIMETRE` | non | non | non |

**Règle de groupe qui l'emporte sur le type : toute page du groupe A est
`content_source`.** Une définition de multiexcerpt ou de `syncBlock` peut vivre
n'importe où dans l'arbre des specs — sur une page chapeau de module, sur un
référentiel, sur une page encore à qualifier. Un faux négatif ici ne produit pas une
erreur : il casse une inclusion en silence. La règle est donc réappliquée en fin de
`classify_page()`, après le calcul par type, pour qu'un type ajouté plus tard ne puisse
pas y échapper par distraction. Un test la verrouille type par type.

Le groupe B reste hors de cette règle : `DOCUMENTATION` n'est pas `content_source`. Si
un multiexcerpt était un jour inclus depuis une page de documentation, le resolver doit
remonter l'inclusion en erreur au rapport — « inclusion non résolue », jamais en
silence.

`SA` n'est pas scoré : le préfixe a été découvert le 5 août 2026 (3 pages), la structure
attendue d'une page de service applicatif n'est pas encore décrite, donc aucun skill ne
sait la scorer. À revoir quand cette structure sera arrêtée.

`A_QUALIFIER` n'est pas scoré non plus, et c'est précisément le danger : une spec qui
atterrirait là serait invisible aux skills de validation. D'où le compteur en tête du
rapport de run, présenté comme une anomalie à résorber et non comme une statistique.

---

## 5. Exclusions

Deux mécanismes, tous deux lus dans `config.ini`, section `[confluence]` :

| Clé | Effet |
|---|---|
| `exclude_page_ids` | exclusion nominative, par identifiant |
| `exclude_title_prefixes` | exclusion par préfixe de titre |

Défauts du code si la clé est vide (`DEFAULT_EXCLUDE_TITLE_PREFIXES`) :
`Archive`, `ARCHIVE_`, `Copie de`, `-NEW-`, `DRAFT`. Une valeur renseignée **remplace**
la liste par défaut, elle ne s'y ajoute pas.

`DRAFT` a été vérifié sur le corpus avant d'être ajouté : une seule page commence par ce
mot (`DRAFT SF-NOTE: Modélisation des données (MLD)`, `432144387`), et aucune page
légitime ne commence par `Draft`, `Brouillon`, `WIP` ni `TODO`. Le préfixe n'écarte donc
aujourd'hui aucune spec vivante.

**Ancrage en début de titre uniquement.** La comparaison est insensible à la casse et
se fait sur le titre normalisé. Une exclusion par sous-chaîne écarterait
`CU-DOSSIER-ARCHIVER`, qui est une spec parfaitement valide — c'est le cas de test qui
verrouille la règle. Quand plusieurs préfixes correspondent, le plus long est reporté
comme motif (`ARCHIVE_` plutôt que `Archive`).

**Une page exclue reste dans l'inventaire, avec son motif.** Elle n'est ni exportée ni
scorée. En revanche **`content_source` est conservé** : un multiexcerpt inclus depuis
une page archivée doit encore pouvoir être résolu, et la clé de résolution étant le
couple (page, nom), une définition archivée n'entre jamais en collision avec sa version
vivante.

Le préfixe est retiré avant le typage : `Archive CU-COMPTE (...)` est un `CU` exclu, pas
une page de type inconnu. L'information « c'est un cas d'utilisation » reste disponible
au rapport.

### L'exclusion est héritée par tout le sous-arbre

Une page dont un ancêtre est exclu par préfixe de titre est elle-même exclue, **quel que
soit son propre titre** — même logique d'héritage que le groupe A/B et le sous-arbre UX.
Une page rangée sous une page archivée appartient à l'archive.

Le motif **nomme la page ancêtre responsable**, pas seulement le préfixe :

```
héritée de « Archive CU-COMPTE (version monolithique, sans API) » (109281281), préfixe « Archive »
```

Deux champs le rendent exploitable sans analyser la chaîne : `exclusion_source_id`
(la page responsable — elle-même ou l'ancêtre) et `exclusion_inherited` (booléen).

Les descendants exclus **conservent `content_source`**, comme les pages exclues
directement, et conservent leur propre type : un descendant de l'archive reste un `CU`
ou un `API`, simplement ni exporté ni scoré.

**Seule l'exclusion par préfixe de titre est héritée.** `exclude_page_ids` reste
nominative : c'est un scalpel pour une page précise, pas un marqueur de branche. Exclure
un chapeau de module par son identifiant ne doit pas faire disparaître le module entier.

L'héritage n'est pas un cas d'école : la page `Archive CU-COMPTE (version monolithique,
sans API)` (`109281281`) porte **9 descendants**, dont 8 étaient exportés et scorés comme
des specs vivantes sur la seule lecture de leur titre.

> **Point ouvert — une page vraisemblablement mal rangée.**
> `API-COMPTE-USER.REINIT.PSW` (`110231568`) est le seul membre de la famille
> `API-COMPTE-*` rangé sous la page d'archive ; ses 8 sœurs sont directement sous
> `SF-COMPTE: gestion des comptes utilisateurs`, et son titre ne porte aucun marqueur
> d'obsolescence. L'héritage l'exclut donc, et le corpus n'en contient aucune autre
> copie. Deux issues : la déplacer dans Confluence — la voie propre — ou constater
> qu'elle est bien obsolète. À vérifier avant le premier run de production.

---

## 6. Module

**Ascendance d'abord, titre à défaut.**

1. On remonte les ancêtres du plus proche au plus lointain ; le premier dont le titre
   normalisé commence par `SF-<CODE>` donne le module. `module_source = "ascendance"`.
2. À défaut seulement, le titre de la page elle-même : préfixe `SF-<CODE>`, sinon 2ᵉ
   segment d'un titre de spec. `module_source = "titre"`.
3. Sinon `module = null` — cas normal pour une page `DOMAINE` ou `UX`.

L'ascendance est prioritaire parce qu'elle rattache correctement les pages dont le titre
ne porte aucun code : `Réflexion` → `COMPTE`, `Réflexion Document` → `DOCUMENT`.

**Extraction du code**, deux règles distinctes :

- préfixe `SF-` : le point est **conservé**. `SF-COMPTE` et `SF-COMPTE.INTERNET` sont
  deux modules distincts, chacun avec sa propre page de modélisation ; de même
  `SF-DROIT.ASSURE` et `SF-DROIT.RETRAITE`.
- titre de spec : 2ᵉ segment, **coupé au premier point**.
  `CU-PERSONNE-PP.CREER` → `PERSONNE`, `CU-TRACE.RECHERCHER` → `TRACE`.

**Désaccord entre ascendance et titre → avertissement**, jamais un choix silencieux.
L'ascendance gagne, et le rapport signale l'écart. Cas réel :
`ARCHIVE_CU-DOSS-CONSULT` (`360054830`) est rangée sous `CU-PERSONNE-CONSULTER`, donc
sous le module `PERSONNE`, alors que son titre annonce `DOSS` — page mal rangée, à
vérifier dans Confluence.

---

## 7. Enregistrement produit par page

```json
{
  "id": "299499522", "title": "CU-PERSONNE-RECHERCHER",
  "title_raw": "CU‑PERSONNE-RECHERCHER",
  "version": 4, "parent_id": "12484666",
  "parent_title": "SF-PERSONNE: gestion des personnes",
  "group": "A", "root_id": "1474581",
  "type": "CU", "module": "PERSONNE", "module_source": "ascendance",
  "excluded": false, "exclusion_reason": null,
  "exclusion_source_id": null, "exclusion_inherited": false,
  "warnings": [],
  "exported": true, "content_source": true, "scored": true
}
```

`title` est toujours le titre **normalisé**. `title_raw` n'est renseigné que si la
normalisation a changé quelque chose — c'est la trace qui permet de retrouver la page
dans Confluence, où le titre brut reste affiché.

---

## 8. État au 5 août 2026

Sur les 246 pages du recensement du 4 août :

| Type | Pages | | Attribut | Pages |
|---|---|---|---|---|
| `CU` | 59 | | **exportées** | 232 |
| `DOCUMENTATION` | 50 | | **sources de contenu** | 196 |
| `MODULE` | 38 | | **scorées** | 101 |
| `API` | 23 | | **exclues** | 14 |
| `MDD` | 20 | | *dont par héritage* | 9 |
| `DOMAINE` | 12 | | | |
| `UX` | 12 | | | |
| `A_QUALIFIER` | **7** | | | |
| `RG` | 7 | | | |
| `JOB` | 6 | | | |
| `GENERIQUE` | 5 | | | |
| `REFERENTIEL` | 4 | | | |
| `SA` | 3 | | | |

Aucune page hors périmètre : les 246 chaînes d'ascendance aboutissent toutes à l'une des
5 racines.

Les 7 pages `A_QUALIFIER` sont des notes de cadrage et des réflexions
(`Briques techniques`, `Questionnement AD CAFAT`, `Réflexion`, `Réflexion Document`,
`EDIT: édition des documents`, `Informatisation du module SF-TRACE`, `Réforme retraites
2027`). Elles ne relèvent d'aucun motif mécanique : à qualifier une par une, puis à
faire disparaître de ce compteur.

### Sort des trois doublons obsolètes connus

Tous les trois sont désormais exclus, par deux mécanismes distincts :

| Page | Mécanisme |
|---|---|
| `SF-COMPTE: Modélisation des données (version avant API)` (`109543425`) | **héritage** — descendante de `Archive CU-COMPTE` |
| `JOB-COMPTE-TOIP (version avant API)` (`110067713`) | **héritage** — même ancêtre |
| `DRAFT SF-NOTE: Modélisation des données (MLD)` (`432144387`) | **préfixe `DRAFT`** |

Le suffixe `(version avant API)` n'a donc pas eu besoin d'être traité : les deux pages
qui le portent vivent sous la page d'archive, et l'héritage suffit. `exclude_page_ids`
reste vide.

### `-NEW-` : aucune jumelle sans préfixe

Une seule page porte ce préfixe, `-NEW- CU-COMPTE-PROFIL.GEST` (`354353153`), et
**aucune page du corpus ne s'appelle `CU-COMPTE-PROFIL.GEST`**. La seule variante est
`CU-COMPTE-PROFIL.GEST (version avant API)` (`109772801`), elle-même exclue par héritage
sous la page d'archive.

> **Conséquence à trancher.** Les deux seules copies de cette spec sont exclues : la
> nouvelle par son préfixe `-NEW-`, l'ancienne par héritage. `CU-COMPTE-PROFIL.GEST`
> disparaît donc entièrement du corpus exporté et scoré. Si `-NEW-` signale « nouvelle
> version en cours » plutôt que « brouillon jetable », c'est la page à conserver — et le
> préfixe `-NEW-` est alors à retirer de `exclude_title_prefixes`, ou le titre à
> nettoyer dans Confluence.

**Ce que l'étape 3 ne couvre pas encore** : la slugification des titres avec détection
de collision, et le delta par `version.number`. `inventory.py` v1.0 ne produit donc pas
encore `md_path` ni `last_exported`.
