"""The normative path allowlist (spec section 8.1).

This is the security boundary of the whole system. A proposal may name any
target it likes; nothing reaches the filesystem unless it resolves to one of the
shapes below, under one of the two permitted roots.

Rejection is by category so the reason can be journaled without echoing an
attacker-controlled path back into state.
"""

import os
import re

from . import paths

USER = "user"
PROJECT = "project"

CLAUDE_MD = "CLAUDE.md"
RULE = "rule"
SKILL = "skill"

# A skill directory name. Deliberately strict: this component is joined into a
# path, so anything exotic is refused rather than normalized.
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RULE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PathRejected(Exception):
    """Raised with a bounded reason category."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def roots(project_dir=None):
    """The two permitted roots, resolved through any symlinks."""
    project = os.path.realpath(project_dir or os.getcwd())
    return {
        USER: os.path.realpath(paths.claude_home()),
        PROJECT: project,
    }


def candidate_paths(scope, kind, name=None, project_dir=None):
    """The paths a proposal of this shape is permitted to target.

    Returned in preference order, so a caller creating a new artifact takes the
    first entry and a caller looking for an existing owner tries each.
    """
    root = roots(project_dir)[scope]
    if kind == CLAUDE_MD:
        if scope == USER:
            return [os.path.join(root, "CLAUDE.md")]
        # Both project locations are documented; the repository root is the
        # conventional one, so it leads.
        return [os.path.join(root, "CLAUDE.md"),
                os.path.join(root, ".claude", "CLAUDE.md")]
    if kind == RULE:
        if not name:
            raise PathRejected("missing_name")
        if not RULE_NAME.match(name):
            raise PathRejected("bad_name")
        base = root if scope == USER else os.path.join(root, ".claude")
        filename = name if name.endswith(".md") else name + ".md"
        return [os.path.join(base, "rules", filename)]
    if kind == SKILL:
        if not name:
            raise PathRejected("missing_name")
        if not SKILL_NAME.match(name):
            raise PathRejected("bad_name")
        base = root if scope == USER else os.path.join(root, ".claude")
        return [os.path.join(base, "skills", name, "SKILL.md")]
    raise PathRejected("bad_kind")


def resolve(target, project_dir=None, must_exist=False):
    """Validate ``target`` and return its real path, scope, and kind.

    Checks, in order: absolute path, no traversal past a root, no symlink
    anywhere in the chain, a shape the allowlist recognizes, and a regular file
    when one already exists.
    """
    if not target or not isinstance(target, str):
        raise PathRejected("empty_target")
    if "\x00" in target:
        raise PathRejected("bad_name")

    expanded = os.path.abspath(os.path.expanduser(target))
    real = os.path.realpath(expanded)

    # Containment is decided on the resolved path, because a caller's spelling
    # of a perfectly ordinary location may differ from its real one: on macOS a
    # project under /tmp is really under /private/tmp. Comparing only the
    # literal spelling rejected such paths as symlink attacks.
    scope = _scope_of(real, expanded, project_dir)
    root = roots(project_dir)[scope]

    # A symlink for the target itself is refused whatever it points at. The
    # indirection is the problem: it makes the reviewed destination and the
    # written destination two different things.
    if os.path.islink(expanded):
        raise PathRejected("symlink")
    _reject_symlinks_below_root(real, root)

    kind = _kind_of(real, scope, project_dir)

    if os.path.exists(real):
        if not os.path.isfile(real):
            raise PathRejected("not_a_regular_file")
    elif must_exist:
        raise PathRejected("missing_target")

    return {"path": real, "scope": scope, "kind": kind}


def _within(path, root):
    return path == root or path.startswith(root + os.sep)


def _reject_symlinks_below_root(real, root):
    """Refuse a symlink anywhere between an allowed root and the target.

    Walking from the resolved root means each component checked is the real
    location, so a link created inside the root is detected wherever the caller
    reached it from. Components above the root are not checked: there symlinks
    are the system's business and routinely legitimate, since macOS reaches
    /etc and /tmp through them and a home directory may be one too.
    """
    relative = os.path.relpath(real, root)
    if relative == os.curdir:
        return
    current = root
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise PathRejected("symlink")


def _scope_of(real, expanded, project_dir):
    """The allowed root containing ``real``, or a reason it is out of bounds."""
    resolved = roots(project_dir)
    for scope in (USER, PROJECT):
        if _within(real, resolved[scope]):
            return scope
    # Out of bounds. When the caller's own path pointed inside a root, a
    # symlink took it out, and naming that is more useful than reporting the
    # destination it happened to land on.
    for scope in (USER, PROJECT):
        for root in (resolved[scope], os.path.abspath(_original_root(scope,
                                                                     project_dir))):
            if _within(expanded, root):
                _reject_symlinks_below_root_of_original(expanded, root)
                raise PathRejected("outside_allowed_roots")
    raise PathRejected("outside_allowed_roots")


def _original_root(scope, project_dir):
    if scope == USER:
        return paths.claude_home()
    return project_dir or os.getcwd()


def _reject_symlinks_below_root_of_original(expanded, root):
    """Walk the caller's own spelling, used only to explain an escape."""
    relative = os.path.relpath(expanded, root)
    if relative == os.curdir:
        return
    current = root
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise PathRejected("symlink")


def _kind_of(real, scope, project_dir):
    root = roots(project_dir)[scope]
    relative = os.path.relpath(real, root)
    if relative.startswith(os.pardir):
        raise PathRejected("traversal")
    parts = relative.split(os.sep)

    # User scope hangs directly off ~/.claude; project scope off ./.claude,
    # except for the repository-root CLAUDE.md.
    if scope == PROJECT and parts == ["CLAUDE.md"]:
        return CLAUDE_MD
    if scope == PROJECT:
        if len(parts) < 2 or parts[0] != ".claude":
            raise PathRejected("not_an_allowed_artifact")
        parts = parts[1:]

    if parts == ["CLAUDE.md"]:
        return CLAUDE_MD
    if len(parts) >= 2 and parts[0] == "rules" and parts[-1].endswith(".md"):
        if not all(RULE_NAME.match(part.replace(".md", "") or "x")
                   for part in parts[1:]):
            raise PathRejected("bad_name")
        return RULE
    if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
        if not SKILL_NAME.match(parts[1]):
            raise PathRejected("bad_name")
        return SKILL
    raise PathRejected("not_an_allowed_artifact")


def describe():
    """Human-readable allowlist, for presenting a rejection to the user."""
    return [
        "~/.claude/CLAUDE.md",
        "~/.claude/rules/*.md",
        "~/.claude/skills/<name>/SKILL.md",
        "./CLAUDE.md",
        "./.claude/CLAUDE.md",
        "./.claude/rules/*.md",
        "./.claude/skills/<name>/SKILL.md",
    ]
