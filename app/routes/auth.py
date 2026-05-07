import os
from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.i18n import TEMPLATES, gettext
from app.models import User
from app.auth import verify_password, get_password_hash, login_user, logout_user, get_current_user

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return TEMPLATES.TemplateResponse(
            request,
            "login.html",
            {"error": "auth.invalid_credentials"},
        )
    login_user(request, user)
    return RedirectResponse(url="/", status_code=302)


@router.get("/register")
def register_page(request: Request):
    return TEMPLATES.TemplateResponse(request, "register.html", {"error": None})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return TEMPLATES.TemplateResponse(
            request,
            "register.html",
            {"error": "auth.username_exists"},
        )
    user = User(username=username, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    login_user(request, user)
    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=302)
