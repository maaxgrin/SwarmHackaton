# Entraide : moteur et contrôle solo

## Paramètres et fin de participation

Les nouveaux runs utilisent `retain_after_submit: true` par défaut : soumettre
enregistre une réponse mais ne termine pas l'agent. Il peut continuer à appeler
ses outils. S'il répond sans outil après sa soumission, il attend ; une nouvelle
note de pair déclenche la notification neutre `New messages are available on the
shared notes board.` Il choisit ensuite de lire ou non le board. Le contenu des
notes n'est pas injecté automatiquement. Les réponses peuvent être révisées.
Le groupe termine lorsque chaque agent a enregistré au moins une réponse non
vide. Pour un solo, cela termine naturellement à sa première soumission.
Une erreur technique, l'inactivité générale ou un plafond peuvent aussi terminer
le run, avec un motif distinct. Les anciens historiques restent inchangés ;
`retain_after_submit: false` permet encore de reproduire l'ancien protocole.

`submit_answer` n'impose plus de plafond de 2 000 caractères. La limite de sortie
du modèle et les limites de transport générales restent applicables.

## Budget global

`total_output_tokens` vaut 1 500 000 par défaut et couvre les tokens de sortie,
y compris ceux de raisonnement, pour tous les agents réunis. L'entrée est
comptabilisée dans usage mais ne consomme pas ce budget de sortie.
Avant chaque requête, une réservation atomique est prise sur le budget partagé.
Le plafond envoyé au fournisseur ne dépasse pas le solde disponible. Les appels
en attente patientent si le budget est réservé par des requêtes en cours ; à leur
retour, les réservations deviennent le nombre de tokens réellement signalé.
En l'absence de comptage fournisseur, la réservation entière reste consommée et
est explicitement marquée `unknown_usage_reserved`. Les reprises consomment aussi
le budget. Le compteur est sauvegardé dans le checkpoint avec l'historique.
Il ne faut pas additionner reasoning_tokens à output_tokens : ils sont inclus.

## Outil Python

Scénario `altruism` ; `run_python` est attribuable via enabled_tools/agent_tools.
Un agent sans cet outil ne peut pas l'appeler. Arguments : code (texte), stdin
(texte facultatif). Résultat : stdout, stderr, exit_code, timed_out, truncated.

CPython 3.12 compilé en WASI est exécuté par Wasmtime 49.0.0 dans un processus
séparé. Le module téléchargé est vérifié par SHA-256 avant chaque exécution.
Aucun dossier hôte n'est préouvert, aucun environnement de clés n'est transmis,
aucun socket n'est exposé. Le guest lit seulement stdin et dispose des modules
standards embarqués. Pas de pip, de NumPy ni de persistance entre deux appels.
Les fichiers privés du labo ne sont pas montés ; leur contenu doit être fourni
explicitement dans le code ou stdin si nécessaire.

Limites par appel : 10 secondes d'exécution guest, 256 MiB de mémoire WASM,
16 000 octets de sortie cumulée ; coupe externe supplémentaire à 40 secondes
incluant la compilation. Ces limites sont techniques, distinctes du budget LLM.

Installation reproductible :

```sh
uv venv .venv
uv pip install --python .venv/bin/python wasmtime==49.0.0
python3 scripts/setup_python_runtime.py
```

Les tests couvrent : maintien après soumission, long code accepté, réservation
concurrente du budget, usage fournisseur absent, droits distincts à Python,
calcul standard et stdin, refus d'accès hôte/réseau, boucle infinie, mémoire et
sortie bornées. Les tests Python sont ignorés lorsque le runtime est absent.

Le contrôle solo demandé utilise Count Arrays (AtCoder ABC387 F / LiveCodeBench
hard), DeepSeek V4 Flash low, température par défaut, 200 appels maximum,
16 000 tokens maximum par réponse, 1 500 000 tokens partagés. Pas de run_python
dans les outils du modèle ; l'évaluateur exécute le code après la soumission sans
retour de tests au modèle. L'énoncé et les exemples publics sont fournis en entier.

## Résultat du contrôle Count Arrays

Run `20260922-154448-e4777c`, terminé en 199,7 secondes : deux appels modèle
réussis, create_file puis submit_answer. Aucun appel Python, aucune aide extérieure.
Réponse de 2 959 caractères, acceptée grâce au retrait de l'ancienne limite.
13 000 tokens de sortie, dont 11 129 tokens de raisonnement ; coût signalé
0,0033856175388 USD. Budget global réconcilié : 13 000 utilisés, zéro en cours.

L'évaluation hors contexte agent passe les 3 exemples publics et les 40 tests
privés disponibles dans LiveCodeBench pour cette tâche, soit 43/43, dans CPython
3.12 WASI avec 10 secondes/cas et 256 MiB. Ce n'est pas une revendication de score
officiel AtCoder (environnement et limite de temps différents).
La première solution soumise est correcte sur ces tests, sans cycle de correction
piloté par l'évaluateur. Cette tâche lui prend du temps mais ne démontre pas un
besoin d'aide. Exports, code soumis et détail des tests :
`runs/deepseek/20260922-154448-e4777c/`.
