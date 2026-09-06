import hashlib
from datetime import date, timedelta
from app import db
from app.models import Contract, Tag, PriceEntry


TAG_COLORS = [
    "#0d6efd",  # primary blue
    "#6610f2",  # indigo
    "#6f42c1",  # purple
    "#d63384",  # pink
    "#dc3545",  # red
    "#fd7e14",  # orange
    "#ffc107",  # yellow
    "#198754",  # green
    "#20c997",  # teal
    "#0dcaf0",  # cyan
]


def pick_tag_color(tag_name: str) -> str:
    """Deterministically pick a consistent hex color for a tag based on its name."""
    hash_val = int(hashlib.md5(tag_name.strip().lower().encode("utf-8")).hexdigest(), 16)
    return TAG_COLORS[hash_val % len(TAG_COLORS)]


def prune_orphaned_tags(user_id: int) -> int:
    """Delete any tags belonging to user_id that are not associated with any contract."""
    db.session.flush()
    orphans = Tag.query.filter_by(user_id=user_id).filter(~Tag.contracts.any()).all()
    count = len(orphans)
    for t in orphans:
        db.session.delete(t)
    return count


def sync_contract_tags(contract: Contract, user_id: int, tags_input: str) -> None:
    """Synchronize tags from a comma-separated string to the contract and clean up unreferenced tags."""
    if not tags_input:
        contract.tags = []
        prune_orphaned_tags(user_id)
        return

    raw_names = [t.strip() for t in tags_input.split(",") if t.strip()]
    unique_names = list(dict.fromkeys(raw_names))  # preserve order, eliminate dupes

    synced_tags = []
    for name in unique_names:
        tag = Tag.query.filter_by(user_id=user_id, name=name).first()
        if not tag:
            tag = Tag(user_id=user_id, name=name, color=pick_tag_color(name))
            db.session.add(tag)
        synced_tags.append(tag)

    contract.tags = synced_tags
    prune_orphaned_tags(user_id)


def check_price_overlap(contract_id: int, valid_from: date, valid_to: date | None, exclude_id: int | None = None):
    """Find conflicting price entries for a contract within the given date interval."""
    query = PriceEntry.query.filter(PriceEntry.contract_id == contract_id)
    if exclude_id is not None:
        query = query.filter(PriceEntry.id != exclude_id)

    target_end = valid_to or date.max

    conflicts = []
    for entry in query.all():
        entry_end = entry.valid_to or date.max
        # Two intervals [A_start, A_end] and [B_start, B_end] overlap if:
        # A_start <= B_end and B_start <= A_end
        if valid_from <= entry_end and entry.valid_from <= target_end:
            conflicts.append(entry)

    return conflicts


def add_price_entry(
    contract: Contract,
    amount: float,
    currency: str,
    valid_from: date,
    valid_to: date | None = None,
    note: str | None = None,
    auto_adjust: bool = False,
) -> tuple[bool, str | None, PriceEntry | None]:
    """Add a price entry with strict overlap detection and smart auto-adjustment."""
    if valid_to and valid_to < valid_from:
        return False, "Das Enddatum darf nicht vor dem Startdatum liegen.", None

    conflicts = check_price_overlap(contract.id, valid_from, valid_to)

    if conflicts and not auto_adjust:
        conf_entry = conflicts[0]
        c_from = conf_entry.valid_from.strftime("%d.%m.%Y")
        c_to = conf_entry.valid_to.strftime("%d.%m.%Y") if conf_entry.valid_to else "offen"
        n_from = valid_from.strftime("%d.%m.%Y")
        n_to = valid_to.strftime("%d.%m.%Y") if valid_to else "offen"
        error_msg = (
            f"Der Gültigkeitszeitraum ({n_from} - {n_to}) überschneidet sich mit einem "
            f"bestehenden Preis vom {c_from} bis {c_to}."
        )
        return False, error_msg, conf_entry

    today = date.today()

    if conflicts and auto_adjust:
        for conf_entry in conflicts:
            # If the conflicting entry started before the new entry:
            if conf_entry.valid_from < valid_from:
                conf_entry.valid_to = valid_from - timedelta(days=1)
                conf_entry.is_current = (
                    conf_entry.valid_from <= today
                    and (conf_entry.valid_to is None or conf_entry.valid_to >= today)
                )
            # If the conflicting entry started at or after the new entry:
            elif conf_entry.valid_from >= valid_from:
                if valid_to is None or conf_entry.valid_to is None or conf_entry.valid_to <= valid_to:
                    # It falls entirely within the new entry's range or is superseded:
                    db.session.delete(conf_entry)
                else:
                    # It started during the new entry and ends after:
                    conf_entry.valid_from = valid_to + timedelta(days=1)
                    conf_entry.is_current = (
                        conf_entry.valid_from <= today
                        and (conf_entry.valid_to is None or conf_entry.valid_to >= today)
                    )

    is_curr = valid_from <= today and (valid_to is None or valid_to >= today)

    # Only mark other prices as not current if this new price is actually active TODAY
    if is_curr:
        for p in contract.price_history:
            if p not in conflicts:
                p.is_current = False

    new_price = PriceEntry(
        contract_id=contract.id,
        amount=amount,
        currency=currency,
        valid_from=valid_from,
        valid_to=valid_to,
        is_current=is_curr,
        note=note,
    )
    db.session.add(new_price)
    db.session.flush()

    sync_contract_prices(contract)
    db.session.commit()
    return True, None, new_price


def sync_contract_prices(contract: Contract, as_of: date | None = None) -> None:
    """
    Synchronize is_current flags for all price entries and ensure contract.amount
    and contract.currency match the currently active price entry.
    """
    ref = as_of or date.today()
    active_entry = None

    for p in contract.price_history:
        p_active = p.valid_from <= ref and (p.valid_to is None or p.valid_to >= ref)
        p.is_current = p_active
        if p_active:
            active_entry = p

    if active_entry:
        contract.amount = active_entry.amount
        contract.currency = active_entry.currency


def delete_price_entry(contract_id: int, price_entry_id: int, user_id: int) -> tuple[bool, str | None]:
    """
    Safely delete a price entry. If an adjacent preceding entry was capped by this entry,
    re-opens or adjusts its valid_to, and re-syncs contract current price.
    """
    contract = Contract.query.filter_by(id=contract_id, user_id=user_id).first()
    if not contract:
        return False, "Vertrag nicht gefunden."

    entry = PriceEntry.query.filter_by(id=price_entry_id, contract_id=contract_id).first()
    if not entry:
        return False, "Preiseintrag nicht gefunden."

    other_entries = [p for p in contract.price_history if p.id != price_entry_id]

    # If this entry had an adjacent preceding entry ending right before entry.valid_from:
    preceding_end = entry.valid_from - timedelta(days=1)
    preceding = next((p for p in other_entries if p.valid_to == preceding_end), None)

    if preceding:
        if entry.valid_to is None:
            preceding.valid_to = None
        else:
            preceding.valid_to = entry.valid_to

    db.session.delete(entry)
    db.session.flush()

    sync_contract_prices(contract)
    db.session.commit()
    return True, None


def apply_price_tiers(
    contract: Contract,
    base_date: date,
    tiers: list[dict],
    currency: str | None = None,
    auto_adjust: bool = True,
) -> list[PriceEntry]:
    """
    Apply a sequence of relative price tiers (e.g. promotional discount phases) to a contract.
    Each tier in `tiers` is expected to be a dict with:
      - 'months': int | None (duration in months, or None/0 for ongoing final tier)
      - 'amount': float (monthly amount)
      - 'note': str | None (optional label)

    The tiers are chained sequentially starting at `base_date`.
    The last tier (or any tier with months=None or months=0) is assigned valid_to=None (ongoing).
    """
    from app.models import add_months

    curr_currency = currency or contract.currency or "EUR"
    created_entries: list[PriceEntry] = []
    curr_start = base_date

    # Filter out empty or invalid tier entries
    valid_tiers = []
    for t in tiers:
        amt = t.get("amount")
        if amt is None:
            continue
        try:
            amt_float = float(amt)
            if amt_float < 0:
                continue
        except (ValueError, TypeError):
            continue
        valid_tiers.append(t)

    if not valid_tiers:
        return created_entries

    total_count = len(valid_tiers)
    for idx, tier in enumerate(valid_tiers):
        amt = float(tier["amount"])
        months_val = tier.get("months")
        note = tier.get("note")

        is_last = (idx == total_count - 1)

        if is_last or months_val is None or months_val == "" or int(months_val) <= 0:
            valid_to = None
        else:
            months = int(months_val)
            next_start = add_months(curr_start, months)
            valid_to = next_start - timedelta(days=1)

        tier_note = note or (f"Staffelpreis Stufe {idx + 1}" if total_count > 1 else "Vertragspreis")
        success, err, entry = add_price_entry(
            contract=contract,
            amount=amt,
            currency=curr_currency,
            valid_from=curr_start,
            valid_to=valid_to,
            note=tier_note,
            auto_adjust=auto_adjust,
        )
        if success and entry:
            created_entries.append(entry)

        if valid_to is not None:
            curr_start = valid_to + timedelta(days=1)

    sync_contract_prices(contract)
    db.session.commit()
    return created_entries


