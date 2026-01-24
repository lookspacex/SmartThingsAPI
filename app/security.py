from __future__ import annotations

import hashlib
import secrets
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User


def hash_api_key(api_key: str) -> str:
    # Store only a deterministic hash; pepper prevents rainbow-table reuse.
    raw = (settings.api_key_pepper + ":" + api_key).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate_api_key() -> str:
    # URL-safe, high-entropy token
    return secrets.token_urlsafe(32)


def get_current_user(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
    db: Session = Depends(get_db),
) -> User:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    key_hash = hash_api_key(x_api_key)
    user = db.query(User).filter(User.api_key_hash == key_hash).one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid X-API-Key")
    return user

