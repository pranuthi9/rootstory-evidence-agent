from __future__ import annotations

import os

from fastapi import Header, HTTPException
from firebase_admin import auth, initialize_app

_firebase_initialized = False


def authenticated_user(
    authorization: str | None = Header(default=None),
    x_rootstory_user: str | None = Header(default=None),
) -> str:
    """Verify Firebase ID tokens in production; explicit header mode is local-only."""
    if os.getenv("AUTH_MODE", "header") == "header":
        if not x_rootstory_user:
            raise HTTPException(status_code=401, detail="Missing local user header")
        return x_rootstory_user

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    global _firebase_initialized
    if not _firebase_initialized:
        initialize_app()
        _firebase_initialized = True
    try:
        decoded = auth.verify_id_token(authorization.removeprefix("Bearer ").strip())
        return str(decoded["uid"])
    except (ValueError, KeyError, auth.InvalidIdTokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
