from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Provider
from app.auth import get_current_user

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter()


@router.get("/providers")
def provider_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    providers = db.query(Provider).filter(Provider.user_id == user.id).order_by(Provider.name).all()
    return TEMPLATES.TemplateResponse("providers.html", {"request": request, "user": user, "providers": providers})


@router.post("/providers")
def add_provider(
    request: Request,
    name: str = Form(...),
    customer_number: str = Form("") ,
    address: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    customer_portal: str = Form(""),
    cancel_url: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    provider = Provider(
        user_id=user.id,
        name=name,
        customer_number=customer_number,
        address=address,
        email=email,
        phone=phone,
        website=website,
        customer_portal=customer_portal,
        cancel_url=cancel_url,
    )
    db.add(provider)
    db.commit()
    return RedirectResponse(url="/providers", status_code=302)
