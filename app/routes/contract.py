import json
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app import db
from app.models import (
    Contract,
    Provider,
    Tag,
    ContractStatus,
    Frequency,
    PriceEntry,
    Note,
    add_months,
    snap_to_target_period,
    calculate_month_delta,
)
from app.forms import ContractForm, PriceEntryForm, NoteForm, ContractExtendForm
from app.services.contract_service import (
    sync_contract_tags,
    prune_orphaned_tags,
    add_price_entry,
    sync_contract_prices,
    delete_price_entry,
    apply_price_tiers,
)
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

    next_url = request.args.get('next')

    if form.validate_on_submit():
        provider_id = form.provider_id.data if form.provider_id.data and form.provider_id.data > 0 else None
        title = form.title.data.strip() if form.title.data else form.category.data.strip()
        status_val = form.status.data
        if form.start_date.data and form.start_date.data > date.today() and status_val == 'active':
            status_val = 'scheduled'

        renewal_type_val = form.renewal_type.data or 'monthly_rolling'
        if renewal_type_val != 'none':
            end_date_val = None
            initial_term_end_val = form.initial_term_end_date.data
            initial_term_val = form.initial_term_months.data or 0
            if initial_term_end_val and form.start_date.data:
                initial_term_val = calculate_month_delta(form.start_date.data, initial_term_end_val)
        else:
            end_date_val = form.end_date.data
            initial_term_end_val = None
            initial_term_val = 0

        contract = Contract(
            user_id=current_user.id,
            provider_id=provider_id,
            title=title,
            category=form.category.data.strip(),
            status=ContractStatus(status_val),
            contract_number=form.contract_number.data.strip() if form.contract_number.data else None,
            start_date=form.start_date.data,
            end_date=end_date_val,
            billing_anchor_date=form.billing_anchor_date.data or form.start_date.data,
            cancellation_notice_amount=form.cancellation_notice_amount.data or 0,
            cancellation_notice_unit=form.cancellation_notice_unit.data or 'days',
            cancellation_target_period=form.cancellation_target_period.data or 'exact',
            initial_term_months=initial_term_val,
            initial_term_end_date=initial_term_end_val,
            renewal_type=renewal_type_val,
            renewal_period_months=form.renewal_period_months.data or 1,
            cancellation_sent_date=form.cancellation_sent_date.data,
            confirmed_end_date=form.confirmed_end_date.data,
            amount=float(form.amount.data or 0.0),
            currency=form.currency.data.strip() if form.currency.data else 'EUR',
            frequency=Frequency(form.frequency.data),
            payment_method=form.payment_method.data.strip() if form.payment_method.data else None,
            notes=form.notes.data.strip() if form.notes.data else None,
        )
        db.session.add(contract)
        db.session.flush()

        if form.notes.data and form.notes.data.strip():
            db.session.add(Note(user_id=current_user.id, contract_id=contract.id, content=form.notes.data.strip()))

        # Synchronize tags
        sync_contract_tags(contract, current_user.id, form.tags.data or '')

        # Check if price tiers were submitted
        price_tiers_raw = request.form.get('price_tiers_json')
        tiers = None
        if price_tiers_raw:
            try:
                parsed = json.loads(price_tiers_raw)
                if isinstance(parsed, list) and len(parsed) > 0:
                    tiers = parsed
            except (json.JSONDecodeError, TypeError):
                tiers = None

        if tiers:
            apply_price_tiers(
                contract=contract,
                base_date=form.start_date.data or date.today(),
                tiers=tiers,
                currency=contract.currency,
                auto_adjust=True,
            )
        else:
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
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('contract.detail', id=contract.id))

    if request.method == 'POST' and not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "danger")
        if next_url and next_url.startswith('/'):
            return redirect(next_url)

    # Query contracts with filters
    status_filter = request.args.get('status', 'all')
    tag_filter = request.args.get('tag')
    category_filter = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()

    archived_count = Contract.query.filter_by(user_id=current_user.id, is_archived=True).count()

    query = Contract.query.filter_by(user_id=current_user.id)

    if status_filter == 'archived':
        query = query.filter(Contract.is_archived.is_(True))
    else:
        query = query.filter(Contract.is_archived.is_(False))
        valid_statuses = ('scheduled', 'active', 'pending_cancellation', 'cancellation_confirmed', 'paused', 'canceled')
        if status_filter in valid_statuses:
            query = query.filter_by(status=ContractStatus(status_filter))

    if category_filter:
        query = query.filter(Contract.category == category_filter)

    if search_query:
        query = query.filter(
            db.or_(
                Contract.title.ilike(f"%{search_query}%"),
                Contract.category.ilike(f"%{search_query}%"),
                Contract.contract_number.ilike(f"%{search_query}%"),
                Contract.notes.ilike(f"%{search_query}%"),
            )
        )

    if tag_filter:
        query = query.join(Contract.tags).filter(Tag.name == tag_filter)

    contracts = query.order_by(Contract.created_at.desc()).all()
    for c in contracts:
        c.sync_contract_status()
        if c.price_history:
            sync_contract_prices(c)
    db.session.commit()

    providers = Provider.query.filter_by(user_id=current_user.id).order_by(Provider.name.asc()).all()
    all_tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    all_user_contracts = Contract.query.filter_by(user_id=current_user.id, is_archived=False).all()
    user_categories = sorted(list(set(c.category for c in all_user_contracts if c.category)))
    user_payment_methods = sorted(list(set(c.payment_method for c in all_user_contracts if c.payment_method)))

    return render_template(
        'contracts.html',
        form=form,
        contracts=contracts,
        providers=providers,
        all_tags=all_tags,
        active_status=status_filter,
        active_tag=tag_filter,
        active_category=category_filter,
        search_query=search_query,
        archived_count=archived_count,
        user_categories=user_categories,
        user_payment_methods=user_payment_methods,
    )


@bp.route('/<int:id>')
@login_required
def detail(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    contract.sync_contract_status()
    sync_contract_prices(contract)
    db.session.commit()

    edit_form = ContractForm(obj=contract)
    populate_provider_choices(edit_form, current_user.id)
    edit_form.title.data = contract.title or contract.category
    edit_form.provider_id.data = contract.provider_id or 0
    edit_form.status.data = contract.status.value
    edit_form.frequency.data = contract.frequency.value
    edit_form.tags.data = ", ".join([t.name for t in contract.tags])

    price_form = PriceEntryForm()
    price_form.currency.data = contract.currency
    price_form.valid_from.data = date.today()

    note_form = NoteForm()

    all_tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    all_user_contracts = Contract.query.filter_by(user_id=current_user.id, is_archived=False).all()
    user_categories = sorted(list(set(c.category for c in all_user_contracts if c.category)))
    user_payment_methods = sorted(list(set(c.payment_method for c in all_user_contracts if c.payment_method)))

    fin_service = FinancialService()
    cost_summary = fin_service.calculate_contract_cost_summary(contract)
    price_chart_data = fin_service.get_contract_price_timeline_chart(contract)

    extend_form = ContractExtendForm()

    return render_template(
        'contract_detail.html',
        contract=contract,
        edit_form=edit_form,
        price_form=price_form,
        note_form=note_form,
        extend_form=extend_form,
        all_tags=all_tags,
        cost_summary=cost_summary,
        price_chart_data=price_chart_data,
        user_categories=user_categories,
        user_payment_methods=user_payment_methods,
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
        contract.title = form.title.data.strip() if form.title.data else form.category.data.strip()
        contract.category = form.category.data.strip()
        contract.status = ContractStatus(form.status.data)
        contract.contract_number = form.contract_number.data.strip() if form.contract_number.data else None
        contract.start_date = form.start_date.data
        renewal_type_val = form.renewal_type.data or 'monthly_rolling'
        contract.renewal_type = renewal_type_val
        if renewal_type_val != 'none':
            contract.end_date = None
            contract.initial_term_end_date = form.initial_term_end_date.data
            initial_term_val = form.initial_term_months.data or 0
            if not initial_term_val and contract.initial_term_end_date and contract.start_date:
                initial_term_val = calculate_month_delta(contract.start_date, contract.initial_term_end_date)
            contract.initial_term_months = initial_term_val
        else:
            contract.end_date = form.end_date.data
            contract.initial_term_end_date = None
            contract.initial_term_months = 0

        contract.billing_anchor_date = form.billing_anchor_date.data or form.start_date.data
        contract.cancellation_notice_amount = form.cancellation_notice_amount.data or 0
        contract.cancellation_notice_unit = form.cancellation_notice_unit.data or 'days'
        contract.cancellation_target_period = form.cancellation_target_period.data or 'exact'
        contract.renewal_period_months = form.renewal_period_months.data or 1
        contract.cancellation_sent_date = form.cancellation_sent_date.data
        contract.confirmed_end_date = form.confirmed_end_date.data
        contract.frequency = Frequency(form.frequency.data)
        contract.payment_method = form.payment_method.data.strip() if form.payment_method.data else None
        if form.notes.data is not None:
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


@bp.route('/<int:id>/extend', methods=['POST'])
@login_required
def extend_contract(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    form = ContractExtendForm()
    if form.validate_on_submit():
        start_mode = form.extension_start_mode.data or 'append'
        period_choice = form.extension_months.data or '24'

        today = date.today()
        current_term_end = contract.initial_term_end_date or contract.earliest_cancellation_date or today
        if start_mode == 'custom_date':
            if not form.custom_start_date.data:
                flash('Bitte gib ein gültiges Startdatum für die Verlängerung an.', 'danger')
                return redirect(url_for('contract.detail', id=contract.id))
            base_date = form.custom_start_date.data
        elif start_mode == 'append' and current_term_end > today:
            base_date = current_term_end
        else:
            base_date = today

        if period_choice == 'custom':
            if not form.custom_end_date.data:
                flash('Bitte gib ein gültiges Enddatum für die Verlängerung an.', 'danger')
                return redirect(url_for('contract.detail', id=contract.id))
            new_end_date = form.custom_end_date.data
            if new_end_date <= base_date:
                flash('Das neue Mindestende muss nach dem Startdatum der Verlängerung liegen.', 'danger')
                return redirect(url_for('contract.detail', id=contract.id))
            months_added = max(1, calculate_month_delta(base_date, new_end_date))
        else:
            try:
                months_to_add = int(period_choice)
            except ValueError:
                months_to_add = 24
            months_added = months_to_add
            new_end_date = add_months(base_date, months_to_add)

        target_period = contract.cancellation_target_period or 'exact'
        new_end_date = snap_to_target_period(new_end_date, target_period)

        if new_end_date <= base_date:
            flash('Das neue Mindestende muss nach dem Startdatum der Verlängerung liegen.', 'danger')
            return redirect(url_for('contract.detail', id=contract.id))

        # Update contract
        contract.initial_term_end_date = new_end_date
        contract.initial_term_months = months_added

        # Reset cancellation status if pending or confirmed
        was_cancelled = contract.status in (ContractStatus.pending_cancellation, ContractStatus.cancellation_confirmed)
        if was_cancelled:
            contract.status = ContractStatus.active
            contract.cancellation_sent_date = None
            contract.confirmed_end_date = None

        # Add price entries (tiers or single amount)
        price_start = today if start_mode == 'from_today' else base_date
        price_tiers_raw = request.form.get('price_tiers_json')
        new_amt = form.new_amount.data
        tiers = None
        if price_tiers_raw:
            try:
                parsed = json.loads(price_tiers_raw)
                if isinstance(parsed, list) and len(parsed) > 0:
                    tiers = parsed
            except (json.JSONDecodeError, TypeError):
                tiers = None

        if tiers:
            apply_price_tiers(
                contract=contract,
                base_date=price_start,
                tiers=tiers,
                currency=contract.currency,
                auto_adjust=True,
            )
        elif new_amt is not None and float(new_amt) > 0:
            add_price_entry(
                contract=contract,
                amount=float(new_amt),
                currency=contract.currency or "EUR",
                valid_from=price_start,
                valid_to=None,
                note=f"Vorzeitige Vertragsverlängerung um {months_added} Monate",
                auto_adjust=True,
            )

        # Add Note to history
        note_text = form.note.data.strip() if form.note.data else ""
        system_note = f"Vorzeitige Vertragsverlängerung um {months_added} Monate bis zum {new_end_date.strftime('%d.%m.%Y')}."
        if tiers:
            system_note += f" Preisstaffel mit {len(tiers)} Stufen hinterlegt."
        elif new_amt is not None and float(new_amt) > 0:
            system_note += f" Neuer Betrag: {new_amt:.2f} {contract.currency}."
        if note_text:
            system_note += f" Notiz: {note_text}"

        db.session.add(Note(
            user_id=current_user.id,
            contract_id=contract.id,
            content=system_note,
        ))

        db.session.commit()
        flash(f'Vertrag erfolgreich um {months_added} Monate bis zum {new_end_date.strftime("%d.%m.%Y")} verlängert.', 'success')
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


@bp.route('/<int:id>/price-entry/<int:price_id>/delete', methods=['POST'])
@login_required
def delete_price(id, price_id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    success, error_msg = delete_price_entry(contract.id, price_id, current_user.id)
    if success:
        flash('Preiseintrag erfolgreich gelöscht.', 'success')
    else:
        flash(error_msg or 'Fehler beim Löschen des Preiseintrags.', 'danger')

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
        if new_status == 'pending_cancellation' and not contract.cancellation_sent_date:
            contract.cancellation_sent_date = date.today()
        elif new_status == 'cancellation_confirmed':
            confirmed_date_str = request.form.get('confirmed_end_date')
            if confirmed_date_str:
                try:
                    contract.confirmed_end_date = date.fromisoformat(confirmed_date_str)
                except ValueError:
                    pass
            if not contract.confirmed_end_date:
                contract.confirmed_end_date = contract.earliest_cancellation_date or contract.end_date
        db.session.commit()
        flash('Vertragsstatus aktualisiert.', 'success')

    return redirect(request.referrer or url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/archive', methods=['POST'])
@login_required
def archive(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    if contract.status != ContractStatus.canceled:
        flash('Nur beendete Verträge können ins Archiv verschoben werden.', 'warning')
        return redirect(request.referrer or url_for('contract.detail', id=contract.id))

    contract.is_archived = True
    db.session.commit()
    flash('Vertrag erfolgreich ins Archiv verschoben.', 'success')
    return redirect(request.referrer or url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/unarchive', methods=['POST'])
@login_required
def unarchive(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    contract.is_archived = False
    db.session.commit()
    flash('Vertrag erfolgreich aus dem Archiv wiederhergestellt.', 'success')
    return redirect(request.referrer or url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/notes', methods=['POST'])
@login_required
def add_note(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    content = request.form.get('content', '').strip()
    if content:
        note = Note(user_id=current_user.id, contract_id=contract.id, content=content)
        db.session.add(note)
        db.session.commit()
        flash('Notiz erfolgreich hinzugefügt.', 'success')

    return redirect(url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_note(id, note_id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    note = db.session.get(Note, note_id)
    if note and note.user_id == current_user.id and note.contract_id == contract.id:
        db.session.delete(note)
        db.session.commit()
        flash('Notiz gelöscht.', 'success')

    return redirect(url_for('contract.detail', id=contract.id))


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    contract = db.session.get(Contract, id)
    if not contract or contract.user_id != current_user.id:
        abort(404)

    user_id = contract.user_id
    db.session.delete(contract)
    db.session.commit()
    prune_orphaned_tags(user_id)
    flash('Vertrag erfolgreich gelöscht.', 'success')
    return redirect(url_for('contract.index'))
