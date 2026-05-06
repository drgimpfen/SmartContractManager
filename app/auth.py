import os
from passlib.context import CryptContext
from fastapi import Request
from sqlalchemy.orm import Session
from .models import User
from .db import get_db
from typing import Optional

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(raw_password, hashed_password)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id
    request.session["username"] = user.username


def logout_user(request: Request) -> None:
    request.session.clear()
