from pathlib import Path
from datetime import date, datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.i18n import TEMPLATES
from app.models import Contract, Provider, ContractStatus
from app.auth import get_current_user
from app.utils import normalize_monthly_amount, parse_notice_amount

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    contracts = db.query(Contract).filter(Contract.user_id == user.id).all()
    providers = db.query(Provider).filter(Provider.user_id == user.id).all()

    now = date.today()
    monthly_budget = 0.0
    categories = {}
    active_contracts = []
    critical_reminders = []
    missing_notice = []

    for contract in contracts:
        if contract.status != ContractStatus.active:
            continue
        active_contracts.append(contract)
        monthly_budget += normalize_monthly_amount(contract.amount or 0.0, contract.frequency.value)
        categories[contract.category] = categories.get(contract.category, 0.0) + (contract.amount or 0.0)
        if not contract.cancellation_notice_amount:
            missing_notice.append(contract)
        elif contract.end_date:
            reminder_date = contract.end_date - parse_notice_amount(contract.cancellation_notice_amount, contract.cancellation_notice_unit)
            if reminder_date <= now <= contract.end_date:
                critical_reminders.append(contract)

    cashflow = []
    if active_contracts:
        for offset in range(12):
            month = now.replace(day=1)
            target = month.replace(day=1)
            month_label = (target.replace(month=((target.month - 1 + offset) % 12) + 1, year=target.year + ((target.month - 1 + offset) // 12))).strftime("%Y-%m")
            cashflow.append({"month": month_label, "amount": round(monthly_budget, 2)})

    distribution = [{"category": key, "value": round(value, 2)} for key, value in categories.items()]

    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "contracts": contracts,
            "providers": providers,
            "monthly_budget": round(monthly_budget, 2),
            "critical_reminders": critical_reminders,
            "missing_notice": missing_notice,
            "distribution": distribution,
            "cashflow": cashflow,
        },
    )
