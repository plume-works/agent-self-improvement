"""Enforce the runtime dependency rule of spec section 4.1.

Plugin runtime code must import successfully with nothing but a system
``python3``, offline. This test is what keeps that true as the plugin grows: an
accidental ``import yaml`` fails here rather than in a user's hook, where it
would surface as a silently skipped capture.
"""

import ast
import os
import sys

import pytest

from tests.conftest import PLUGIN_ROOT, REPO_ROOT

# Modules the standard library gained after 3.9, which the runtime targets.
# sys.stdlib_module_names is 3.10+, so the test interpreter may know names the
# runtime interpreter would not have.
POST_39_STDLIB = {"tomllib", "graphlib", "zoneinfo"}


def runtime_modules():
    for dirpath, dirnames, filenames in os.walk(PLUGIN_ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def imported_roots(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        # node.level > 0 is a relative import, which stays inside this package.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.skipif(sys.version_info < (3, 10), reason="sys.stdlib_module_names requires Python 3.10")
@pytest.mark.parametrize("path", sorted(runtime_modules()), ids=lambda p: os.path.relpath(p, PLUGIN_ROOT))
def test_runtime_imports_stdlib_only(path):
    local_packages = {"selfimprove"}
    allowed = set(sys.stdlib_module_names) | local_packages
    offenders = sorted(root for root in imported_roots(path) if root not in allowed)
    assert not offenders, (
        "%s imports non-stdlib module(s) %s; plugin runtime code must load with a "
        "bare system python3" % (os.path.relpath(path, PLUGIN_ROOT), offenders)
    )


@pytest.mark.skipif(sys.version_info < (3, 10), reason="sys.stdlib_module_names requires Python 3.10")
@pytest.mark.parametrize("path", sorted(runtime_modules()), ids=lambda p: os.path.relpath(p, PLUGIN_ROOT))
def test_runtime_avoids_post_39_stdlib(path):
    used = imported_roots(path) & POST_39_STDLIB
    assert not used, "%s imports %s, which the 3.9 runtime target does not provide" % (
        os.path.relpath(path, PLUGIN_ROOT),
        sorted(used),
    )


def test_project_declares_no_runtime_dependencies():
    """``project.dependencies`` must stay empty.

    Parsed textually rather than with tomllib so this check also runs on 3.9.
    """
    with open(os.path.join(REPO_ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        text = handle.read()
    assert "\ndependencies = []\n" in text, "pyproject.toml must declare an empty project.dependencies list"
