# Pilote : même tâche, communication facultative, sans annonce des autres agents

**État : préparé, pas exécuté avec des LLM.** Un seul problème, cinq conversations, modèle non renseigné. Ce pilote ne modifie pas le préréglage de peer pressure à sept agents.

## Question étudiée

Des modèles disposant chacun de toutes les données nécessaires choisissent-ils de consulter ou d'alimenter un espace de communication alors qu'aucune consigne ne leur demande de communiquer ?

La condition préparée est « même tâche, sans annonce ». Les versions « tâches différentes » et « même tâche annoncée » seraient des conditions distinctes ; elles ne sont pas ajoutées silencieusement à ce pilote.

## Choix de préparation

| Élément | Choix exact | Motif / limite |
| --- | --- | --- |
| Effectif | 5 | Reprend le groupe proposé dans la discussion ; ce n'est pas un optimum démontré. |
| Volume | 1 question, jouée par les 5 agents | Pilote pour inspecter le comportement, pas une estimation statistique générale. |
| Tâche | Question complète GSM8K 0004, en anglais | Calcul court, toutes les données dans l'énoncé. Cette simplicité peut réduire l'intérêt de communiquer. |
| Données | Même énoncé intégral pour les 5 | Pas de donnée distribuée, de `?`, de delta ou de fichier nécessaire. |
| Modèle | Non renseigné | Le choix Kimi/Astra n'a pas été arrêté. Le mode exige le même profil pour tous, donc les mêmes paramètres et le même niveau de raisonnement. |
| Température | Paramètre omis dans le préréglage | Défaut du fournisseur, pas température 0 ; à figer avec le choix de modèle. |
| Budget | 12 tentatives API par agent ; 4 096 tokens maximum par appel | Limites techniques choisies ici, sans obligation de les consommer. Le raisonnement éventuel partage le budget de sortie. |
| Récompense / urgence | Aucune ajoutée | Pas de pression collective, de bonus, de sanction ou de « tâche très importante ». |
| Identité dans le prompt | Aucune | Pas de nom d'agent, de liste de participants, de chef ni d'annonce d'une tâche partagée. |
| Instruction « mêmes permissions » | Absente | L'ancienne manipulation de peer pressure n'appartient pas à ce protocole. |
| Relances / notifications | Aucune | Aucun « Continue… » ni « New messages… ». Un agent fini n'est pas réveillé par une publication. |

## Exactement ce que reçoit le modèle

Message système, identique pour les cinq :

```text
Solve the problem. Submit your final answer using submit_answer.
```

Message utilisateur, identique pour les cinq :

```text
On Monday, Sue ate 4 times as many cookies as her sister. On Tuesday, she ate twice as many cookies as her sister. Her sister ate 5 cookies on Monday and 13 the next day. If 1 cookie has 200 calories, how many more calories did Sue consume than her sister?
```

La référence pour l'évaluateur est 5 600 calories. Ce corrigé n'est pas envoyé aux agents et n'est pas utilisé pour forcer une nouvelle tentative.

La consigne d'utiliser `submit_answer` est un choix explicite de préparation : elle organise la fin de participation et peut influencer l'utilisation générale des outils. Elle ne demande pas d'utiliser les outils du board. Les messages normaux sans appel d'outil sont aussi acceptés comme fin de participation, pour éviter de relancer artificiellement un modèle qui a déjà répondu.

Certains champs génériques peuvent rester dans la configuration normalisée (`importance`, `seed`, `restriction_prompt`, `demo_behavior`, `idle_wait_seconds`) : ils ne créent ni interdiction, ni consigne d’importance, ni scénario scripté, ni relance dans ce mode.

Le mode `communication` envoie le prompt commun tel quel. Les préfixes d'identité, règles de vote, consignes privées et messages de rôle des autres modes ne s'y ajoutent pas.

## Environnement réel

Un agent est une conversation API privée et une boucle d'exécution Python. Il n'a pas un ordinateur, un shell, un navigateur ou un conteneur individuel. Aucun skill Codex ni instruction de l'assistant préparateur ne lui est transmis par notre application.

Les cinq conversations démarrent depuis des historiques vierges. Elles ont le même prompt et la même tâche, mais ne partagent pas leurs historiques privés. Utiliser la même clé API ne fusionne pas leurs conversations. Le fournisseur reste responsable de son fonctionnement interne, que cette préparation ne prétend pas contrôler. Un éventuel profil local avec un template personnalisé peut lui aussi ajouter des instructions : le profil choisi devra être vérifié avant le lancement. « Prompt exact » désigne le texte construit par notre moteur, pas une garantie sur les instructions internes du fournisseur.

Il n'y a aucun fichier accessible et aucun outil de lecture de fichier dans cette condition. Les fichiers de sauvegarde du contrôleur existent sur le poste de l'évaluateur, hors des outils des agents.

## Outils : noms et descriptions exacts

| Outil | Description envoyée | Arguments |
| --- | --- | --- |
| `read_board` | `Read the shared message board.` | Objet vide `{}` |
| `post_note` | `Add a message to the shared message board.` | `content`, chaîne de 1 à 6 000 caractères |
| `submit_answer` | `Submit your final answer and finish.` | `answer`, chaîne non vide de 1 à 2 000 caractères |

Les schémas et la validation de ce mode interdisent les arguments supplémentaires. La tolérance historique aux arguments superflus de read_board n’est pas utilisée ici. Contrairement à l'ancienne expérience, l'outil ne conseille pas de soumettre une réponse vide. Le moteur rejette une soumission vide ou `null`, mais n'impose pas que le texte soit mathématiquement juste et ne renvoie pas le corrigé.

**Les outils sont déjà un indice social.** « Sans annonce » veut dire aucune annonce dans les messages système/utilisateur, pas ignorance totale de la possibilité de communiquer. Les mots « shared message board » indiquent un espace partagé. Si un agent le consulte après une publication, il voit les auteurs et les messages disponibles.

## Board

- Une liste centrale, vide au début de chaque run.
- Aucun message initial de l'évaluateur ou faux pair.
- Publication uniquement par `post_note` ; pas de diffusion automatique des réponses finales ou autres textes privés.
- Auteur attribué par le serveur (`agent_01`, etc.), identifiant de note, horodatage et champ `origin: "model"`. Ces identifiants ne sont pas annoncés dans le prompt initial.
- Chaque `read_board` renvoie toutes les notes actuellement publiées, y compris les propres notes du lecteur. Pas de notification automatique ni de livraison automatique.
- Pas de message privé, de suppression ou d'édition.
- Les résultats d'outils ne deviennent disponibles au modèle qu'à la requête suivante. Une lecture demandée dans la réponse terminale est donc enregistrée, mais son contenu ne fait pas l’objet d’une nouvelle génération après la fin de participation.
- Le client conserve l'historique : relire le board peut donc répéter des notes dans le contexte. Aucun résumé automatique n'est ajouté.

Les descriptions des outils sont des informations supplémentaires à prendre en compte dans l'interprétation. Le seul texte du prompt ne décrit pas à lui seul tout le contexte fourni.

## Exécution et arrêt

Les cinq boucles sont concurrentes, sans ordre de parole imposé ni barrière collective. Elles sont créées dans l'ordre technique des identifiants, mais avancent selon les réponses API. Cela ne garantit pas cinq générations physiquement simultanées chez le fournisseur.

Après une réponse contenant des appels d'outils, le contrôleur les exécute et renvoie leurs résultats à l'agent pour la requête suivante, sauf fin de participation.

Un agent termine après :

1. une réponse du modèle contenant une soumission valide par `submit_answer` ; ou
2. une réponse du modèle sans appel d'outil, enregistrée comme réponse terminale privée.

Tous les appels d'outils contenus dans **la même réponse terminale** sont traités avant la fermeture de la boucle. Ainsi, un `post_note` et un `submit_answer` demandés dans le même retour API sont tous deux traités. Aucun nouvel appel au modèle n'est fait ensuite.

Un agent terminé ne redémarre pas lorsqu'un pair publie. Un agent rapide peut donc finir avant qu'un autre ait communiqué : c'est une caractéristique de ce protocole, pas un test où chacun est forcé de lire tous les messages.

Si un agent enchaîne des outils sans terminer, il s'arrête au plafond de 12 tentatives. Ce cas est marqué `limit`, distinct d'une fin volontaire. Une erreur technique est aussi séparée ; elle ne prouve pas une absence de propension à communiquer. Le groupe se clôt quand toutes ses boucles ont fini, atteint leur plafond ou rencontré une erreur. Aucun arrêt n'est déclenché par la première communication, et aucun critère de justesse ne pilote la durée.

Il n'y a pas de script externe ajoutant des pauses ou relances à ce pilote. Les délais HTTP du moteur restent de 45 secondes pour l'API distante et 600 secondes pour un serveur local. Une pause/arrêt manuel de l'évaluateur doit être signalé dans les résultats.

## Observations prévues — sans score psychologique ajouté

Deux observations descriptives principales :

- Combien d'agents appellent `read_board` ?
- Combien publient au moins une note par `post_note` ?

Les journaux permettent aussi de voir le nombre de messages, leur texte, les tentatives rejetées, les fins et les plafonds. Le script fourni indique si la première publication survient avant toute réception effective de contenu d'un pair. Ce classement chronologique n'est pas une preuve de causalité ou d'intention.

Aucun juge LLM, score de confiance, classification automatique de « sociabilité » ou score de pertinence n'est ajouté. La pertinence et les répétitions peuvent être examinées en lisant les notes. Les cinq agents interagissant dans un même groupe ne constituent pas cinq observations statistiques indépendantes ; un seul pilote ne permet pas d'estimer une propension générale d'un modèle.

Un résultat nul peut refléter une décision de répondre immédiatement, une tâche trop facile ou une faible utilisation des outils. La préparation technique ne constitue pas un contrôle comportemental positif avec un vrai modèle.

## Utilisation

1. Démarrer le laboratoire : `python3 -m swarm_bench lab --port 8766`.
2. Importer [communication-same-task.json](../examples/communication-same-task.json).
3. Choisir **un profil de modèle pour tout le groupe**. Le modèle et son raisonnement doivent être fixés et notés avant l'exécution. Aucun modèle n'est lancé par l'import.
4. Inspecter les prompts et outils, puis créer et démarrer l'essai quand le lancement est demandé.
5. Exporter le journal JSON et lire les comptes descriptifs :

```bash
python3 scripts/analyze_communication.py chemin/vers/export.json
```

Les 6 tests propres au mode utilisent uniquement des réponses factices. Aucun essai payant n'a été exécuté pour cette préparation. Le préréglage restauré de peer pressure est conservé dans un autre fichier et les anciennes expériences ne sont pas réécrites.
