"""Test accounts, one on each side of the E10.3 role boundary.

``tests/conftest.py`` puts them in ``REWIND_USERS`` before the API is imported, so every
suite signs in the same way, and a request with no account is the one exception a test
asks for explicitly.
"""

from __future__ import annotations

import base64

PASSWORD = "secret"
USERS = f"investigator:{PASSWORD}:investigator,analyst:{PASSWORD}:analyst"


def as_user(name: str) -> dict[str, str]:
    """Return the header that signs a request as ``name``."""
    token = base64.b64encode(f"{name}:{PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


INVESTIGATOR = as_user("investigator")
ANALYST = as_user("analyst")
