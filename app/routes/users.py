from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import generate_api_key, get_current_user, hash_api_key

router = APIRouter(prefix="/users", tags=["users"])


class SignUpBody(BaseModel):
    email: EmailStr


@router.post("/signup")
def signup(body: SignUpBody, db: Session = Depends(get_db)) -> Any:
    # Minimal SaaS bootstrap: create a user and issue an API key.
    existing = db.query(User).filter(User.email == str(body.email)).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")

    api_key = generate_api_key()
    user = User(email=str(body.email), api_key_hash=hash_api_key(api_key))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"userId": user.id, "apiKey": api_key}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> Any:
    return {"userId": user.id, "email": user.email}

