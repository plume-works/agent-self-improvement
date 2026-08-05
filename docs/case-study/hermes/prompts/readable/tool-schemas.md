# Human-readable tool-schema prompt copy

This is a rendered reading copy of the Python snapshot at
[`../python/tool_schemas.py`](../python/tool_schemas.py). Python strings are joined,
and the sole runtime interpolation, `display_hermes_home()`, is replaced with its
default display value, `~/.hermes`. The parameter descriptions are included because
function schemas are model-visible prompt policy, not merely API documentation.

## Memory tool

### Tool description

Save durable facts to persistent memory that survive across sessions. Memory is injected into every future turn, so keep entries compact and high-signal.

HOW: make ALL your changes in ONE call via an 'operations' array (each item: {action, content?, old_text?}). The batch applies atomically and the char limit is checked only on the FINAL result — so a single call can remove/replace stale entries to free room AND add new ones, even when an add alone would overflow. The response reports current/limit chars and confirms completion; one batch call finishes the update, so don't repeat it. Use the bare action/content/old_text fields only for a single lone change.

WHEN: save proactively when the user states a preference, correction, or personal detail, or you learn a stable fact about their environment, conventions, or workflow. Priority: user preferences & corrections > environment facts > procedures. The best memory stops the user repeating themselves.

IF FULL: an add is rejected with the current entries shown. Reissue as ONE batch that removes or shortens enough stale entries and adds the new one together.

TARGETS: 'user' = who the user is (name, role, preferences, style). 'memory' = your notes (environment, conventions, tool quirks, lessons).

SKIP: trivial/obvious info, easily re-discovered facts, raw data dumps, task progress, completed-work logs, temporary TODO state (use session_search for those). Reusable procedures belong in a skill, not memory.

### Parameter schema

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "add",
        "replace",
        "remove"
      ],
      "description": "The action to perform (single-op shape). Omit when using 'operations'."
    },
    "target": {
      "type": "string",
      "enum": [
        "memory",
        "user"
      ],
      "description": "Which memory store: 'memory' for personal notes, 'user' for user profile."
    },
    "content": {
      "type": "string",
      "description": "The entry content. Required for 'add' and 'replace' (single-op shape)."
    },
    "old_text": {
      "type": "string",
      "description": "REQUIRED for 'replace' and 'remove' (single-op shape): a short unique substring identifying the existing entry to modify. Omit only for 'add'."
    },
    "operations": {
      "type": "array",
      "description": "Batch shape: a list of operations applied atomically in one call against the final char budget. Preferred when making multiple changes or consolidating to make room. Each item is {action, content?, old_text?}.",
      "items": {
        "type": "object",
        "properties": {
          "action": {
            "type": "string",
            "enum": [
              "add",
              "replace",
              "remove"
            ]
          },
          "content": {
            "type": "string",
            "description": "Entry content for add/replace."
          },
          "old_text": {
            "type": "string",
            "description": "Substring identifying the entry for replace/remove."
          }
        },
        "required": [
          "action"
        ]
      }
    }
  },
  "required": [
    "target"
  ]
}
```

## Skill-management tool

### Tool description

Manage skills (create, update, delete). Skills are your procedural memory — reusable approaches for recurring task types. New skills go to ~/.hermes/skills/; existing skills can be modified wherever they live.

Actions: create (full SKILL.md + optional category), patch (old_string/new_string — preferred for fixes), edit (full SKILL.md rewrite — major overhauls only), delete, write_file, remove_file.

On delete, pass `absorbed_into=<umbrella>` when you're merging this skill's content into another one, or `absorbed_into=""` when you're pruning it with no forwarding target. This lets the curator tell consolidation from pruning without guessing, so downstream consumers (cron jobs that reference the old skill name, etc.) get updated correctly. The target you name in `absorbed_into` must already exist — create/patch the umbrella first, then delete.

Create when: complex task succeeded (5+ calls), errors overcome, user-corrected approach worked, non-trivial workflow discovered, or user asks you to remember a procedure.
Update when: instructions stale/wrong, OS-specific failures, missing steps or pitfalls found during use. If you used a skill and hit issues not covered by it, patch it immediately.

After difficult/iterative tasks, offer to save as a skill. Skip for simple one-offs. Confirm with user before creating/deleting.

Good skills: trigger conditions, numbered steps with exact commands, pitfalls section, verification steps. Use skill_view() to see format examples.

Description: long descriptions are truncated to the first 57 chars plus '...' in the system prompt skill index; longer text is visible via skills_list/skill_view. Keep the trigger self-contained in that first 57-char window: 'Use when <trigger>. <one-line behavior>.'

Pinned skills are protected from deletion only — skill_manage(action='delete') will refuse with a message pointing the user to `hermes curator unpin <name>`. Patches and edits go through on pinned skills so you can still improve them as pitfalls come up; pin only guards against irrecoverable loss.

### Parameter schema

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "create",
        "patch",
        "edit",
        "delete",
        "write_file",
        "remove_file"
      ],
      "description": "The action to perform."
    },
    "name": {
      "type": "string",
      "description": "Skill name (lowercase, hyphens/underscores, max 64 chars). Must match an existing skill for patch/edit/delete/write_file/remove_file."
    },
    "content": {
      "type": "string",
      "description": "Full SKILL.md content (YAML frontmatter + markdown body). Required for 'create' and 'edit'. For 'edit', read the skill first with skill_view() and provide the complete updated text."
    },
    "old_string": {
      "type": "string",
      "description": "Text to find in the file (required for 'patch'). Must be unique unless replace_all=true. Include enough surrounding context to ensure uniqueness."
    },
    "new_string": {
      "type": "string",
      "description": "Replacement text (required for 'patch'). Can be empty string to delete the matched text."
    },
    "replace_all": {
      "type": "boolean",
      "description": "For 'patch': replace all occurrences instead of requiring a unique match (default: false)."
    },
    "category": {
      "type": "string",
      "description": "Optional category/domain for organizing the skill (e.g., 'devops', 'data-science', 'mlops'). Creates a subdirectory grouping. Only used with 'create'."
    },
    "file_path": {
      "type": "string",
      "description": "Path to a supporting file within the skill directory. For 'write_file'/'remove_file': required, must be under references/, templates/, scripts/, or assets/. For 'patch': optional, defaults to SKILL.md if omitted."
    },
    "file_content": {
      "type": "string",
      "description": "Content for the file. Required for 'write_file'."
    },
    "absorbed_into": {
      "type": "string",
      "description": "For 'delete' only — declares intent so the curator can tell consolidation from pruning without guessing. Pass the umbrella skill name when this skill's content was merged into another (the target must already exist). Pass an empty string when the skill is truly stale and being pruned with no forwarding target. Omitting the arg on delete is supported for backward compatibility but downstream tooling (e.g. cron-job skill reference rewriting) will have to guess at intent."
    }
  },
  "required": [
    "action",
    "name"
  ]
}
```
