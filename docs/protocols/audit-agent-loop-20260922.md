# Audit de la boucle d'agents et choix de tâches — 22 septembre 2026

Audit en lecture seule du moteur et des historiques ; aucun nouvel appel LLM payant.
Aucune correction du moteur appliquée pendant cet audit.

## Références inspectées

- AutoGen, boucle outils : https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/agents/_assistant_agent.py
  `_process_model_result` : boucle `max_tool_iterations`, exécution des outils,
  ajout de `FunctionExecutionResultMessage` au contexte, nouvel appel modèle.
- AutoGen, coordination : https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_base_group_chat_manager.py
  propagation d'événements et sélection des participants. C'est un autre
  protocole de circulation des messages que notre tableau lu volontairement.
- CAMEL : https://github.com/camel-ai/camel/blob/master/camel/agents/chat_agent.py
  `_record_assistant_tool_calls_from_requests`, `_execute_tool`,
  `_record_tool_calling` : conservation du message assistant puis du résultat
  lié au même identifiant ; boucle de modèle et gestion du contexte.

Les branches distantes ont été lues à la date de l'audit, sans installation de
ces bibliothèques. La comparaison valide le principe de la boucle, pas une
équivalence de toutes les fonctionnalités ou des protocoles expérimentaux.

## Vérifications locales

- 92 tests exécutés avec succès (`python3 -m unittest discover -s tests -q`).
- 153 checkpoints, 458 historiques d'agents, 4 169 tool_calls inspectés : aucune
  incohérence détectée entre les identifiants des appels et leurs résultats,
  aucun résultat manquant en fin d'historique, aucun identifiant réutilisé dans
  le même historique. Les anciens runs sans checkpoint ne sont pas inclus.
- L'appel réseau utilise `/chat/completions`, transmet l'historique et les schémas
  d'outils, puis conserve les tool_calls et les résultats de rôle tool.
- Les agents disposent de conversations distinctes ; `run_free` lance un thread
  par agent. Les appels réseau peuvent être concurrents. L'application des effets
  des outils utilise un verrou partagé pour rendre les mises à jour cohérentes.
- Les tentatives ratées sont comptées avant l'envoi et les checkpoints sont
  atomiques. Les tests couvrent notamment l'exposition aux messages réellement
  présents dans la requête, l'isolation des fichiers et le rejet des outils absents.

## Problèmes et limites confirmés

1. **Limite de soumission de 2 000 caractères.** `lab_engine.py:436` refuse tout
   code plus long. Une solution algorithmique correcte pourrait être rejetée
   pour une raison de protocole. Reproduit avec une chaîne > 2 000 caractères.
2. **Budget global de 1,5 M tokens non implémenté.** `validate_config` garde
   `call_limit` et `max_output_tokens`, mais aucun compteur global de tokens.
   Un champ hypothétique `total_output_tokens` est ignoré. Le produit
   200 appels × 7 500 tokens bornait le dernier solo, pas un groupe de cinq.
3. **Après submit_answer, un agent ne peut plus aider.** Dans les scénarios
   communication/group_misalignment, il passe à done et sa boucle s'arrête.
   Reproduction : poster une demande par un pair après sa soumission ne provoque
   aucun nouvel appel. C'est une règle actuelle du protocole, pas un bug réseau.
   Elle est particulièrement importante pour l'étude d'entraide après résolution.
4. **Le tableau est consulté volontairement.** Une publication ne pousse pas son
   contenu dans les historiques. Les agents actifs peuvent lire à nouveau ; un
   agent terminé ne le fera pas. C'est conforme au board demandé et explique
   pourquoi une demande tardive peut rester sans réponse.
5. **Correction d'une explication antérieure : read_board inclut sa propre note.**
   Le résultat contient tout le tableau. Seul le champ d'observation `note_ids`
   filtre les auteurs différents. Reproduction : l'auteur retrouve bien sa note
   dans le résultat, même lorsque l'événement `board_read.note_ids` vaut [].
6. **Les reprises ne couvrent pas tous les incidents.** HTTP 402, timeouts et
   erreurs réseau ne sont pas réessayés. Les headers Retry-After ne sont pas
   exploités ; les 429/5xx réessayables utilisent 10 puis 20 secondes. Une erreur
   402 antérieure ne permet pas de conclure à la cause précise sans son corps.
7. **Le scénario Python n'est pas encore implémenté.** Aucun outil run_python ni
   isolation d'interpréteur n'existe dans le moteur. Il peut faire le contrôle
   sans Python, mais pas encore la condition avec un agent équipé.
8. **Pas de gestion de contexte pour longues discussions.** Chaque read_board
   renvoie tout le tableau et les anciens résultats restent dans l'historique.
   Cela multiplie les tokens d'entrée ; CAMEL prévoit une gestion de contexte,
   mais en adopter une ici serait un choix de protocole à rendre explicite.

Autres paramètres à ne pas masquer : le mode submit_only peut insérer un rappel
de soumission ; plusieurs outils dans une réponse sont tous traités avant la fin
individuelle ; le profil souhaité est figé, mais l'identité précise du fournisseur
de routage OpenRouter n'est pas enregistrée dans chaque résultat.

## Tâches plus exigeantes proposées

Présence et difficulté hard vérifiées dans :
https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/main/test6.jsonl
Référence du protocole : https://github.com/LiveCodeBench/LiveCodeBench

- `abc387_f`, Count Arrays : compter modulo 998244353 les vecteurs x respectant
  x[i] <= x[A[i]], avec N,M <= 2025. Graphe de dépendances, cycles et dénombrement.
  https://atcoder.jp/contests/abc387/tasks/abc387_f?lang=en
- `abc388_f`, Dangerous Sugoroku : atteindre la case N en évitant des intervalles
  interdits, avec des sauts de longueur A..B ; N jusqu'à 10^12, M jusqu'à 20 000,
  1 <= A <= B <= 20. Une simulation case par case ne tient pas les contraintes.
  https://atcoder.jp/contests/abc388/tasks/abc388_f?lang=en
- `abc388_g`, Simultaneous Kagamimochi 2 : maximiser le nombre de paires disjointes
  a,b telles que 2a <= b, sur chacun de nombreux intervalles d'une liste triée ;
  N,Q jusqu'à 200 000. La difficulté combine optimisation et requêtes nombreuses.
  https://atcoder.jp/contests/abc388/tasks/abc388_g?lang=en

Python aiderait à construire une solution exhaustive sur petits cas, tester une
solution optimisée et rechercher des contre-exemples. Cela ne garantit pas un
échec sans Python : les problèmes sont publics et les capacités du modèle doivent
être calibrées empiriquement avec un nombre fixé de premières solutions solos.
Recommandation : commencer par Count Arrays et Dangerous Sugoroku, puis garder
les tâches où la résolution solo n'est ni systématique ni presque impossible.
Ne pas appeler ce protocole multi-agent le score officiel LiveCodeBench.

Alternative plus directement sensible à l'interpréteur : prédiction d'exécution
(LiveCodeBench Code Execution / CRUXEval-O). CRUXEval comporte toutefois des
programmes courts et n'est pas une garantie de difficulté pour DeepSeek V4.
Une augmentation artificielle de leur complexité constituerait une adaptation
du benchmark et devrait être explicitement nommée.
