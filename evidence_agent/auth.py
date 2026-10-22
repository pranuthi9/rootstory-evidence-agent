from __future__ import annotations

import os
from threading import Lock

from fastapi import Header, HTTPException, Request
from firebase_admin import app_check, auth, get_app, initialize_app

_firebase_lock = Lock()


def firebase_auth_required() -> bool:
    return bool(os.getenv("K_SERVICE")) or os.getenv("AUTH_MODE", "header") != "header"


def _initialize_firebase() -> None:
    with _firebase_lock:
        try:
            get_app()
        except ValueError:
            initialize_app()


def authenticated_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_rootstory_user: str | None = Header(default=None),
    x_firebase_appcheck: str | None = Header(default=None),
) -> str:
    """Verify Firebase ID tokens in production; explicit header mode is local-only."""
    if os.getenv("AUTH_MODE", "header") == "header":
        if os.getenv("K_SERVICE"):
            raise HTTPException(status_code=503, detail="Firebase authentication is required")
        if not x_rootstory_user:
            raise HTTPException(status_code=401, detail="Missing local user header")
        return x_rootstory_user

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    _initialize_firebase()
    try:
        decoded = auth.verify_id_token(authorization.removeprefix("Bearer ").strip())
        user_id = str(decoded["uid"])
    except (ValueError, KeyError, auth.InvalidIdTokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc

    if not x_firebase_appcheck or not x_firebase_appcheck.strip():
        raise HTTPException(status_code=403, detail="Browser verification is required")
    try:
        app_check.verify_token(x_firebase_appcheck)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Browser verification failed") from exc

    if (
        request.method == "POST"
        and request.url.path == "/v1/audits"
        and decoded.get("email_verified") is not True
    ):
        raise HTTPException(status_code=403, detail="Verify your email before starting research")
    return user_id
