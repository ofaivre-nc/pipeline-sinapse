# Contrat de frontmatter des `.md` exportés

Ce que tout `.md` produit par le pipeline garantit à un skill qui le lit.
Reprend le §4.5 du brief v3, archivé.

**Un seul chemin de lecture pour les skills : les `.md` locaux, jamais Confluence.**

---

## 1. Le bloc YAML

Frontmatter YAML **visible**, en tête de fichier, délimité par `---`.

```yaml
---
page_id: "329318407"
page_title: "CU-PERSONNE-MODIFIER"
page_url: "https://sinapse-gie-nc.atlassian.net/wiki/spaces/SINAPSE/pages/329318407"
confluence_version: 47
version_date: "2026-06-15T10:22:00Z"
exported_at: "2026-08-02T07:03:12Z"
pipeline_version: "1.0"
schema_version: 1
module: "PERSONNE"
type: "CU"
parse_status: "ok"
jira_test_key: "REC-95"
jira_jql: "id in linkedIssues(REC-95,\"réfère\") or \"Specs[URL Field]\" = \"...\""
---
```

| Champ | Type | Obligatoire | Rôle |
|---|---|---|---|
| `page_id` | chaîne de chiffres | oui | identifiant Confluence, **toujours entre guillemets** — un identifiant n'est pas un nombre sur lequel on calcule |
| `page_title` | chaîne | oui | titre **normalisé** (voir §2) |
| `page_url` | chaîne | oui | permet de remonter à la source depuis un compte-rendu |
| `confluence_version` | entier | oui | `version.number`, seule base du delta |
| `version_date` | date ISO 8601 | oui | date de la version Confluence, **jamais** utilisée pour le delta |
| `exported_at` | date ISO 8601 | oui | horodatage de l'export — voir §3 |
| `pipeline_version` | chaîne | oui | version du pipeline producteur |
| `schema_version` | entier | oui | version de ce contrat ; un skill qui lit une autre valeur s'arrête au lieu de deviner |
| `module` | chaîne ou `null` | oui | code module sans préfixe `SF-` ; `null` est normal pour un `DOMAINE` ou une page `UX` |
| `type` | chaîne | oui | l'une des 14 valeurs de `contracts/pages_inventory.schema.json` |
| `parse_status` | `ok` / `partial` / `failed` | oui | voir §4 |
| `title_raw` | chaîne | si applicable | titre brut, **uniquement** si la normalisation l'a modifié |
| `jira_test_key` | chaîne ou `null` | non | clé du ticket d'ancrage, relevée dans le JQL |
| `jira_jql` | chaîne ou `null` | non | requête JQL remise en clair |

Le pipeline **n'appelle pas Jira** : `jira_test_key` et `jira_jql` sont extraits de la page, jamais interrogés. Les données Jira sont plus volatiles que les specs et n'ont pas leur place dans une page de spec ; les appels restent dans le skill `confluence-outil-lien-jira`, au moment de la validation.

## 2. Titre normalisé

`page_title` porte le titre après `html.unescape()` et repli des tirets Unicode vers l'ASCII — la même normalisation que l'inventaire, décrite dans `contracts/classification_pages.md` §1. Un skill qui recompose un identifiant de règle depuis le titre obtient donc la même forme que celle de l'index croisé.

Quand le titre brut différait, `title_raw` le conserve : c'est la seule trace permettant de retrouver la page dans Confluence, où le titre brut reste affiché.

## 3. `exported_at` est affiché par tous les skills

**Règle transverse à inscrire dans chaque `SKILL.md`** : `exported_at` figure en tête de **tous** les comptes-rendus de skills. C'est ce qui permet à un BA de voir qu'il travaille sur un export de la veille — ou d'il y a trois semaines si le run planifié est tombé.

Chaque skill affiche également sa propre version (`Skill : nom-du-skill vX.Y`), pour repérer un décalage avec l'espace GIE de claude.ai.

## 4. `parse_status` est obligatoire

Jamais absent, sur aucune page.

Sans lui, un skill lisant `regles: []` ne peut pas distinguer « aucune règle » de « le parser a échoué », et produit un rapport entièrement faux.

**Règle imposée aux skills : une page en `parse_status ≠ ok` n'est pas scorée, elle est signalée.**

Un nœud `nested-table` ne déclasse **pas** la page en `partial` : son contenu est intégralement récupérable via `parameters.adf`. Voir `contracts/normalisation_adf.md` §2.

---

## 5. Contenu réutilisé, marqué visiblement

Une inclusion résolue n'est jamais fondue dans le texte : le lecteur doit voir que le contenu vient d'ailleurs, et le skill doit pouvoir le rattacher à sa source.

```markdown
> 📎 *Multiexcerpt **RG-PERSONNE-CARACTERES.AUTORISES** — source : [SF-PERSONNE: Règles de gestion consolidées](https://.../265453570)*

Les caractères autorisés sont : ...

> *(fin multiexcerpt RG-PERSONNE-CARACTERES.AUTORISES)*
```

Le nom affiché est le nom **nettoyé** (`html.unescape()` puis `.strip()`), pas la forme brute : c'est celui sur lequel la jointure a été faite, donc celui que le skill retrouvera dans `reused_content_cache.json`.

Deux mécanismes, donc deux marquages — le lecteur doit pouvoir distinguer la nature de la source, et sa clé :

| Mécanisme | Désignation de la source dans le marquage |
|---|---|
| multiexcerpt | nom + **titre** de la page source |
| syncBlock | **identifiant** de la page source + UUID du bloc |

Une inclusion **inline** se substitue dans un paragraphe : elle ne peut pas être encadrée par des blocs `>`. Le marquage inline reste à arrêter — voir §7.

## 6. Macros Jira remises en clair

Les trois formes du corpus (`extension :: jira`, `blockCard` à table JQL, `inlineCard` vers `/browse/REC-xxx`) sont rendues en clair dans le `.md`, avec leur clé de test et leur JQL. Aucun appel réseau.

---

---

## 7. Emplacement du fichier — le frontmatter ne le porte pas

Les `.md` reproduisent **la hiérarchie Confluence** sous `specs/` (groupe A) et `docs/`
(groupe B) : une page avec filles vit dans `{slug}/{slug}.md` aux côtés de ses filles,
une page sans fille donne un simple `{slug}.md`. Décision et justification dans
`docs/reference-pipeline-sinapse.md` §5.

**Le frontmatter ne contient pas `md_path`, volontairement.** Un chemin recopié dans le
fichier qu'il désigne devient faux au premier déplacement, sans que rien ne le signale —
et les déplacements sont attendus : l'ajout d'une première fille à une page déplace son
`.md` alors que son contenu n'a pas changé.

**La référence unique du chemin est `md_path` dans `pages_inventory.json`.** Un skill le
lit depuis le cache. Il ne le recalcule jamais depuis `page_title`, et ne déduit jamais
le chemin d'une page voisine du sien : la profondeur et le slug du parent ne sont pas
dans le titre.

Ce que le frontmatter porte, et qui suffit à tout rattachement : `page_id`, stable au
renommage comme au déplacement.

---

## 8. Ce qui reste à arrêter

- **le marquage d'une inclusion inline**, qui ne peut pas utiliser la forme en bloc ci-dessus ;
- la forme exacte du marquage `syncBlock`, aucune page n'ayant encore été exportée ;
- la **slugification** elle-même : les titres contiennent des caractères interdits sous Windows (`SF-PERSONNE: …`). Slugification obligatoire, collisions détectées et signalées. La *forme* de l'arborescence est tranchée, le *gabarit du slug* ne l'est pas.

**État d'implémentation au 5 août 2026** : aucun `.md` n'a encore été produit. Ce contrat est écrit avant l'étape 1 (export d'une page CU) pour que le premier export s'y conforme au lieu de le définir par accident.
