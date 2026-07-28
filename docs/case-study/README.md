# Case study index

Case studies examine adjacent implementations and patterns against the architecture in [`docs/specs/`](../specs/README.md). They distinguish upstream claims from repository reality and record concrete implications for Claude Self-Improvement.

| Case study | Upstream snapshot | Verdict |
| --- | --- | --- |
| [Hermes Agent](hermes/README.md) | [`NousResearch/hermes-agent@a41d280`](https://github.com/NousResearch/hermes-agent/tree/a41d280f95c69f67380358b305b62345934ecaf3) | Layer durable fact memory, reusable skills, deterministic triggers, and curation rather than treating self-improvement as one prompt |
| [Claude Meta](claude-meta/README.md) | [`aviadr1/claude-meta@93bf944`](https://github.com/aviadr1/claude-meta/tree/93bf944ffabc525808f4cd7d5cca09ff9cd0876c) | Adopt the reflection rubric and user trigger; do not adopt direct, single-file self-mutation as the control plane |
