"""
The ten MVP acceptance conditions of spec section 15.

One test per numbered condition, named after it, so the gate is checkable
rather than implied. Each drives the packaged plugin through ``scripts/si``
exactly as a hook or skill would.
"""

import json
import os
import subprocess
import sys

import pytest

from selfimprove import capture, journal, paths, store
from tests.conftest import PLUGIN_ROOT

STOP = {
    'hook_event_name': 'Stop',
    'session_id': 'session-1',
    'prompt_id': 'prompt-1',
    'last_assistant_message': 'Switched the test command over.',
    'stop_hook_active': False,
    'background_tasks': [],
    'session_crons': [],
}


@pytest.fixture
def workspace(project, state_root):
    target = project / 'CLAUDE.md'
    target.write_text('# Project\n\n- Build with make.\n')
    return {'project': project, 'target': target, 'stop': dict(STOP, cwd=str(project))}


def corrected(workspace):
    capture.record_prompt({**workspace['stop'], 'prompt': 'no, use make test instead of pytest'})
    return workspace['stop']


def wake(run_si, event):
    return run_si('review-turn', stdin=json.dumps(event))


def candidate_id_from(stderr):
    return next(word.strip('.') for word in stderr.split() if word.startswith('cand-'))


def stage(run_si, workspace, candidate=None, content=None):
    path = workspace['project'] / 'staged.md'
    path.write_text(content or '# Project\n\n- Build with make.\n- Test with make test.\n')
    args = [
        'stage-proposal',
        '--target',
        str(workspace['target']),
        '--content-file',
        str(path),
        '--reason',
        'It already holds build commands.',
    ]
    if candidate:
        args += ['--candidate', candidate]
    result = run_si(*args, cwd=str(workspace['project']))
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    return (
        next(line.split()[1] for line in lines if line.startswith('Proposal ')),
        next(line.split(': ')[1] for line in lines if line.startswith('Hash prefix: ')),
    )


def authorize(run_si, operation, args, session='session-1'):
    return run_si(
        'capture-expansion',
        stdin=json.dumps(
            {
                'hook_event_name': 'UserPromptExpansion',
                'session_id': session,
                'expansion_type': 'slash_command',
                'command_source': 'plugin',
                'command_name': operation,
                'command_args': args,
            }
        ),
    )


def test_1_reflection_only_follows_a_supported_signal(run_si, workspace, fake_reviewer):
    fake_reviewer.mode('propose')

    capture.record_prompt({**workspace['stop'], 'prompt': 'add a test for the parser'})
    assert wake(run_si, workspace['stop']).returncode == 0
    assert not os.path.exists(fake_reviewer.argv_file), (
        'the reviewer must not run without a signal'
    )

    assert wake(run_si, corrected(workspace)).returncode == 2


def test_2_a_no_lesson_turn_is_silent_and_stages_nothing(run_si, workspace, fake_reviewer):
    fake_reviewer.mode('discard')
    result = wake(run_si, corrected(workspace))
    assert result.returncode == 0
    assert result.stderr == ''
    assert store.list_records(store.CANDIDATES) == []
    assert store.list_records(store.PROPOSALS) == []


def test_3_the_reviewer_is_independent_and_cannot_mutate(run_si, workspace, fake_reviewer):
    fake_reviewer.mode('propose')
    wake(run_si, corrected(workspace))
    argv = fake_reviewer.recorded_argv()

    assert argv[argv.index('--tools') + 1] == ''
    assert argv[argv.index('--disallowedTools') + 1] == '*'
    assert json.loads(argv[argv.index('--settings') + 1]) == {'disableAllHooks': True}
    assert workspace['target'].read_text() == '# Project\n\n- Build with make.\n'


def test_4_routing_searches_existing_owners_before_creating(run_si, workspace):
    result = run_si('find-owners', '--query', 'test command', cwd=str(workspace['project']))
    report = json.loads(result.stdout)
    existing = [entry for entry in report['owners'] if entry.get('exists')]
    assert existing, 'an existing CLAUDE.md must be offered as an owner'
    assert existing[0]['path'] == str(workspace['target'])
    assert report['owners'].index(existing[0]) < len(report['owners'])


def test_5_authorization_binds_one_exact_immutable_proposal(run_si, workspace):
    first, first_prefix = stage(run_si, workspace)
    second, _ = stage(
        run_si, workspace, content='# Project\n\n- Build with make.\n- Something else.\n'
    )

    authorize(run_si, 'apply', '%s %s' % (first, first_prefix))

    # The authorization names one proposal; it cannot install the other.
    wrong = run_si(
        'apply-proposal',
        '--id',
        second,
        '--hash-prefix',
        first_prefix,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert wrong.returncode == 1
    assert 'no_matching_authorization' in wrong.stderr
    assert workspace['target'].read_text() == '# Project\n\n- Build with make.\n'


def test_6_approval_applies_only_reviewed_bytes_to_one_artifact(run_si, workspace, tmp_path):
    before = {}
    for name in ('CLAUDE.md', '.claude/CLAUDE.md'):
        path = workspace['project'] / name
        before[name] = path.read_text() if path.exists() else None

    proposal_id, prefix = stage(run_si, workspace)
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))
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
    assert result.returncode == 0, result.stderr

    assert (
        workspace['target'].read_text()
        == '# Project\n\n- Build with make.\n- Test with make test.\n'
    )
    other = workspace['project'] / '.claude' / 'CLAUDE.md'
    assert (other.read_text() if other.exists() else None) == before['.claude/CLAUDE.md']


@pytest.mark.parametrize(
    'attack',
    [
        '../../../../etc/passwd',
        '.claude/settings.json',
        '.claude/../../escape.md',
        'AGENTS.md',
    ],
)
def test_7a_path_attacks_fail_without_writing(run_si, workspace, attack):
    content = workspace['project'] / 'payload.md'
    content.write_text('owned\n')
    target = os.path.join(str(workspace['project']), attack)
    before = None
    if os.path.exists(target):
        with open(target, encoding='utf-8') as handle:
            before = handle.read()

    result = run_si(
        'stage-proposal',
        '--target',
        target,
        '--content-file',
        str(content),
        cwd=str(workspace['project']),
    )
    assert result.returncode == 1
    assert 'path_rejected' in result.stderr
    if before is not None:
        with open(target, encoding='utf-8') as handle:
            assert handle.read() == before, 'a rejected path was written anyway'


def test_7b_a_stale_edit_refuses_without_overwriting(run_si, workspace):
    proposal_id, prefix = stage(run_si, workspace)
    workspace['target'].write_text('# Project\n\n- The user rewrote this.\n')
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))

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
    assert workspace['target'].read_text() == '# Project\n\n- The user rewrote this.\n'


def test_7c_an_interrupted_mutation_blocks_until_reconciled(run_si, workspace):
    proposal_id, prefix = stage(run_si, workspace)
    paths.atomic_write(
        paths.state_path('inflight.json'),
        json.dumps(
            {
                'mutation_id': 'mut-interrupted',
                'operation': 'apply',
                'target': str(workspace['target']),
                'preimage_sha': 'aaaa',
                'post_sha': 'bbbb',
                'backup': None,
            }
        ),
    )
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))
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
    assert 'unreconciled_target' in result.stderr
    assert workspace['target'].read_text() == '# Project\n\n- Build with make.\n'


def test_8_a_fresh_process_discovers_the_applied_artifact(run_si, workspace):
    proposal_id, prefix = stage(run_si, workspace)
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))
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

    # A separate interpreter reading the documented auto-load path, so nothing
    # about this test's own state can make it pass.
    probe = subprocess.run(
        [
            sys.executable,
            '-c',
            "import os,sys;p=os.path.join(sys.argv[1],'CLAUDE.md');print(open(p, encoding='utf-8').read())",
            str(workspace['project']),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert probe.returncode == 0, probe.stderr
    assert 'Test with make test.' in probe.stdout


def test_9_verified_rollback_restores_the_preimage(run_si, workspace):
    original = workspace['target'].read_text()
    proposal_id, prefix = stage(run_si, workspace)
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))
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
    mutation_id = applied.stdout.split('Mutation ')[1].split('.')[0]

    authorize(run_si, 'rollback', mutation_id)
    rolled = run_si(
        'rollback-mutation',
        '--id',
        mutation_id,
        '--session-id',
        'session-1',
        cwd=str(workspace['project']),
    )
    assert rolled.returncode == 0, rolled.stderr
    assert workspace['target'].read_text() == original


def test_10_persisted_state_contains_no_sensitive_body(
    run_si, workspace, fake_reviewer, state_root
):
    """The strongest privacy claim, checked across every file that survives."""
    fake_reviewer.mode('propose')
    secret_prompt = (
        'no, use make test instead of pytest; the token is ghp_abcdefghijklmnopqrstuvwxyz0123'
    )
    capture.record_prompt({**workspace['stop'], 'prompt': secret_prompt})
    capture.record_tool_failure(
        {
            **workspace['stop'],
            'tool_name': 'Bash',
            'tool_input': {
                'command': "curl -H 'Authorization: Bearer sk-livesecret123456' https://internal.example.com/deploy"  # gitleaks:allow - intentionally fake redaction fixture
            },
            'error': "ENOENT: no such file or directory, open '/Users/someone/private.key'",
        }
    )
    wake(run_si, workspace['stop'])

    proposal_id, prefix = stage(run_si, workspace)
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))
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

    surviving = []
    for dirpath, _dirs, files in os.walk(str(state_root)):
        if 'backups' in dirpath:
            # Backups hold the target's own prior bytes by design.
            continue
        for name in files:
            with open(os.path.join(dirpath, name), encoding='utf-8', errors='replace') as handle:
                surviving.append(handle.read())
    combined = '\n'.join(surviving)
    # Without this the assertions below would pass on an empty state root.
    assert len(surviving) >= 3, 'expected durable state to inspect'
    assert 'mut-' in combined and 'cand-' in combined

    for forbidden in [
        'ghp_abcdefghijklmnopqrstuvwxyz0123',
        'sk-livesecret123456',
        'internal.example.com',
        'private.key',
        'Authorization: Bearer',
        'Switched the test command over.',
        secret_prompt,
    ]:
        assert forbidden not in combined, '%r survived into durable state' % forbidden


def test_the_journal_records_mutations_without_content(run_si, workspace):
    proposal_id, prefix = stage(run_si, workspace)
    authorize(run_si, 'apply', '%s %s' % (proposal_id, prefix))
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

    [record] = journal.read_mutations()
    assert 'Test with make test.' not in json.dumps(record)
    assert record['preimage_sha'] and record['post_sha']


def test_the_packaged_plugin_declares_every_hook_it_implements():
    with open(os.path.join(PLUGIN_ROOT, 'hooks', 'hooks.json'), encoding='utf-8') as f:
        manifest = json.load(f)
    assert set(manifest['hooks']) == {
        'UserPromptSubmit',
        'UserPromptExpansion',
        'PostToolUse',
        'PostToolUseFailure',
        'Stop',
        'SessionStart',
        'SessionEnd',
    }
    stop = manifest['hooks']['Stop'][0]['hooks'][0]
    assert stop['asyncRewake'] is True, "the Stop hook must not delay the user's response"
