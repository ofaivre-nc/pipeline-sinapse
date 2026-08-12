# Anomalies Confluence à remonter aux BA

Registre des défauts relevés dans le corpus SINAPSE au fil de la construction du
pipeline. **Le pipeline ne les corrige pas** : il les traverse sans casser, et les
consigne. La correction est un geste de rédaction, dans Confluence.

Ce fichier est le seul endroit où cette liste vit. Le §8 du document de référence y
renvoie.

## Règles incluses et jamais définies

Un nom inclus dont la définition n'existe nulle part. Le BA voit un blanc à l'écran, sans
message ni indice.

| Nom inclus | Défini | Pages consommatrices | État |
|---|---|---|---|
| `RG-NOTE-AUTEUR-AUTORISE-CREATION-MODIFICATION` | nulle part | `28344344` CU-NOTE-MODIFIER, `180944899` API-NOTE | **corrigée par le BA** |
| `RG-NOTE-AUTEUR-AUTORISE--MODIFICATION-SUPPRESSION` | nulle part | `180944899` API-NOTE, `28934145` CU-NOTE-SUPPRIMER | ouverte |
| `IHM_module` | nulle part | `5046303` CU-COMPTE-UTILISATEUR.GERER (2 inclusions) | ouverte |
| `MSG-DOSS.CHA-026` | nulle part | `360054830` ARCHIVE_CU-DOSS-CONSULT | ouverte |

Les fixtures étant figées au 4 août, une anomalie corrigée depuis continue d'apparaître
dans les mesures prises sur elles. C'est attendu, et ce n'est pas une régression.

`MSG-DOSS.CHA-026` est introuvable sur `279019522`, qui porte pourtant `CHA-008`, `009`,
`027`, `029` et `099` : voir les définitions en double ci-dessous, même cause probable.

La seconde porte un **double tiret** : c'est une faute de frappe de
`RG-NOTE-AUTEUR-AUTORISE-MODIFICATION-SUPPRESSION`, seule définition réelle, sur
`180256775`. La première n'a pas de définition approchante — la règle n'a
vraisemblablement jamais été écrite.

Les deux premières entrées sont sorties du premier passage de `resolver.py` sur le corpus
doré, en statut `definition_absente` ; les deux suivantes d'une mesure du 11 août sur les
248 fixtures du recensement. C'est le même mécanisme qui les rend visibles : une macro non
résolue s'affiche vide dans Confluence, sans rien signaler.

**Aucune des deux dernières n'est dans le périmètre d'export** — `IHM_module` vit sur une
page exclue, `MSG-DOSS.CHA-026` sur une page en `ARCHIVE_`. Elles restent au registre : une
page exclue aujourd'hui peut être réintégrée, et l'anomalie l'attendrait.

## Identifiants de bloc dupliqués

- **`CU-NOTE-TYPENOTE.CREER` (396361729) est une copie de `CU-NOTE-CREER` (28344321)
  qui a hérité de ses identifiants de bloc** — même `resourceId`, même `localId`,
  contenus divergents. Deux specs vivantes prétendent définir le même bloc. Le pipeline
  s'en sort par la clé `(page_id, uuid)`, mais l'édition de l'une des deux réserve des
  surprises.

## Définitions en double sur une même page

Un même nom défini deux fois sur la même page. La clé de résolution étant `(page, nom)`,
elle devient ambiguë : aucune inclusion qui la demande ne se résout, et le fait remonte au
rapport de run. **Le pipeline ne choisit pas** entre les deux corps.

- **`habilitation` sur `27787265`** — deux `bodiedExtension :: excerpt` de même nom,
  contenu identique à ce jour. Sans effet visible jusqu'au jour où les deux divergeront ;
  ni le plugin ni la macro native ne disent laquelle gagne.
- **`MSG-DOSS.RECH-031` sur `279019522`** (SF-DOSS: Messages système consolidés) — défini
  deux fois, et aucun des deux corps ne correspond à ce nom : l'un porte le message
  `RECH-004` (« XX dossiers trouvés… »), l'autre le `RECH-005` (« Veuillez renseigner au
  moins un critère de recherche »). Copier-coller où le paramètre `name` de la macro n'a
  pas été mis à jour.
- **`RG-COORDONNEE-ADRESSE.CONTROLE-BP` sur `334888965`** (SF-COORDONNEE: Règles de
  gestion consolidées) — défini deux fois avec **deux règles distinctes** : « Contrôle du
  champ Boîte postale » et « Contrôle de cohérence d'une BP sur une adresse NC ». Les deux
  sont légitimes : c'est un nom à départager, pas une définition à supprimer.

## Liens et requêtes

- 5 requêtes JQL avec gabarit `{{page.url}}` non substitué — ces tables Jira ne ciblent
  aucune page réelle.
- 3 `blockCard` sans datasource, en fait des liens SharePoint — **sur le corpus complet
  des 246 pages** ; les 9 fixtures du corpus doré n'en contiennent aucun, leurs
  5 `blockCard` portent tous un `datasource`.
- **`380567556` porte un `inlineCard` vers une URL d'édition** —
  `…/pages/edit-v2/380567556#IHM-concernant-la-gestion-du-profil…`, pointant vers la
  page elle-même. Un lien d'édition n'a rien à faire dans une spec.
- **Deux inclusions visent `SINAPSE:CU-COMPTE-USER.GEST`** — sur `417267729`
  API-DOCUMENT-DOCUMENT et `555483185` SA-PERSONNE-EVENEMENT.CREER. Le paramètre `page`
  porte un préfixe d'espace, reste du wiki markup où la source s'écrivait `spaceKey:Titre`.
  La référence est **doublement cassée** : même sans le préfixe, `CU-COMPTE-USER.GEST` n'a
  plus ce titre — la page vivante s'appelle `CU-COMPTE-USER.GEST (version avant API)`.
  Elle ne se résoudra pas au run complet. À corriger dans les deux pages consommatrices.
- **Une inclusion vise « Nom de page de test multiexcerpt v2 »**, page de test hors
  périmètre — reste d'essai à retirer.

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
