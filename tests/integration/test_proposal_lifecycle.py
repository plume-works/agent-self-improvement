"""
Slice 1 end to end, through the same entry point a hook and skill use.

Stage, present, authorize, apply, discover in a fresh process, roll back. Each
step goes through ``scripts/si`` so the test exercises the real boundary rather
than importing past it.
"""

import json
import os
import subprocess
import sys

import pytest

from selfimprove import store
from tests.conftest import PLUGIN_ROOT

ORIGINAL = '# Project\n\n- Existing instruction.\n'
UPDATED = '# Project\n\n- Existing instruction.\n- Run the suite with `make test`.\n'


@pytest.fixture
def workspace(project, state_root, tmp_path):
    target = project / 'CLAUDE.md'
    target.write_text(ORIGINAL)
    content = tmp_path / 'new-content.md'
    content.write_text(UPDATED)
    return {'target': target, 'content': content, 'project': project}


def expansion_event(command_name, command_args, session='session-1'):
    return json.dumps(
        {
            'hook_event_name': 'UserPromptExpansion',
            'session_id': session,
            'expansion_type': 'slash_command',
            'command_source': 'plugin',
            'command_name': command_name,
            'command_args': command_args,
        }
    )


def stage(run_si, workspace, candidate=None):
    args = [
        'stage-proposal',
        '--target',
        str(workspace['target']),
        '--content-file',
        str(workspace['content']),
        '--reason',
        "This file already holds the project's build commands.",
    ]
    if candidate:
        args += ['--candidate', candidate]
    result = run_si(*args, cwd=str(workspace['project']))
    assert result.returncode == 0, result.stderr
    return result.stdout


def ids_from(summary):
    proposal_id = next(
        line.split()[1] for line in summary.splitlines() if line.startswith('Proposal ')
    )
    prefix = next(
        line.split(': ')[1] for line in summary.splitlines() if line.startswith('Hash prefix: ')
    )
    return proposal_id, prefix


def test_staging_presents_destination_hash_and_exact_diff(run_si, workspace):
    summary = stage(run_si, workspace)
    assert str(workspace['target']) in summary
    assert '+- Run the suite with `make test`.' in summary
    assert '/self-improve:apply' in summary
    assert '/self-improve:reject' in summary
    # Staging must not touch the target.
    assert workspace['target'].read_text() == ORIGINAL


def test_apply_without_authorization_refuses(run_si, workspace):
    """The central claim: a model calling apply cannot install anything."""
    proposal_id, prefix = ids_from(stage(run_si, workspace))
    result = run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        cwd=str(workspace['project']),
    )
    assert result.returncode == 1
    assert 'no_matching_authorization' in result.stderr
    assert workspace['target'].read_text() == ORIGINAL


def test_a_skill_tool_invocation_creates_no_authorization(run_si, workspace):
    """
    Claude invoking the skill produces no UserPromptExpansion event.

    Simulated here as an expansion whose source is not this plugin, which is the
    closest a non-typed path can get.
    """
    proposal_id, prefix = ids_from(stage(run_si, workspace))
    event = json.dumps(
        {
            'hook_event_name': 'UserPromptExpansion',
            'session_id': 'session-1',
            'expansion_type': 'slash_command',
            'command_source': 'user',
            'command_name': 'apply',
            'command_args': '%s %s' % (proposal_id, prefix),
        }
    )
    run_si('capture-expansion', stdin=event)
    assert store.list_records(store.AUTHORIZATIONS) == []

    result = run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        cwd=str(workspace['project']),
    )
    assert result.returncode == 1
    assert workspace['target'].read_text() == ORIGINAL


def test_full_apply_and_rollback_cycle(run_si, workspace):
    proposal_id, prefix = ids_from(stage(run_si, workspace))

    granted = run_si(
        'capture-expansion', stdin=expansion_event('apply', '%s %s' % (proposal_id, prefix))
    )
    assert granted.returncode == 0
    assert 'authorized apply' in granted.stdout

    applied = run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert applied.returncode == 0, applied.stderr
    assert workspace['target'].read_text() == UPDATED

    mutation_id = applied.stdout.split('Mutation ')[1].split('.')[0]

    run_si('capture-expansion', stdin=expansion_event('rollback', mutation_id))
    rolled = run_si(
        'rollback-mutation',
        '--id',
        mutation_id,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert rolled.returncode == 0, rolled.stderr
    assert workspace['target'].read_text() == ORIGINAL


def test_a_fresh_process_discovers_the_applied_instruction(run_si, workspace):
    """
    Section 15 point 8: the artifact has to be real, not just written.

    Read back from a separate interpreter at a path Claude Code documents as
    auto-loaded, so nothing about this test's own state can make it pass.
    """
    proposal_id, prefix = ids_from(stage(run_si, workspace))
    run_si('capture-expansion', stdin=expansion_event('apply', '%s %s' % (proposal_id, prefix)))
    run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )

    probe = subprocess.run(
        [
            sys.executable,
            '-c',
            "import sys;print(open(sys.argv[1], encoding='utf-8').read())",
            str(workspace['target']),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert probe.returncode == 0
    assert 'Run the suite with `make test`.' in probe.stdout
    assert workspace['target'].name == 'CLAUDE.md'
    assert workspace['target'].parent == workspace['project']


def test_rejection_leaves_the_target_unchanged(run_si, workspace):
    proposal_id, _prefix = ids_from(stage(run_si, workspace))
    run_si('capture-expansion', stdin=expansion_event('reject', proposal_id))
    result = run_si(
        'reject-proposal',
        '--id',
        proposal_id,
        '--reason-category',
        'wrong_scope',
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert result.returncode == 0, result.stderr
    assert workspace['target'].read_text() == ORIGINAL
    assert store.list_records(store.PROPOSALS) == []


def test_a_rejected_lesson_is_not_proposed_again(run_si, workspace):
    """Rejection keeps only a fingerprint and a category, and that is enough."""
    store.write_record(
        store.CANDIDATES,
        'cand-1',
        {'lesson': 'Run the suite with make test.', 'signal_type': 'explicit_correction'},
        ttl=3600,
    )
    proposal_id, _ = ids_from(stage(run_si, workspace, candidate='cand-1'))
    run_si('capture-expansion', stdin=expansion_event('reject', proposal_id))
    run_si(
        'reject-proposal',
        '--id',
        proposal_id,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )

    again = run_si(
        'stage-proposal',
        '--target',
        str(workspace['target']),
        '--content-file',
        str(workspace['content']),
        '--candidate',
        'cand-1',
        cwd=str(workspace['project']),
    )
    assert again.returncode == 1
    assert 'duplicate_of_rejected_proposal' in again.stderr


def test_authorization_is_consumed_exactly_once(run_si, workspace):
    proposal_id, prefix = ids_from(stage(run_si, workspace))
    run_si('capture-expansion', stdin=expansion_event('apply', '%s %s' % (proposal_id, prefix)))

    first = run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert first.returncode == 0

    second = run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert second.returncode == 1
    assert 'no_matching_authorization' in second.stderr


def test_a_stale_target_refuses_and_preserves_the_edit(run_si, workspace):
    proposal_id, prefix = ids_from(stage(run_si, workspace))
    workspace['target'].write_text('# Project\n\n- The user edited this.\n')
    run_si('capture-expansion', stdin=expansion_event('apply', '%s %s' % (proposal_id, prefix)))

    result = run_si(
        'apply-proposal',
        '--id',
        proposal_id,
        '--hash-prefix',
        prefix,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert result.returncode == 1
    assert 'stale_target' in result.stderr
    assert workspace['target'].read_text() == '# Project\n\n- The user edited this.\n'


def test_staging_outside_the_allowlist_refuses(run_si, workspace, tmp_path):
    outside = tmp_path / 'somewhere' / 'notes.md'
    outside.parent.mkdir()
    outside.write_text('x')
    result = run_si(
        'stage-proposal',
        '--target',
        str(outside),
        '--content-file',
        str(workspace['content']),
        cwd=str(workspace['project']),
    )
    assert result.returncode == 1
    assert 'path_rejected' in result.stderr
    assert outside.read_text() == 'x'


def test_find_owners_reports_only_allowlisted_paths(run_si, workspace):
    (workspace['project'] / '.claude' / 'settings.json').write_text('{}')
    result = run_si('find-owners', '--query', 'test command', cwd=str(workspace['project']))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    for entry in report['owners']:
        assert 'settings.json' not in entry['path']
    assert any(entry['path'] == str(workspace['target']) for entry in report['owners'])


def test_malformed_authorization_command_explains_the_syntax(run_si, workspace):
    result = run_si('capture-expansion', stdin=expansion_event('apply', 'only-one'))
    assert result.returncode == 0
    assert 'was not authorized' in result.stdout


def test_skills_are_discoverable_and_restrict_their_tools():
    """A skill that could edit files directly would bypass the whole protocol."""
    for name in ('improve', 'apply', 'reject', 'rollback'):
        path = os.path.join(PLUGIN_ROOT, 'skills', name, 'SKILL.md')
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        assert text.startswith('---')
        assert 'name: %s' % name in text
        assert 'allowed-tools:' in text
        allowed = next(line for line in text.splitlines() if line.startswith('allowed-tools:'))
        assert 'Edit' not in allowed
        assert 'Write' not in allowed
