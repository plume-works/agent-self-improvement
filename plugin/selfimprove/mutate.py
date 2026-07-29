"""Applying and rolling back exactly the approved bytes (spec section 9).

The ordering here is the safety property, not an implementation detail. Every
precondition is checked before anything is written, so a failure at any point
before installation leaves the target byte-identical. After installation, the
result is verified by re-reading it; the operation does not claim success on the
strength of having attempted it.

An interrupted run leaves an in-flight marker. The next operation must reconcile
that marker against what is actually on disk before any further mutation is
allowed, so an ambiguous state is resolved deliberately rather than overwritten.
"""

import contextlib
import json
import os
import shutil
import time
import uuid

from . import allowlist, journal, locking, paths, proposals, store

INFLIGHT = "inflight.json"


class MutationError(Exception):
    """Raised with a bounded reason category."""

    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _inflight_path():
    return paths.state_path(INFLIGHT)


def read_inflight():
    return store.read_path(_inflight_path(), allow_expired=True)


def _write_inflight(record):
    paths.atomic_write(_inflight_path(),
                       json.dumps(record, sort_keys=True, indent=2) + "\n")


def _clear_inflight():
    with contextlib.suppress(OSError):
        os.unlink(_inflight_path())


def reconcile():
    """Resolve an interrupted mutation before permitting another.

    Three outcomes are possible for a marker left behind by a crash: the target
    still holds the preimage, so nothing was installed; it holds the post-image,
    so installation completed but the record was never written; or it holds
    something else, which means an independent edit landed and a person has to
    look at it.
    """
    marker = read_inflight()
    if marker is None:
        return None

    target = marker["target"]
    observed = proposals.sha256_file(target)

    if observed == marker["preimage_sha"]:
        outcome = "not_installed"
    elif observed == marker["post_sha"]:
        outcome = "installed"
        journal.mutation(_mutation_record(marker, reconciled=True))
    else:
        raise MutationError("unreconciled_target", marker.get("mutation_id"))

    _clear_inflight()
    journal.diagnostic("reconcile", outcome, mutation_id=marker.get("mutation_id"))
    return {"outcome": outcome, "mutation_id": marker.get("mutation_id")}


def _mutation_record(marker, reconciled=False):
    record = {
        "mutation_id": marker["mutation_id"],
        "ts": int(time.time()),
        "operation": marker.get("operation", "apply"),
        "target": marker["target"],
        "scope": marker.get("scope"),
        "kind": marker.get("kind"),
        "proposal_id": marker.get("proposal_id"),
        "fingerprint": marker.get("fingerprint"),
        "signal_type": marker.get("signal_type"),
        "preimage_sha": marker["preimage_sha"],
        "post_sha": marker["post_sha"],
        "backup": marker.get("backup"),
        "was_new_file": marker.get("was_new_file", False),
    }
    if reconciled:
        record["reconciled"] = True
    return record


def _backup(target, mutation_id):
    """A mode-preserving copy of the current contents, synced before we proceed.

    Returns ``None`` for a proposal that creates a new file: there is nothing to
    preserve, and rollback deletes rather than restores.
    """
    if not os.path.exists(target):
        return None
    directory = paths.state_path("backups", mutation_id)
    paths.ensure_dir(directory)
    destination = os.path.join(directory, os.path.basename(target))
    shutil.copy2(target, destination)
    with open(destination, "rb") as handle:
        os.fsync(handle.fileno())
    paths.fsync_dir(directory)
    return destination


def _install(target, data):
    """Write ``data`` to ``target`` atomically, preserving an existing mode."""
    mode = paths.FILE_MODE
    if os.path.exists(target):
        mode = os.stat(target).st_mode & 0o777
    else:
        paths.ensure_dir(os.path.dirname(target))
        # A new instruction file is readable like the rest of the user's config.
        mode = 0o644
    paths.atomic_write(target, data, mode=mode)


def apply_proposal(proposal_id, hash_prefix, session_id=None, project_dir=None):
    """Install exactly the staged bytes, or change nothing.

    Implements the ten steps of section 9 in order. The authorization is
    consumed by the caller before this runs.
    """
    with locking.state_lock("mutate"):
        reconcile()

        record = proposals.load(proposal_id)
        proposals.verify_hash_prefix(record, hash_prefix)

        # Re-validate the destination now rather than trusting what staging
        # recorded: the filesystem may have changed since.
        try:
            resolved = allowlist.resolve(record["target"], project_dir=project_dir)
        except allowlist.PathRejected as exc:
            raise MutationError("path_rejected", exc.reason) from exc
        target = resolved["path"]
        if target != record["target"]:
            raise MutationError("target_moved")

        observed = proposals.sha256_file(target)
        if observed != record["preimage_sha"]:
            # Section 11: a stale target or a conflicting edit refuses and
            # requires regeneration. Never merge, never overwrite.
            raise MutationError("stale_target")

        data = proposals.decode_bytes(record)
        mutation_id = "mut-%s" % uuid.uuid4().hex[:12]
        backup = _backup(target, mutation_id)

        marker = {
            "mutation_id": mutation_id,
            "operation": "apply",
            "target": target,
            "scope": record["scope"],
            "kind": record["kind"],
            "proposal_id": proposal_id,
            "fingerprint": record["fingerprint"],
            "signal_type": record.get("signal_type"),
            "preimage_sha": record["preimage_sha"],
            "post_sha": record["post_sha"],
            "backup": backup,
            "was_new_file": record["is_new_file"],
        }
        _write_inflight(marker)

        try:
            _install(target, data)
        except OSError as exc:
            _clear_inflight()
            raise MutationError("install_failed") from exc

        installed = proposals.sha256_file(target)
        if installed != record["post_sha"]:
            raise MutationError("verification_failed", mutation_id)

        mutation = _mutation_record(marker)
        journal.mutation(mutation)
        _clear_inflight()

        proposals.invalidate(proposal_id)
        journal.record_fingerprint(record["fingerprint"], "accepted")
        return mutation


def rollback_mutation(mutation_id, project_dir=None):
    """Restore a verified preimage, or refuse.

    The same checks as installation, in reverse. A target that no longer hashes
    to the post-image has been edited since, and restoring a backup over it
    would destroy that work.
    """
    with locking.state_lock("mutate"):
        reconcile()

        original = journal.find_mutation(mutation_id)
        if original is None:
            raise MutationError("unknown_mutation")
        if original.get("operation") == "rollback":
            raise MutationError("already_a_rollback")
        if _already_rolled_back(mutation_id):
            raise MutationError("already_rolled_back")

        try:
            resolved = allowlist.resolve(original["target"], project_dir=project_dir)
        except allowlist.PathRejected as exc:
            raise MutationError("path_rejected", exc.reason) from exc
        target = resolved["path"]

        observed = proposals.sha256_file(target)
        if observed != original["post_sha"]:
            raise MutationError("target_changed_since_mutation")

        rollback_id = "mut-%s" % uuid.uuid4().hex[:12]
        marker = {
            "mutation_id": rollback_id,
            "operation": "rollback",
            "target": target,
            "scope": original.get("scope"),
            "kind": original.get("kind"),
            "proposal_id": original.get("proposal_id"),
            "fingerprint": original.get("fingerprint"),
            "preimage_sha": original["post_sha"],
            "post_sha": original["preimage_sha"],
            "backup": original.get("backup"),
            "rolls_back": mutation_id,
            "was_new_file": original.get("was_new_file", False),
        }
        _write_inflight(marker)

        try:
            if original.get("was_new_file"):
                # The mutation created this file; undoing it means removing it.
                os.unlink(target)
            else:
                backup = original.get("backup")
                if not backup or not os.path.exists(backup):
                    _clear_inflight()
                    raise MutationError("backup_missing")
                with open(backup, "rb") as handle:
                    data = handle.read()
                if proposals.sha256_bytes(data) != original["preimage_sha"]:
                    _clear_inflight()
                    raise MutationError("backup_corrupt")
                _install(target, data)
        except OSError as exc:
            _clear_inflight()
            raise MutationError("restore_failed") from exc

        restored = proposals.sha256_file(target)
        if restored != original["preimage_sha"]:
            raise MutationError("verification_failed", rollback_id)

        record = _mutation_record(marker)
        record["rolls_back"] = mutation_id
        journal.mutation(record)
        _clear_inflight()
        return record


def _already_rolled_back(mutation_id):
    return any(record.get("rolls_back") == mutation_id
               for record in journal.read_mutations())
