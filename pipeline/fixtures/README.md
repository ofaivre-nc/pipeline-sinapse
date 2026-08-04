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
