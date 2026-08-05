"""
State root resolution and filesystem primitives.

Every durable write in the plugin goes through :func:`atomic_write`, and every
directory is created private to the user. See spec sections 4.1 and 10.1.
"""

import contextlib
import errno
import os
import tempfile

DIR_MODE = 0o700
FILE_MODE = 0o600


def state_root():
    """
    Resolve the runtime state root.

    Order is fixed by spec section 4.1: an explicit override, then the plugin
    data directory Claude Code provides, then a directory under the Claude home.

    The override has to be checked first to be usable at all. Claude Code sets
    ``CLAUDE_PLUGIN_DATA`` itself in every hook environment, replacing whatever
    the surrounding environment held, so a root that lost to it would be ignored
    by precisely the hooks that produce state.
    """
    for key in ('SELF_IMPROVE_STATE_DIR', 'CLAUDE_PLUGIN_DATA'):
        value = os.environ.get(key)
        if value:
            return os.path.abspath(os.path.expanduser(value))
    return os.path.join(claude_home(), 'self-improvement')


def claude_home():
    """Return the user's Claude configuration directory."""
    override = os.environ.get('CLAUDE_CONFIG_DIR')
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser('~'), '.claude')


def plugin_root():
    """
    Return the installed plugin directory.

    ``CLAUDE_PLUGIN_ROOT`` is set by Claude Code when it runs a hook. Falling
    back to the package location keeps direct invocation and tests working.
    """
    value = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if value:
        return os.path.abspath(os.path.expanduser(value))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure_dir(path):
    """Create ``path`` and its parents, private to the user."""
    try:
        os.makedirs(path, DIR_MODE)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    else:
        return path
    # A directory created before this plugin ran, or by an older umask, may be
    # wider than intended. Narrow it rather than trusting what we find.
    with contextlib.suppress(OSError):
        if os.stat(path).st_mode & 0o777 != DIR_MODE:
            os.chmod(path, DIR_MODE)
    return path


def state_path(*parts):
    """Absolute path inside the state root, with parent directories created."""
    path = os.path.join(state_root(), *parts)
    ensure_dir(os.path.dirname(path))
    return path


def fsync_dir(path):
    """Flush a directory entry so a rename survives power loss."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        # Some filesystems reject fsync on a directory handle. The rename is
        # still atomic; only the durability guarantee is weaker.
        pass
    finally:
        os.close(fd)


def atomic_write(path, data, mode=FILE_MODE):
    """
    Install ``data`` at ``path`` atomically.

    The temporary file is created in the destination directory so the rename
    stays within one filesystem, and both the file and its directory are synced
    before the call returns. A reader either sees the previous contents or the
    complete new contents, never a partial write.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    directory = os.path.dirname(os.path.abspath(path))
    ensure_dir(directory)
    fd, temp = tempfile.mkstemp(dir=directory, prefix='.si-tmp-')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    fsync_dir(directory)
    return path
