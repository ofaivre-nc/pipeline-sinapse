# Fixtures ADF

ADF bruts figés, extraits du recensement du 4 août 2026 (`recense_adf.py` v1.1, corpus
complet : 246 pages sur 247). Les tests les lisent **sans jamais joindre le réseau**.

Le nom du fichier est l'`id` de la page Confluence. Pour régénérer un ADF à jour :

```
python pipeline/src/recense_adf.py --pages <id> --out <dossier-temporaire>
```

| Fichier | Page | Pourquoi cette page |
|---|---|---|
| `380567556.json` | CU-PORTAIL-ACCUEIL | type **CU** — le cas d'utilisation le plus riche du corpus (24 types de nœuds) |
| `241532980.json` | API-PORTAIL-FAVORIS | type **API** |
| `110067713.json` | JOB-COMPTE-TOIP (version avant API) | type **JOB** |
| `109543425.json` | SF-COMPTE: Modélisation des données (version avant API) | type **MDD** — tableaux à 9 colonnes |
| `180256775.json` | SF-NOTE: Règles de gestion consolidées | type **RG** — cible du resolver multiexcerpt |
| `10485761.json` | Référentiel IHM | type **GENERIQUE** — page de **définition** de multiexcerpts (`MSG-*`, `RG-CHAMPS*`) |
| `28344321.json` | CU-NOTE-CREER | `bodiedSyncBlock` **et** `extension :: nested-table` |
| `28344344.json` | CU-NOTE-MODIFIER | `syncBlock` nu — le second mécanisme de réutilisation de contenu |
| `560201732.json` | 2. Fondation et tokens | `codeBlock` et `status` |

Couverture : 33 des 36 types de nœuds du corpus. Restent non couverts `date`, `emoji` et
`mediaInline` — trois nœuds marginaux (respectivement 1, 7 et 3 pages) à ajouter si le
normalizer les traite spécifiquement.

Les `.md` attendus seront ajoutés à côté de chaque `.json` au moment d'écrire le renderer :
**toute modification du normalizer rejoue ces fixtures.**

## `pages_classification_20260805.json` — corpus de non-régression

Ce fichier n'est pas un ADF : c'est le dump de classification produit par
`inventory.py`, 246 pages avec leurs métadonnées et sans aucun contenu. Il sert de
corpus de non-régression aux sept mesures du §11 de `contracts/slugification.md` —
nombre de pages exportées, collisions, longueurs de `md_path`, profondeur.

**Corpus incomplet, et c'est su.** Il porte 246 pages là où le périmètre en compte
247 : `334888965` (`SF-COORDONNEE: Règles de gestion consolidées`, page **RG**,
v130) a été perdue sur un timeout au recensement du 4 août. Elle est retrouvée,
non collectée.

Le recensement est **à rejouer dans un commit dédié**, où seul le jeu de données
change — jamais en même temps que du code. Il ramènera aussi `180256775` et
`27787265`, modifiées le 5 août. Au rafraîchissement, les sept mesures doivent être
**re-dérivées délibérément** : un écart est attendu, ce n'est pas une régression.
