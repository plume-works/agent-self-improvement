"""
Finding the artifact that should own a lesson (spec section 8).

Routing prefers patching something that already exists over creating something
new, so this module reports what exists and how it is organized. It reads only
allowlisted paths, and reports headings and frontmatter rather than file
contents: enough for the model to judge ownership, not enough to leak a file
into a model call.
"""

import os
import re

from . import allowlist, redact

MAX_HEADINGS = 12
MAX_BYTES = 200_000

HEADING = re.compile(r'^(#{1,4})\s+(.+?)\s*#*$')
FRONTMATTER_FIELD = re.compile(r'^(name|description)\s*:\s*(.+?)\s*$')


def read_frontmatter(path):
    """
    Read a skill's ``name`` and ``description`` without a YAML parser.

    Only two scalar fields are ever needed, and depending on PyYAML would put a
    third-party import in a hook path. Anthropic's own security-guidance plugin
    made the same call, treating YAML support as best-effort because it does not
    install the parser for the user.
    """
    fields = {}
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            first = handle.readline()
            if first.strip() != '---':
                return fields
            for line in handle:
                if line.strip() == '---':
                    break
                match = FRONTMATTER_FIELD.match(line)
                if match:
                    value = match.group(2).strip().strip('\'"')
                    fields[match.group(1)] = redact.scrub(value, limit=300)
    except OSError:
        return fields
    return fields


def headings(path):
    """Top-level headings, which describe how a document is organized."""
    found = []
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            in_fence = False
            for line in handle:
                stripped = line.strip()
                if stripped.startswith('```'):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                match = HEADING.match(stripped)
                if match:
                    found.append(redact.scrub(match.group(2), limit=120))
                    if len(found) >= MAX_HEADINGS:
                        break
    except OSError:
        return found
    return found


def describe(path, scope, kind):
    """Return a bounded summary of one candidate owner."""
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    entry = {
        'path': path,
        'scope': scope,
        'kind': kind,
        'exists': True,
        'bytes': size,
        'headings': headings(path),
    }
    if kind == allowlist.SKILL:
        entry.update(read_frontmatter(path))
    return entry


def discover(project_dir=None, include_missing=True):
    """
    Every allowlisted artifact, existing or available to create.

    Existing owners come first so the caller sees what it could patch before it
    sees where it could create something new, which is the section 8 preference
    order made visible rather than merely documented.
    """
    project_dir = project_dir or os.getcwd()
    found = []
    available = []

    for scope in (allowlist.PROJECT, allowlist.USER):
        for path in allowlist.candidate_paths(scope, allowlist.CLAUDE_MD, project_dir=project_dir):
            if os.path.isfile(path):
                found.append(describe(path, scope, allowlist.CLAUDE_MD))
            elif include_missing:
                available.append(
                    {'path': path, 'scope': scope, 'kind': allowlist.CLAUDE_MD, 'exists': False}
                )

        found.extend(_scan_directory(scope, allowlist.RULE, 'rules', project_dir))
        found.extend(_scan_directory(scope, allowlist.SKILL, 'skills', project_dir))

    return found + available


def _scan_directory(scope, kind, subdir, project_dir):
    root = (
        allowlist.roots(project_dir)[scope]
        if scope == allowlist.USER
        else os.path.join(allowlist.roots(project_dir)[scope], '.claude')
    )
    base = os.path.join(root, subdir)
    if not os.path.isdir(base):
        return []

    entries = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(dirnames)[:50]
        for name in sorted(filenames):
            if kind == allowlist.SKILL and name != 'SKILL.md':
                continue
            if kind == allowlist.RULE and not name.endswith('.md'):
                continue
            path = os.path.join(dirpath, name)
            try:
                # Round-trip through the allowlist so discovery can never
                # surface a path the mutator would refuse.
                resolved = allowlist.resolve(path, project_dir=project_dir)
            except allowlist.PathRejected:
                continue
            if os.path.getsize(path) > MAX_BYTES:
                continue
            entries.append(describe(resolved['path'], scope, resolved['kind']))
    return entries


def search(query, project_dir=None):
    """
    Rank candidate owners by overlap with the reviewer's ``owner_query``.

    A deliberately simple keyword score. The model makes the ownership decision;
    this only orders what it looks at, and a wrong order costs nothing but a
    slightly longer read.
    """
    terms = {term for term in re.split(r'\W+', (query or '').lower()) if len(term) > 2}
    scored = []
    for entry in discover(project_dir=project_dir):
        haystack = ' '.join(
            [
                entry.get('path', ''),
                ' '.join(entry.get('headings', [])),
                entry.get('name', ''),
                entry.get('description', ''),
            ]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if entry.get('exists'):
            score += 1
        scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['path']))
    return [entry for _score, entry in scored]
