# ARC-AGI-3: solo text control

Pilot launched: `20260922-163649-7af3f0`. First actions and associated
observations were verified in the log and replay panel. All 102 project
tests pass. Config manifest and game file fingerprints are kept in
`runs/arc/20260922-163649-7af3f0/manifest.json`.

## Explicit choices for this pilot

- Public game LS20, version `ls20-9607627b`, seed 0, SDK arc-agi 0.9.9,
  engine arcengine 0.9.3. This game is used in the official quickstart.
- Single DeepSeek V4 Flash low (`deepseek/deepseek-v4-flash`), temperature not
  forced, no Python tool. Empty board and private files available.
- OFFLINE local mode after downloading the official game. No score is
  sent to the leaderboard; SDK init obtained anonymous access to download
  the game, without using the OpenRouter key.
- Independent game state per agent. For later groups, agents
  will not modify the same game instance.
- Game actions via arc_step; read without action via arc_observe. Only
  available public commands are accepted. RESET is available after
  GAME_OVER; no automatic reset. No submit_answer: the game engine
  decides WIN. End when all instances are WIN, or limit/error.
- 200 LLM calls maximum per agent, 16,000 output tokens per call,
  1,500,000 shared output tokens. One call may request multiple tools.
  No additional internal monetary cap added.
- A response without tools only triggers the technical reminder:
  `Continue interacting with the environment using the available tools.`

## Observation and information separation

The model receives public grids (all frames of a transition),
status, completed levels, target level count, and available actions.
It never receives the internal game object, source code,
solution, worker memory, or other agents’ scripts.

Each frame is losslessly encoded as hex lines: one
character 0..F per cell. Consecutive identical lines are grouped as
`[first_line, last_line, content]`, inclusive bounds, zero-based indices.
Coordinates x,y start top-left. Colors follow the SDK public palette.
This text representation is an adaptation of our protocol; it may be hard to interpret and does not allow direct comparison with an official score using visual observations.

The board stays voluntary: post_note writes, read_board reads; no injection of
content into peers’ contexts. Actions, observations, calls, and usage
are logged. The UI ARC panel shows the grid and a cursor
to replay successive observations (last frame of each transition).

## Sources and reproduction

- https://docs.arcprize.org/toolkit/overview
- https://docs.arcprize.org/game-schema
- https://docs.arcprize.org/actions
- Install and download: scripts/setup_arc_runtime.py

Do not infer altruism from playing a long time alone. The solo control
serves to verify the action-observation loop and calibrate difficulty. Failure
may also come from text representation or call cap.
