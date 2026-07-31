"""Advisory locking for state mutation.

Hooks from concurrent sessions share one state root, and the mutation protocol
in spec section 9 must not interleave. ``fcntl.flock`` is released automatically
when the process exits, so a crash mid-mutation cannot leave a lock behind.
"""

import contextlib
import fcntl
import os

from . import paths


@contextlib.contextmanager
def state_lock(name="state", blocking=True):
    """Hold an exclusive lock for the duration of the block.

    With ``blocking=False`` a lock already held elsewhere raises
    :class:`BlockingIOError` rather than waiting, which lets capture hooks give
    up instead of spending their five-second budget queueing.
    """
    path = paths.state_path("locks", "%s.lock" % name)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, paths.FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
