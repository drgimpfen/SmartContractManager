from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.services.financial_service import FinancialService
from app.forms import ContractForm
from app.routes.contract import populate_provider_choices
from app.models import Tag, Contract

bp = Blueprint('dashboard', __name__)


@bp.route('/')
@login_required
def index():
    contracts = current_user.contracts
    providers = current_user.providers
    user_currency = current_user.currency or "EUR"

    contract_form = ContractForm()
    populate_provider_choices(contract_form, current_user.id)
    contract_form.currency.data = user_currency

    all_tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()
    all_user_contracts = Contract.query.filter_by(user_id=current_user.id, is_archived=False).all()
    user_categories = sorted(list(set(c.category for c in all_user_contracts if c.category)))
    user_payment_methods = sorted(list(set(c.payment_method for c in all_user_contracts if c.payment_method)))

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
        contract_form=contract_form,
        all_tags=all_tags,
        user_categories=user_categories,
        user_payment_methods=user_payment_methods,
    )
