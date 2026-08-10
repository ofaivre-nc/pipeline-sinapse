# Anomalies Confluence à remonter aux BA

Registre des défauts relevés dans le corpus SINAPSE au fil de la construction du
pipeline. **Le pipeline ne les corrige pas** : il les traverse sans casser, et les
consigne. La correction est un geste de rédaction, dans Confluence.

Ce fichier est le seul endroit où cette liste vit. Le §8 du document de référence y
renvoie.

## Règles incluses et jamais définies

Quatre emplacements où un BA voit un blanc à l'écran, sans message ni indice.

| Nom inclus | Défini | Pages consommatrices |
|---|---|---|
| `RG-NOTE-AUTEUR-AUTORISE-CREATION-MODIFICATION` | nulle part | `28344344` CU-NOTE-MODIFIER, `180944899` API-NOTE |
| `RG-NOTE-AUTEUR-AUTORISE--MODIFICATION-SUPPRESSION` | nulle part | `180944899` API-NOTE, `28934145` CU-NOTE-SUPPRIMER |

La seconde porte un **double tiret** : c'est une faute de frappe de
`RG-NOTE-AUTEUR-AUTORISE-MODIFICATION-SUPPRESSION`, seule définition réelle, sur
`180256775`. La première n'a pas de définition approchante — la règle n'a
vraisemblablement jamais été écrite.

Ces deux entrées sont sorties du premier passage de `resolver.py` sur le corpus doré,
en statut `definition_absente`. C'est le mécanisme qui les rend visibles : une macro
non résolue s'affiche vide dans Confluence, sans rien signaler.

## Identifiants de bloc dupliqués

- **`CU-NOTE-TYPENOTE.CREER` (396361729) est une copie de `CU-NOTE-CREER` (28344321)
  qui a hérité de ses identifiants de bloc** — même `resourceId`, même `localId`,
  contenus divergents. Deux specs vivantes prétendent définir le même bloc. Le pipeline
  s'en sort par la clé `(page_id, uuid)`, mais l'édition de l'une des deux réserve des
  surprises.
- **`habilitation` défini deux fois sur `27787265`** — deux `bodiedExtension :: excerpt`
  de même nom, contenu identique à ce jour. Sans effet visible jusqu'au jour où les deux
  divergeront ; ni le plugin ni la macro native ne disent laquelle gagne. Le pipeline
  lève à la construction de l'index.

## Liens et requêtes

- 5 requêtes JQL avec gabarit `{{page.url}}` non substitué — ces tables Jira ne ciblent
  aucune page réelle.
- 3 `blockCard` sans datasource, en fait des liens SharePoint — **sur le corpus complet
  des 246 pages** ; les 9 fixtures du corpus doré n'en contiennent aucun, leurs
  5 `blockCard` portent tous un `datasource`.
- **`380567556` porte un `inlineCard` vers une URL d'édition** —
  `…/pages/edit-v2/380567556#IHM-concernant-la-gestion-du-profil…`, pointant vers la
  page elle-même. Un lien d'édition n'a rien à faire dans une spec.

## Rangement et nommage

- `Règles génériques utilisables pour les recherches` (28803126) rangée sous
  `4. Patterns`, au milieu du sous-arbre Design System, alors que ses quatre sœurs sont
  directement sous la racine.
- Écart module titre/ascendance sur `SF-DOCUMENT` et `ARCHIVE_CU-DOSS-CONSULT` — le
  titre annonce DOSS, l'arbre dit PERSONNE.
- `-NEW- CU-COMPTE-PROFIL.GEST` — préfixe à retirer si c'est la version vivante.
- Spécifications archivées encore rattachées à la racine `Spécifications fonctionnelles`
  (1474581) — leur déplacement hors du périmètre serait le geste propre, l'héritage
  d'exclusion en tient lieu en attendant.

## Écarté

*L'emplacement de `SF-DOSS: Messages système consolidés` sous « 2. Fondation et tokens »
est volontaire — multiexcerpt source à terme. Ce n'est pas une anomalie.*
