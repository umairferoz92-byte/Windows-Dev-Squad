"""Pytest configuration for the Windows Dev Squad test suite.

On Windows, pytest's default temp base lives under the OS ``%TEMP%`` dir and
pytest maintains a *junction* (``pytest-of-<user>/pytest-current``) pointing at
the active numbered run directory. If a run is interrupted (killed, system
hibernation, crash), that junction can be left in a broken state and pytest's
``cleanup_dead_symlinks`` then crashes on ``os.stat`` with WinError 5 on every
subsequent run -- all tests pass but the session still exits rc:1.

This conftest relocates the temp base to a user-writable directory *outside*
the repo and *outside* the OS Temp dir, so junction/symlink tests are created
and cleaned on a healthy volume and the stale-junction crash cannot occur.
"""

import os
import sys

def pytest_configure(config):
    if sys.platform != "win32":
        return
    if config.option.basetemp:  # an explicit --basetemp wins
        return
    base = os.path.join(os.path.expanduser("~"), ".squad-pytest-tmp")
    config.option.basetemp = base