from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.services.financial_service import FinancialService

bp = Blueprint('dashboard', __name__)


@bp.route('/')
@login_required
def index():
    contracts = current_user.contracts
    providers = current_user.providers
    user_currency = current_user.currency or "EUR"

    fin_svc = FinancialService()

    monthly_budget = fin_svc.calculate_monthly_budget(contracts, user_currency)
    current_month_expenses = fin_svc.calculate_current_month_expenses(contracts, user_currency)
    annual_budget = fin_svc.calculate_annual_budget(contracts, user_currency)

    cashflow = fin_svc.calculate_cashflow_projection(contracts, user_currency, months=12)
    distribution = fin_svc.calculate_category_distribution(contracts, user_currency)

    critical_reminders = fin_svc.get_critical_deadlines(contracts)
    missing_notice = fin_svc.get_missing_notice(contracts)

    return render_template(
        'dashboard.html',
        monthly_budget=monthly_budget,
        current_month_expenses=current_month_expenses,
        annual_budget=annual_budget,
        contracts=contracts,
        providers=providers,
        cashflow=cashflow,
        distribution=distribution,
        critical_reminders=critical_reminders,
        missing_notice=missing_notice,
    )
