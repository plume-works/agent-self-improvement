"""
The mutation protocol (spec section 9).

The safety property is ordering: every precondition is checked before anything
is written, so a failure at any point before installation leaves the target
byte-identical. After installation the result is verified by re-reading it.
"""

import os

import pytest
from selfimprove import journal, mutate, proposals

ORIGINAL = '# Project\n\n- Existing instruction.\n'
UPDATED = '# Project\n\n- Existing instruction.\n- Run the suite with `make test`.\n'


@pytest.fixture
def target(project, state_root):
    path = project / 'CLAUDE.md'
    path.write_text(ORIGINAL)
    return path


@pytest.fixture
def staged(target, state_root):
    return proposals.stage(str(target), UPDATED, {'lesson': 'Use make test.'})


def apply(record):
    return mutate.apply_proposal(record['proposal_id'], record['hash_prefix'])


def test_apply_installs_exactly_the_staged_bytes(target, staged):
    apply(staged)
    assert target.read_text() == UPDATED


def test_apply_verifies_the_installed_content(target, staged):
    record = apply(staged)
    assert record['post_sha'] == proposals.sha256_file(str(target))


def test_apply_records_a_redacted_mutation(target, staged):
    record = apply(staged)
    [journaled] = journal.read_mutations()
    assert journaled['mutation_id'] == record['mutation_id']
    assert ORIGINAL not in str(journaled)
    assert UPDATED not in str(journaled)


def test_apply_creates_a_recoverable_backup(target, staged):
    record = apply(staged)
    with open(record['backup'], encoding='utf-8') as handle:
        assert handle.read() == ORIGINAL


def test_backup_preserves_the_file_mode(target, staged):
    os.chmod(target, 0o640)
    record = apply(staged)
    assert os.stat(record['backup']).st_mode & 0o777 == 0o640


def test_apply_preserves_an_existing_file_mode(target, staged):
    os.chmod(target, 0o640)
    apply(staged)
    assert os.stat(target).st_mode & 0o777 == 0o640


def test_apply_invalidates_the_proposal(target, staged):
    apply(staged)
    with pytest.raises(proposals.ProposalError):
        proposals.load(staged['proposal_id'])


def test_a_proposal_cannot_be_applied_twice(target, staged):
    apply(staged)
    with pytest.raises(proposals.ProposalError):
        apply(staged)


def test_a_wrong_hash_prefix_changes_nothing(target, staged):
    with pytest.raises(proposals.ProposalError):
        mutate.apply_proposal(staged['proposal_id'], '000000000000')
    assert target.read_text() == ORIGINAL


def test_a_stale_target_changes_nothing(target, staged):
    """Section 11: a conflicting edit refuses; it never merges or overwrites."""
    target.write_text('# Project\n\n- Someone else edited this.\n')
    with pytest.raises(mutate.MutationError) as caught:
        apply(staged)
    assert caught.value.reason == 'stale_target'
    assert target.read_text() == '# Project\n\n- Someone else edited this.\n'


def test_a_deleted_target_changes_nothing(target, staged):
    target.unlink()
    with pytest.raises(mutate.MutationError) as caught:
        apply(staged)
    assert caught.value.reason == 'stale_target'
    assert not target.exists()


def test_applying_to_a_new_file_creates_it(project, state_root):
    absent = project / '.claude' / 'rules' / 'testing.md'
    record = proposals.stage(str(absent), '# Testing\n\n- Use make test.\n')
    apply(record)
    assert absent.read_text() == '# Testing\n\n- Use make test.\n'


def test_a_new_file_proposal_refuses_if_the_file_appeared(project, state_root):
    absent = project / '.claude' / 'rules' / 'testing.md'
    record = proposals.stage(str(absent), '# Testing\n')
    absent.parent.mkdir(parents=True, exist_ok=True)
    absent.write_text('someone got here first\n')
    with pytest.raises(mutate.MutationError) as caught:
        apply(record)
    assert caught.value.reason == 'stale_target'
    assert absent.read_text() == 'someone got here first\n'


def test_rollback_restores_the_verified_preimage(target, staged):
    record = apply(staged)
    mutate.rollback_mutation(record['mutation_id'])
    assert target.read_text() == ORIGINAL


def test_rollback_of_a_created_file_removes_it(project, state_root):
    absent = project / '.claude' / 'rules' / 'testing.md'
    record = apply(proposals.stage(str(absent), '# Testing\n'))
    mutate.rollback_mutation(record['mutation_id'])
    assert not absent.exists()


def test_rollback_refuses_when_the_file_changed_since(target, staged):
    """Restoring over independent work would destroy it."""
    record = apply(staged)
    target.write_text(UPDATED + '- And something the user added.\n')
    with pytest.raises(mutate.MutationError) as caught:
        mutate.rollback_mutation(record['mutation_id'])
    assert caught.value.reason == 'target_changed_since_mutation'
    assert 'something the user added' in target.read_text()


def test_rollback_cannot_be_repeated(target, staged):
    record = apply(staged)
    mutate.rollback_mutation(record['mutation_id'])
    with pytest.raises(mutate.MutationError) as caught:
        mutate.rollback_mutation(record['mutation_id'])
    assert caught.value.reason in {'already_rolled_back', 'target_changed_since_mutation'}


def test_rollback_of_an_unknown_mutation_fails(state_root, project):
    with pytest.raises(mutate.MutationError) as caught:
        mutate.rollback_mutation('mut-nope')
    assert caught.value.reason == 'unknown_mutation'


def test_rollback_detects_a_corrupted_backup(target, staged):
    record = apply(staged)
    with open(record['backup'], 'w', encoding='utf-8') as handle:
        handle.write('not the original content')
    with pytest.raises(mutate.MutationError) as caught:
        mutate.rollback_mutation(record['mutation_id'])
    assert caught.value.reason == 'backup_corrupt'
    assert target.read_text() == UPDATED


def test_rollback_detects_a_missing_backup(target, staged):
    record = apply(staged)
    os.unlink(record['backup'])
    with pytest.raises(mutate.MutationError) as caught:
        mutate.rollback_mutation(record['mutation_id'])
    assert caught.value.reason == 'backup_missing'


def test_an_interrupted_mutation_that_did_not_install_is_reconciled(target, staged):
    """The marker says a mutation began; the file says it never landed."""
    mutate._write_inflight(
        {
            'mutation_id': 'mut-interrupted',
            'operation': 'apply',
            'target': str(target),
            'preimage_sha': proposals.sha256_file(str(target)),
            'post_sha': 'deadbeef',
            'backup': None,
        }
    )
    outcome = mutate.reconcile()
    assert outcome['outcome'] == 'not_installed'
    assert mutate.read_inflight() is None
    assert target.read_text() == ORIGINAL


def test_an_interrupted_mutation_that_did_install_is_journaled(target, state_root):
    """Installation completed but the record never got written."""
    target.write_text(UPDATED)
    mutate._write_inflight(
        {
            'mutation_id': 'mut-interrupted',
            'operation': 'apply',
            'target': str(target),
            'preimage_sha': proposals.sha256_bytes(ORIGINAL.encode()),
            'post_sha': proposals.sha256_file(str(target)),
            'backup': None,
        }
    )
    outcome = mutate.reconcile()
    assert outcome['outcome'] == 'installed'
    assert journal.find_mutation('mut-interrupted')['reconciled'] is True


def test_an_ambiguous_interrupted_state_blocks_further_mutation(target, staged):
    """Neither preimage nor post-image: a person has to look at it."""
    mutate._write_inflight(
        {
            'mutation_id': 'mut-interrupted',
            'operation': 'apply',
            'target': str(target),
            'preimage_sha': 'aaaa',
            'post_sha': 'bbbb',
            'backup': None,
        }
    )
    with pytest.raises(mutate.MutationError) as caught:
        apply(staged)
    assert caught.value.reason == 'unreconciled_target'
    assert target.read_text() == ORIGINAL


def test_the_inflight_marker_is_cleared_after_a_successful_apply(target, staged):
    apply(staged)
    assert mutate.read_inflight() is None


def test_applying_records_the_fingerprint_as_accepted(target, staged):
    apply(staged)
    assert journal.fingerprint_status(staged['fingerprint']) == 'accepted'
