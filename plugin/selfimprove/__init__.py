"""Local learning engine for the self-improve Claude Code plugin.

Runtime code in this package imports the Python standard library only. Hook
scripts run inside Claude Code's environment on a five-second budget and must
fail open, so there is no import here that could require a bootstrap step. See
spec section 4.1.
"""

__version__ = "0.1.0"
