"""Staging one exact, immutable proposal (spec section 8).

This module is the trust boundary between what a model suggests and what can be
installed. Claude drafts the bytes, but every hash here is computed from the
bytes and from the target as they actually are on disk. A model cannot present
content it did not stage, or a hash prefix it invented, because the prefix the
user types is checked against a digest this code produced.
"""

import base64
import difflib
import hashlib
import os
import time
import uuid

from . import allowlist, config, redact, store

NEW_FILE = "new-file"


class ProposalError(Exception):
    """Raised with a bounded reason category."""

    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    """The digest of a file's current contents, or ``NEW_FILE`` if absent.

    The sentinel is deliberate: "this file does not exist" has to be as
    verifiable as any other precondition, or a proposal to create a file could
    silently overwrite one that appeared in the meantime.
    """
    if not os.path.exists(path):
        return NEW_FILE
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read())


def fingerprint(lesson, scope, kind):
    """A stable identity for a lesson, used to suppress duplicates.

    Normalized so that trivial rewording still collides: the same advice
    proposed twice should be recognized the second time.
    """
    normalized = " ".join((lesson or "").lower().split())
    return hashlib.sha256(
        ("%s|%s|%s" % (normalized, scope, kind)).encode("utf-8")
    ).hexdigest()[:32]


def content_hash(target, preimage_sha, new_bytes):
    """The digest the user authorizes against.

    Binds the destination and the expected prior state as well as the content,
    so an authorization for one proposal cannot apply another's bytes, and the
    same bytes aimed at a different file is a different proposal.
    """
    digest = hashlib.sha256()
    digest.update(target.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(preimage_sha.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(new_bytes)
    return digest.hexdigest()


def unified_diff(old_text, new_text, path):
    label = os.path.basename(path)
    lines = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="a/%s" % label,
        tofile="b/%s" % label,
        n=3,
    )
    return "".join(lines)


def stage(target, new_bytes, candidate=None, project_dir=None, reason=None):
    """Validate, hash, and store one immutable proposal.

    The caller supplies a destination and the exact bytes to install. Everything
    else — the preimage digest, the content hash, the diff — is derived here
    from the filesystem, not from anything the caller asserts.
    """
    if isinstance(new_bytes, str):
        new_bytes = new_bytes.encode("utf-8")
    if not new_bytes:
        raise ProposalError("empty_content")

    try:
        resolved = allowlist.resolve(target, project_dir=project_dir)
    except allowlist.PathRejected as exc:
        raise ProposalError("path_rejected", exc.reason) from exc

    path = resolved["path"]
    preimage_sha = sha256_file(path)
    post_sha = sha256_bytes(new_bytes)
    if preimage_sha == post_sha:
        raise ProposalError("no_change")

    old_text = ""
    if preimage_sha != NEW_FILE:
        with open(path, "rb") as handle:
            old_text = handle.read().decode("utf-8", errors="replace")
    new_text = new_bytes.decode("utf-8", errors="replace")

    candidate = candidate or {}
    lesson = candidate.get("lesson", "")
    proposal_id = "prop-%s" % uuid.uuid4().hex[:12]
    full_hash = content_hash(path, preimage_sha, new_bytes)

    record = {
        "proposal_id": proposal_id,
        "content_hash": full_hash,
        "hash_prefix": full_hash[:config.HASH_PREFIX_LENGTH],
        "target": path,
        "scope": resolved["scope"],
        "kind": resolved["kind"],
        "preimage_sha": preimage_sha,
        "post_sha": post_sha,
        "is_new_file": preimage_sha == NEW_FILE,
        "new_bytes_b64": _encode(new_bytes),
        "diff": unified_diff(old_text, new_text, path),
        "fingerprint": fingerprint(lesson, resolved["scope"], resolved["kind"]),
        "lesson": redact.scrub(lesson, limit=400),
        "applicability": redact.scrub(candidate.get("applicability"), limit=300),
        "counterexample": redact.scrub(candidate.get("counterexample"), limit=300),
        "evidence_summary": redact.scrub(candidate.get("evidence_summary"), limit=600),
        "signal_type": candidate.get("signal_type"),
        "ownership_reason": redact.scrub(reason, limit=400),
        "candidate_id": candidate.get("candidate_id"),
        "staged_at": int(time.time()),
    }
    store.write_record(store.PROPOSALS, proposal_id, record, ttl=config.PROPOSAL_TTL)
    return record


def _encode(data):
    return base64.b64encode(data).decode("ascii")


def decode_bytes(record):
    """The staged bytes, verified against the digest recorded alongside them."""
    data = base64.b64decode(record["new_bytes_b64"].encode("ascii"))
    if sha256_bytes(data) != record["post_sha"]:
        raise ProposalError("staged_content_corrupt")
    return data


def load(proposal_id):
    record = store.read_record(store.PROPOSALS, proposal_id)
    if record is None:
        raise ProposalError("unknown_or_expired_proposal")
    return record


def verify_hash_prefix(record, prefix):
    """Require the prefix the user typed to match the staged content hash.

    Compared against the full digest rather than the stored prefix, so a
    tampered record cannot make a mismatched prefix pass.
    """
    if not prefix:
        raise ProposalError("missing_hash_prefix")
    prefix = prefix.strip().lower()
    if len(prefix) < 6:
        raise ProposalError("hash_prefix_too_short")
    if not record["content_hash"].startswith(prefix):
        raise ProposalError("hash_mismatch")
    return True


def invalidate(proposal_id):
    return store.delete_record(store.PROPOSALS, proposal_id)


def summary(record):
    """The presentation block a skill shows the user, in one place.

    Kept here rather than in the skill's markdown so the identifiers, hash
    prefix, and destination shown to the user are always the staged ones.
    """
    lines = [
        "Proposal %s" % record["proposal_id"],
        "Destination: %s (%s scope, %s)"
        % (record["target"], record["scope"], record["kind"]),
        "Hash prefix: %s" % record["hash_prefix"],
        "Action: %s" % ("create new file" if record["is_new_file"] else "patch"),
        "",
        "Lesson: %s" % record["lesson"],
    ]
    if record.get("applicability"):
        lines.append("Applies: %s" % record["applicability"])
    if record.get("counterexample"):
        lines.append("Does not apply: %s" % record["counterexample"])
    if record.get("ownership_reason"):
        lines.append("Why this artifact: %s" % record["ownership_reason"])
    if record.get("evidence_summary"):
        lines.append("Evidence: %s" % record["evidence_summary"])
    lines += [
        "",
        "--- exact change ---",
        record["diff"] or "(new file)",
        "--- end change ---",
        "",
        "Apply:  /self-improve:apply %s %s"
        % (record["proposal_id"], record["hash_prefix"]),
        "Reject: /self-improve:reject %s" % record["proposal_id"],
    ]
    return "\n".join(lines)
