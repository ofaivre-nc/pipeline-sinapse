# Première séance Claude Code — procédure pas à pas

**Objectif de la séance** : installer Claude Code, créer le dépôt SINAPSE, et exécuter le recensement des nœuds ADF sur de vraies pages Confluence.
**Durée** : environ 2 heures, en cinq blocs indépendants. Tu peux t'arrêter entre deux blocs.
**Prérequis** : PC bureau, accès Confluence, droits d'installation de logiciels.

> Astuce de lecture : les blocs 1 à 3 se font **sans** Claude Code (installation et préparation). À partir du bloc 4, c'est Claude Code qui travaille.

---

## Bloc 1 — Installation (20 min)

### 1.1 Vérifier les prérequis

Ouvre un terminal (PowerShell ou l'invite de commandes) et tape :

```bash
node --version
python --version
git --version
```

Il te faut Node.js (Claude Code est distribué via npm), Python 3.11 ou plus, et Git.
Si l'un manque : Node.js sur nodejs.org, Python sur python.org (**coche « Add Python to PATH »** à l'installation), Git sur git-scm.com.

### 1.2 Installer Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

### 1.3 Premier lancement

```bash
claude
```

La première exécution te demande de te connecter à ton compte Claude. Une fois dans la session, tape :

```
/doctor
```

C'est le diagnostic d'installation. S'il ne signale rien de bloquant, tu es prêt.

Pour sortir d'une session : `Ctrl+C` deux fois, ou tape `/exit`.

**Si ça coince** : `npm install -g` peut échouer faute de droits. Sous Windows, relance le terminal en tant qu'administrateur.

---

## Bloc 2 — Le token Atlassian (10 min)

Le pipeline s'authentifie auprès de Confluence avec ton email et un token API personnel.

### 2.1 Créer le token

Depuis ton compte Atlassian, section sécurité du profil, crée un token API. **Copie-le immédiatement**, il n'est affiché qu'une fois.

### 2.2 L'enregistrer en variable d'environnement

```bash
setx ATLASSIAN_EMAIL "prenom.nom@..."
setx ATLASSIAN_API_TOKEN "colle-le-token-ici"
```

⚠️ `setx` n'affecte pas le terminal en cours. **Ferme-le et rouvres-en un neuf**, puis vérifie :

```bash
echo %ATLASSIAN_API_TOKEN%
```

Tu dois voir le token s'afficher. Si tu vois `%ATLASSIAN_API_TOKEN%` tel quel, c'est que la variable n'est pas prise en compte : rouvre un terminal.

> Le token ne doit jamais être écrit dans un fichier versionné, ni collé dans une conversation.

---

## Bloc 3 — Créer le dépôt (20 min)

### 3.1 Le répertoire de travail

```bash
mkdir C:\dev
cd C:\dev
mkdir sinapse-claude
cd sinapse-claude
git init
```

Configure ton identité Git si c'est la première fois :

```bash
git config --global user.name "Olivier ..."
git config --global user.email "prenom.nom@..."
```

### 3.2 Déposer les documents de référence

Crée un sous-dossier `docs\` et copie dedans :

- `brief-pipeline-sinapse-v3.md`
- `guide_implementation_skills_sinapse_v4.md`
- ce guide

Crée aussi `pipeline\src\` et copie `recense_adf.py` dedans.

### 3.3 Le remote sur SharePoint

Repère le chemin local de ton SharePoint GIE dans l'explorateur, puis :

```bash
git init --bare "C:\Users\<toi>\<SharePoint GIE>\sinapse\sinapse.git"
git remote add origin "C:\Users\<toi>\<SharePoint GIE>\sinapse\sinapse.git"
```

Tu ne mettras jamais les pieds dans ce dossier : tu ne fais que `push` et `pull` dessus. C'est ce qui évite les conflits de synchronisation.

---

## Bloc 4 — Première vraie session Claude Code (30 min)

```bash
cd C:\dev\sinapse-claude
claude
```

À partir d'ici, **tu parles à Claude Code en français, normalement**. Voici les instructions à lui donner, dans l'ordre.

### 4.1 Faire créer les fichiers de configuration

> Je démarre un projet. Le dossier `docs/` contient `brief-pipeline-sinapse-v3.md` qui décrit tout le projet — lis-le.
>
> Crée ensuite, en te basant sur la section 2 du brief :
> - le `.gitignore` (config.ini, CLAUDE.local.md, __pycache__, .venv, recensement/)
> - le `CLAUDE.md` racine, moins de 200 lignes, factuel
> - `.claude/rules/python.md` avec un frontmatter `paths` ciblant `pipeline/**/*.py`
> - `CLAUDE.local.md` décrivant cette machine : PC bureau, accès Confluence disponible, token en variable d'environnement
> - l'arborescence de dossiers vides prévue par le brief
>
> Montre-moi le `CLAUDE.md` avant de l'écrire.

### 4.2 Vérifier que le contexte est chargé

Tape :

```
/context
```

Tu dois voir `CLAUDE.md` et `CLAUDE.local.md` dans la section des fichiers de mémoire. S'ils n'y sont pas, redémarre la session — les fichiers créés pendant une session ne sont pris en compte qu'au lancement suivant.

### 4.3 Premier commit

> Fais un premier commit avec tout ce qu'on vient de créer, puis pousse sur origin.

Laisse-le exécuter les commandes Git et regarde ce qu'il fait — c'est la meilleure façon d'apprendre Git sans lire de documentation.

---

## Bloc 5 — Le recensement ADF (40 min)

C'est le vrai test de la séance : lire de vraies pages Confluence et découvrir ce qu'elles contiennent.

### 5.1 Préparer l'exécution

> Le script `pipeline/src/recense_adf.py` recense les types de nœuds ADF d'un échantillon de pages Confluence. Il ne dépend que de `requests`.
>
> Installe la dépendance si besoin, puis lance-le en mode échantillon. Mes identifiants sont dans les variables d'environnement ATLASSIAN_EMAIL et ATLASSIAN_API_TOKEN.

Commande sous-jacente, si tu veux la lancer toi-même :

```bash
python pipeline\src\recense_adf.py --sample
```

### 5.2 Ce qui doit se passer

Le script explore les cinq pages racines, sélectionne jusqu'à 5 pages par type (CU, RG, MDD, API, JOB, générique), télécharge leur ADF et produit :

- `recensement/recensement_adf_AAAAMMJJ.md` — le rapport à lire
- `recensement/recensement_adf_AAAAMMJJ.json` — les données
- `recensement/fixtures/*.json` — l'ADF brut de chaque page échantillonnée

**Si l'échantillon tombe à côté** (peu de pages, mauvais types), force des pages précises :

```bash
python pipeline\src\recense_adf.py --pages 329318407,265453570
```

**Erreurs possibles** :

| Erreur | Cause probable |
|---|---|
| `401 Unauthorized` | Email ou token incorrect, ou terminal non rouvert après `setx` |
| `404` sur une page racine | ID de page erroné dans le script |
| `ERREUR : renseigner ATLASSIAN_EMAIL...` | Variables non visibles → rouvrir le terminal |

### 5.3 Analyser le résultat

> Lis `recensement/recensement_adf_*.md` et analyse-le. Trois questions :
> 1. Quels types de nœuds ne sont pas couverts par la table de normalisation de la section 3 du brief ?
> 2. Y a-t-il des `expand`, `layoutSection` ou `bodiedExtension` ? Combien, sur quelles pages ?
> 3. Les tableaux contiennent-ils des cellules fusionnées ou des listes imbriquées ?
>
> Propose ensuite une version complète de `contracts/normalisation_adf.md`.

### 5.4 Sauvegarder

> Commit le recensement et la table de normalisation, et pousse.

---

## Ce qui vient ensuite

Une fois le recensement analysé, la suite logique est le **bake-off** : convertir les mêmes 5 pages avec `marklas` puis `pyadf`, comparer les deux sorties, choisir. Les fixtures téléchargées au bloc 5 servent d'entrée — plus besoin de rappeler Confluence.

Instruction type pour la séance suivante :

> Écris `pipeline/src/bakeoff.py` : il lit les ADF de `recensement/fixtures/`, les convertit avec `marklas` puis avec `pyadf`, écrit les deux sorties côte à côte et produit un rapport de comparaison — nœuds perdus, warnings émis, différences de structure de tableau.

---

## Mémo des commandes Claude Code

| Commande | Effet |
|---|---|
| `/doctor` | Diagnostic de l'installation et de la configuration |
| `/context` | Ce qui est réellement chargé dans la session |
| `/memory` | Voir et éditer les fichiers de mémoire |
| `/init` | Générer un `CLAUDE.md` à partir du code existant |
| `/clear` | Repartir sur un contexte propre |
| `/compact` | Compresser l'historique d'une session longue |
| `Shift+Tab` | Cycler entre les modes, dont le mode plan |

**Trois réflexes utiles dès le début :**

1. **Demander un plan** avant toute modification non triviale — Claude montre ce qu'il compte faire avant de le faire.
2. **`/clear` entre deux sujets sans rapport** — un contexte propre coûte moins cher qu'un historique traîné.
3. **Si tu corriges deux fois la même chose, écris-la dans le `CLAUDE.md`.** C'est le seul critère fiable pour savoir ce qui mérite d'y figurer.

---

## Rappels de sécurité

- Le token Atlassian reste en variable d'environnement. Jamais dans un fichier versionné, jamais collé dans une conversation.
- `config.ini` et `CLAUDE.local.md` sont dans le `.gitignore` dès le départ.
- Avant le premier `push`, vérifie ce qui part : `git status` puis `git diff --cached`.
