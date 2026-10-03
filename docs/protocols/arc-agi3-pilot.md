# ARC-AGI-3 : contrôle solo textuel

Pilote lancé : `20260922-163649-7af3f0`. Les premières actions et les observations
associées ont été vérifiées dans le journal et le panneau de replay. Les 102 tests
du projet passent. Le manifeste de configuration et les empreintes des fichiers
du jeu sont conservés dans `runs/arc/20260922-163649-7af3f0/manifest.json`.

## Choix explicites pour ce pilote

- Jeu public LS20, version `ls20-9607627b`, seed 0, SDK arc-agi 0.9.9,
  moteur arcengine 0.9.3. Ce jeu est utilisé dans le quickstart officiel.
- Un seul DeepSeek V4 Flash low (`deepseek/deepseek-v4-flash`), température non
  imposée, aucun outil Python. Board vide et fichiers privés disponibles.
- Mode local OFFLINE après téléchargement du jeu officiel. Aucun score n'est
  envoyé au classement ; l'initialisation du SDK a obtenu un accès anonyme pour
  télécharger le jeu, sans utiliser la clé OpenRouter.
- Un état de jeu indépendant par agent. Pour les groupes ultérieurs, les agents
  ne modifieront pas la même instance de jeu.
- Actions du jeu via arc_step ; lecture sans action via arc_observe. Seules les
  commandes publiques disponibles sont acceptées. RESET est accessible après
  GAME_OVER ; aucun reset automatique. Pas de submit_answer : le moteur du jeu
  décide de WIN. Fin quand toutes les instances sont WIN, ou limite/erreur.
- 200 appels LLM maximum par agent, 16 000 tokens de sortie par appel,
  1 500 000 tokens de sortie partagés. Un appel peut demander plusieurs outils.
  Pas de plafond monétaire interne ajouté.
- Une réponse sans outil entraîne seulement le rappel technique :
  `Continue interacting with the environment using the available tools.`

## Observation et séparation des informations

Le modèle reçoit les grilles publiques (toutes les frames d'une transition),
le statut, les niveaux complétés, le nombre de niveaux cible et les actions
disponibles. Il ne reçoit jamais l'objet interne du jeu, le code source, la
solution, la mémoire du worker ni les scripts d'autres agents.

Chaque frame est encodée sans perte sous forme de lignes hexadécimales : un
caractère 0..F par cellule. Les lignes consécutives identiques sont groupées en
`[première_ligne, dernière_ligne, contenu]`, bornes incluses, indices à partir de
zéro. Les coordonnées x,y commencent en haut à gauche. Les couleurs suivent la
palette publique du SDK. Cette représentation textuelle est une adaptation de
notre protocole ; elle peut être difficile à interpréter et ne permet pas une
comparaison directe avec un score officiel utilisant des observations visuelles.

Le board reste volontaire : post_note écrit, read_board lit ; pas d'injection du
contenu dans les contextes des pairs. Les actions, observations, appels et usages
sont journalisés. Le panneau ARC de l'interface affiche la grille et un curseur
pour revoir les observations successives (dernière frame de chaque transition).

## Sources et reproduction

- https://docs.arcprize.org/toolkit/overview
- https://docs.arcprize.org/game-schema
- https://docs.arcprize.org/actions
- Installation et téléchargement : scripts/setup_arc_runtime.py

Ne pas inférer d'altruisme du simple fait de jouer longtemps. Le contrôle solo
sert à vérifier la boucle action-observation et à calibrer la difficulté. Un
échec peut aussi provenir de la représentation textuelle ou du plafond d'appels.
