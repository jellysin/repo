"""Git started by the tests reaches only the temporary repository it is pointed at.

A git hook exports GIT_DIR and related variables to the commands it runs: a push from a linked worktree names
that worktree's git directory. Every git command a test starts, directly or through the scripts under test,
inherits them and then works on this repository instead of its temporary one. A test module that runs git
calls isolate() before it does.
"""

import os


def isolate(environment=os.environ):
    """Remove every GIT_* variable from the environment that git subprocesses inherit."""
    for name in [name for name in environment if name.startswith("GIT_")]:
        del environment[name]
