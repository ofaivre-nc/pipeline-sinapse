# Guide d'implémentation des skills SINAPSE

**Date** : 27 février 2026 — v4 (restructuration complète des blocs)  
**Objet** : Pour chaque skill à réaliser — description, sources exactes, stratégie de reprise

## Comment lire ce document

**Colonne "Sources"** :
- `skill:validation v3.5 §Phase2` = section "Phase 2" du SKILL.md actuel `validation-specs-sinapse`
- `skill:migration v3.0 §Phase0` = section "Phase 0" du SKILL.md actuel `migration-specs-sinapse`
- `script:check_coherence.py::verify_maxlength_consistency()` = fonction exacte dans un script joint à la discussion **validation**
- `orch:generate_specs.py::generate_mdd()` = fonction exacte dans un script joint à la discussion **migration** (orchestrateur-sinapse-v1.0.0)

**Colonne "Stratégie"** :
- **Reprendre script** = le script est la source principale, adapter en SKILL.md
- **Reprendre skill** = extraire du SKILL.md existant, créer le skill unitaire correspondant
- **Mixte** = combiner skill et script(s), les deux apportent des éléments complémentaires
- **Créer** = ni dans le skill ni dans un script exploitable, rédiger à partir des templates SINAPSE

---

## Action préalable — Nettoyage de sinapse-references

**sinapse-references est conservé** comme skill de références partagées. Action à réaliser avant toute implémentation :

- **Conserver** : tout le répertoire `/mnt/skills/user/sinapse-references/references/` (TEMPLATE_*.md, PROCEDURES_*.md, CONVENTIONS_*.md, REGLES_*.md)
- **Supprimer** : tous les autres fichiers du skill (SKILL.md, scripts/, README_*.md, INDEX.md, INTEGRATION_EXAMPLES.md) — ces fichiers appartiennent aux skills legacy deprecated
- **Résultat attendu** : sinapse-references ne contient plus qu'un répertoire `references/` lu via `view` depuis les autres skills

---

## Bloc 1 — Outils (infrastructure)

### confluence-outil-resolve-multiexcerpt
**Statut** : Existant v1.1 — opérationnel  
**Action** : Aucune — ne pas toucher

---

### confluence-outil-lien-jira
**Description** : Vérifie les liens Jira depuis les cartouches SINAPSE — (d1) lien tâche de test → sous-tâche Jira `TEST-{NOM_CU}`, (d3) tableau ÉVOLUTIONS → Story avec champ Specs = URL de la page. Conçu pour être appelé par `structure-cu`, `structure-api`, `structure-job` en tant que dépendance, mais peut aussi s'appeler seul.  
**Priorité** : 2  
**Sources** :
- `script:validate_cartouche.py` (script legacy dans sinapse-references/scripts/, à récupérer)

**Stratégie** : Reprendre script.

---

### confluence-outil-analyse-module
**Description** : Lit les pages d'un module *déjà en format FE/BE* depuis Confluence (pages résolues) et produit un INDEX_CROISE structuré en JSON : entités/attributs, règles, CU (habilitations, règles référencées), APIs (endpoints par entité), croisement avec schémas OpenAPI, statistiques globales. Outil de fondation utilisé par la validation complète et le mode de complétion.  
**Priorité** : 4  
**Sources** :
- `script:analyze_structure.py` entier — `read_all_specs()`, `extract_entities_from_mdd()`, `extract_rules_from_rg()`, `extract_use_cases_from_cu()`, `extract_apis_from_api()`, `generate_index_croise()`
- `skill:validation v3.5 §Phase1` — logique de lecture des pages Confluence résolues

**Stratégie** : Reprendre script. `analyze_structure.py` est complet. L'adapter comme script Python du skill.

---

## Bloc 2 — Validation structure et conformité templates

### confluence-validation-structure-mdd
**Description** : Vérifie la conformité structurelle du MDD au template SINAPSE : tableau 9 colonnes, champs système présents (id, dateCreation, auteurCreation, dateModification, auteurModification, version), clés étrangères au format `uuid MODULE.ENTITE`, absence de section "Règles génériques" (qui doit être dans le RG).  
**Priorité** : 3  
**Sources** :
- `skill:validation v3.5 §Phase2` — section "MDD"
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_MDD.md`

**Stratégie** : Reprendre skill.

---

### confluence-validation-structure-rg
**Description** : Vérifie la conformité structurelle du RG : format des codes `RG-{MODULE}.{ENT}-{NUM}`, structure de chaque règle (Titre + Description + Implémentation API), codes erreur en gras `**CODE-XXX**`, absence de tableau consolidé des codes erreur (anti-pattern — ne doit figurer que dans l'OpenAPI), organisation par entité.  
**Priorité** : 3  
**Sources** :
- `skill:validation v3.5 §Phase2` — section "RG"
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_RG.md`

**Stratégie** : Reprendre skill.

---

### confluence-validation-structure-cu
**Description** : Vérifie la conformité structurelle des CU : cartouches (identification, Plugin Jira, ÉVOLUTIONS, TOC), 3 frames (bandeau/menu | recherche/liste | détail/formulaire), tableaux IHM 5 colonnes (Libellé | Champ | Saisie | Obligatoire | Description), conventions nommage `_IHM_MODULE_ENTITE_Champ_` et `MODULE.ENTITE.champ`, types IHM standards référencés. Anti-patterns : sections Acteurs/Pré-conditions/Post-conditions. Règle absolue : screenshots non obligatoires, jamais pénalisés. **Appelle `confluence-outil-lien-jira`** pour la vérification des liens cartouche.  
**Priorité** : 3  
**Dépendance** : `confluence-outil-lien-jira`  
**Sources** :
- `skill:validation v3.5 §Phase2` — section "CU" + règle v2.2 screenshots
- `script:check_completude.py::check_cu_completeness()` — contrôle frame count
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_CU.md`

**Stratégie** : Reprendre skill principalement.

---

### confluence-validation-structure-api
**Description** : Vérifie la conformité structurelle des fiches API : cartouches (identification, Plugin Jira, ÉVOLUTIONS, TOC), section "But & scénarios", section "Pré-conditions (sécurité & rôles)", tableau contrats DTO 4 colonnes (ListItem | Detail | Create | Patch) avec légende R/O/P/RO, flux par endpoint (GET/POST/PATCH/DELETE), références RG et OpenAPI. Intègre la vérification de la **nomenclature** : format camelCase des propriétés DTOs, format des paths (`/module/entites/{id}`). **Appelle `confluence-outil-lien-jira`** pour la vérification des liens cartouche.  
**Priorité** : 3  
**Dépendance** : `confluence-outil-lien-jira`  
**Sources** :
- `skill:validation v3.5 §Phase2` — section "API"
- `skill:validation v3.5 §Phase3` — contrôle 2.4 nomenclature
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_API.md`

**Stratégie** : Reprendre skill.

---

### confluence-validation-habilitations
**Description** : Vérifie (1) présence du champ "Habilitation requise" dans les cartouches API, (2) cohérence de la valeur d'habilitation entre les CU et les fiches API du même module.  
**Priorité** : 3  
**Sources** :
- `skill:validation v3.5 §Phase3` — contrôles 2.8 et 2.9
- `script:check_coherence.py::check_api_habilitation_present()` — présence champ habilitation
- `script:check_coherence.py::check_habilitation_cu_api_coherence()` — cohérence valeur CU↔API
- `/mnt/skills/user/sinapse-references/references/PROCEDURES_API_HABILITATION.md`

**Stratégie** : Mixte. Les 2 fonctions des scripts sont directement réutilisables. Niveaux de sévérité depuis le skill.

---

### confluence-validation-structure-job
**Description** : Vérifie la conformité structurelle des fiches JOB/Batch au template SINAPSE. **Appelle `confluence-outil-lien-jira`** pour la vérification des liens cartouche.  
**Priorité** : 5  
**Dépendance** : `confluence-outil-lien-jira`  
**Sources** :
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_JOB.md`

**Stratégie** : Créer.

---

## Bloc 3 — Validation cohérence inter-documents

### confluence-validation-coherence-mdd-openapi
**Description** : Vérifie la cohérence complète entre le MDD et l'OpenAPI : (1) **maxLength** — pour chaque champ texte du MDD, vérifier que `maxLength` est identique dans les 4 DTOs — tout écart est CRITIQUE, (2) champs MDD présents dans chaque DTO, (3) types compatibles (VARCHAR→string, UUID→uuid, DATE→date-time), (4) contraintes cohérentes (NOT NULL→required), (5) champs obligatoires MDD présents dans `required` du schéma Detail.  
**Priorité** : 1  
**Sources** :
- `script:check_coherence.py::verify_maxlength_consistency()`
- `script:check_interdocs.py::check_fields_properties_mapping()`
- `script:check_coherence.py::check_dto_consistency()`
- `skill:validation v3.5 §Phase3` — règle "4 DTOs obligatoires", sévérité CRITIQUE sur maxLength

**Stratégie** : Mixte.

---

### confluence-validation-coherence-codes-http
**Description** : Vérifie deux familles : (1) **Codes erreur** — les codes définis dans les règles RG sont présents dans `ErrorResponse.code.enum` de l'OpenAPI, (2) **Statuts HTTP** — cohérence GET→200, POST→201, DELETE→204, présence 400/404/409 dans chaque endpoint.  
**Priorité** : 2  
**Sources** :
- `script:check_coherence.py::check_error_codes_consistency()`
- `script:parse_error_codes.py` (script legacy sinapse-references/scripts/)
- `skill:validation v3.5 §Phase3` — contrôle 2.5

**Stratégie** : Mixte.

---

### confluence-validation-coherence-rg-cu-api
**Description** : Vérifie (1) que chaque règle RG référencée dans un CU ou une API existe bien dans la page RG, (2) cohérence des codes erreur entre RG et CU/API, (3) règles RG orphelines (aucune référence dans CU ni API), (4) présence des règles globales obligatoires RG-API-1, RG-API-2, RG-API-3 dans chaque fiche API, (5) présence RG-API-3 dans les CU effectuant des appels POST/PATCH/DELETE, (6) analyse sémantique Claude : doublons, règles contradictoires, mauvaise catégorisation.  
**Priorité** : 3  
**Sources** :
- `skill:validation v3.5 §Phase3` — contrôle 2.6 + contrôles 2.10 et 2.11 (déplacés depuis habilitations)
- `script:check_coherence.py::check_global_api_rules()` — présence RG-API-1/2 dans fiches API
- `script:check_coherence.py::check_rg_api3_in_cu()` — RG-API-3 conditionnel dans CU
- `script:check_interdocs.py::check_rules_usage_semantic()` — règles orphelines
- `script:check_interdocs.py::analyze_rules_semantic_with_claude()` — doublons/contradictions

**Stratégie** : Mixte.

---

### confluence-validation-coherence-cu-api
**Description** : Vérifie la cohérence entre les CU et les fiches API : chaque bouton IHM d'un CU correspond à un endpoint API existant, chaque champ IHM correspond à une propriété DTO dans l'OpenAPI, messages erreur IHM cohérents avec codes RG.  
**Priorité** : 3  
**Sources** :
- `skill:validation v3.5 §Phase3` — contrôle 2.7
- `skill:validation v3.5 §Phase2` — analyse CU approfondie v3.2

**Stratégie** : Reprendre skill.

---

### confluence-validation-coherence-api-openapi
**Description** : Vérifie que chaque endpoint documenté dans une fiche API est présent dans l'OpenAPI (paths), que chaque DTO défini dans le tableau contrats est présent dans les schémas, et que les codes erreur métier figurent dans `ErrorResponse`.  
**Priorité** : 3  
**Sources** :
- `script:check_interdocs.py::check_endpoints_paths_mapping()`
- `skill:validation v3.5 §Phase3` — cohérence DTOs et ErrorResponse

**Stratégie** : Mixte.

---

## Bloc 4 — Validation complétude et qualité

### confluence-validation-completude
**Description** : Vérifie la complétude fonctionnelle en deux temps. **(1) Contrôles mécaniques via script** — MDD (entités, attributs, absence de [TODO]), RG (règles, multi-excerpt, catégories distinctes), CU (présence, structure, frames), API (CRUD complet GET/POST/PATCH/DELETE présents — sauf entités lecture seule explicites selon MDD), OpenAPI (paths, schemas, section `security`, 4 schémas par entité). **(2) Analyse LLM** — Claude évalue si le périmètre fonctionnel est plausible pour ce type de domaine : entités ou règles métier typiques semblant manquer, cas limites habituels non couverts, contraintes métier insuffisamment précises.  
**Priorité** : 4  
**Sources** :
- `script:check_completude.py::check_mdd_completeness()`
- `script:check_completude.py::check_rg_completeness()`
- `script:check_completude.py::check_cu_completeness()`
- `script:check_completude.py::check_api_completeness()` *(absent du skill actuel)*
- `script:check_completude.py::check_openapi_completeness()` *(absent du skill actuel)*
- `skill:validation v3.5 §Phase4` — règle entités lecture seule non pénalisées

**Stratégie** : Mixte. Scripts pour les contrôles mécaniques (déterministes, traçables). Claude pour la lecture critique du fond : le LLM apporte sa connaissance du domaine pour détecter les manques sémantiques que le script ne peut pas voir.

---

### confluence-validation-qualite-mdd *(NOUVEAU)*
**Description** : Analyse qualité du MDD via Claude — descriptions non vagues, types appropriés (pas tout en VARCHAR), longueurs cohérentes, champs obligatoires correctement identifiés. Score qualité avec les 5 problèmes les plus critiques.  
**Priorité** : 4  
**Sources** :
- `script:check_completude.py::analyze_mdd_quality_with_claude()`

**Stratégie** : Reprendre script.

---

### confluence-validation-qualite-rg *(NOUVEAU)*
**Description** : Analyse qualité du RG via Claude — règles précises et actionnables, codes erreur associés à chaque règle, organisation par catégorie claire, descriptions professionnelles.  
**Priorité** : 4  
**Sources** :
- `script:check_completude.py::analyze_rg_quality_with_claude()`

**Stratégie** : Reprendre script.

---

### confluence-validation-qualite-cu *(NOUVEAU)*
**Description** : Analyse qualité des CU via Claude — parcours utilisateur clair, frames IHM bien structurés, règles métier référencées, cas nominaux ET cas alternatifs décrits.  
**Priorité** : 4  
**Sources** :
- `script:check_completude.py::analyze_cu_quality_with_claude()`

**Stratégie** : Reprendre script.

---

### confluence-validation-qualite-api *(NOUVEAU)*
**Description** : Analyse qualité des fiches API via Claude — endpoints bien nommés et granularité cohérente, DTOs expressifs (pas de champs fourre-tout), codes erreur métier distinctifs et couvrant les cas réels, pagination homogène entre endpoints, cohérence du modèle de sécurité.  
**Priorité** : 4  
**Sources** :
- À créer sur le pattern des autres qualite-* — même format de retour `{score, issues}`
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_API.md`

**Stratégie** : Créer sur le pattern qualite-*.

---

## Bloc 5 — Migration : pipeline de préparation

*Ces skills couvrent les étapes entre la Phase 0 (résolution multiexcerpt, opérationnelle dans `migration-specs-sinapse`) et la génération des specs. Spécifiques au contexte de migration depuis un ancien modèle monolithique.*

---

### confluence-migration-extract-data *(NOUVEAU)*
**Description** : Enrichit la Phase 1 du skill migration. Extrait depuis les pages résolues de l'ancien modèle : entités, attributs avec les **9 colonnes MDD** complètes (type, longueur, obligatoire, valeur défaut, contrainte, commentaire), règles RG et règles CU intégrées au corpus global, écrans CU avec champs détaillés par frame, messages/codes erreur, endpoints API, jobs. Produit `extracted_data` en JSON.  
**Priorité** : 1 (migration)  
**Sources** :
- `skill:migration v3.0 §Phase1` — `migration_phase1.py` (extraction basique à enrichir)
- `orch:extract_all_data.py` — extraction complète 9 colonnes, messages, jobs, règles CU dans corpus

**Stratégie** : Mixte. Enrichir `migration_phase1.py` avec les extractions manquantes de `extract_all_data.py`. Conserver l'interface stabilisée `resolved_pages → extracted_data`.

---

### confluence-migration-analyse-gaps *(NOUVEAU)*
**Description** : Analyse les données extraites pour détecter les non-conformités avant génération. Deux familles : **(1) mécaniques** — champs audit manquants (seuil : ≥ 2 absents parmi auteurCreation, dateCreation, auteurModification, dateModification), champ statut manquant, entités sans règles, CU sans habilitations (HIGH), codes erreur malformés (pattern `XXX-YYY-NNN`) ; **(2) conventions SINAPSE** — nommage entités (MODULE.ENTITE majuscules), nommage attributs (camelCase), champs système par entité. Produit `analysis_gaps` avec sévérité HIGH/MEDIUM/LOW/OK par contrôle.  
**Priorité** : 1 (migration)  
**Sources** :
- `orch:analyze_gaps.py` — toutes les fonctions de vérification mécanique et conventions v2.0

**Stratégie** : Reprendre script orchestrateur.

---

### confluence-migration-ask-clarifications *(NOUVEAU)*
**Description** : Dialogue stratégique LLM-natif avec le chef de projet avant génération. À partir des données extraites et des gaps détectés, Claude formule des questions ouvertes ciblées sur les décisions structurantes (champs audit à ajouter, habilitations manquantes, nommage des entités non conformes, champ statut…). Le chef de projet répond dans la conversation. Claude interprète les réponses et produit `decisions` : liste d'actions structurées (`add_field`, `rename_entity`, `modify_field`, `restructure_rule`) qui alimentent le skill suivant.  
**Priorité** : 2 (migration)  
**Sources** :
- `orch:ask_clarifications.py` — catégories de questions et structure des décisions à conserver

**Stratégie** : Créer (LLM-natif). Le script orchestrateur implémentait une mécanique complexe (appels API Claude externe, mémoire JSON persistante) nécessaire parce qu'il tournait en dehors de Claude. En mode skill, Claude est directement dans la conversation : il pose les questions inline, reçoit les réponses, et produit les décisions sans aucune infrastructure intermédiaire. Reprendre uniquement les **catégories de questions** et la **structure des décisions** du script — pas sa mécanique.

---

### confluence-migration-generate-mapping *(NOUVEAU)*
**Description** : Construit la cartographie entre l'ancien modèle et le nouveau à partir des décisions issues des clarifications. Produit `MAPPING-{MODULE}.md` avec trois tableaux (entités, attributs, règles) montrant chaque transformation (unchanged/renamed/type_changed/added/restructured) avec sa justification. Génère statistiques et observations sur l'ampleur des changements.  
**Priorité** : 2 (migration)  
**Sources** :
- `orch:generate_mapping.py` — toutes les fonctions de construction et génération du document

**Stratégie** : Reprendre script orchestrateur.

---

## Bloc 6 — Génération des specs

### confluence-generation-mdd
**Description** : Génère une page MDD conforme au template SINAPSE à partir des données extraites. Tableau 9 colonnes, champs système injectés automatiquement (id, version, dateCreation, auteurCreation, dateModification, auteurModification).  
**Priorité** : 6  
**Sources** :
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_MDD.md`
- `skill:migration v3.0 §Mode2`
- `orch:generate_specs.py::generate_mdd()` + `enrich_mdd_with_claude()`

**Stratégie** : Mixte.

---

### confluence-generation-rg
**Description** : Génère une page RG conforme au template SINAPSE. Organise les règles par catégorie (VAL, CALC, TRT, ERR…), injecte les macros multiexcerpt.  
**Priorité** : 6  
**Sources** :
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_RG.md`
- `skill:migration v3.0 §Mode2`
- `orch:generate_specs.py::generate_rg()` + `extract_category()`

**Stratégie** : Mixte.

---

### confluence-generation-cu
**Description** : Génère les pages CU conformes au template SINAPSE. Cartouche complet, habilitation suggérée depuis le titre (à valider par le chef de projet), 3 frames IHM numérotées (4.1, 4.2, 4.3), injection conditionnelle de RG-API-3 uniquement si le CU effectue des appels POST/PATCH/DELETE.  
**Priorité** : 6  
**Sources** :
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_CU.md`
- `skill:migration v3.0 §Mode2`
- `orch:generate_specs.py::generate_cu()` + `auto_detect_habilitation()` + `detect_api_calls_in_cu()`

**Stratégie** : Mixte.

---

### confluence-generation-api
**Description** : Génère les fiches API conformes au template SINAPSE. Cartouche avec habilitation, section "Règles globales" avec RG-API-1/2/3 systématiques, endpoints CRUD avec codes HTTP standards, DTOs.  
**Priorité** : 6  
**Sources** :
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_API.md`
- `/mnt/skills/user/sinapse-references/references/PROCEDURES_API_HABILITATION.md`
- `skill:migration v3.0 §Mode2`
- `orch:generate_specs.py::generate_api()`

**Stratégie** : Mixte.

---

### confluence-generation-openapi *(NOUVEAU)*
**Description** : Génère le fichier YAML OpenAPI 3.0.3 du module. Mapping types MDD → OpenAPI, paths CRUD standards par entité, 4 schemas par entité (Detail/Create/Patch/ListItem + ListResponse paginée), ErrorResponse standardisée, sécurité JWT Bearer globale, codes erreur extraits des règles intégrés dans `ErrorResponse.code.enum`.  
**Priorité** : 6  
**Sources** :
- `orch:generate_openapi.py` entier

**Stratégie** : Reprendre script orchestrateur.

---

### confluence-generation-job *(NOUVEAU)*
**Description** : Génère une fiche JOB/Batch conforme au template SINAPSE.  
**Priorité** : 6  
**Sources** :
- `/mnt/skills/user/sinapse-references/references/TEMPLATE_JOB.md`
- `orch:generate_specs.py::generate_job()`

**Stratégie** : Mixte.

---

## Bloc 7 — Orchestrateurs

### confluence-validation-module
**Description** : Orchestrateur de validation complète d'un module FE/BE (F1). Enchaîne : (1) `confluence-outil-resolve-multiexcerpt`, (2) `confluence-outil-analyse-module`, (3) tous les `structure-*` (mdd, rg, cu, api, job si présent), (4) `confluence-validation-habilitations`, (5) tous les `coherence-*`, (6) `confluence-validation-completude`, (7) tous les `qualite-*` (mdd, rg, cu, api). Agrège les scores et produit une synthèse globale avec recommandations prioritaires.  
**Priorité** : 7  
**Sources** :
- `script:calculate_score.py::calculate_weighted_score()` — pondération 30%/30%/25%/15%
- `script:calculate_score.py::generate_recommendations_with_claude()`
- `script:calculate_score.py::generate_validation_report()`
- `skill:validation v3.5 §Phase5` — seuils 95/90 + règle maxLength bloque l'avis ✅
- `skill:validation v3.5 §Système checkpoints`

**Stratégie** : Mixte. Logique de scoring depuis `calculate_score.py`. Orchestrateur sans logique métier propre.

---

### confluence-migration-module
**Description** : Orchestrateur de migration complète depuis un ancien modèle monolithique (F2). **Mode A** (migration directe) : (1) `confluence-outil-resolve-multiexcerpt` Phase 0, (2) `confluence-migration-extract-data`, (3) `confluence-migration-analyse-gaps`, (4) `confluence-migration-ask-clarifications`, (5) `confluence-migration-generate-mapping`, (6) `confluence-generation-mdd`, (7) `confluence-generation-rg`, (8) N × `confluence-generation-cu`, (9) N × `confluence-generation-api`, (10) `confluence-generation-openapi`, (11) `confluence-generation-job` si présent, (12) `confluence-validation-module` sur le résultat généré. **Mode B** (migration comparative) : insère une étape de comparaison ancien/nouveau entre les étapes 2 et 3 pour détecter les pertes avant toute génération — cette logique est intégrée directement dans l'orchestrateur (pas en skill séparé), s'appuyant sur `script:compare_old_vs_new.py`.  
**Priorité** : 8  
**Sources** :
- `skill:migration v3.0` — Phase 0 (checkpoints, cache), format de sortie
- `orch:sinapse_orchestrator.py` — logique d'enchaînement et gestion workspace
- `script:compare_old_vs_new.py` — comparaison ancien/nouveau pour Mode B

**Stratégie** : Mixte. Structure d'enchaînement depuis `sinapse_orchestrator.py`. Checkpoints Phase 0 depuis le skill migration. Logique de comparaison Mode B intégrée directement (pas en skill séparé).

---

## Récapitulatif

| # | Skill | Bloc | Priorité | Stratégie | Note |
|---|---|---|---|---|---|
| 0 | sinapse-references | — | — | Nettoyer (garder references/ uniquement) | Action préalable |
| 1 | confluence-outil-resolve-multiexcerpt | 1 | — | Existant v1.1 | Ne pas toucher |
| 2 | confluence-outil-lien-jira | 1 | 2 | Reprendre script `validate_cartouche.py` | Appelé par structure-cu/api/job |
| 3 | confluence-outil-analyse-module | 1 | 4 | Reprendre script `analyze_structure.py` | Outil partagé |
| 4 | confluence-validation-structure-mdd | 2 | 3 | Reprendre skill §Phase2 MDD | — |
| 5 | confluence-validation-structure-rg | 2 | 3 | Reprendre skill §Phase2 RG | — |
| 6 | confluence-validation-structure-cu | 2 | 3 | Reprendre skill §Phase2 CU | Dépend lien-jira |
| 7 | confluence-validation-structure-api | 2 | 3 | Reprendre skill §Phase2 API + 2.4 nomenclature | Dépend lien-jira |
| 8 | confluence-validation-habilitations | 2 | 3 | Mixte : 2 fonctions scripts + skill 2.8/2.9 | Recentré habilitations uniquement |
| 9 | confluence-validation-structure-job | 2 | 5 | Créer depuis TEMPLATE_JOB.md | Dépend lien-jira |
| 10 | confluence-validation-coherence-mdd-openapi | 3 | 1 | Mixte : 3 fonctions scripts + règles skill | Absorbe maxLength |
| 11 | confluence-validation-coherence-codes-http | 3 | 2 | Mixte : scripts + skill contrôle 2.5 | Fusion codes-erreur + statuts-http |
| 12 | confluence-validation-coherence-rg-cu-api | 3 | 3 | Mixte : skill 2.6 + scripts + contrôles 2.10/2.11 déplacés | Absorbe RG-API-1/2/3 |
| 13 | confluence-validation-coherence-cu-api | 3 | 3 | Reprendre skill 2.7 + analyse CU v3.2 | — |
| 14 | confluence-validation-coherence-api-openapi | 3 | 3 | Mixte : script endpoints + skill DTOs | — |
| 15 | confluence-validation-completude | 4 | 4 | Mixte : scripts mécaniques + LLM sémantique | LLM pour lecture domaine |
| 16 | confluence-validation-qualite-mdd | 4 | 4 | Reprendre script `analyze_mdd_quality_with_claude()` | NOUVEAU |
| 17 | confluence-validation-qualite-rg | 4 | 4 | Reprendre script `analyze_rg_quality_with_claude()` | NOUVEAU |
| 18 | confluence-validation-qualite-cu | 4 | 4 | Reprendre script `analyze_cu_quality_with_claude()` | NOUVEAU |
| 19 | confluence-validation-qualite-api | 4 | 4 | Créer sur pattern qualite-* | NOUVEAU — manquait |
| 20 | confluence-migration-extract-data | 5 | 1 mig | Mixte : enrichir migration_phase1.py + orch extract_all_data | NOUVEAU |
| 21 | confluence-migration-analyse-gaps | 5 | 1 mig | Reprendre script `orch:analyze_gaps.py` | NOUVEAU |
| 22 | confluence-migration-ask-clarifications | 5 | 2 mig | Créer LLM-natif (catégories + décisions de l'orch, mécanique simplifiée) | NOUVEAU — réarchitecté |
| 23 | confluence-migration-generate-mapping | 5 | 2 mig | Reprendre script `orch:generate_mapping.py` | NOUVEAU |
| 24 | confluence-generation-mdd | 6 | 6 | Mixte : TEMPLATE_MDD + orch generate_mdd | Mise à jour v2→v3 |
| 25 | confluence-generation-rg | 6 | 6 | Mixte : TEMPLATE_RG + orch generate_rg | Mise à jour v2→v3 |
| 26 | confluence-generation-cu | 6 | 6 | Mixte : TEMPLATE_CU + orch generate_cu + habilitation auto + RG-API-3 conditionnel | Mise à jour v2→v3 |
| 27 | confluence-generation-api | 6 | 6 | Mixte : TEMPLATE_API + orch generate_api | Mise à jour v2→v3 |
| 28 | confluence-generation-openapi | 6 | 6 | Reprendre script `orch:generate_openapi.py` | NOUVEAU |
| 29 | confluence-generation-job | 6 | 6 | Mixte : TEMPLATE_JOB + orch generate_job | NOUVEAU |
| 30 | confluence-validation-module | 7 | 7 | Mixte : `calculate_score.py` + checkpoints skill | Orchestrateur F1 |
| 31 | confluence-migration-module | 7 | 8 | Mixte : skill migration (Phase 0) + orch sinapse_orchestrator + compare_old_vs_new Mode B | Orchestrateur F2 |
