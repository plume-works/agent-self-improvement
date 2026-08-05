"""The path allowlist (spec section 8.1).

This is the security boundary: a proposal may name any target, and nothing
reaches the filesystem unless it resolves inside one of two roots with a
recognized shape. Attacks tested here are traversal, symlinks, symlinked
parents, and paths that merely look like allowed artifacts.
"""

import os

import pytest

from selfimprove import allowlist


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home = tmp_path / "claude-home"
    (home / "rules").mkdir(parents=True)
    (home / "skills" / "deploy").mkdir(parents=True)
    project = tmp_path / "project"
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / ".claude" / "skills" / "deploy").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    monkeypatch.chdir(project)
    return {"home": home, "project": project, "tmp": tmp_path}


@pytest.mark.parametrize(
    "relative",
    [
        "CLAUDE.md",
        "rules/testing.md",
        "rules/frontend/style.md",
        "skills/deploy/SKILL.md",
    ],
)
def test_user_scope_artifacts_are_allowed(workspace, relative):
    target = workspace["home"] / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved = allowlist.resolve(str(target))
    assert resolved["scope"] == allowlist.USER


@pytest.mark.parametrize(
    ("relative", "kind"),
    [
        ("CLAUDE.md", allowlist.CLAUDE_MD),
        (".claude/CLAUDE.md", allowlist.CLAUDE_MD),
        (".claude/rules/testing.md", allowlist.RULE),
        (".claude/skills/deploy/SKILL.md", allowlist.SKILL),
    ],
)
def test_project_scope_artifacts_are_allowed(workspace, relative, kind):
    target = workspace["project"] / relative
    resolved = allowlist.resolve(str(target))
    assert resolved["scope"] == allowlist.PROJECT
    assert resolved["kind"] == kind


@pytest.mark.parametrize(
    "relative",
    [
        "settings.json",
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".claude/hooks/hooks.json",
        "src/main.py",
        "README.md",
        ".claude/skills/deploy/reference.md",
        ".claude/rules",
        ".git/config",
    ],
)
def test_everything_else_in_the_project_is_rejected(workspace, relative):
    with pytest.raises(allowlist.PathRejected):
        allowlist.resolve(str(workspace["project"] / relative))


def test_agents_md_is_rejected(workspace):
    """Deliberately excluded: Claude Code does not load AGENTS.md directly."""
    with pytest.raises(allowlist.PathRejected) as caught:
        allowlist.resolve(str(workspace["project"] / "AGENTS.md"))
    assert caught.value.reason == "not_an_allowed_artifact"


def test_claude_managed_state_is_rejected(workspace):
    for relative in ("history.jsonl", "projects/x/y.jsonl", "plugins/config.json"):
        with pytest.raises(allowlist.PathRejected):
            allowlist.resolve(str(workspace["home"] / relative))


def test_paths_outside_both_roots_are_rejected(workspace):
    with pytest.raises(allowlist.PathRejected) as caught:
        allowlist.resolve("/etc/passwd")
    assert caught.value.reason == "outside_allowed_roots"


@pytest.mark.parametrize(
    "attack",
    [
        "../../../etc/passwd",
        ".claude/../../outside/CLAUDE.md",
        ".claude/rules/../../../CLAUDE.md",
    ],
)
def test_traversal_is_rejected(workspace, attack):
    with pytest.raises(allowlist.PathRejected):
        allowlist.resolve(str(workspace["project"] / attack))


def test_an_ordinary_path_reached_through_a_symlinked_prefix_is_allowed(workspace, tmp_path, monkeypatch):
    """A regression: /tmp is a symlink to /private/tmp on macOS.

    Comparing only the caller's literal spelling of the path rejected every
    project under such a prefix as a symlink attack, which is most scratch
    directories and any repository reached through a symlinked parent.
    """
    real_project = tmp_path / "real-project"
    real_project.mkdir()
    (real_project / "CLAUDE.md").write_text("# Real\n")
    alias = tmp_path / "alias"
    alias.symlink_to(real_project)
    monkeypatch.chdir(real_project)

    resolved = allowlist.resolve(str(alias / "CLAUDE.md"))
    assert resolved["scope"] == allowlist.PROJECT
    assert resolved["kind"] == allowlist.CLAUDE_MD
    assert resolved["path"] == str(real_project / "CLAUDE.md")


def test_a_symlinked_target_is_rejected(workspace):
    """Even one pointing somewhere legitimate: the indirection is the problem."""
    real = workspace["project"] / ".claude" / "real.md"
    real.write_text("x")
    link = workspace["project"] / "CLAUDE.md"
    link.symlink_to(real)
    with pytest.raises(allowlist.PathRejected) as caught:
        allowlist.resolve(str(link))
    assert caught.value.reason == "symlink"


def test_a_symlinked_parent_directory_is_rejected(workspace):
    """The check realpath alone would miss.

    A symlinked parent redirects the write exactly as a symlinked file does,
    and resolving the path silently follows it.
    """
    elsewhere = workspace["tmp"] / "elsewhere"
    elsewhere.mkdir()
    link = workspace["project"] / ".claude" / "rules"
    link_target = workspace["project"] / ".claude" / "rules-link"
    link_target.symlink_to(elsewhere)
    assert link.exists()

    with pytest.raises(allowlist.PathRejected) as caught:
        allowlist.resolve(str(link_target / "evil.md"))
    assert caught.value.reason == "symlink"


def test_a_directory_target_is_rejected(workspace):
    with pytest.raises(allowlist.PathRejected):
        allowlist.resolve(str(workspace["project"] / ".claude" / "skills" / "deploy"))


def test_a_non_regular_file_is_rejected(workspace):
    fifo = workspace["home"] / "rules" / "pipe.md"
    os.mkfifo(str(fifo))
    with pytest.raises(allowlist.PathRejected) as caught:
        allowlist.resolve(str(fifo))
    assert caught.value.reason == "not_a_regular_file"


def test_must_exist_is_enforced_when_requested(workspace):
    absent = workspace["project"] / ".claude" / "rules" / "absent.md"
    assert allowlist.resolve(str(absent))["kind"] == allowlist.RULE
    with pytest.raises(allowlist.PathRejected) as caught:
        allowlist.resolve(str(absent), must_exist=True)
    assert caught.value.reason == "missing_target"


@pytest.mark.parametrize("target", ["", None, 42, "with\x00null"])
def test_degenerate_targets_are_rejected(workspace, target):
    with pytest.raises(allowlist.PathRejected):
        allowlist.resolve(target)


@pytest.mark.parametrize("name", ["../escape", "Deploy", "a" * 80, "with space", ""])
def test_bad_skill_names_are_rejected(workspace, name):
    with pytest.raises(allowlist.PathRejected):
        allowlist.candidate_paths(allowlist.PROJECT, allowlist.SKILL, name=name)


def test_candidate_paths_prefers_the_repository_root_claude_md(workspace):
    candidates = allowlist.candidate_paths(allowlist.PROJECT, allowlist.CLAUDE_MD)
    assert candidates[0] == str(workspace["project"] / "CLAUDE.md")
    assert candidates[1] == str(workspace["project"] / ".claude" / "CLAUDE.md")


def test_candidate_paths_for_a_rule_appends_the_extension(workspace):
    [path] = allowlist.candidate_paths(allowlist.USER, allowlist.RULE, name="testing")
    assert path == str(workspace["home"] / "rules" / "testing.md")


def test_candidate_paths_rejects_an_unknown_kind(workspace):
    with pytest.raises(allowlist.PathRejected):
        allowlist.candidate_paths(allowlist.USER, "settings.json")


def test_every_described_shape_actually_resolves(workspace):
    """The list shown to a user must match the list actually enforced."""
    for shape in allowlist.describe():
        concrete = (
            shape.replace("<name>", "deploy")
            .replace("*", "testing")
            .replace("~", str(workspace["home"]))
            .replace("./", str(workspace["project"]) + "/")
        )
        if concrete.startswith(str(workspace["home"])) and "/.claude/" in concrete:
            concrete = concrete.replace("/.claude/", "/")
        allowlist.resolve(concrete)
