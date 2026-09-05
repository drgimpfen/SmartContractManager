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


def sync_contract_tags(contract: Contract, user_id: int, tags_input: str) -> None:
    """Synchronize tags from a comma-separated string to the contract."""
    if not tags_input:
        contract.tags = []
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

    if conflicts and auto_adjust:
        for conf_entry in conflicts:
            # If the conflicting entry started before the new entry:
            if conf_entry.valid_from < valid_from:
                conf_entry.valid_to = valid_from - timedelta(days=1)
                conf_entry.is_current = False
            # If the conflicting entry started at or after the new entry:
            elif conf_entry.valid_from >= valid_from:
                if valid_to is None or conf_entry.valid_to is None or conf_entry.valid_to <= valid_to:
                    # It falls entirely within the new entry's range or is superseded:
                    db.session.delete(conf_entry)
                else:
                    # It started during the new entry and ends after:
                    conf_entry.valid_from = valid_to + timedelta(days=1)
                    conf_entry.is_current = (conf_entry.valid_from <= date.today() and (conf_entry.valid_to is None or conf_entry.valid_to >= date.today()))

    # Mark other open-ended prices as not current if this new price is open-ended
    today = date.today()
    is_curr = valid_from <= today and (valid_to is None or valid_to >= today)

    if is_curr or valid_to is None:
        for p in contract.price_history:
            if p not in conflicts:
                if valid_to is None:
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

    # Sync contract's active amount if the new price is currently active
    if is_curr:
        contract.amount = amount
        contract.currency = currency

    db.session.commit()
    return True, None, new_price
