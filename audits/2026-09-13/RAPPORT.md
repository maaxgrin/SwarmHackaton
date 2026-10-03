# Audit de l'environnement des agents — Swarm Lab

**Date : 13 septembre 2026. Verdict : la base fonctionne, mais deux défauts prioritaires empêchent de considérer les mesures et les budgets comme entièrement fiables.** Cinq anomalies ont été reproduites. L'isolation des fichiers, les outils désactivés et les boucles normales respectent les contrôles effectués.

L'audit porte sur le laboratoire du projet `SprintHF`, son moteur `LabRun`, ses adaptateurs, son serveur local et ses journaux. Il ne porte pas sur la configuration générale de Codex. Le point de départ est le commit `0e9be46`, avec sept fichiers déjà modifiés localement, notamment le moteur et les tests. Les constats décrivent ce code local. Les seuls fichiers ajoutés par cet audit se trouvent dans ce dossier.

## Vérifications effectuées

| Vérification | Résultat |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | **45 tests réussis**, incluant le laboratoire et l'ancien protocole |
| `python3 -m swarm_bench validate` | **100 questions, 200 variantes, 9 704 contrôles réussis** |
| Reproductions ciblées de cet audit | **3 contrôles réussis, 5 invariants en échec** |
| Serveur en cours sur `127.0.0.1:8766` | Accessible ; 100 tâches et les cinq outils attendus |
| Aperçu du serveur comparé au code sur disque | Identique pour le solo peer pressure avec restriction en tête et le solo libre |
| Ollama sur `127.0.0.1:11434` | Accessible ; les quatre profils locaux renseignés référencent des modèles installés |
| Cinquième profil | Brouillon sans URL ni modèle ; il n'est pas prêt à démarrer |
| Historique local | 27 essais recensés, dont 24 marqués `live_models` et trois démonstrations |

Les sondes utilisent des fournisseurs factices et des dossiers temporaires. Aucun nouvel appel de génération LLM n'a été lancé. L'accès au serveur existant s'est limité à la lecture et à deux aperçus sans création d'essai. Le diagnostic ne certifie donc pas la qualité actuelle des réponses de chaque modèle réel.

Les traces locales ont été examinées sans les recopier dans ce dossier. Elles couvrent plusieurs versions du moteur : elles ne constituent pas toutes des validations du code actuel.

## Anomalies confirmées

### A1 — P1 : une lecture est classée « après exposition » avant que le modèle ait reçu les messages

**Code :** [lab_engine.py](../../swarm_bench/lab_engine.py), lignes 311–314 et 401–425.

Un pair publie une note. L'agent restreint, qui ne l'a pas encore reçue, produit **une seule réponse** contenant deux appels : `read_board`, puis `read_file`. Le moteur exécute le premier outil et met immédiatement à jour `exposures`. Il exécute ensuite le second et classe la lecture comme postérieure à une exposition aux pairs.

La reproduction donne `after_peer_exposure = 1` et `before_peer_exposure = 0`, alors que le contenu de la note ne figurait dans **aucune requête envoyée au modèle**. Les deux décisions d'outils étaient déjà produites avant leur exécution.

**Conséquence :** la mesure confond l'ordre d'exécution des outils avec les informations disponibles lorsque le modèle a choisi son action. Le nombre de transgressions reste correct, mais leur classement temporel peut être faux.

**Correction proposée :** conserver, pour chaque réponse du modèle, les notes incluses dans sa requête. Attribuer aux actions de cette réponse cette exposition préalable. Les résultats de `read_board` deviennent disponibles pour une décision ultérieure. Distinguer dans les traces « résultat d'outil récupéré » et « résultat envoyé au modèle », avec des identifiants de requête et d'appel.

**Portée constatée :** défaut reproduit avec un modèle factice ; aucun message contenant simultanément `read_board` et `read_file` n'a été retrouvé dans les 24 historiques LLM locaux examinés. Cet audit n'attribue donc pas ce défaut aux transgressions déjà observées.

### A2 — P1 : les réponses tronquées échappent au compteur et au plafond d'appels

**Code :** [providers.py](../../swarm_bench/providers.py), lignes 153–168 ; [lab_engine.py](../../swarm_bench/lab_engine.py), lignes 401–410 et 438–440 ; [lab_server.py](../../swarm_bench/lab_server.py), lignes 104–154.

L'adaptateur lève une erreur lorsque la réponse atteint le plafond de tokens. Le compteur n'est incrémenté qu'après un retour réussi de l'adaptateur. La requête effectivement effectuée et les tokens annoncés par cette réponse sont perdus pour la comptabilité. Un essai en erreur peut ensuite être repris avec le même compteur.

**Reproduction :** avec `call_limit = 1`, trois démarrages/reprises produisent **trois requêtes HTTP simulées**, mais les compteurs restent à **zéro appel et zéro token**. Les réponses factices annoncent au total 444 tokens qui ne sont pas enregistrés.

**Conséquence :** sous-estimation des ressources consommées et dépassement du budget cumulé par reprises successives. Il n'y a pas de relance automatique infinie ; le dépassement reproduit passe par « Reprendre ». Des erreurs de troncature existent aussi dans les historiques locaux, sans que leur coût puisse être reconstitué depuis ces compteurs.

**Correction proposée :** comptabiliser chaque tentative d'appel avant l'envoi, distinguer tentatives, succès et erreurs, puis conserver l'usage disponible même si la réponse est inutilisable. Appliquer le plafond au cumul des tentatives, reprises comprises. Ne pas compter une validation de profil échouée avant tout appel comme une requête envoyée.

### A3 — P2 : modifier un profil global change le modèle d'un essai existant

**Code :** [lab_engine.py](../../swarm_bench/lab_engine.py), lignes 401–411 ; [providers.py](../../swarm_bench/providers.py), lignes 70–90.

Chaque appel résout à nouveau le profil global par son identifiant. Dans la reproduction, le premier appel utilise `fake-A`. Après modification du même profil, le deuxième appel du même agent et du même essai utilise `fake-B`, alors que la configuration de l'essai conserve le même identifiant de profil.

**Conséquence :** risque de changer involontairement une condition expérimentale en préparant d'autres expériences ou entre une pause et une reprise. Les événements `model_response` conservent correctement le profil réellement employé ; la dérive reste détectable dans l'export détaillé.

**Correction proposée :** figer une copie des paramètres non secrets de chaque profil au premier démarrage. Une modification globale doit s'appliquer aux nouveaux essais. Si un changement en cours d'essai est souhaité, en faire une intervention explicite et journalisée. Aucun gel de secret en clair sur disque n'est nécessaire.

### A4 — P2 : une interruption de sauvegarde peut rendre un historique inexploitable

**Code :** [lab_engine.py](../../swarm_bench/lab_engine.py), lignes 269–276 ; [common.py](../../swarm_bench/common.py), fonction `write_json` ; [lab_server.py](../../swarm_bench/lab_server.py), lignes 75–102.

`state.json` est remplacé via un fichier temporaire. `histories.json` est réécrit directement, avec troncature du précédent contenu. Une interruption pendant cette écriture peut laisser du JSON incomplet.

**Reproduction avec panne injectée :** une écriture d'historique est interrompue après un fragment de JSON. Après rechargement du gestionnaire, l'essai apparaît dans les archives, mais son export échoue avec `JSONDecodeError`.

**Conséquence :** perte de consultabilité et d'export d'un essai après incident d'écriture ou arrêt au mauvais moment. Aucune corruption de ce type n'a été constatée dans les fichiers locaux lus : il s'agit d'un test de résistance aux pannes.

**Correction proposée :** remplacer également les historiques de manière atomique et préserver la dernière version valide. Pour garantir la cohérence entre état et conversations après incident, employer un instantané commun ou des générations d'instantanés avec un pointeur de validation. Tester aussi une interruption entre la sauvegarde d'une action et celle de son résultat dans l'historique.

### A5 — P2 : le prompt solo libre demande une collaboration avec des agents inexistants

**Code :** [lab_engine.py](../../swarm_bench/lab_engine.py), lignes 44, 120–122 et 239–244.

Avec `scenario = custom`, un agent et le prompt commun par défaut, le système indique d'abord que l'agent travaille seul, puis lui demande de travailler avec les autres participants. Le défaut a aussi été confirmé via l'aperçu du serveur actuellement ouvert.

**Conséquence :** le témoin solo libre reçoit des instructions contradictoires et peut chercher des contributions qui n'existent pas. Le solo du préréglage peer pressure passe ses tests ; c'est la branche libre qui manque de couverture.

**Correction proposée :** choisir un défaut commun adapté à l'effectif, tout en conservant un prompt commun explicitement personnalisé par le chercheur. Ajouter un test couvrant `custom` avec un agent et un prompt absent ou `null`.

## Fonctionnements confirmés et limites

- **Fichiers privés :** six formes de chemins hors périmètre sont rejetées dans la sonde supplémentaire. Une lecture autorisée renvoie uniquement le fichier de l'agent appelant. Les contenus sont fournis par le dictionnaire privé du moteur, sans accès shell.
- **Outils :** un outil désactivé est refusé à l'exécution. La restriction textuelle de non-lecture reste volontairement transgressable, conformément au protocole.
- **Prompts :** les tests vérifient que les restrictions privées ne sont pas ajoutées aux prompts des pairs, que la position en tête fonctionne et que les fichiers ne sont pas préchargés.
- **Coordination :** les tests vérifient le démarrage indépendant des agents, l'accès immédiat au tableau, les règles de pluralité et de chef, ainsi que la distinction entre publication explicite et automatique.
- **Budget normal :** les appels réussis d'une boucle d'outils s'arrêtent au plafond prévu. Le problème A2 concerne les appels échoués, notamment les réponses tronquées.
- **Pause, reprise et arrêt :** les sondes confirment l'absence d'appels suivants après prise en compte de la commande et la reprise après pause. En revanche, la requête HTTP déjà engagée va à son terme et **ses outils sont encore exécutés**, y compris après une demande d'arrêt. Les événements `operator_stop` marquent donc une demande, pas une coupure immédiate des observations. Le délai HTTP local configuré peut atteindre 600 secondes.
- **Secrets et archives :** les tests existants vérifient qu'une clé de test n'est ni persistée ni retournée dans les profils, que les redirections fournisseurs sont refusées et que les origines tierces sont rejetées. Le rechargement des archives ne relance aucun modèle.

Le serveur reste destiné à l'évaluateur local. L'isolation testée est celle des outils proposés aux LLM ; elle ne transforme pas l'ensemble du dépôt en sandbox pour un agent auquel on donnerait séparément un shell.

## Reproduire et décider

Depuis la racine du projet :

```bash
python3 audits/2026-09-13/check_environment.py
```

Le script utilise uniquement la bibliothèque standard, produit du JSON et renvoie **le code 1 tant qu'au moins un invariant échoue**. Les résultats de cette exécution sont conservés dans [results.json](results.json). Il n'écrit aucun essai dans `runs/lab` et n'ouvre aucune connexion réseau.

**Priorité : corriger A1 et A2 avant une campagne comparative, puis A3 à A5.** Ajouter les cas correspondants à la suite de non-régression et refaire un court parcours avec les modèles locaux choisis permettra ensuite de distinguer les garanties du moteur des capacités réelles de ces modèles. Les démonstrations scriptées et les tests factices ne suffisent pas à établir qu'un modèle respecte une consigne ou cède à la pression.
