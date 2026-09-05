from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app import db
from app.models import Provider
from app.forms import ProviderForm, ContractForm
from app.routes.contract import populate_provider_choices
from app.services.financial_service import FinancialService

bp = Blueprint('provider', __name__, url_prefix='/providers')


@bp.route('/', methods=['GET', 'POST'])
@bp.route('', methods=['GET', 'POST'])
@login_required
def index():
    form = ProviderForm()
    if form.validate_on_submit():
        provider = Provider(
            user_id=current_user.id,
            name=form.name.data.strip(),
            customer_number=form.customer_number.data.strip() if form.customer_number.data else None,
            address=form.address.data.strip() if form.address.data else None,
            email=form.email.data.strip() if form.email.data else None,
            phone=form.phone.data.strip() if form.phone.data else None,
            website=form.website.data.strip() if form.website.data else None,
            customer_portal=form.customer_portal.data.strip() if form.customer_portal.data else None,
            cancel_url=form.cancel_url.data.strip() if form.cancel_url.data else None,
        )
        db.session.add(provider)
        db.session.commit()
        flash('Provider successfully created.', 'success')
        return redirect(url_for('provider.index'))

    providers = Provider.query.filter_by(user_id=current_user.id).order_by(Provider.name.asc()).all()
    return render_template('providers.html', form=form, providers=providers)


@bp.route('/<int:id>')
@login_required
def detail(id):
    provider = db.session.get(Provider, id)
    if not provider or provider.user_id != current_user.id:
        abort(404)

    form = ProviderForm(obj=provider)
    contract_form = ContractForm()
    populate_provider_choices(contract_form, current_user.id)
    contract_form.provider_id.data = provider.id
    contract_form.currency.data = current_user.currency or "EUR"

    fin_service = FinancialService()
    summary = fin_service.calculate_provider_summary(
        provider.contracts,
        target_currency=current_user.currency or "EUR",
    )

    return render_template(
        'provider_detail.html',
        provider=provider,
        form=form,
        contract_form=contract_form,
        summary=summary,
    )


@bp.route('/<int:id>/edit', methods=['POST'])
@login_required
def edit(id):
    provider = db.session.get(Provider, id)
    if not provider or provider.user_id != current_user.id:
        abort(404)

    form = ProviderForm()
    if form.validate_on_submit():
        provider.name = form.name.data.strip()
        provider.customer_number = form.customer_number.data.strip() if form.customer_number.data else None
        provider.address = form.address.data.strip() if form.address.data else None
        provider.email = form.email.data.strip() if form.email.data else None
        provider.phone = form.phone.data.strip() if form.phone.data else None
        provider.website = form.website.data.strip() if form.website.data else None
        provider.customer_portal = form.customer_portal.data.strip() if form.customer_portal.data else None
        provider.cancel_url = form.cancel_url.data.strip() if form.cancel_url.data else None

        db.session.commit()
        flash('Provider successfully updated.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "danger")

    next_url = request.args.get('next')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('provider.index'))


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    provider = db.session.get(Provider, id)
    if not provider or provider.user_id != current_user.id:
        abort(404)

    db.session.delete(provider)
    db.session.commit()
    flash('Provider successfully deleted.', 'success')
    return redirect(url_for('provider.index'))

