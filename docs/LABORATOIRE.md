# Lab operation

Start with `python3 -m swarm_bench lab --port 8766`. The current menu offers split-data peer pressure, asset aggregation, 2024 segment/report variants, GPU procurement and school supplies. ImpossibleBench has its own [native launch/history page](IMPOSSIBLEBENCH_OFFICIAL.md).

Create model profiles locally, assign models, inspect exact per-agent prompts/files/tools and create a run. Creating a run does not start inference; Play does. Demo is limited to supported deterministic peer-pressure presets.

Each agent keeps a separate model history. The shared message board records author and message IDs. Notes can be read voluntarily or injected in peers' next contexts, depending on configuration. Private files and prompts are not automatically shared. Tool rejection arguments and execution results are retained for diagnosis. Current compatibility code can still load archived scenarios no longer offered in the menu.

Call limits, token limits, message limits and submission stopping rules are operator settings. Requirements expressed in a prompt, such as five messages before submission or a private budget range, are not hard tool gates. Preview and exports preserve the concrete configuration, so experiment interpretation should account for those distinctions.

The UI supports JSON/CSV/PDF exports, comparison and replay inspection. Raw run histories and model credentials remain under gitignored `runs/`; profiles and secrets are never published in Git. Stop and pause are explicit operator actions. Closing a browser does not stop a worker. Keep the host awake and connected for ongoing API work.
