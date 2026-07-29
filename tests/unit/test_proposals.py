"""Proposal staging: the boundary between what a model suggests and what installs."""

import pytest

from selfimprove import proposals

CANDIDATE = {
    "lesson": "Run the suite with `make test`.",
    "applicability": "Whenever running tests here.",
    "counterexample": "Not for a single test in isolation.",
    "evidence_summary": "The user corrected the command twice.",
    "signal_type": "explicit_correction",
}


@pytest.fixture
def target(project, state_root):
    path = project / "CLAUDE.md"
    path.write_text("# Project\n\n- Existing instruction.\n")
    return path


def test_staging_computes_hashes_from_disk(target, state_root):
    """The plugin hashes what is actually there, not what a caller asserts."""
    record = proposals.stage(str(target), "# Project\n\n- New.\n", CANDIDATE)
    assert record["preimage_sha"] == proposals.sha256_file(str(target))
    assert record["post_sha"] == proposals.sha256_bytes(b"# Project\n\n- New.\n")
    assert record["content_hash"].startswith(record["hash_prefix"])
    assert len(record["hash_prefix"]) == 12


def test_staging_does_not_touch_the_target(target, state_root):
    before = target.read_text()
    proposals.stage(str(target), "# Different\n", CANDIDATE)
    assert target.read_text() == before


def test_staged_record_carries_a_readable_diff(target, state_root):
    record = proposals.stage(str(target), "# Project\n\n- Existing instruction.\n"
                             "- Run the suite with `make test`.\n", CANDIDATE)
    assert "+- Run the suite with `make test`." in record["diff"]
    assert record["diff"].startswith("---")


def test_new_file_staging_records_the_sentinel(project, state_root):
    absent = project / ".claude" / "rules" / "testing.md"
    record = proposals.stage(str(absent), "# Testing\n")
    assert record["is_new_file"] is True
    assert record["preimage_sha"] == proposals.NEW_FILE


def test_content_hash_binds_the_destination(project, state_root):
    """The same bytes aimed at a different file must be a different proposal."""
    one = project / "CLAUDE.md"
    two = project / ".claude" / "CLAUDE.md"
    one.write_text("x")
    two.write_text("x")
    first = proposals.stage(str(one), "same bytes\n")
    second = proposals.stage(str(two), "same bytes\n")
    assert first["content_hash"] != second["content_hash"]


def test_content_hash_binds_the_expected_prior_state(target, state_root):
    first = proposals.stage(str(target), "new content\n")
    target.write_text("someone else edited this\n")
    second = proposals.stage(str(target), "new content\n")
    assert first["content_hash"] != second["content_hash"]


def test_a_no_op_proposal_is_refused(target, state_root):
    with pytest.raises(proposals.ProposalError) as caught:
        proposals.stage(str(target), target.read_text())
    assert caught.value.reason == "no_change"


def test_empty_content_is_refused(target, state_root):
    with pytest.raises(proposals.ProposalError) as caught:
        proposals.stage(str(target), b"")
    assert caught.value.reason == "empty_content"


def test_a_target_outside_the_allowlist_is_refused(project, state_root, tmp_path):
    with pytest.raises(proposals.ProposalError) as caught:
        proposals.stage(str(tmp_path / "elsewhere.md"), "content\n")
    assert caught.value.reason == "path_rejected"


def test_hash_prefix_verification_accepts_the_displayed_prefix(target, state_root):
    record = proposals.stage(str(target), "new\n", CANDIDATE)
    assert proposals.verify_hash_prefix(record, record["hash_prefix"])


def test_hash_prefix_verification_is_case_insensitive(target, state_root):
    record = proposals.stage(str(target), "new\n", CANDIDATE)
    assert proposals.verify_hash_prefix(record, record["hash_prefix"].upper())


@pytest.mark.parametrize("prefix", ["", None, "abc", "0" * 12, "deadbeefcafe"])
def test_a_wrong_hash_prefix_is_refused(target, state_root, prefix):
    record = proposals.stage(str(target), "new\n", CANDIDATE)
    if prefix == record["hash_prefix"]:
        pytest.skip("collision with the real prefix")
    with pytest.raises(proposals.ProposalError):
        proposals.verify_hash_prefix(record, prefix)


def test_hash_prefix_is_checked_against_the_full_digest(target, state_root):
    """A tampered stored prefix must not make a mismatched prefix pass."""
    record = proposals.stage(str(target), "new\n", CANDIDATE)
    record["hash_prefix"] = "000000000000"
    with pytest.raises(proposals.ProposalError):
        proposals.verify_hash_prefix(record, "000000000000")


def test_decode_detects_corrupted_staged_content(target, state_root):
    record = proposals.stage(str(target), "new\n", CANDIDATE)
    record["new_bytes_b64"] = "dGFtcGVyZWQ="
    with pytest.raises(proposals.ProposalError) as caught:
        proposals.decode_bytes(record)
    assert caught.value.reason == "staged_content_corrupt"


def test_loading_an_unknown_proposal_fails(state_root):
    with pytest.raises(proposals.ProposalError) as caught:
        proposals.load("prop-nope")
    assert caught.value.reason == "unknown_or_expired_proposal"


def test_fingerprints_ignore_trivial_rewording():
    assert proposals.fingerprint("Use  MAKE test.", "project", "CLAUDE.md") == \
        proposals.fingerprint("use make TEST.", "project", "CLAUDE.md")


def test_fingerprints_distinguish_scope():
    assert proposals.fingerprint("x y z", "project", "CLAUDE.md") != \
        proposals.fingerprint("x y z", "user", "CLAUDE.md")


def test_summary_shows_destination_hash_and_both_commands(target, state_root):
    record = proposals.stage(str(target), "new\n", CANDIDATE)
    text = proposals.summary(record)
    assert record["target"] in text
    assert record["hash_prefix"] in text
    assert "/self-improve:apply %s %s" % (record["proposal_id"],
                                          record["hash_prefix"]) in text
    assert "/self-improve:reject %s" % record["proposal_id"] in text


def test_summary_scrubs_credentials_from_the_lesson(target, state_root):
    record = proposals.stage(str(target), "new\n",
                             {"lesson": "token is ghp_abcdefghijklmnopqrstuvwxyz01"})
    assert "ghp_" not in proposals.summary(record)
