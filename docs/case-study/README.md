# Case study index

Case studies examine adjacent implementations and patterns against the architecture in [`docs/specs/`](../specs/README.md). They distinguish upstream claims from repository reality and record concrete implications for Claude Self-Improvement.

| Case study | Upstream snapshot | Verdict |
| --- | --- | --- |
| [Hermes Agent](hermes/README.md) | [`NousResearch/hermes-agent@a41d280`](https://github.com/NousResearch/hermes-agent/tree/a41d280f95c69f67380358b305b62345934ecaf3) | Layer durable fact memory, reusable skills, deterministic triggers, and curation rather than treating self-improvement as one prompt |
| [Claude Meta](claude-meta/README.md) | [`aviadr1/claude-meta@93bf944`](https://github.com/aviadr1/claude-meta/tree/93bf944ffabc525808f4cd7d5cca09ff9cd0876c) | Adopt the reflection rubric and user trigger; do not adopt direct, single-file self-mutation as the control plane |
| [Self-improving Claude Code bootstrap seed](bootstrap-seed/README.md) | [Gist revision `860d3f7`](https://gist.github.com/ChristopherA/fd2985551e765a86f4fbb24080263a2f/860d3f71fef949ff5692c86bb251c571caf53790) | Adopt triage, anti-proliferation, pressure-driven structure, and user steering; keep mutation authority outside the prompt |
