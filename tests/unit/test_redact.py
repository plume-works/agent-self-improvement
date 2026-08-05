"""Redaction, command normalization, and error classification.

Spec section 10 forbids persisting credentials, raw tool output, and full shell
commands with arguments. These are the tests that hold that line.
"""

import pytest

from selfimprove import redact


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("npm test", "npm test"),
        ("git commit -m 'add the thing'", "git commit"),
        ("git  push   --force origin main", "git push"),
        ("pytest tests/unit", "pytest"),
        ("/usr/local/bin/cargo build --release", "cargo build"),
        ("sudo systemctl restart nginx", "systemctl restart"),
        ("env FOO=bar npm run build", "npm run"),
        ("NODE_ENV=production node server.js", "node"),
        ("ls -la", "ls"),
        ("", "unknown"),
        ("   ", "unknown"),
    ],
)
def test_normalize_command_keeps_only_program_and_subcommand(command, expected):
    assert redact.normalize_command(command) == expected


def test_normalize_command_drops_argument_values():
    """The specific thing section 10 forbids: arguments surviving into state."""
    signature = redact.normalize_command(
        "curl -H 'Authorization: Bearer sk-secretvalue123456' https://api.example.com/v1"
    )
    assert signature == "curl"
    assert "sk-" not in signature
    assert "example.com" not in signature


def test_normalize_command_survives_unbalanced_quotes():
    assert redact.normalize_command("echo 'unterminated") == "echo"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("bash: frobnicate: command not found", "command_not_found"),
        ("ENOENT: no such file or directory, open 'x'", "file_not_found"),
        ("EACCES: permission denied", "permission_denied"),
        ("Command timed out after 2m", "timeout"),
        ("fatal: could not resolve host: github.com", "network"),
        ("SyntaxError: invalid syntax", "syntax_error"),
        ("AssertionError: expected 1 to equal 2", "assertion_failed"),
        ("Command exited with non-zero status code 1", "nonzero_exit"),
        ("user interrupted the operation", "interrupted"),
        ("something entirely unfamiliar", "other"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_error_class_reduces_message_to_category(message, expected):
    assert redact.error_class(message) == expected


@pytest.mark.parametrize(
    "secret",
    [
        "sk-abcdefghijklmnopqrstuvwxyz012345",
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "xoxb-1234567890-abcdefghij",
        "Bearer abcdefghijklmnopqrstuvwx",
    ],
)
def test_scrub_removes_credential_shaped_values(secret):
    scrubbed = redact.scrub("the token is %s ok" % secret, limit=500)
    assert secret not in scrubbed
    assert redact.REDACTED in scrubbed


def test_scrub_removes_values_of_secret_named_keys():
    scrubbed = redact.scrub("DATABASE_PASSWORD=hunter2 and api_key: abc123", limit=500)
    assert "hunter2" not in scrubbed
    assert "abc123" not in scrubbed


def test_scrub_removes_private_key_blocks():
    scrubbed = redact.scrub("-----BEGIN RSA PRIVATE KEY-----", limit=500)
    assert "BEGIN RSA PRIVATE KEY" not in scrubbed


def test_scrub_bounds_length():
    scrubbed = redact.scrub("x" * 5000, limit=100)
    assert len(scrubbed) <= 101


def test_scrub_passes_ordinary_text_through():
    text = "the build failed because the port was already in use"
    assert redact.scrub(text, limit=500) == text


def test_normalize_path_keeps_project_relative_paths(tmp_path):
    target = tmp_path / "src" / "main.py"
    assert redact.normalize_path(str(target), cwd=str(tmp_path)) == "src/main.py"


def test_normalize_path_marks_paths_outside_the_project(tmp_path):
    outside = tmp_path.parent / "elsewhere" / "secrets.txt"
    assert redact.normalize_path(str(outside), cwd=str(tmp_path)) == redact.EXTERNAL


def test_tool_signature_is_stable_across_failure_and_retry(tmp_path):
    """Pairing depends on a failed attempt and its retry sharing a signature."""
    failed = redact.tool_signature("Bash", {"command": "pytest tests/unit -x"}, cwd=str(tmp_path))
    succeeded = redact.tool_signature("Bash", {"command": "pytest tests/unit"}, cwd=str(tmp_path))
    assert failed == succeeded == "Bash:pytest"


def test_tool_signature_distinguishes_different_programs(tmp_path):
    assert redact.tool_signature("Bash", {"command": "npm test"}, cwd=str(tmp_path)) != redact.tool_signature(
        "Bash", {"command": "npm build"}, cwd=str(tmp_path)
    )


def test_tool_signature_for_file_tools_uses_relative_path(tmp_path):
    signature = redact.tool_signature("Edit", {"file_path": str(tmp_path / "src" / "a.py")}, cwd=str(tmp_path))
    assert signature == "Edit:src/a.py"
