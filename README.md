# Swarm Lab

**La base commune pour construire vos expériences de comportement collectif entre agents LLM.** Configurez le groupe, les prompts, les modèles, les outils et les informations privées ; observez les échanges et exportez les traces.

La **peer pressure** est la première expérience incluse. Le sacrifice, l'émergence d'un chef, l'écoute d'un chef désigné et l'usage du message board sont des axes de recherche à définir avec le groupe. L'outil ne leur attribue pas de score ou de protocole par défaut.

## Démarrage

```bash
git clone https://github.com/maaxgrin/SwarmHackaton.git
cd SwarmHackaton
python3 -m swarm_bench lab --port 8766
```

Ouvrir **http://127.0.0.1:8766**. Python 3.10+ suffit pour lancer l'interface. Le dépôt GitHub est public ; les profils et clés API restent locaux et ne sont pas inclus.

- Pour découvrir le moniteur sans clé : choisir **Peer pressure → Démonstration**, créer puis démarrer.
- Pour votre protocole : choisir **Expérience libre**, saisir la tâche, ouvrir **Prompts, fichiers, outils et modèles**, puis préparer les paramètres de chaque agent.
- Pour exécuter des LLM : créer vos profils dans **Modèles**, choisir un profil par agent, créer puis démarrer. Les clés peuvent rester vides pendant la préparation ; les serveurs locaux peuvent fonctionner sans clé.

## Ce que fournit la base commune

| Élément | Réglages et fonctionnement |
| --- | --- |
| Groupe | 1 à 32 agents, modèles identiques ou différents, chef facultatif |
| Scénarios | Peer pressure, expérience libre, communication, entraide avec Python, misalignement de groupe et ARC-AGI-3 |
| Prompts | Prompt commun personnalisable, consignes privées par agent, aperçu du prompt exact |
| Tâche et fichiers | Corpus inclus ou tâche libre ; fichiers texte / JSON privés par agent |
| Appels d'outils | Sélection globale ou par agent parmi les outils de fichiers, `read_board`, `post_note`, `submit_answer`, Python isolé et outils ARC |
| Message board | Tableau partagé ; lecture volontaire, publication automatique facultative ou injection directe d'une note dans le contexte des pairs |
| Exécution | Boucles indépendantes ; attente d'un pair après publication facultative, plafond de messages, température, budget de tokens, plafond d'appels, pause et arrêt |
| Chef et réponse | Désignation du chef séparée du choix de la réponse collective : pluralité, réponse du chef ou réponses individuelles seulement |
| Modèles | API compatible OpenAI Chat Completions, Anthropic Messages ; URL et modèle configurables, local ou distant |
| Partage | Import/export de configurations JSON, copie des réglages d'un essai, journaux JSON complets et comparaison CSV |

Un outil désactivé est réellement indisponible. À l'inverse, dans la peer pressure, `don't access files` est une consigne du prompt : `read_file` reste utilisable pour observer si l'agent transgresse. Une réponse mathématique incorrecte ne bloque ni la poursuite des essais ni l'analyse des transgressions.

Les modèles n'ont accès qu'aux fichiers de leur environnement via les outils exposés. Les exports complets sont destinés aux chercheurs : ils incluent les prompts, fichiers privés, conversations, appels et résultats d'outils. Les démonstrations sont scriptées et identifiées ; elles ne mesurent aucun LLM.

Python pour les agents s'exécute dans une machine virtuelle WASI isolée. Pour le préparer, lancer `python3 scripts/setup_python_runtime.py`. ARC-AGI-3 nécessite le runtime officiel et les jeux publics : `python3 scripts/setup_arc_runtime.py`.

## Préparer une expérience en équipe

1. Importer [la configuration libre minimale](examples/custom.json) ou [la peer pressure](examples/peer-pressure.json), ou utiliser le formulaire.
2. Définir la tâche, les informations disponibles, les consignes et les outils. Affecter vos propres profils de modèles.
3. Exporter la configuration et l'ajouter au dépôt pour la partager. L'import ne lance aucun essai.
4. Définir ensemble les critères de votre expérience et analyser les traces exportées. Aucun score général d'« esprit de swarm » n'est encore défini.

[Créer et étendre une expérience](docs/EXPERIENCES.md) · [Guide du laboratoire et peer pressure](docs/LABORATOIRE.md) · [Corpus et ancien protocole](docs/CORPUS.md)

## Données locales et clés

Le dépôt ne contient ni clé API, ni poids de modèles, ni journaux de nos essais locaux. Les profils et runs sont enregistrés dans `runs/lab/`, ignoré par Git. Une clé saisie dans l'interface reste en mémoire du serveur ; on peut aussi utiliser une variable d'environnement. Les profils sont propres à chaque installation.

Le serveur écoute uniquement sur `127.0.0.1`. L'isolation des fichiers est assurée par les outils du moteur ; ne donnez pas aux participants un shell sur l'ensemble du dépôt, qui contient les corrigés GSM8K réservés à l'évaluateur.

Le [préréglage restauré à sept agents](examples/peer-pressure-seven-agents.json), ses [instructions de chargement](docs/EXPERIENCES.md#préréglage-à-sept-contributions) et un [profil Terra sans clé](examples/provider-terra.json) sont inclus. Les dernières corrections de mesure, de budget et de sauvegarde sont documentées dans [les corrections de l’audit](docs/AUDIT_CORRECTIONS.md).

## Vérifier le projet

```bash
python3 -m unittest discover -s tests -v
python3 -m swarm_bench validate
```

Les tests des fournisseurs utilisent des serveurs factices, sans clé ni requête payante. Le corpus comprend 100 questions GSM8K mutées, leurs deux variantes et la provenance de la source sous [licence MIT](sources/GSM8K-LICENSE.txt).
