from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.auth import get_current_user

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter()

TIMEZONE_OPTIONS = [
    "Europe/Berlin",
    "Europe/London",
    "Europe/Paris",
    "America/New_York",
    "America/Los_Angeles",
    "Asia/Tokyo",
    "UTC",
]
CURRENCY_OPTIONS = ["EUR", "USD", "GBP", "CHF"]


@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return TEMPLATES.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "timezones": TIMEZONE_OPTIONS,
            "currencies": CURRENCY_OPTIONS,
            "message": None,
        },
    )


@router.post("/settings")
def update_settings(
    request: Request,
    timezone: str = Form("Europe/Berlin"),
    currency: str = Form("EUR"),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    user.timezone = timezone
    user.currency = currency
    db.add(user)
    db.commit()
    return RedirectResponse(url="/settings", status_code=302)
