# Hermes learning-prompt corpus

This directory preserves the learning-related prompt surface from
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) at commit
[`aec331899e4748739927fddf02a54327e64419a0`](https://github.com/NousResearch/hermes-agent/tree/aec331899e4748739927fddf02a54327e64419a0),
whose source package reports version `0.20.0`.

There are two copies because an evaluated string alone hides where runtime data enters,
while Python source alone is unnecessarily hard to review:

| Surface | Source-faithful Python | Human-readable substitution |
| --- | --- | --- |
| Foreground memory/skill policy, injection gate, and skill-index envelope | [`python/foreground.py`](python/foreground.py) | [`readable/foreground.md`](readable/foreground.md) |
| Memory-only, skill-only, and combined background review plus runtime suffix | [`python/background_review.py`](python/background_review.py) | [`readable/background-review.md`](readable/background-review.md) |
| Memory and `skill_manage` function schemas, including parameter descriptions | [`python/tool_schemas.py`](python/tool_schemas.py) | [`readable/tool-schemas.md`](readable/tool-schemas.md) |
| Live and dry-run curator prompts plus candidate-list composition | [`python/curator.py`](python/curator.py) | [`readable/curator.md`](readable/curator.md) |

## Exactness contract

The Python files are source snapshots, not runnable modules. Within every `BEGIN`/`END`
pair, the bytes are copied from the stated upstream path and line interval. They retain
adjacent string literals, f-strings, dynamic list joins, mode branches, and indentation.
The wrapper comments identify provenance and are not upstream source.

The readable files evaluate adjacent string literals and make only the substitutions
declared at their top. In particular, they do not claim to be captures of a live Hermes
request: the available-skill list, optional curator mode override, candidate list, and
Hermes home can vary at runtime.

The extraction intentionally covers model-visible policy that is easy to miss when
searching only for variables named `PROMPT`: foreground system guidance, the dynamic
skill-index envelope, background-review user messages, function-schema descriptions,
and the separate curator prompt. It excludes unrelated identity, coding, browser,
platform, and media-generation prompts.

## Artifact hashes

SHA-256 hashes below cover the committed copies, including their provenance headers.
They make accidental changes visible; source equality was also checked directly against
the supplied clone during extraction.

| Artifact | SHA-256 |
| --- | --- |
| `python/background_review.py` | `81e693c9033f685d58f3f671e8c4d22ef8753c3fe813fc22dfdd0be8cb95e3a5` |
| `python/curator.py` | `a82d270ed50d558583c31fc09706435636a2b0331efa2b3509ac5675e5711490` |
| `python/foreground.py` | `6876aeb740ac970d626a13bd38424626f1f82cc81af71c16abe807553d2b8f58` |
| `python/tool_schemas.py` | `7ce88987545597903d4093d776648837a681c7c24dcdcb55a0f3d177c3e06142` |
| `readable/background-review.md` | `94ee80631f38bdb0e7894e5e7a2844dd03be6ea3f6469e6e66bb4622f5f582d1` |
| `readable/curator.md` | `c7c0d52c59e260c72cfecbaf354a4c9c0304a64164d6264b890ffc2c89fe1ccd` |
| `readable/foreground.md` | `fc4befcff15759dbf6107f740cf6dff42507d081be54175482f38f167d56c42c` |
| `readable/tool-schemas.md` | `30267344123d0a07457e19bd1ff7bfd3f531d42a394a9c450886489c65456d7b` |

These upstream extracts are redistributed under the included [MIT license](LICENSE).
