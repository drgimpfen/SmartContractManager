from datetime import date, timedelta
import pytest
from app import db
from app.models import (
    User,
    Contract,
    Provider,
    ContractStatus,
    Frequency,
    PriceEntry,
    Note,
    add_months,
    snap_to_target_period,
)
from app.services.financial_service import FinancialService


@pytest.fixture
def user(app):
    with app.app_context():
        u = User(username="lifecycle_user", hashed_password="pw")
        db.session.add(u)
        db.session.commit()
        user_id = u.id
    return user_id


def test_contract_status_enum_values():
    assert ContractStatus.active.value == "active"
    assert ContractStatus.pending_cancellation.value == "pending_cancellation"
    assert ContractStatus.cancellation_confirmed.value == "cancellation_confirmed"
    assert ContractStatus.paused.value == "paused"
    assert ContractStatus.canceled.value == "canceled"
    assert ContractStatus.archived.value == "archived"


def test_earliest_cancellation_before_initial_term_deadline(app, user):
    """A 24-month contract with 1 month notice viewed well before the minimum term deadline."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            category="Internet",
            start_date=date(2024, 1, 1),
            initial_term_months=24,
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        # As of 2025-06-01: Deadline is 2025-12-01 (2024-01-01 + 24m - 1m)
        as_of = date(2025, 6, 1)
        earliest_end = contract.get_earliest_cancellation_date(as_of=as_of)
        deadline = contract.get_cancellation_deadline(as_of=as_of)

        assert earliest_end == date(2026, 1, 1)
        assert deadline == date(2025, 12, 1)


def test_earliest_cancellation_monthly_rolling_after_initial_term(app, user):
    """After the initial term passes, monthly rolling extends month-by-month."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            category="Mobile",
            start_date=date(2022, 1, 15),
            initial_term_months=24,  # Ended 2024-01-15
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        # As of 2026-09-05:
        # Notice is 1 month.
        # Candidate 2026-10-15 has deadline 2026-09-15 >= 2026-09-05.
        as_of = date(2026, 9, 5)
        earliest_end = contract.get_earliest_cancellation_date(as_of=as_of)
        deadline = contract.get_cancellation_deadline(as_of=as_of)

        assert earliest_end == date(2026, 10, 15)
        assert deadline == date(2026, 9, 15)


def test_earliest_cancellation_fixed_period_renewal(app, user):
    """A contract with fixed 12-month extension (e.g. gym/B2B)."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            category="Fitness",
            start_date=date(2023, 1, 1),
            initial_term_months=12,  # Cycle 1 ends 2024-01-01
            renewal_type="fixed_period",
            renewal_period_months=12,  # Extends by 12m
            cancellation_notice_amount=3,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        # As of 2024-05-01:
        # Cycle 1 (ended 2024-01-01) is past.
        # Cycle 2 ends 2025-01-01.
        # Deadline for Cycle 2: 2025-01-01 - 3m = 2024-10-01.
        # As of 2024-05-01 <= 2024-10-01 -> can still cancel for Cycle 2 end!
        as_of = date(2024, 5, 1)
        assert contract.get_earliest_cancellation_date(as_of=as_of) == date(2025, 1, 1)
        assert contract.get_cancellation_deadline(as_of=as_of) == date(2024, 10, 1)

        # But as of 2024-11-01 (deadline 2024-10-01 missed):
        # Cycle 2 missed -> rolls into Cycle 3 ending 2026-01-01.
        # Deadline for Cycle 3: 2026-01-01 - 3m = 2025-10-01.
        as_of_late = date(2024, 11, 1)
        assert contract.get_earliest_cancellation_date(as_of=as_of_late) == date(2026, 1, 1)
        assert contract.get_cancellation_deadline(as_of=as_of_late) == date(2025, 10, 1)


def test_contract_cancellation_confirmed_status(app, user):
    """When cancellation is confirmed, confirmed_end_date takes priority."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            category="Streaming",
            start_date=date(2024, 1, 1),
            initial_term_months=12,
            status=ContractStatus.cancellation_confirmed,
            confirmed_end_date=date(2025, 3, 31),
            cancellation_sent_date=date(2025, 1, 10),
        )
        db.session.add(contract)
        db.session.commit()

        assert contract.status == ContractStatus.cancellation_confirmed
        assert contract.get_earliest_cancellation_date() == date(2025, 3, 31)
        # For confirmed cancellations, no deadline action is needed
        assert contract.cancellation_status == "none"


def test_contract_paused_status_next_billing(app, user):
    """When a contract is paused, next_billing_date returns None."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            category="Gym",
            start_date=date(2024, 1, 1),
            billing_anchor_date=date(2024, 1, 1),
            frequency=Frequency.monthly,
            amount=30.0,
            status=ContractStatus.paused,
        )
        db.session.add(contract)
        db.session.commit()

        assert contract.next_billing_date is None


def test_contract_lifecycle_web_integration(client, app, user):
    """Test full HTTP lifecycle: create, toggle statuses, filter, and view detail."""
    # Log in
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user)
        sess['_fresh'] = True

    # 1. Create contract with rollover fields
    create_resp = client.post(
        '/contracts/',
        data={
            'category': 'DSL Internet',
            'amount': '39.99',
            'currency': 'EUR',
            'frequency': 'monthly',
            'start_date': '2024-01-01',
            'initial_term_months': '24',
            'renewal_type': 'monthly_rolling',
            'renewal_period_months': '1',
            'cancellation_notice_amount': '1',
            'cancellation_notice_unit': 'months',
            'status': 'active',
        },
        follow_redirects=True,
    )
    assert create_resp.status_code == 200
    assert b"DSL Internet" in create_resp.data

    with app.app_context():
        c = Contract.query.filter_by(category="DSL Internet").first()
        assert c is not None
        assert c.initial_term_months == 24
        assert c.renewal_type == "monthly_rolling"
        contract_id = c.id

    # 2. Toggle status to pending_cancellation
    toggle_resp = client.post(
        f'/contracts/{contract_id}/status',
        data={'status': 'pending_cancellation'},
        follow_redirects=True,
    )
    assert toggle_resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, contract_id)
        assert c.status == ContractStatus.pending_cancellation

    # 3. Filter contracts by pending_cancellation
    filter_resp = client.get('/contracts/?status=pending_cancellation')
    assert filter_resp.status_code == 200
    assert b"DSL Internet" in filter_resp.data

    # 4. Toggle status to paused
    client.post(
        f'/contracts/{contract_id}/status',
        data={'status': 'paused'},
        follow_redirects=True,
    )
    with app.app_context():
        c = db.session.get(Contract, contract_id)
        assert c.status == ContractStatus.paused

    filter_paused = client.get('/contracts/?status=paused')
    assert filter_paused.status_code == 200
    assert b"DSL Internet" in filter_paused.data

    # 5. Detail view rendering
    detail_resp = client.get(f'/contracts/{contract_id}')
    assert detail_resp.status_code == 200
    assert b"DSL Internet" in detail_resp.data


def test_contract_auto_transition_at_confirmed_end_date(app, user):
    """When a confirmed end date is in the past, sync_contract_status auto-transitions to canceled (Beendet)."""
    with app.app_context():
        # Case A: End date was yesterday -> should transition
        past_contract = Contract(
            user_id=user,
            category="Old Streaming",
            status=ContractStatus.cancellation_confirmed,
            confirmed_end_date=date.today() - timedelta(days=1),
        )
        db.session.add(past_contract)

        # Case B: End date is tomorrow -> should NOT transition
        future_contract = Contract(
            user_id=user,
            category="Active Streaming",
            status=ContractStatus.cancellation_confirmed,
            confirmed_end_date=date.today() + timedelta(days=1),
        )
        db.session.add(future_contract)
        db.session.commit()

        # Run sync
        assert past_contract.sync_contract_status() is True
        assert past_contract.status == ContractStatus.canceled

        assert future_contract.sync_contract_status() is False
        assert future_contract.status == ContractStatus.cancellation_confirmed


def test_contract_archive_and_unarchive_flow(client, app, user):
    """Test archiving and restoring contracts via POST endpoints and list filtering."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user)
        sess['_fresh'] = True

    with app.app_context():
        c = Contract(
            user_id=user,
            category="Archive Test Contract",
            status=ContractStatus.canceled,
            is_archived=False,
        )
        db.session.add(c)
        db.session.commit()
        contract_id = c.id

    # 1. Verify it appears in default /contracts list
    resp = client.get('/contracts/')
    assert resp.status_code == 200
    assert b"Archive Test Contract" in resp.data

    # 2. Archive it
    archive_resp = client.post(f'/contracts/{contract_id}/archive', follow_redirects=True)
    assert archive_resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, contract_id)
        assert c.is_archived is True

    # 3. Verify it is now hidden from default /contracts list
    resp_after = client.get('/contracts/')
    assert resp_after.status_code == 200
    assert b"Archive Test Contract" not in resp_after.data

    # 4. Verify it is visible in the archive view
    resp_archive = client.get('/contracts/?status=archived')
    assert resp_archive.status_code == 200
    assert b"Archive Test Contract" in resp_archive.data

    # 5. Unarchive it
    unarchive_resp = client.post(f'/contracts/{contract_id}/unarchive', follow_redirects=True)
    assert unarchive_resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, contract_id)
        assert c.is_archived is False

    # 6. Verify it is visible again in default /contracts list
    resp_restored = client.get('/contracts/')
    assert resp_restored.status_code == 200
    assert b"Archive Test Contract" in resp_restored.data


def test_archive_failsafe_blocks_non_canceled_contracts(app, user, client):
    """Contracts can strictly only be moved to archive if status is canceled."""
    with app.app_context():
        # Log in the user
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user)

        c = Contract(
            user_id=user,
            title="Active Service",
            category="Service",
            status=ContractStatus.active,
            is_archived=False,
        )
        db.session.add(c)
        db.session.commit()
        contract_id = c.id

    # Attempt to archive while active
    resp = client.post(f'/contracts/{contract_id}/archive', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        c_db = db.session.get(Contract, contract_id)
        assert c_db.is_archived is False


def test_scheduled_contract_lifecycle_auto_activation(app, user):
    """Scheduled contract auto-activates when today >= start_date."""
    with app.app_context():
        # 1. Start date is tomorrow -> remains scheduled
        tomorrow = date.today() + timedelta(days=1)
        c = Contract(
            user_id=user,
            title="Future Fitness",
            category="Fitness",
            start_date=tomorrow,
            status=ContractStatus.scheduled,
        )
        db.session.add(c)
        db.session.commit()

        changed = c.sync_contract_status(as_of=date.today())
        assert changed is False
        assert c.status == ContractStatus.scheduled

        # 2. When date reaches start_date -> auto-activates
        changed_on_start = c.sync_contract_status(as_of=tomorrow)
        assert changed_on_start is True
        assert c.status == ContractStatus.active


def test_confirmed_cancellation_auto_terminates(app, user):
    """Contract with cancellation_confirmed auto-closes to canceled when today > confirmed_end_date."""
    with app.app_context():
        yesterday = date.today() - timedelta(days=1)
        c = Contract(
            user_id=user,
            title="Old Broadband",
            category="Internet",
            confirmed_end_date=yesterday,
            status=ContractStatus.cancellation_confirmed,
        )
        db.session.add(c)
        db.session.commit()

        changed = c.sync_contract_status(as_of=date.today())
        assert changed is True
        assert c.status == ContractStatus.canceled


def test_snap_to_target_period_exact_month_quarter_year():
    """Verify snap_to_target_period accurately maps to exact, month end, quarter end, and year end."""
    # 1. Exact
    d = date(2024, 2, 14)
    assert snap_to_target_period(d, "exact") == d

    # 2. End of Month (handling leap year)
    assert snap_to_target_period(date(2024, 2, 14), "end_of_month") == date(2024, 2, 29)
    assert snap_to_target_period(date(2023, 2, 14), "end_of_month") == date(2023, 2, 28)
    assert snap_to_target_period(date(2024, 4, 1), "end_of_month") == date(2024, 4, 30)
    assert snap_to_target_period(date(2024, 12, 5), "end_of_month") == date(2024, 12, 31)

    # 3. End of Quarter
    assert snap_to_target_period(date(2024, 1, 10), "end_of_quarter") == date(2024, 3, 31)
    assert snap_to_target_period(date(2024, 5, 20), "end_of_quarter") == date(2024, 6, 30)
    assert snap_to_target_period(date(2024, 7, 1), "end_of_quarter") == date(2024, 9, 30)
    assert snap_to_target_period(date(2024, 10, 15), "end_of_quarter") == date(2024, 12, 31)

    # 4. End of Year
    assert snap_to_target_period(date(2024, 3, 1), "end_of_year") == date(2024, 12, 31)


def test_cancellation_date_with_cancellation_target_period(app, user):
    """Test earliest cancellation date with end_of_month and end_of_quarter target periods."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            category="Internet",
            start_date=date(2024, 1, 15),
            initial_term_months=12,
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            cancellation_target_period="end_of_month",
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        # Initial term: 2024-01-15 + 12m = 2025-01-15 -> snaps to end_of_month: 2025-01-31
        # Deadline: 2025-01-31 - 1m = 2024-12-31
        as_of = date(2024, 6, 1)
        assert contract.get_earliest_cancellation_date(as_of=as_of) == date(2025, 1, 31)
        assert contract.get_cancellation_deadline(as_of=as_of) == date(2024, 12, 31)

        # Switch target period to end_of_quarter:
        # Initial term snaps to Q1 end: 2025-03-31
        # Deadline: 2025-03-31 - 1m = 2025-02-28
        contract.cancellation_target_period = "end_of_quarter"
        assert contract.get_earliest_cancellation_date(as_of=as_of) == date(2025, 3, 31)
        assert contract.get_cancellation_deadline(as_of=as_of) == date(2025, 2, 28)


def test_is_monthly_flexible_and_cancellation_status(app, user):
    """Test monthly flexible detection and cancellation status de-escalation."""
    with app.app_context():
        # Case A: Pure monthly rolling contract with no initial term
        flexible_contract = Contract(
            user_id=user,
            category="Streaming",
            start_date=date(2024, 1, 1),
            initial_term_months=0,
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=30,
            cancellation_notice_unit="days",
            status=ContractStatus.active,
        )
        assert flexible_contract.is_monthly_flexible is True
        # For monthly flexible contracts, cancellation_status is 'flexible', preventing yellow alarm badges
        assert flexible_contract.cancellation_status == "flexible"

        # Case B: Contract with active 24-month initial term
        locked_contract = Contract(
            user_id=user,
            category="Mobile",
            start_date=date.today(),
            initial_term_months=24,
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        assert locked_contract.is_monthly_flexible is False
        assert locked_contract.cancellation_status != "flexible"

        # Case C: Fixed-term contract (no rollover)
        fixed_contract = Contract(
            user_id=user,
            category="Trial",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),
            renewal_type="none",
            status=ContractStatus.active,
        )
        assert fixed_contract.is_monthly_flexible is False


def test_scheduled_contract_price_history_no_spurious_badge(app, user):
    """Future scheduled contract with an initial PriceEntry matching its start price does NOT show a price change badge."""
    with app.app_context():
        future_start = date.today() + timedelta(days=30)
        contract = Contract(
            user_id=user,
            title="Future DSL",
            category="Internet",
            start_date=future_start,
            status=ContractStatus.scheduled,
            amount=48.0,
            currency="EUR",
        )
        db.session.add(contract)
        db.session.commit()

        # Initial price entry effective at start_date with the same amount
        pe_initial = PriceEntry(
            contract_id=contract.id,
            amount=48.0,
            currency="EUR",
            valid_from=future_start,
        )
        db.session.add(pe_initial)
        db.session.commit()

        # Should NOT be counted as an upcoming price change
        assert contract.upcoming_price_entries == []
        assert contract.next_price_change is None

        # Add a genuine future price change (e.g. promotional phase ends)
        pe_promo_end = PriceEntry(
            contract_id=contract.id,
            amount=59.0,
            currency="EUR",
            valid_from=future_start + timedelta(days=180),
        )
        db.session.add(pe_promo_end)
        db.session.commit()

        assert len(contract.upcoming_price_entries) == 1
        assert contract.next_price_change.id == pe_promo_end.id
        assert float(contract.next_price_change.amount) == 59.0


def test_initial_commitment_financial_service(app, user):
    """FinancialService accurately calculates guaranteed minimum commitment duration and total costs."""
    with app.app_context():
        start = date.today() - timedelta(days=60)
        contract = Contract(
            user_id=user,
            category="Broadband",
            start_date=start,
            initial_term_months=24,
            amount=40.0,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        fin_service = FinancialService()
        summary = fin_service.calculate_contract_cost_summary(contract)

        commitment = summary.get("initial_commitment")
        assert commitment is not None
        assert commitment["months"] == 24
        assert commitment["total_amount"] == 960.0  # 24 * 40.0
        assert commitment["currency"] == "EUR"
        assert commitment["is_active"] is True
        assert commitment["end_date"] == add_months(start, 24)


def test_cancellation_workflow_pending_and_confirmed_web(client, app, user):
    """Test web status transitions: pending_cancellation auto-sets sent date, confirmed records confirmed_end_date."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user)
        sess["_fresh"] = True

    with app.app_context():
        contract = Contract(
            user_id=user,
            title="Streaming Subscription",
            category="Streaming",
            status=ContractStatus.active,
            start_date=date(2024, 1, 1),
            initial_term_months=0,
            renewal_type="monthly_rolling",
        )
        db.session.add(contract)
        db.session.commit()
        contract_id = contract.id

    # 1. Switch to pending_cancellation -> auto-sets cancellation_sent_date to today
    resp_pending = client.post(
        f"/contracts/{contract_id}/status",
        data={"status": "pending_cancellation"},
        follow_redirects=True,
    )
    assert resp_pending.status_code == 200

    with app.app_context():
        c_pending = db.session.get(Contract, contract_id)
        assert c_pending.status == ContractStatus.pending_cancellation
        assert c_pending.cancellation_sent_date == date.today()

    # 2. Confirm cancellation with confirmed_end_date
    resp_confirmed = client.post(
        f"/contracts/{contract_id}/status",
        data={
            "status": "cancellation_confirmed",
            "confirmed_end_date": "2026-10-31",
        },
        follow_redirects=True,
    )
    assert resp_confirmed.status_code == 200

    with app.app_context():
        c_confirmed = db.session.get(Contract, contract_id)
        assert c_confirmed.status == ContractStatus.cancellation_confirmed
        assert c_confirmed.confirmed_end_date == date(2026, 10, 31)


def test_initial_term_end_date_model_logic(app, user):
    """Explicit initial_term_end_date takes precedence over initial_term_months."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            title="Fiber 1000",
            category="Internet",
            start_date=date(2025, 1, 1),
            initial_term_end_date=date(2027, 1, 1),
            initial_term_months=24,
            renewal_type="monthly_rolling",
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        # When viewing during the initial lock-in period
        as_of_during = date(2026, 6, 1)
        assert contract.get_earliest_cancellation_date(as_of=as_of_during) == date(2027, 1, 1)
        # Check flexibility: before initial_term_end_date it is not flexible yet
        assert contract.is_monthly_flexible is False

        # When viewing after the initial lock-in period (e.g. 2027-02-01)
        as_of_after = date(2027, 2, 1)
        earliest_end = contract.get_earliest_cancellation_date(as_of=as_of_after)
        assert earliest_end == date(2027, 3, 1)


def test_fixed_term_contract_renewal_none(app, user):
    """Fixed-term contract with renewal_type='none' terminates on end_date without monthly flexibility."""
    with app.app_context():
        contract = Contract(
            user_id=user,
            title="Software Project License",
            category="Software",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            renewal_type="none",
            status=ContractStatus.active,
        )
        db.session.add(contract)
        db.session.commit()

        assert contract.is_monthly_flexible is False
        assert contract.get_earliest_cancellation_date(as_of=date(2025, 6, 1)) == date(2025, 12, 31)


def test_extend_contract_web_append_and_price(client, app, user):
    """Web test for extending contract term (VVL): appends months, updates price entry and adds system note."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user)
        sess["_fresh"] = True

    with app.app_context():
        contract = Contract(
            user_id=user,
            title="Mobile Unlimited",
            category="Mobile",
            status=ContractStatus.active,
            start_date=date(2025, 1, 1),
            initial_term_end_date=date(2027, 1, 1),
            initial_term_months=24,
            amount=49.99,
            currency="EUR",
            renewal_type="monthly_rolling",
        )
        db.session.add(contract)
        db.session.commit()
        contract_id = contract.id

    # Post extension by 24 months (append) with discount price 39.99
    resp = client.post(
        f"/contracts/{contract_id}/extend",
        data={
            "extension_months": "24",
            "extension_start_mode": "append",
            "new_amount": "39.99",
            "note": "Treueangebot 10€ Rabatt",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, contract_id)
        # Appended to 2027-01-01 + 24 months = 2029-01-01
        assert c.initial_term_end_date == date(2029, 1, 1)
        # Current amount remains 49.99 until 2027-01-01
        assert float(c.amount) == 49.99

        # PriceEntry was created as upcoming price entry
        price_entries = PriceEntry.query.filter_by(contract_id=contract_id).all()
        assert len(price_entries) >= 1
        new_pe = [p for p in price_entries if float(p.amount) == 39.99][0]
        assert new_pe.valid_from == date(2027, 1, 1)
        assert c.next_price_change is not None
        assert float(c.next_price_change.amount) == 39.99

        # Note was added
        notes = Note.query.filter_by(contract_id=contract_id).all()
        assert len(notes) == 1
        assert "Vorzeitige Vertragsverlängerung" in notes[0].content
        assert "Treueangebot 10€ Rabatt" in notes[0].content


def test_extend_contract_reverts_cancellation_status(client, app, user):
    """Extending a contract that is currently pending cancellation resets status to active, applies from_today price and clears cancellation dates."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user)
        sess["_fresh"] = True

    with app.app_context():
        contract = Contract(
            user_id=user,
            title="DSL 250",
            category="Internet",
            status=ContractStatus.pending_cancellation,
            cancellation_sent_date=date.today(),
            confirmed_end_date=date(2026, 12, 31),
            start_date=date(2024, 1, 1),
            initial_term_end_date=date(2026, 1, 1),
            amount=39.99,
            currency="EUR",
        )
        db.session.add(contract)
        db.session.commit()
        contract_id = contract.id

    # User accepted a retention deal -> extend from today by 12 months with immediate new price 29.99
    resp = client.post(
        f"/contracts/{contract_id}/extend",
        data={
            "extension_months": "12",
            "extension_start_mode": "from_today",
            "new_amount": "29.99",
            "note": "Kündigung zurückgenommen, 12M Verlängerung",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, contract_id)
        assert c.status == ContractStatus.active
        assert c.cancellation_sent_date is None
        assert c.confirmed_end_date is None
        assert c.initial_term_end_date == add_months(date.today(), 12)
        # Immediate price change active today
        assert float(c.amount) == 29.99


def test_cancellation_deadline_displayed_for_scheduled_and_flexible(client, app, user):
    """Ensure cancellation deadline date is rendered for both scheduled and monthly flexible contracts."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user)
        sess["_fresh"] = True

    with app.app_context():
        # 1. Scheduled contract starting in 40 days
        c_sched = Contract(
            user_id=user,
            title="Strom Zukunftsvertrag",
            category="Energy",
            status=ContractStatus.scheduled,
            start_date=date.today() + timedelta(days=40),
            initial_term_months=12,
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            amount=50.00,
            currency="EUR",
        )
        # 2. Monthly flexible contract past initial term
        c_flex = Contract(
            user_id=user,
            title="sim24 Flexi",
            category="Mobile",
            status=ContractStatus.active,
            start_date=date(2022, 1, 1),
            initial_term_months=0,
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            amount=10.00,
            currency="EUR",
        )
        db.session.add_all([c_sched, c_flex])
        db.session.commit()
        sched_id = c_sched.id
        flex_id = c_flex.id

    # Check scheduled contract detail page
    resp_sched = client.get(f"/contracts/{sched_id}?lang=de")
    assert resp_sched.status_code == 200
    sched_html = resp_sched.get_data(as_text=True)
    # Both the cancellation deadline label and date should be present
    assert "Kündigungsfrist bis" in sched_html
    assert "Frist im Plan" in sched_html
    with app.app_context():
        c_sched_obj = db.session.get(Contract, sched_id)
        assert c_sched_obj.cancellation_deadline.strftime("%d.%m.%Y") in sched_html

    # Check monthly flexible contract detail page
    resp_flex = client.get(f"/contracts/{flex_id}?lang=de")
    assert resp_flex.status_code == 200
    flex_html = resp_flex.get_data(as_text=True)
    # Flexible badge AND cancellation deadline date must both be present
    assert "Monatlich flexibel kündbar" in flex_html
    assert "Kündigungsfrist bis" in flex_html
    with app.app_context():
        c_flex_obj = db.session.get(Contract, flex_id)
        assert c_flex_obj.cancellation_deadline.strftime("%d.%m.%Y") in flex_html


def test_cancellation_confirmed_hides_rollover_and_notice(client, app, user):
    """Ensure confirmed canceled contracts hide rollover mechanics and notice deadlines."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user)
        sess["_fresh"] = True

    with app.app_context():
        c = Contract(
            user_id=user,
            title="Strom Gekündigt",
            category="Energy",
            status=ContractStatus.cancellation_confirmed,
            start_date=date(2025, 10, 13),
            confirmed_end_date=date(2026, 10, 13),
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            amount=53.23,
            currency="EUR",
        )
        db.session.add(c)
        db.session.commit()
        c_id = c.id

    resp = client.get(f"/contracts/{c_id}?lang=de")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Must show confirmed cancellation status
    assert "Kündigung bestätigt" in html
    assert "13.10.2026" in html

    # Must NOT show rollover lifecycle 4-box row or notice period
    assert "Monatlich rollierend" not in html
    assert "Verlängerungsart" not in html


def test_extend_contract_sets_exact_extension_months_not_history(client, app, user):
    """Ensure extending an older contract sets initial_term_months to extension duration, not history."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user)
        sess["_fresh"] = True

    with app.app_context():
        c = Contract(
            user_id=user,
            title="Old Gym Contract",
            category="Sport",
            status=ContractStatus.active,
            start_date=date(2020, 10, 25),
            initial_term_months=12,
            initial_term_end_date=date(2021, 10, 25),
            amount=29.99,
            currency="EUR",
            renewal_type="monthly_rolling",
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    # User extends by 24 months starting from custom date 2026-09-28 to 2028-09-28
    resp = client.post(
        f"/contracts/{cid}/extend",
        data={
            "extension_months": "24",
            "extension_start_mode": "custom_date",
            "custom_start_date": "2026-09-28",
            "new_amount": "24.99",
            "note": "VVL 24 Monate",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        updated = db.session.get(Contract, cid)
        # initial_term_months must be 24, NOT 95!
        assert updated.initial_term_months == 24
        assert updated.initial_term_end_date == date(2028, 9, 28)


def test_statutory_bgb_309_monthly_rolling_after_initial_term(app, user):
    """Verify BGB § 309 Nr. 9 lit. b: Contracts concluded post March 2022 roll monthly with max 1m notice."""
    with app.app_context():
        c = Contract(
            user_id=user,
            title="Post-2022 Telco Contract",
            category="Internet",
            status=ContractStatus.active,
            start_date=date(2023, 1, 1),
            initial_term_months=24,
            initial_term_end_date=date(2025, 1, 1),
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
        )
        db.session.add(c)
        db.session.commit()

        # As of 2025-05-10 (after 24-month initial commitment):
        as_of = date(2025, 5, 10)
        earliest_end = c.get_earliest_cancellation_date(as_of=as_of)
        deadline = c.get_cancellation_deadline(as_of=as_of)

        # In monthly rolling, next valid end is 2025-07-01 with deadline 2025-06-01 (>= 2025-05-10)
        # (Candidate 2025-06-01 has deadline 2025-05-01 < 2025-05-10, so candidate is 2025-07-01)
        assert earliest_end == date(2025, 7, 1)
        assert deadline == date(2025, 6, 1)


def test_insurance_vvg_fixed_period_exception(app, user):
    """Verify VVG § 11 Abs. 2: Insurance contracts are exempt from BGB § 309 Nr. 9 and renew for up to 12m."""
    with app.app_context():
        c = Contract(
            user_id=user,
            title="KFZ-Haftpflicht",
            category="Versicherung",
            status=ContractStatus.active,
            start_date=date(2023, 1, 1),
            initial_term_months=12,
            initial_term_end_date=date(2024, 1, 1),
            renewal_type="fixed_period",
            renewal_period_months=12,
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
        )
        db.session.add(c)
        db.session.commit()

        # As of 2024-03-15 (missed deadline for 2024-01-01, into cycle 2):
        as_of = date(2024, 3, 15)
        earliest_end = c.get_earliest_cancellation_date(as_of=as_of)
        deadline = c.get_cancellation_deadline(as_of=as_of)

        assert earliest_end == date(2025, 1, 1)
        assert deadline == date(2024, 12, 1)


def test_deadline_calculation_no_forward_shift_on_weekend(app, user):
    """Verify BGH/BAG principle: § 193 BGB does NOT apply to cancellation deadlines in favor of the sender.
    Deadlines falling on Saturday or Sunday must NEVER be pushed forward to Monday.
    """
    with app.app_context():
        # Suppose a contract period ends on 2026-08-31.
        # Notice period: 1 month.
        # Calculated statutory deadline: 2026-07-31 (Friday).
        # But if term ends on 2026-05-31 (Sunday) with 1 month notice:
        # Notice deadline is 2026-04-30 (Thursday).
        # If term ends on 2026-06-30 (Tuesday) with 30 days notice:
        # Notice deadline is 2026-05-31 (Sunday).
        c = Contract(
            user_id=user,
            title="Sunday Deadline Test",
            category="General",
            status=ContractStatus.active,
            start_date=date(2026, 1, 1),
            initial_term_months=6,
            initial_term_end_date=date(2026, 7, 1),
            renewal_type="monthly_rolling",
            renewal_period_months=1,
            cancellation_notice_amount=30,
            cancellation_notice_unit="days",
        )
        db.session.add(c)
        db.session.commit()

        # 2026-07-01 minus 30 days is 2026-06-01 (Monday).
        # Let's test with end date 2026-07-05 (Sunday) and notice of 7 days:
        # 2026-07-05 - 7 days = 2026-06-28 (Sunday).
        c.end_date = date(2026, 7, 5)
        c.cancellation_notice_amount = 7
        c.cancellation_notice_unit = "days"
        db.session.commit()

        deadline = c.get_cancellation_deadline()
        # 2026-06-28 is a Sunday. Under BGH/BAG, it must remain 2026-06-28, NOT 2026-06-29 (Monday).
        assert deadline.weekday() == 6  # Sunday
        assert deadline == date(2026, 6, 28)
