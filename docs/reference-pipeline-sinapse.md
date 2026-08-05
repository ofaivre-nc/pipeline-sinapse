# Pipeline SINAPSE — document de référence

*Document unique de la conversation de conception. Remplace `brief-pipeline-sinapse-v3.md` et `reprise-contexte-sinapse.md`, tous deux archivés.*
*Mis à jour le 5 août 2026.*

---

## 0. Comment lire ce document, et où vit le reste

Ce document porte **ce qui a été décidé et pourquoi**. Il n'est vérifiable contre aucun fichier : si son contenu se perd, il se perd définitivement et les arbitrages sont à refaire.

Le détail technique — **ce qui existe** — vit dans le dépôt, maintenu par Claude Code et vérifiable contre le code :

| Fichier du dépôt | Contenu |
|---|---|
| `CLAUDE.md` | organisation du code, instructions de session |
| `.claude/rules/python.md` | règles de robustesse du run |
| `contracts/normalisation_adf.md` | table de normalisation ADF |
| `contracts/classification_pages.md` | règles de classification des pages |
| `contracts/*.schema.json` | schémas des caches JSON |
| `contracts/frontmatter.md` | métadonnées des `.md` exportés |

**Règle** : si ce document et le dépôt divergent sur un fait technique, le dépôt a raison. S'ils divergent sur une décision ou sa justification, ce document a raison.

À joindre à une nouvelle conversation : ce document, plus `guide_implementation_skills_sinapse_v4.md` (cartographie des 31 skills, février 2026, partiellement périmé) et les `contracts/` concernés par le sujet.

### Message d'amorçage suggéré

> Je construis un pipeline Python qui exporte les pages Confluence SINAPSE en `.md` + caches JSON, pour que mes skills Claude de validation de specs travaillent sur des fichiers locaux au lieu d'interroger Confluence à chaque session.
>
> Le document de référence joint décrit le projet, l'état d'avancement et les décisions prises : lis-le en premier. Le développement se fait en **Claude Code** sur mon PC ; toi, tu es mon interlocuteur de conception — tu m'aides à arbitrer, à rédiger les instructions à donner à Claude Code, et à relire ce qu'il produit. Tu n'as accès ni à Confluence ni à ma machine.
>
> Je débute sur Claude Code et sur Git : explique-moi ce que je fais quand ce n'est pas évident.

---

## 1. Pourquoi ce pipeline

### Les quatre phases

- **Phase 1 — prompts ad hoc** : aucune persistance.
- **Phase 2 — skills monolithiques** : séquencement non garanti, la résolution multiexcerpt pouvait être sautée. **C'est la cause racine des résultats aléatoires.**
- **Phase 3 — script + appels API Claude externes** : séquencement fiable, mais la mémoire de conversation devait être réimplémentée (mémoire JSON, `config_loader.py`). Abandonnée pour cette raison.
- **Phase 4 (actuelle)** — skills unitaires + orchestrateur. Python pour le déterministe, Claude en conversation pour le sémantique.

Le pipeline étend la Phase 4 : le fetch Confluence passe par l'API REST directe parce qu'il tourne hors session Claude. **Aucun LLM dans le pipeline** — donc aucun retour à la mécanique de la Phase 3.

### Le problème résolu

Les pages SINAPSE réutilisent du contenu : une règle définie une fois sur une page source est incluse ailleurs. L'API Confluence retourne ces inclusions vides en markdown. Le skill `confluence-outil-resolve-multiexcerpt` résout le problème en session, mais le résultat est local et éphémère : chaque BA, chaque conversation, doit recommencer.

### La solution cible

Un script Python autonome, planifié quotidiennement à 7h, qui établit l'inventaire des pages et détecte les changements, résout le contenu réutilisé, normalise les nœuds ADF spécifiques à Confluence, exporte chaque page en `.md` dans le SharePoint synchronisé, met à jour les caches JSON, et produit un rapport d'exécution `.md` + `.json`. Les skills Claude opèrent ensuite sur ces fichiers au lieu de lire Confluence.

### Environnement

- Atlassian Cloud : `sinapse-gie-nc.atlassian.net`, API REST v2 (`/wiki/api/v2`)
- Auth Basic (email + token API), token en variable d'environnement — **jamais versionné, jamais transmis en conversation**
- Python 3.11+, point d'entrée `.venv\Scripts\python.exe` (`requests` absent du Python système)
- Conversion ADF → MD : `marklas`

### Périmètre Confluence

**Groupe A — specs fonctionnelles** : contenu réutilisé résolu, index croisé produit, soumis aux validations.

| Page racine | ID |
|---|---|
| Spécifications fonctionnelles | `1474581` |
| Référentiels du projet | `1277977` |

**Groupe B — documentation** : export `.md` simple, sans résolution ni index.

| Page racine | ID |
|---|---|
| Analyse de l'existant | `1245499` |
| Documentations | `1310723` |
| Skills claude | `219086849` |

Export récursif, profondeur illimitée. 247 pages au total.

---

## 2. Où on en est

| Étape | État |
|---|---|
| 0a — accès REST | ✅ |
| 0b — resolver : réutiliser ou réécrire | 🟡 à trancher en écrivant le parcours récursif |
| 0c — environnement | ✅ |
| **0d — recensement + table de normalisation** | 🟡 recensement ✅ ; `contracts/normalisation_adf.md` **partiel** |
| 0e — inventaire du space | ✅ |
| 1, 2 — export d'une page, puis une par type | ⬜ |
| 2bis — corpus doré | 🟡 9 fixtures figées ; `.md` attendus manquants |
| **3 — inventaire et delta** | 🟡 classification ✅ ; **slugification et delta restants** — voir la note ci-dessous |
| 4 — cache du contenu réutilisé | ⬜ |
| 5 — index croisé (module PERSONNE) | ⬜ |
| 6 — `mcd_sinapse_data` | ⬜ |
| 7 à 9 — run complet, incrémental, planification | ⬜ |
| 10 — adaptation des skills | ⬜ |
| 11 — run à la demande | ⬜ |

Deux étapes ouvertes en parallèle (0d et 3) : la classification a été anticipée parce qu'elle était devenue prérequis du resolver.

**Étape 3 — l'inventaire n'est pas encore assemblé.** `inventory.py` v1.1 émet un **tableau de pages à plat**, alors que `contracts/pages_inventory.schema.json` décrit une **carte indexée par identifiant** — la forme utile au delta. Ni `md_path` ni `last_exported` ne sont renseignés. L'assemblage arrive **avec la slugification et le delta**, qui closent l'étape ; ce qui existe aujourd'hui est un dump de classification, pas `pages_inventory.json`.

### Critères de validation par étape

Récupérés du brief archivé. Ce sont des **tests d'acceptation fondés sur une connaissance du corpus** : les perdre reviendrait à valider chaque étape à vue.

| Étape | Critère |
|---|---|
| **4** — cache du contenu réutilisé | sur `RG-PERSONNE-CARACTERES.AUTORISES`, les **3 consommateurs connus** sont listés |
| **5** — index croisé (module PERSONNE) | nombre de règles cohérent avec le RG ; **une règle orpheline connue apparaît** ; habilitations CU↔API conformes aux cartouches ; `parse_status` correct sur une page **volontairement dégradée** |
| **6** — `mcd_sinapse_data` | validation par **modification d'un attribut MDD** |
| **7** — run complet | mesure du temps, vérification du rapport, **contrôle manuel de 5 pages** |
| **8** — runs incrémentaux | tester les 4 cas : page modifiée, **source de contenu réutilisé modifiée**, suppression, renommage |

Le critère de l'étape 8 est à étendre : « source de multiexcerpt modifiée » date d'avant la découverte des `syncBlock`. Les deux mécanismes doivent être testés, l'invalidation transitive valant pour l'un comme pour l'autre.

### Environnement en place

Claude Code opérationnel, dépôt `C:\dev\sinapse-claude`. Token Atlassian en variables `ATLASSIAN_EMAIL` / `ATLASSIAN_API_TOKEN`. **Aucun remote configuré** — le chemin SharePoint sera renseigné le jour où le travail à domicile devient nécessaire. `recensement/` non versionné (37 Mo, régénérable en 93 s).

### Prochaines étapes

1. **Compléter `contracts/normalisation_adf.md`** — `expand`, `layoutSection`/`layoutColumn`, `media*`, les 3 formes de cartes Jira, `status`, `taskList`, les 15 marks. Tout est tranchable sur les fixtures, sans Confluence. Clôture de l'étape 0d.
2. **Test de conversion `marklas`** sur les 9 fixtures, avec la liste des warnings émis.
3. **Finir l'étape 3** : slugification et delta par `version.number`.
4. Puis étapes 1 et 2 (export de pages), 2bis (corpus doré complété), 4, 5…

---

## 3. Ce qui a été établi

### Recensement ADF — corpus complet

247 pages, 498 appels API, 93 s : 36 types de nœuds, 12 macros, 15 marks, 3 formes de liens Jira. `recense_adf.py` v1.2. 9 fixtures dans `pipeline/fixtures/` couvrant 33 des 36 types.

- **`marklas` retenu** pour la conversion. `layoutSection`, `layoutColumn`, `bodiedExtension`, `expand`, `media`, `rule` sont tous présents dans le corpus ; `pyadf` les perdrait silencieusement.
- **Trois formes de liens Jira** : `blockCard` avec table JQL (82), `inlineCard` (6), macro historique `extension :: jira` (8). 64 tickets REC-* cartographiés page ↔ ticket **sans aucun appel Jira** — la décision tient.
- **`colspan` (6) et `rowspan` (10) existent**, plus 467 cellules à liste ou tableau imbriqué. Confirme « index croisé depuis l'ADF, pas depuis le `.md` ».
- **Décodage générique obligatoire** : `html.unescape()` — le corpus contient `&period;` et `&lowbar;`.
- **Marks à traiter** : `fragment`, `breakout`, `textColor`, `backgroundColor`, `alignment`, `annotation`, `subsup`, `border`, `fontSize`.

### Réutilisation de contenu — deux mécanismes, deux clés

**Multiexcerpt** — 6 variantes, 908 occurrences : 3 formes de définition (`bodiedExtension`, sans paramètre `page` : elles définissent sur leur propre page) et 3 formes d'inclusion.

- **Règle de reconnaissance** : `multiexcerpt` dans la clé → c'est un multiexcerpt ; corps présent → définition, absent → inclusion. **Ne jamais énumérer les variantes.**
- Clé de résolution : **`(page, nom)`** — le nom n'est pas unique globalement (`habilitation` défini 5 fois).
- La source est désignée **par titre**. Confluence maintient ce titre à jour côté serveur au renommage, sans incrémenter la version de la consommatrice. REST v2 et connecteur MCP concordent. **Aucun repli par ID nécessaire.**
- Nettoyage obligatoire : `html.unescape()` **puis** `.strip()` des deux côtés. 10 occurrences portent un espace de tête, cohérent des deux côtés aujourd'hui — la jointure marche par chance, une retouche d'un seul côté casserait 4 inclusions en silence. Vérifié : aucun couple de noms ne fusionne après nettoyage.
- L'inclusion **inline** se substitue dans un paragraphe : le remplacement doit produire des nœuds inline.

**syncBlock** — mécanisme distinct, absent de l'échantillon initial. Un visiteur limité aux nœuds `Extension` le manquerait **en silence**.

```
bodiedSyncBlock (définition)  attrs.resourceId = "{UUID}"                           content = [...]
syncBlock       (inclusion)   attrs.resourceId = "confluence-page/{PAGE_ID}/{UUID}"  content = []
```

- Le contenu est **absent** de la page consommatrice → résolution nécessaire, ce n'est pas de la normalisation.
- Clé : **`(page_id, uuid)`**. Ce n'est pas une précaution théorique — le corpus contient déjà un `resourceId` défini sur **deux pages CU vivantes et scorées** (`CU-NOTE-CREER` 28344321 et `CU-NOTE-TYPENOTE.CREER` 396361729), avec des contenus divergents. Une indexation par UUID seul aurait choisi arbitrairement et produit du contenu faux sans lever d'erreur.
- Les inclusions restent non ambiguës : chacune porte son `confluence-page/{id}/`.
- Les 4 inclusions du corpus trouvent toutes leur définition, aucune orpheline.
- Enjeu mesuré : sans résolution, `CU-NOTE-MODIFIER` sort sans aucun de ses tableaux IHM, et `structure-cu` la validerait comme une CU sans frames.

**Les deux mécanismes cohabitent dans la même pile de récursion**, clés préfixées par leur mécanisme pour interdire toute collision. `CycleGuard` implémenté dans `pipeline/src/multiexcerpt.py` v1.0. Le parcours récursif reste à écrire.

### `nested-table` — pas un échec de conversion

Le nœud porte `parameters.adf`, chaîne JSON contenant le document ADF complet de la table imbriquée : contenu intégralement récupérable par un second `json.loads()`. **Aucun `parse_status: partial`.** Vérifié sur les 248 fixtures : les 11 occurrences portent toutes `adf`, `cxhtml` et `reason`.

Le champ `reason` décrit une limitation de l'éditeur Confluence, et il est **localisé** (anglais et français observés sur le même module) — ne jamais matcher dessus. `cxhtml` coexiste avec `adf` : utiliser `adf`.

*Cette conclusion annule une décision antérieure fondée sur la seule lecture de `reason`.*

### Classification des pages

`pipeline/src/inventory.py` v1.1, 56 tests. La chaîne `parent_id` est complète sur 246/246 et aboutit toujours à une des 5 racines : l'appartenance groupe A/B est **dérivable localement**, sans appel API. L'endpoint ancêtres ne servira jamais.

232 exportées · 196 sources de contenu · 101 scorées · 14 exclues (5 directes, 9 héritées).

| Type | Pages | exported | content_source | scored |
|---|---|---|---|---|
| CU | 59 | ✅ | ✅ | ✅ |
| API | 23 | ✅ | ✅ | ✅ |
| MDD | 20 | ✅ | ✅ | ✅ |
| RG | 7 | ✅ | ✅ | ✅ |
| JOB | 6 | ✅ | ✅ | ✅ |
| MODULE (SF-*) | 38 | ✅ | ✅ | — |
| DOMAINE (Q-*) | 12 | ✅ | ✅ | — |
| UX | 12 | ✅ | ✅ | — |
| A_QUALIFIER | 7 | ✅ | ✅ | — |
| GENERIQUE | 5 | ✅ | ✅ | — |
| REFERENTIEL | 4 | ✅ | ✅ | — |
| SA | 3 | ✅ | ✅ | — |
| DOCUMENTATION | 50 | ✅ | — | — |
| HORS_PERIMETRE | 0 | — | — | — |

**14 valeurs de type**, et non 13 : `HORS_PERIMETRE` complète l'énumération sans avoir aucune occurrence dans le corpus — les 246 chaînes d'ascendance aboutissent toutes à une des 5 racines. Elle existe pour qu'une page rattachée hors périmètre ne puisse pas emprunter un type de spec par défaut.

**Règles acquises** — détail dans `contracts/classification_pages.md` :

- **Toute page du groupe A est `content_source`**, quel que soit son type. Une source peut vivre n'importe où dans l'arbre des specs ; un faux négatif casse une inclusion en silence. *Confirmé : une CU peut être source d'une autre CU.*
- **Aucun type partagé entre groupes A et B** — permet l'invariante : toute page du groupe A en `A_QUALIFIER` est une anomalie, le compteur doit tendre vers zéro.
- **Normalisation des titres avant matching** : `html.unescape()`, puis repli des tirets Unicode (U+2010–U+2015, U+2212, U+FE58, U+FF0D) vers l'ASCII. NFKC seul ne suffit pas. A permis de récupérer `CU-PERSONNE-RECHERCHER`, invisible à l'œil.
- **Préfixe d'exclusion retiré avant le typage**, jamais par désancrage des motifs — sinon `Archive CU-…` deviendrait une spec fantôme scorée.
- **L'exclusion est héritée par tout le sous-arbre.** Règle les doublons `(version avant API)` sans intervention des BA ; `exclude_page_ids` reste vide.
- **Module dérivé de l'ascendance** (ancêtre `SF-*`) en priorité, du titre à défaut.
- `DOC-*` et `TAB-*` : types réservés, non implémentés.

---

## 4. Impact sur les skills

### Supprimés

| Skill | Raison |
|---|---|
| `confluence-outil-analyse-module` | remplacé par `index_croise_{MODULE}.json` |
| `confluence-validation-coherence-mdd-openapi` | OpenAPI hors périmètre |
| `confluence-validation-coherence-api-openapi` | idem |

> **Conséquence assumée** : le contrôle **maxLength** (MDD ↔ DTO, sévérité CRITIQUE) disparaît. Deux actions obligatoires à l'étape 10 : **repondérer** l'orchestrateur (les poids 30/30/25/15 et les seuils 95/90 avaient été calibrés avec ce contrôle bloquant), et **documenter** dans le README de `confluence-validation-module` que la cohérence des longueurs n'est plus vérifiée.

### Modifiés — lecture sur `.md` local

`confluence-outil-lien-jira` (macros en clair depuis le `.md`, appels Jira conservés), `coherence-rg-cu-api`, `coherence-cu-api`, `coherence-codes-http` (partie OpenAPI retirée), `habilitations`, `completude`, `qualite-mdd`, `qualite-cu`, `validation-module` (phase 1 supprimée, phase 2 remplacée par l'index).

**Deux règles transverses à inscrire dans chaque SKILL.md** : afficher `exported_at` en tête du compte-rendu ; ne pas scorer une page dont `parse_status ≠ ok`.

### `confluence-mcd-sync`

Bloc A absorbé par le pipeline. Bloc B (injection planning) reste un skill manuel.

### Distribution

Deux canaux **indépendants** — une session Claude Code ne lit que le disque, elle ne voit pas l'espace GIE de claude.ai.

| Canal | Public | Mécanisme |
|---|---|---|
| Dépôt `.claude/skills/` | Olivier, devs, BAs sur Claude Code | `git pull` |
| Espace GIE claude.ai | BAs sur l'interface web | zip produit par `build/make_skill_zip.py`, importé manuellement |

Le dépôt est la source de vérité ; l'espace GIE est une cible de déploiement. La version en tête de chaque compte-rendu (`Skill : nom-du-skill vX.Y`) permet de repérer un décalage.

---

## 5. Décisions arbitrées — ne pas rouvrir sans raison

**Architecture**
- Tout Python — **aucun LLM dans le pipeline**, sinon retour à la mécanique abandonnée en Phase 3.
- Le pipeline produit des **faits** ; verdicts, sévérités et scores restent dans les skills — sinon changer un seuil impose de redéployer le pipeline.
- **Un seul chemin de lecture** pour les skills : les `.md` locaux, jamais Confluence.
- **Aucun appel Jira dans le pipeline** — données plus volatiles que les specs ; macros remises en clair, appels dans le skill `confluence-outil-lien-jira`.

**Données**
- **Delta par `version.number`**, jamais par date : `lastmodified` est à la minute, sensible au fuseau, et ne bouge pas sur certains déplacements. Le diff de versions donne en prime suppressions, renommages et déplacements.
- **Index croisé construit depuis l'ADF**, pas depuis le `.md` : les tableaux markdown perdent leur structure dès qu'une cellule contient une liste ou un saut de ligne — précisément le cas des tableaux IHM 5 colonnes et MDD 9 colonnes.
- **`parse_status` obligatoire par page** : sans lui, un skill lisant `regles: []` ne peut pas distinguer « aucune règle » de « le parser a échoué », et produit un rapport entièrement faux. Une page en `parse_status ≠ ok` n'est pas scorée, elle est signalée.
- **Pas de cache ADF brut global** — seulement `pipeline/fixtures/` pour les tests. Une évolution du convertisseur implique un run complet depuis Confluence.
- **Aucun nœud ADF ignoré silencieusement** : tout nœud non couvert remonte en erreur au rapport. Un warning résiduel de la lib = un bug du normalizer.
- **`marklas`** pour la conversion ADF → Markdown.
- **Résolution : par titre pour le multiexcerpt, par identifiant de page pour le syncBlock.**
- **OpenAPI hors périmètre** → maxLength abandonné assumé.

**Exécution**
- Cadence quotidienne, 7h. First run avec `last_run = 2020-01-01`, puis delta.
- Écriture atomique (temporaire + rename) ; **write-if-changed**, sinon SharePoint resynchronise tout chaque jour.
- Une page en échec n'interrompt pas le run : listée au rapport, retentée au run suivant.
- Frontmatter YAML visible ; contenu réutilisé marqué visiblement dans le `.md`.
- `exported_at` affiché dans l'en-tête de **tous** les comptes-rendus de skills.

**Organisation**
- Git avec dépôt nu sur le SharePoint comme remote ; GitLab différé, réversible en une commande.
- Sorties du pipeline sur le SharePoint d'équipe.
- **Aucun skill SINAPSE dans `~/.claude/skills/`** : le personnel l'emporte sur le projet, une copie oubliée gagnerait silencieusement sur celle du dépôt.
- Skills Claude Code et espace GIE claude.ai : deux stocks séparés.
- Le token Atlassian n'est jamais versionné ni transmis en conversation.
- **`contracts/` est la source de vérité technique** ; ce document ne le duplique pas.

---

## 6. Exigences à porter dans le code

> **Backoff** — `confluence_client.py` doit couvrir `requests.exceptions.Timeout` et `ConnectionError`, pas seulement le HTTP 429. Le run complet du 4 août a perdu une page sur un timeout transitoire (elle repasse en 0,3 s au réessai) — page qui, de ce fait, n'est pas classée. À raison d'un run quotidien, ce sont des pages qui disparaissent des specs sans que personne ne le remarque.

> **Rangement** — `build_report()` vit provisoirement dans `inventory.py` ; sa place est dans `report.py` quand ce module existera.

> **Nommage des fichiers** — les titres contiennent des caractères interdits sous Windows (`SF-PERSONNE: …`). Slugification obligatoire, collisions détectées et signalées.

> **Horodatage des sorties** — un run partiel ne doit pas pouvoir écraser le rapport d'un run complet du même jour.

---

## 7. Ce qui reste ouvert

**Technique**
- compléter la table de normalisation : `expand`, `layoutSection`/`layoutColumn`, `media*`, cartes Jira, `status`, `taskList`, marks ;
- **réutiliser ou réécrire le resolver** (étape 0b du brief) — deux voies : injecter des fonctions `requests` en place des fonctions connecteur dans `confluence_adf_multiexcerpt_resolver.py`, **ou** réimplémenter comme visiteur de l'AST. **Ne pas maintenir deux logiques.** À arbitrer au vu de la table de normalisation. Les clés et le `CycleGuard` sont faits, le parcours récursif reste à écrire — et il doit désormais couvrir les deux mécanismes, ce que le resolver d'origine ne fait pas ;
- sort de `confluence-outil-resolve-multiexcerpt` (retiré ou conservé en secours) — dépend de la fiabilité du pipeline en production ;
- emplacement des 3 outils existants (`tools/` ou skill) : artefact autonome → `tools/` ; déclenché en conversation → skill.

**Périmètre**
- classification des 7 pages `A_QUALIFIER` (notes de cadrage, à qualifier une par une) ;
- **`-NEW- CU-COMPTE-PROFIL.GEST` est exclue, et son ancienne version l'est par héritage → cette spec disparaît entièrement du corpus.** Seul trou connu ;
- format des pages `SA-*` (services applicatifs) — typées, exportées, non scorées en attendant validation du principe ;
- chemin SharePoint réel et exclusions de pages.

**Déploiement**
- repondération de l'orchestrateur après abandon d'OpenAPI (étape 10) ;
- accès des BAs sur claude.ai aux `.md` : miroir SharePoint conservé, ou passage des BAs sur Claude Code (étape 10) ;
- mécanisme de run à la demande : Python portable + `.bat`, ou CI (étape 11) ;
- distribution des skills aux BAs sur Claude Code — le dépôt suffit tant qu'Olivier est seul ;
- migration GitLab + CI, après l'étape 9 ou à l'arrivée d'un 2ᵉ contributeur ;
- **runner CI capable de joindre `atlassian.net`** — question longue à obtenir, à poser tôt en parallèle.

---

## 8. Anomalies Confluence à remonter aux BA

À tenir dans `docs/anomalies-confluence.md` :

- **`CU-NOTE-TYPENOTE.CREER` (396361729) est une copie de `CU-NOTE-CREER` (28344321) qui a hérité de ses identifiants de bloc** — même `resourceId`, même `localId`, contenus divergents. Deux specs vivantes prétendent définir le même bloc. Le pipeline s'en sort par la clé `(page_id, uuid)`, mais l'édition de l'une des deux réserve des surprises ;
- 5 requêtes JQL avec gabarit `{{page.url}}` non substitué — ces tables Jira ne ciblent aucune page réelle ;
- 3 `blockCard` sans datasource, en fait des liens SharePoint ;
- `Règles génériques utilisables pour les recherches` (28803126) rangée sous `4. Patterns`, au milieu du sous-arbre Design System, alors que ses quatre sœurs sont directement sous la racine ;
- écart module titre/ascendance sur `SF-DOCUMENT` et `ARCHIVE_CU-DOSS-CONSULT` (titre annonce DOSS, arbre dit PERSONNE) ;
- `-NEW- CU-COMPTE-PROFIL.GEST` — préfixe à retirer si c'est la version vivante ;
- spécifications archivées encore rattachées à la racine `Spécifications fonctionnelles` (1474581) — leur déplacement hors du périmètre serait le geste propre, l'héritage d'exclusion en tient lieu en attendant.

*Non retenu comme anomalie : l'emplacement de `SF-DOSS: Messages système consolidés` sous « 2. Fondation et tokens » est volontaire (multiexcerpt source à terme).*

---

## 9. Contraintes de la relation de travail

- **L'interlocuteur de conception n'a accès ni à Confluence ni à la machine.** Son bac à sable ne peut pas joindre `atlassian.net`. Tout ce qui touche à Confluence passe par un script exécuté en local — ou par un partage de fixtures JSON en pièce jointe, qui s'est révélé efficace.
- **Le token Atlassian n'est jamais transmis en conversation** ni écrit dans un fichier versionné.
- Le développement se fait en Claude Code ; cette conversation sert à concevoir, arbitrer et relire.
