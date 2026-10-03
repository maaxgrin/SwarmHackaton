# Corpus GSM8K et outil historique

Cette page décrit le corpus inclus et la commande historique `serve`. Pour le moteur commun à effectif variable et les expériences libres, voir le [README](../README.md) et le [guide des expériences](EXPERIENCES.md).


**100 problèmes GSM8K où des données utiles existent dans l'environnement, sans que l'énoncé dise d'aller chercher un fichier.** Dix agents peuvent explorer, discuter, répondre ou s'abstenir. La lecture n'est jamais imposée par le serveur : on peut donc mesurer l'oubli d'explorer.

- `data/questions.jsonl` : **100 questions prêtes à charger**, uniquement `task_id` et `question`, sans nom de fichier ni métadonnée de traitement.
- `data/evaluator/assignments.jsonl` : association aux fichiers et aux variantes, réservée au contrôleur. Le lot principal contient 50 cas avec fichier complet et 50 cas distribués.
- `data/tasks/` : chaque problème existe aussi dans **les deux versions**, soit 200 instances appariées et 2 000 fichiers d'indices.
- `data/evaluator/` : réponses, solutions sources et provenance, réservées à l'évaluateur.
- `swarm_bench/` : générateur reproductible, tableau de messages HTTP, outils par agent et calcul des scores.
- `docs/EXEMPLE.md` : un problème expliqué avec ses dix contributions.
- `docs/PROTOCOLE.md` : protocole de pression sociale et de leadership.
- `docs/API.md` : branchement à votre système d'agents.

## Comment les questions sont mutées

Les problèmes viennent du [test officiel GSM8K](https://github.com/openai/grade-school-math/blob/3101c7d5072418e28b9008a6636bde82a006892c/grade_school_math/data/test.jsonl), sous [licence MIT](../sources/GSM8K-LICENSE.txt). La version source, son empreinte SHA-256 et les indices sélectionnés sont conservés.

1. **50 cas avec `?`** : une seule quantité de l'histoire est remplacée par `?`, et la correction finale est indiquée par `c = ?`.
2. **50 cas avec omission** : l'histoire est complète, mais le calcul demandé fait intervenir « the case correction » sans en donner la valeur.
3. Le problème source donne `r`. Le résultat demandé est `Y = multiplicateur × r + c`. La définition de `c` et ses dix contributions sont dans un fichier nommé sobrement `notes.json`, découvrable avec des outils génériques. Aucune consigne ne mentionne ce fichier dans le mode implicite.

Les deux types de lacunes sont équilibrés avec les deux répartitions de fichiers : 25 problèmes dans chacune des quatre combinaisons du lot principal. Dans les notes, `c` est défini comme la somme de `delta_01` à `delta_10`. Cette formule détaillée n'est pas révélée avant la découverte. Les réponses numériques des 100 problèmes de la version précédente sont conservées.

Le mode **`implicit` est le défaut**. Le mode **`explicit`** ajoute à la même question une consigne précisant quel fichier consulter et comment réunir les contributions. Il sert de contrôle apparié, avec exactement les mêmes fichiers et le même corrigé. Même dans ce contrôle, un agent peut ignorer la consigne et voter sans avoir lu.

Les quantités et la solution mathématique du problème d'origine sont conservées : **la mutation porte sur l'accès aux données et le calcul final**, pas sur une réécriture numérique complète de l'histoire. Les énoncés et les consignes aux agents restent en anglais pour conserver le texte source. La documentation est en français.

| Version | Contenu du fichier privé de chaque agent | Collaboration nécessaire pour déterminer FINAL |
| --- | --- | --- |
| `complete` | Copie complète des paramètres et des dix ajustements | Non : contrôle de consultation de fichier et de pression sociale |
| `split10` | Sous-ensemble de paramètres et exactement un ajustement indépendant | Oui : les dix contributions sont nécessaires |

Dans `split10`, un agent peut avoir un ajustement sans paramètre de l'énoncé. Sa contribution reste nécessaire. L'affectation des indices est mélangée. Les deux versions d'un même problème ont exactement la même information totale et la même réponse finale. Connaître par cœur la réponse GSM8K ne suffit pas à déterminer le nouveau résultat. Une réponse devinée reste possible ; on ne prétend pas prouver qu'une valeur correcte résulte d'une lecture attentive.

## Vérifier immédiatement

Depuis ce dossier, avec Python 3.10 ou supérieur, sans dépendance externe :

```bash
python3 -m swarm_bench validate
python3 -m unittest discover -s tests -v
python3 -m swarm_bench dry-run --variant split10 --pressure majority_wrong
```

Le `dry-run` utilise explicitement un oracle scripté qui lit le corrigé : **il vérifie le fonctionnement du protocole, pas les performances d'un modèle**. Aucun résultat d'évaluation de LLM n'est fourni dans cette livraison.

## Ouvrir une expérience avec dix agents

```bash
python3 -m swarm_bench serve \
  --task gsm8k_0001 \
  --variant split10 \
  --orchestration leader_led \
  --pressure leader_wrong \
  --run-dir runs/essai-001
```

Le serveur écoute sur `127.0.0.1:8765`. Il exporte dix dossiers sous `runs/essai-001/agents/`, chacun avec `problem.json`, `notes.json`, `connection.json` et des consignes génériques. Chaque jeton ne permet d'accéder qu'au fichier de son agent et au tableau commun. Les votes individuels restent privés. Ajouter `--prompt-style explicit` pour le contrôle.

Le contexte initial ne contient ni liste de fichiers, ni nom du fichier utile, ni règle de partage, ni avertissement demandant de vérifier les fichiers. Les outils `list_files()` et `read_file(path)` sont disponibles sans être automatiquement appelés. **Ne préchargez pas les notes dans le prompt et ne demandez pas aux agents de chercher un fichier.** Les dossiers `evaluator/`, le manifeste et les corrigés ne font pas partie du contexte des agents.

La commande historique **`serve` n'exécute pas les modèles** : elle permet de brancher son propre orchestrateur à dix participants. La nouvelle commande **`lab`**, décrite en haut de cette page, fournit l'interface et l'exécution des modèles avec un effectif variable. Le client de l'ancien protocole reste décrit dans [API.md](API.md).

Donnez à chaque modèle uniquement ses outils autorisés, ou montez uniquement son dossier dans un conteneur distinct. **Des dossiers voisins ne constituent pas une isolation système.** Un agent disposant d'un shell sur tout ce dépôt pourrait lire les corrigés ou les fichiers des autres. Le contrôleur conserve les jetons ; il expose les méthodes de l'agent, sans lui transmettre les autres clients ni l'objet `Experiment`. L'API est locale et n'est pas conçue pour être exposée sur Internet.

Après les trois phases et les trente votes :

```bash
python3 -m swarm_bench score --run-dir runs/essai-001
```

Le journal et les votes sont dans `state.json`, les métriques dans `score.json`. Chaque action est enregistrée. Arrêt par `Ctrl-C` ; la reprise d'une expérience interrompue n'est pas implémentée. Utilisez un nouveau dossier pour chaque essai, car les dossiers existants ne sont pas écrasés.

## Conditions disponibles

| Axe | Valeurs |
| --- | --- |
| Accès à l'information | `complete`, `split10` |
| Indication de recherche | `implicit` par défaut, `explicit` pour le contrôle |
| Coordination | `swarm` : décision à la pluralité ; `leader_led` : décision du coordinateur |
| Pression après partage | `none`, `majority_wrong`, `leader_wrong`, `peer_wrong` |

Le corpus principal comprend exactement 100 instances. Les 100 problèmes × 2 répartitions × 2 coordinations × 4 pressions donnent **1 600 essais par style de consigne**, soit 3 200 pour la comparaison implicite/explicite complète, avant répétitions. Aucun de ces essais avec modèles n'est lancé automatiquement.

Les métriques incluent la consultation avant chaque vote, les réponses données sans lecture locale, leur exactitude et le premier agent à lister/lire les fichiers ou partager une preuve. Un autre agent peut transmettre une information sur le tableau : une réponse sans lecture locale n'est donc pas automatiquement une hallucination. Le rôle de leader tourne équitablement ; voir le [protocole](docs/PROTOCOLE.md).

## Régénérer ou passer à 1 000 questions

```bash
python3 -m swarm_bench generate --count 100 --seed 42 --output data-seed42
python3 -m swarm_bench generate --count 1000 --seed 42 --output data-1000
python3 -m swarm_bench validate --data data-1000
```

La sélection est déterministe et sans doublon parmi les problèmes éligibles. La source officielle complète est incluse dans `sources/`, réservée au contrôleur. Une même graine reproduit la sélection, les ajustements et les propriétaires. Pour de nouvelles évaluations, utilisez des graines non communiquées aux agents et des contextes ne contenant pas les corrigés. Ce dépôt et son archive complète sont des **outils pour l'évaluateur**, pas des environnements à donner intégralement aux participants.
