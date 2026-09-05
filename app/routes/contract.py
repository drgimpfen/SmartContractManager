from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app import db
from app.models import Contract, Provider, Tag, ContractStatus, Frequency, PriceEntry
from app.forms import ContractForm, PriceEntryForm
from app.services.contract_service import sync_contract_tags, add_price_entry
from app.services.financial_service import FinancialService

bp = Blueprint('contract', __name__, url_prefix='/contracts')


def populate_provider_choices(form, user_id):
    """Populate provider select choices for the current user."""
    providers = Provider.query.filter_by(user_id=user_id).order_by(Provider.name.asc()).all()
    form.provider_id.choices = [(0, '--- Kein Anbieter ---')] + [(p.id, p.name) for p in providers]


@bp.route('/', methods=['GET', 'POST'])
@bp.route('', methods=['GET', 'POST'])
@login_required
def index():
    form = ContractForm()
    populate_provider_choices(form, current_user.id)

    if form.validate_on_submit():
        provider_id = form.provider_id.data if form.provider_id.data and form.provider_id.data > 0 else None

        contract = Contract(
            user_id=current_user.id,
            provider_id=provider_id,
            category=form.category.data.strip(),
            status=ContractStatus(form.status.data),
            contract_number=form.contract_number.data.strip() if form.contract_number.data else None,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            billing_anchor_date=form.billing_anchor_date.data,
            cancellation_notice_amount=form.cancellation_notice_amount.data or 0,
            cancellation_notice_unit=form.cancellation_notice_unit.data or 'days',
            amount=float(form.amount.data or 0.0),
            currency=form.currency.data.strip() if form.currency.data else 'EUR',
            frequency=Frequency(form.frequency.data),
            payment_method=form.payment_method.data.strip() if form.payment_method.data else None,
            notes=form.notes.data.strip() if form.notes.data else None,
        )
        db.session.add(contract)
        db.session.flush()

        # Synchronize tags
        sync_contract_tags(contract, current_user.id, form.tags.data or '')

        # Automatically log initial price entry
        initial_price = PriceEntry(
            contract_id=contract.id,
            valid_from=form.start_date.data or date.today(),
            valid_to=None,
            is_current=True,
            amount=contract.amount,
            currency=contract.currency,
            note="Initialer Vertragspreis",
        )
        db.session.add(initial_price)
        db.session.commit()

        flash('Vertrag erfolgreich erstellt.', 'success')
        return redirect(url_for('contract.detail', id=contract.id))

    # Query contracts with filters
    status_filter = request.args.get('status', 'all')
    tag_filter = request.args.get('tag')
    search_query = request.args.get('q', '').strip()

    query = Contract.query.filter_by(user_id=current_user.id)

    if status_filter in ('active', 'canceled', 'archived'):
        query = query.filter_by(status=ContractStatus(status_filter))

    if search_query:
        query = query.filter(
            db.or_(
                Contract.category.ilike(f"%{search_query}%"),
                Contract.contract_number.ilike(f"%{search_query}%"),
                Contract.notes.ilike(f"%{search_query}%"),
            )
        )

    if tag_filter:
        query = query.join(Contract.tags).filter(Tag.name == tag_filter)

    contracts = query.order_by(Contract.created_at.desc()).all()
    providers = Provider.query.filter_by(user_id=current_user.id).order_by(Provider.name.asc()).all()
    all_tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    return render_template(
        'contracts.html',
        form=form,
        contracts=contracts,
        providers=providers,
        all_tags=all_tags,
        active_status=status_filter,
        active_tag=tag_filter,
        search_query=search_query,
    )


@bp.route('/<int:id>')
@login_required
def detail(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    edit_form = ContractForm(obj=contract)
    populate_provider_choices(edit_form, current_user.id)
    edit_form.provider_id.data = contract.provider_id or 0
    edit_form.status.data = contract.status.value
    edit_form.frequency.data = contract.frequency.value
    edit_form.tags.data = ", ".join([t.name for t in contract.tags])

    price_form = PriceEntryForm()
    price_form.currency.data = contract.currency
    price_form.valid_from.data = date.today()
    all_tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    fin_service = FinancialService()
    cost_summary = fin_service.calculate_contract_cost_summary(contract)

    return render_template(
        'contract_detail.html',
        contract=contract,
        edit_form=edit_form,
        price_form=price_form,
        all_tags=all_tags,
        cost_summary=cost_summary,
    )


@bp.route('/<int:id>/edit', methods=['POST'])
@login_required
def edit(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    form = ContractForm()
    populate_provider_choices(form, current_user.id)

    if form.validate_on_submit():
        contract.provider_id = form.provider_id.data if form.provider_id.data and form.provider_id.data > 0 else None
        contract.category = form.category.data.strip()
        contract.status = ContractStatus(form.status.data)
        contract.contract_number = form.contract_number.data.strip() if form.contract_number.data else None
        contract.start_date = form.start_date.data
        contract.end_date = form.end_date.data
        contract.billing_anchor_date = form.billing_anchor_date.data
        contract.cancellation_notice_amount = form.cancellation_notice_amount.data or 0
        contract.cancellation_notice_unit = form.cancellation_notice_unit.data or 'days'
        contract.frequency = Frequency(form.frequency.data)
        contract.payment_method = form.payment_method.data.strip() if form.payment_method.data else None
        contract.notes = form.notes.data.strip() if form.notes.data else None

        # Synchronize tags
        sync_contract_tags(contract, current_user.id, form.tags.data or '')

        db.session.commit()
        flash('Vertrag erfolgreich aktualisiert.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "danger")

    return redirect(url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/price-entry', methods=['POST'])
@login_required
def add_price(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    form = PriceEntryForm()
    if form.validate_on_submit():
        success, error_msg, _ = add_price_entry(
            contract=contract,
            amount=float(form.amount.data),
            currency=form.currency.data.strip() if form.currency.data else 'EUR',
            valid_from=form.valid_from.data,
            valid_to=form.valid_to.data,
            note=form.note.data.strip() if form.note.data else None,
            auto_adjust=form.auto_adjust.data,
        )
        if success:
            flash('Preisänderung erfolgreich erfasst.', 'success')
        else:
            flash(error_msg, 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "danger")

    return redirect(url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/status', methods=['POST'])
@login_required
def toggle_status(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    new_status = request.form.get('status')
    if new_status in [s.value for s in ContractStatus]:
        contract.status = ContractStatus(new_status)
        db.session.commit()
        flash('Vertragsstatus aktualisiert.', 'success')

    return redirect(request.referrer or url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    db.session.delete(contract)
    db.session.commit()
    flash('Vertrag erfolgreich gelöscht.', 'success')
    return redirect(url_for('contract.index'))
