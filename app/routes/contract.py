import os
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.i18n import TEMPLATES
from app.models import Contract, Provider, Tag, Document, Frequency, ContractStatus
from app.auth import get_current_user
from app.utils import normalize_monthly_amount
from pdfminer.high_level import extract_text

router = APIRouter()


def save_upload(upload: UploadFile, uploads_dir: Path) -> str:
    suffix = Path(upload.filename).suffix
    stored_name = f"{datetime.utcnow().timestamp():.0f}_{upload.filename.replace(' ', '_')}"
    stored_path = uploads_dir / stored_name
    with stored_path.open("wb") as buffer:
        buffer.write(upload.file.read())
    return stored_name


@router.get("/contracts")
def contract_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    contracts = db.query(Contract).filter(Contract.user_id == user.id).order_by(Contract.category).all()
    providers = db.query(Provider).filter(Provider.user_id == user.id).all()
    return TEMPLATES.TemplateResponse(
        request,
        "contracts.html",
        {"user": user, "contracts": contracts, "providers": providers, "frequencies": list(Frequency)},
    )


@router.post("/contracts")
def add_contract(
    request: Request,
    category: str = Form(...),
    provider_id: int | None = Form(None),
    contract_number: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    cancellation_notice_amount: int = Form(0),
    cancellation_notice_unit: str = Form("days"),
    amount: float = Form(0.0),
    currency: str = Form("EUR"),
    frequency: Frequency = Form(Frequency.monthly),
    payment_term: str = Form(""),
    payment_method: str = Form(""),
    notes: str = Form(""),
    tags: str = Form(""),
    document: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    contract = Contract(
        user_id=user.id,
        provider_id=provider_id,
        category=category,
        contract_number=contract_number,
        start_date=datetime.fromisoformat(start_date).date() if start_date else None,
        end_date=datetime.fromisoformat(end_date).date() if end_date else None,
        cancellation_notice_amount=cancellation_notice_amount,
        cancellation_notice_unit=cancellation_notice_unit,
        amount=amount,
        currency=currency,
        frequency=frequency,
        payment_term=payment_term,
        payment_method=payment_method,
        notes=notes,
        status=ContractStatus.active,
    )

    if tags:
        for tag_name in [value.strip() for value in tags.split(",") if value.strip()]:
            tag = db.query(Tag).filter(Tag.user_id == user.id, Tag.name == tag_name).first()
            if not tag:
                tag = Tag(user_id=user.id, name=tag_name)
            contract.tags.append(tag)

    db.add(contract)
    db.commit()
    db.refresh(contract)

    if document and document.filename.lower().endswith(".pdf"):
        uploads_dir = Path(__file__).resolve().parent.parent / "static" / "uploads"
        stored_name = save_upload(document, uploads_dir)
        extracted = ""
        try:
            extracted = extract_text(uploads_dir / stored_name)
        except Exception:
            extracted = ""
        doc = Document(
            contract_id=contract.id,
            filename=document.filename,
            stored_filename=stored_name,
            extracted_text=extracted,
        )
        db.add(doc)
        db.commit()

    return RedirectResponse(url="/contracts", status_code=302)
