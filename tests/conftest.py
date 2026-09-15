"""Settings every suite needs before the application is imported."""

from __future__ import annotations

import os

from tests.accounts import USERS

# Set, not defaulted: `make test` inherits the Makefile's demo accounts, and the suites
# sign in with their own.
os.environ["REWIND_USERS"] = USERS
