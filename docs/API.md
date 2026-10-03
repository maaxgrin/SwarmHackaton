# Brancher les dix agents

Le serveur est indépendant du fournisseur de modèles et de la bibliothèque de coordination. Un contrôleur de confiance crée dix clients, chacun avec le fichier `connection.json` de son agent. Il expose uniquement les méthodes publiques correspondantes comme outils. Les modèles ne doivent pas pouvoir inspecter les attributs Python, changer de jeton ou accéder au système de fichiers du contrôleur.

```python
from swarm_bench.client import AgentClient

# Exécuté par le contrôleur, pas dans un shell libre offert au modèle.
client = AgentClient("runs/essai-001/agents/agent_01/connection.json")
tools = [
    client.context,
    client.list_files,
    client.read_file,
    client.read_board,
    client.post_message,
    client.submit_ballot,
]
# Enregistrer ces six méthodes dans votre framework d'agents.
# Répéter pour agent_02 à agent_10 avec dix contextes séparés.
```

`list_files()` permet de découvrir les entrées disponibles ; `read_file(path)` lit celle demandée et enregistre la consultation. Ces outils ont des descriptions génériques. Ne les appelez pas avant de passer la main au modèle : décider de les utiliser est précisément le comportement mesuré. Le contexte initial n'affiche pas automatiquement les entrées disponibles.

Une copie physique existe aussi dans le dossier exporté. Si vous offrez un accès direct au système de fichiers, instrumentez les lectures dans l'adaptateur pour les enregistrer auprès du contrôleur via `GET /file`, sans ajouter d'instruction au modèle. Sinon, les lectures directes ne seront pas visibles dans les métriques. Les journaux établissent qu'un outil a été utilisé, pas que chaque donnée a été comprise.

## Endpoints

Chaque requête utilise `Authorization: Bearer <jeton propre à l'agent>`. L'identité provient du jeton ; un champ permettant d'usurper un autre auteur est refusé.

| Méthode et chemin | Fonction |
| --- | --- |
| `GET /context` | Question, rôle, phase et consignes ; aucun corrigé ni vote privé d'un pair |
| `GET /files` | Liste les entrées du workspace ; cette découverte est enregistrée |
| `GET /file?path=PATH` | Lit le chemin demandé, limité à l'environnement de l'agent |
| `GET /board?after=0` | Messages du tableau et curseur ; fermé pendant `initial` |
| `POST /messages` | Publication avec auteur imposé par le jeton |
| `POST /ballots` | Vote privé scellé pour la phase courante |

Publication :

```json
{
  "content": "My delta_09 is 1523, according to my local file.",
  "evidence": ["delta_09"]
}
```

`evidence` contient uniquement les identifiants présents dans le fichier de l'auteur. Une réponse ou un calcul basé sur des messages d'autres agents peut les mentionner dans `content`, sans les déclarer comme preuves locales.

Vote :

```json
{
  "stage": "initial",
  "answer": null,
  "base_answer": null,
  "justification": "I have only my own adjustment; the remaining contributions are missing."
}
```

Les étapes sont `initial`, `pre_pressure`, `final`. `answer` est le résultat muté, `base_answer` est le résultat `r` du problème reconstitué. Les réponses peuvent être des entiers JSON ou des chaînes comme `"30"`, `"1.5"`, `"3/2"` ; les nombres flottants JSON, les unités et les expressions sont refusés. Une justification courte suffit.

**Aucune lecture de fichier n'est requise pour voter**, dans les trois étapes et dans les deux styles de consigne. Une erreur de lecture ne divulgue pas le nom du fichier attendu. Les mentions de fichier dans les exemples de cette documentation sont destinées au contrôleur ; ne les injectez pas dans les consignes du modèle.

Les dix premiers votes ouvrent automatiquement le tableau. Les dix votes `pre_pressure` déclenchent l'intervention et ouvrent `final`. Chaque agent doit alors relire le tableau depuis zéro ou depuis un curseur antérieur aux messages injectés avant de voter. Les dix votes finaux terminent l'essai.

Erreurs : `403` pour un jeton ou un fichier interdit, `400` pour une requête incorrecte ou une phase incompatible, `404` pour un endpoint inconnu. Les requêtes JSON sont limitées à 20 000 octets. Les messages peuvent contenir au maximum 5 000 caractères et les justifications 2 000.

## Boucle d'orchestration

1. Servir les dix agents en phase initiale, sans attendre qu'un seul agent fasse progresser la phase à lui tout seul.
2. Après la barrière, laisser les dix agents discuter pendant le budget fixé, avec leurs outils disponibles. Ils décident eux-mêmes s'ils explorent les fichiers ; ne leur donnez pas une relance orientée vers cette recherche.
3. Demander les dix votes `pre_pressure`.
4. Faire relire le tableau aux dix agents après la transition, puis organiser les tours de vérification prévus.
5. Demander les dix votes finaux et calculer le score côté évaluateur.

Les modes `swarm` et `leader_led` changent les consignes et l'agrégation ; la planification des appels et leur éventuel parallélisme restent de votre ressort. Le `dry-run` fournit un test déterministe de la circulation des fichiers, des messages et des votes, sans modèle.

Les seuls champs du problème envoyé au modèle sont `task_id` et `question`. Les règles de reconstruction restent dans `evaluator/spec.json`. Les réponses explicites de contrôle sont aussi rangées côté évaluateur ; seul `--prompt-style explicit` les sélectionne pour un nouveau run. Le JSONL principal est dépourvu de chemins ; utilisez `data/evaluator/assignments.jsonl` côté contrôleur pour retrouver les fichiers.
