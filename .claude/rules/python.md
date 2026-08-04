---
paths: pipeline/**/*.py
description: Règles de code pour le pipeline Python
---

# Règles Python — pipeline

## Interdits absolus

- **Aucun appel LLM** dans le pipeline. Il est déterministe de bout en bout.
- **Aucun appel Jira**. Les macros Jira sont remises en clair dans le `.md` ; les appels
  restent dans le skill `confluence-outil-lien-jira`.
- **Aucun secret en dur** : ni token, ni email, ni chemin SharePoint nominatif.
  Lecture par `os.environ` (`ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`) puis `config.ini`,
  la variable d'environnement étant prioritaire.
- **Aucun nœud ADF ignoré silencieusement**. Un nœud non couvert par le normalizer
  est remonté en erreur dans le rapport. Un warning résiduel de la bibliothèque de
  conversion est un bug du normalizer, pas un détail.

## Écriture de fichiers

- **Atomique** : écrire dans un temporaire, puis `os.replace()`. Jamais de `.md` partiel visible.
- **Write-if-changed** : comparer le contenu avant d'écrire, sinon SharePoint resynchronise
  tout le corpus chaque jour.
- `PermissionError` (verrou OneDrive) : retenter avec une courte pause avant d'abandonner.
- Toujours `encoding="utf-8"` en lecture comme en écriture, explicite. Le contenu écrit dans
  un fichier — y compris les rapports `.md` — est en français accentué.
- Chemins via `pathlib.Path`. Slugifier les titres Confluence : ils contiennent `:` et
  d'autres caractères interdits sous Windows. Collisions détectées et signalées.

## Appels HTTP

- API REST Confluence v2 (`/wiki/api/v2`), Basic Auth (email + token).
- Corps en `atlas_doc_format` : `body.atlas_doc_format.value` est une **chaîne JSON**,
  double parsing obligatoire.
- HTTP 429 : backoff exponentiel en respectant `Retry-After`, concurrence plafonnée.
- Pagination v2 : suivre `_links.next` jusqu'à épuisement.

## Robustesse du run

- Une page en échec **n'interrompt pas** le run : elle est listée au rapport et retentée
  au run suivant.
- Tout ce qui est anormal finit dans le rapport `.md` + `.json` : pages en échec avec motif,
  multiexcerpts non résolus, nœuds non couverts, avertissements de parsing, pages non
  classifiées, durée.
- `parse_status` par page dans l'index croisé : `ok` / `partial` / `failed`, jamais absent.

## Style

- Python 3.11+, bibliothèque standard + `requests`. Toute autre dépendance se justifie.
- **Commentaires, docstrings et tout ce qui part vers `print()` en français sans accents** —
  la console Windows en cp1252 casse l'affichage (`recense_adf.py` suit déjà cette
  convention). Cette règle ne s'applique pas au contenu écrit dans un fichier.
- Fonctions courtes, un rôle par module (`confluence_client`, `inventory`, `multiexcerpt`,
  `normalizer`, `renderer`, `index_builder`, `mcd`, `report`).
- Un commentaire explique **pourquoi**, jamais **quoi**.
- Pas de `except Exception: pass`. Une exception capturée est journalisée et remontée au rapport.

## Tests

- `pipeline/fixtures/` contient des ADF figés et les `.md` attendus.
- **Toute modification du normalizer rejoue les fixtures.** C'est la seule protection contre
  une régression silencieuse de conversion.
- Les tests ne joignent jamais le réseau : ils lisent les fixtures.
