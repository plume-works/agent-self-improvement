"""
The single chokepoint for anything that reaches disk.

Spec section 10 forbids persisting raw prompts, assistant responses, transcript
bodies, credentials, raw tool output, full shell commands with arguments, and
unrelated project file content. Every writer in this package routes through the
functions here rather than deciding for itself what is safe.
"""

import os
import posixpath
import re
import shlex

from . import config

EXTERNAL = '<external>'
REDACTED = '<redacted>'

# Values that look like credentials, regardless of the key they appear under.
_SECRET_VALUE_PATTERNS = [
    re.compile(r'\bsk-[A-Za-z0-9_-]{16,}'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+'),
    re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
]

# key=value and key: value pairs whose key implies a secret.
_SECRET_ASSIGNMENT = re.compile(
    r'(?i)\b([A-Za-z0-9_.-]*(?:secret|token|password|passwd|apikey|api_key|'
    r'access_key|private_key|credential|auth)[A-Za-z0-9_.-]*)'
    r"\s*[:=]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)

# Long opaque strings that no legitimate signature needs.
_LONG_OPAQUE = re.compile(r'\b[A-Za-z0-9+/_-]{40,}={0,2}\b')

# Error classes, ordered most specific first. The raw message is never kept.
_ERROR_CLASSES = [
    ('interrupted', re.compile(r'(?i)interrupt|cancell?ed|sigint|sigterm')),
    ('timeout', re.compile(r'(?i)timed?\s*out|etimedout|deadline exceeded')),
    (
        'command_not_found',
        re.compile(
            r'(?i)command not found|no such command|executable file not found|'
            r'is not recognized as an internal'
        ),
    ),
    (
        'file_not_found',
        re.compile(
            r'(?i)no such file or directory|enoent|cannot find the (file|path)|'
            r'file (does not exist|not found)'
        ),
    ),
    (
        'permission_denied',
        re.compile(
            r'(?i)permission denied|eacces|eperm|operation not permitted|'
            r'access is denied'
        ),
    ),
    (
        'network',
        re.compile(
            r'(?i)econnrefused|enotfound|network is unreachable|could not resolve|'
            r'connection reset|ssl|certificate'
        ),
    ),
    ('not_found_remote', re.compile(r'(?i)\b404\b|not found on remote')),
    ('unauthorized', re.compile(r'(?i)\b401\b|\b403\b|unauthorized|forbidden')),
    ('syntax_error', re.compile(r'(?i)syntaxerror|parse error|unexpected token|invalid syntax')),
    ('type_error', re.compile(r'(?i)typeerror|type mismatch|cannot read propert')),
    (
        'assertion_failed',
        re.compile(r'(?i)assertionerror|assertion failed|test(s)? failed|\bfailed\b.*\btest'),
    ),
    ('conflict', re.compile(r'(?i)merge conflict|already exists|conflict')),
    ('nonzero_exit', re.compile(r'(?i)exit(ed)? (code|status)|non-?zero')),
]

# Tokens that wrap the command actually being run.
_WRAPPERS = {'env', 'sudo', 'command', 'nohup', 'time', 'exec', 'nice', 'xargs'}

# A subcommand-shaped token: no path separators, no dots, no assignment.
_SUBCOMMAND = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')


def scrub(text, limit=None):
    """
    Remove credential-shaped substrings and bound the length.

    Applied to any free text that survives a turn, including text held only in
    the ephemeral turn file. Ephemeral data still lands on disk, so it gets the
    same treatment as durable data.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    text = _SECRET_ASSIGNMENT.sub(lambda m: '%s=%s' % (m.group(1), REDACTED), text)
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = _LONG_OPAQUE.sub(REDACTED, text)
    return truncate(text, limit if limit is not None else config.MAX_FIELD_LENGTH)


def truncate(text, limit):
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + '…'


def error_class(message):
    """
    Reduce an error message to a bounded category.

    Spec section 5.3 permits an error class and forbids the raw output, so the
    message itself is discarded once it has been classified.
    """
    if not message:
        return 'unknown'
    for name, pattern in _ERROR_CLASSES:
        if pattern.search(message):
            return name
    return 'other'


def normalize_command(command):
    """
    Reduce a shell command to ``program`` or ``program subcommand``.

    Spec section 10 forbids storing full commands with arguments. Dropping the
    arguments also makes the signature a better key for failure-to-success
    pairing: ``pytest tests/unit`` and ``pytest tests/integration`` are the same
    operation for the purpose of noticing that a retry finally worked.
    """
    if not command:
        return 'unknown'
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Unbalanced quotes. Fall back to whitespace splitting rather than
        # letting a malformed command break capture.
        tokens = command.split()
    if not tokens:
        return 'unknown'

    # Step past wrappers and leading VAR=value assignments.
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if '=' in token and not token.startswith('-') and '/' not in token.split('=')[0]:
            index += 1
            continue
        if posixpath.basename(token) in _WRAPPERS:
            index += 1
            continue
        break
    if index >= len(tokens):
        return 'unknown'

    program = posixpath.basename(tokens[index]).lower()
    if not program:
        return 'unknown'

    for token in tokens[index + 1 :]:
        if token.startswith('-'):
            continue
        if _SUBCOMMAND.match(token):
            return '%s %s' % (program, token.lower())
        break
    return program


def normalize_path(path, cwd=None):
    """
    Express a path relative to the working directory, or mark it external.

    Paths inside the project are kept because routing needs them. Anything
    outside is reduced to a marker: an absolute path elsewhere on the machine
    can disclose directory names that have nothing to do with the project.
    """
    if not path:
        return None
    cwd = os.path.abspath(cwd or os.getcwd())
    absolute = os.path.abspath(os.path.expanduser(path))
    try:
        relative = os.path.relpath(absolute, cwd)
    except ValueError:
        # Different drive on Windows.
        return EXTERNAL
    if relative.startswith(os.pardir):
        return EXTERNAL
    return relative.replace(os.sep, '/')


def tool_signature(tool_name, tool_input, cwd=None):
    """
    Return a bounded, comparable signature for one tool operation.

    This is what failure-to-success pairing compares, so it must be stable
    across a failed attempt and the later successful one while carrying no
    argument values.
    """
    tool_input = tool_input or {}
    if tool_name == 'Bash':
        return 'Bash:%s' % normalize_command(tool_input.get('command'))
    target = tool_input.get('file_path') or tool_input.get('notebook_path')
    if target:
        return '%s:%s' % (tool_name, normalize_path(target, cwd))
    return str(tool_name)
