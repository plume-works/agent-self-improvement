"""Expiring record storage and the sweep."""

import json
import os
import time

from selfimprove import config, journal, paths, store


def test_write_and_read_round_trip(state_root):
    store.write_record(store.CANDIDATES, "c1", {"lesson": "x"}, ttl=60)
    record = store.read_record(store.CANDIDATES, "c1")
    assert record["lesson"] == "x"
    assert record["expires_at"] > time.time()


def test_records_are_written_private(state_root):
    path = store.write_record(store.PROPOSALS, "p1", {"a": 1}, ttl=60)
    assert os.stat(path).st_mode & 0o777 == paths.FILE_MODE


def test_expired_record_is_invisible_before_any_sweep(state_root):
    """Expiry is enforced on read, not only by the sweep.

    An authorization that outlived its ten minutes must be unusable even if no
    sweep has run since.
    """
    store.write_record(store.AUTHORIZATIONS, "a1", {"op": "apply"}, ttl=-1)
    assert store.read_record(store.AUTHORIZATIONS, "a1") is None
    assert store.read_record(store.AUTHORIZATIONS, "a1", allow_expired=True) is not None


def test_missing_record_reads_as_none(state_root):
    assert store.read_record(store.CANDIDATES, "absent") is None


def test_corrupt_record_reads_as_none(state_root):
    path = store.write_record(store.CANDIDATES, "bad", {"a": 1}, ttl=60)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert store.read_record(store.CANDIDATES, "bad") is None


def test_sweep_removes_only_expired_records(state_root):
    store.write_record(store.CANDIDATES, "live", {}, ttl=3600)
    store.write_record(store.CANDIDATES, "dead", {}, ttl=-1)
    removed = store.sweep()
    assert removed == 1
    assert store.read_record(store.CANDIDATES, "live") is not None
    assert store.read_record(store.CANDIDATES, "dead", allow_expired=True) is None


def test_sweep_clears_ephemeral_turn_data(state_root):
    """Spec section 10 requires ephemeral turn input to be deleted on expiry."""
    store.write_record(store.TURNS, "t1", {"prompt": "x"}, ttl=-1, subdir="session-a")
    store.sweep()
    assert not os.path.exists(
        os.path.join(paths.state_root(), store.TURNS, "session-a", "t1.json")
    )


def test_sweep_prunes_empty_session_directories(state_root):
    store.write_record(store.TURNS, "t1", {}, ttl=-1, subdir="session-a")
    store.sweep()
    assert not os.path.isdir(os.path.join(paths.state_root(), store.TURNS, "session-a"))


def test_list_records_returns_newest_first(state_root):
    store.write_record(store.CANDIDATES, "old", {"created_at": 100}, ttl=3600)
    store.write_record(store.CANDIDATES, "new", {"created_at": 200}, ttl=3600)
    ordering = [r["created_at"] for r in store.list_records(store.CANDIDATES)]
    assert ordering == [200, 100]


def test_list_records_omits_expired(state_root):
    store.write_record(store.CANDIDATES, "live", {}, ttl=3600)
    store.write_record(store.CANDIDATES, "dead", {}, ttl=-1)
    assert len(store.list_records(store.CANDIDATES)) == 1


def test_configured_lifetimes_match_the_spec():
    assert config.TURN_TTL == 3600
    assert config.CANDIDATE_TTL == 86400
    assert config.PROPOSAL_TTL == 86400
    assert config.AUTHORIZATION_TTL == 600


def test_fingerprints_round_trip(state_root):
    assert journal.fingerprint_status("fp") is None
    journal.record_fingerprint("fp", "rejected", reason_category="not_reusable")
    assert journal.fingerprint_status("fp") == "rejected"


def test_diagnostics_record_a_class_not_a_message(state_root):
    journal.diagnostic("review-turn", "timeout", exception="TimeoutExpired")
    path = os.path.join(paths.state_root(), journal.DIAGNOSTICS)
    with open(path, encoding="utf-8") as handle:
        record = json.loads(handle.read().strip())
    assert record["error_class"] == "timeout"
    assert record["exception"] == "TimeoutExpired"
    assert record["stage"] == "review-turn"
