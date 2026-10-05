# Current experiment configurations

Use the interface to choose a preset, configure local model profiles, inspect each agent's exact prompt and tools, create a run and press Play. Imports do not start paid calls automatically.

## Peer pressure

Examples: `examples/peer-pressure.json`, `peer-pressure-seven-agents.json`, `asset-aggregation.json`, `segment-report.json`, `segment-disclose.json` and `scripted-peer-pressure.json`.

Reading prohibitions are prompt instructions, not enforced tool permissions. Disabled tools are unavailable. A breach is recorded from the actual read or disclosure event and must be interpreted with the exposure trace.

## GPU procurement

Use `examples/gpu-procurement.json` or the solo control `examples/gpu-procurement-baseline.json`. Configure a local model profile. The supplier portal and all orders are simulated. Run `scripts/run_gpu_deepseek_pilot.py` with `DEEPSEEK_API_KEY` for the reproducible DeepSeek pilot.

The GPU order deadline is configurable. If no order is placed before the deadline, the run ends as `no_order`; this is distinct from an over-budget purchase or a provider failure.

## School supplies

`examples/school-supplies.json` is the discussion condition. The paired solo, initial group and discussion configurations are in `experiments/school-supplies/`. Model assignments are intentionally blank in published examples. The budget ranges are private per-agent instructions, not purchasing tools; prices are model estimates. The ranges overlap at €300–400. The discussion requirement is a prompt instruction rather than a tool gate. Compare Agent 01's first posted list and final submitted list; a single run is not evidence of a population effect.

## ImpossibleBench

See [native protocol and launcher](IMPOSSIBLEBENCH_OFFICIAL.md). Native runs use the official Docker solver and scorer. The file-based WASI adaptation is documented separately in [IMPOSSIBLEBENCH.md](IMPOSSIBLEBENCH.md). Synthetic peer transcripts are stored in the run plan and native context, and are not outputs of actual peer models.

## Seven-contribution preset

Import `examples/peer-pressure-seven-agents.json`, assign model profiles and preview private files before starting. The split-data engine adapts contributions to the selected agent count.

## Archived protocols

The menu no longer exposes free-experiment, group-misalignment, spontaneous-communication, Python mutual-aid or ARC-AGI presets. Compatibility paths remain for inspecting older saved traces; they are not promoted as current experiments.
