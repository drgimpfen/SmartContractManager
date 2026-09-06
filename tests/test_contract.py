import datetime
from datetime import date
import json
import pytest
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Provider, Contract, PriceEntry, Tag, ContractStatus, Frequency
from app.services.contract_service import pick_tag_color, sync_contract_tags, check_price_overlap, add_price_entry


def test_pick_tag_color_deterministic():
    c1 = pick_tag_color("Internet")
    c2 = pick_tag_color("Internet")
    c3 = pick_tag_color("Streaming")
    assert c1 == c2
    assert c1.startswith('#')
    assert len(c1) == 7


def test_contract_creation_and_initial_price(client, app):
    from app import db
    with app.app_context():
        user = User(username='con_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(user)
        db.session.commit()
        prov = Provider(user_id=user.id, name='Vodafone')
        db.session.add(prov)
        db.session.commit()
        prov_id = prov.id

    client.post('/login', data={'username': 'con_user', 'password': 'pass123'}, follow_redirects=True)

    resp = client.post('/contracts', data={
        'category': 'Internet & Phone',
        'provider_id': prov_id,
        'contract_number': 'VF-998877',
        'amount': '39.99',
        'currency': 'EUR',
        'frequency': 'monthly',
        'start_date': '2025-01-01',
        'billing_anchor_date': '2025-01-15',
        'cancellation_notice_amount': 1,
        'cancellation_notice_unit': 'months',
        'payment_method': 'SEPA Direct Debit',
        'tags': 'Home, Web',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b'Internet &amp; Phone' in resp.data or b'Internet & Phone' in resp.data

    with app.app_context():
        c = Contract.query.filter_by(contract_number='VF-998877').first()
        assert c is not None
        assert c.category == 'Internet & Phone'
        assert c.frequency == Frequency.monthly
        assert c.billing_anchor_date == datetime.date(2025, 1, 15)
        assert c.provider_id == prov_id

        # Verify initial price entry
        assert len(c.price_history) == 1
        initial_p = c.price_history[0]
        assert initial_p.amount == 39.99
        assert initial_p.is_current is True
        assert initial_p.valid_from == datetime.date(2025, 1, 1)
        assert initial_p.valid_to is None

        # Verify tags
        tag_names = {t.name for t in c.tags}
        assert 'Home' in tag_names
        assert 'Web' in tag_names


def test_contract_user_isolation(client, app):
    from app import db
    with app.app_context():
        u1 = User(username='alice_con', hashed_password=generate_password_hash('pass123'))
        u2 = User(username='bob_con', hashed_password=generate_password_hash('pass123'))
        db.session.add_all([u1, u2])
        db.session.commit()

        c1 = Contract(
            user_id=u1.id,
            category='Alice Secret Contract',
            amount=100.0,
            currency='EUR',
            frequency=Frequency.yearly,
            status=ContractStatus.active,
        )
        db.session.add(c1)
        db.session.commit()
        c1_id = c1.id

    # Bob tries to access Alice's contract
    client.post('/login', data={'username': 'bob_con', 'password': 'pass123'}, follow_redirects=True)

    # Bob visits contract detail -> 404
    resp = client.get(f'/contracts/{c1_id}')
    assert resp.status_code == 404

    # Bob attempts edit -> 404
    resp = client.post(f'/contracts/{c1_id}/edit', data={'category': 'Hacked Contract'})
    assert resp.status_code == 404

    # Bob attempts delete -> 404
    resp = client.post(f'/contracts/{c1_id}/delete')
    assert resp.status_code == 404

    # Contract remains untouched
    with app.app_context():
        c = db.session.get(Contract, c1_id)
        assert c.category == 'Alice Secret Contract'


def test_contract_edit_and_status_change(client, app):
    from app import db
    with app.app_context():
        u = User(username='user_status', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        c = Contract(
            user_id=u.id,
            category='Streaming',
            amount=15.0,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()
        c_id = c.id

    client.post('/login', data={'username': 'user_status', 'password': 'pass123'}, follow_redirects=True)

    # Quick status change to canceled
    resp = client.post(f'/contracts/{c_id}/status', data={'status': 'canceled'}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, c_id)
        assert c.status == ContractStatus.canceled

    # Full edit
    resp = client.post(f'/contracts/{c_id}/edit', data={
        'category': 'Premium Streaming',
        'frequency': 'yearly',
        'status': 'canceled',
        'tags': 'TV, Entertainment',
        'notes': 'Canceled due to price increase',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, c_id)
        assert c.category == 'Premium Streaming'
        assert c.frequency == Frequency.yearly
        assert c.status == ContractStatus.canceled
        assert c.notes == 'Canceled due to price increase'
        assert len(c.tags) == 2

    # Test archiving via dedicated archive endpoint
    archive_resp = client.post(f'/contracts/{c_id}/archive', follow_redirects=True)
    assert archive_resp.status_code == 200
    with app.app_context():
        c = db.session.get(Contract, c_id)
        assert c.is_archived is True


def test_price_adjustment_auto_close_open_ended(client, app):
    from app import db
    with app.app_context():
        u = User(username='price_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        c = Contract(
            user_id=u.id,
            category='Gym Membership',
            amount=40.0,
            currency='EUR',
            frequency=Frequency.monthly,
            start_date=datetime.date(2025, 1, 1),
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.flush()

        p1 = PriceEntry(
            contract_id=c.id,
            amount=40.0,
            currency='EUR',
            valid_from=datetime.date(2025, 1, 1),
            valid_to=None,
            is_current=True,
            note='Initial Price',
        )
        db.session.add(p1)
        db.session.commit()
        c_id = c.id
        p1_id = p1.id

    client.post('/login', data={'username': 'price_user', 'password': 'pass123'}, follow_redirects=True)

    # Add new price starting 2025-07-01 with auto_adjust=y
    resp = client.post(f'/contracts/{c_id}/price-entry', data={
        'amount': '45.00',
        'currency': 'EUR',
        'valid_from': '2025-07-01',
        'valid_to': '',
        'note': 'Summer 2025 price hike',
        'auto_adjust': 'y',
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        p1 = db.session.get(PriceEntry, p1_id)
        assert p1.is_current is False
        assert p1.valid_to == datetime.date(2025, 6, 30)

        c = db.session.get(Contract, c_id)
        assert c.amount == 45.00
        current_price = [p for p in c.price_history if p.is_current][0]
        assert current_price.amount == 45.00
        assert current_price.valid_from == datetime.date(2025, 7, 1)
        assert current_price.valid_to is None


def test_price_collision_detection_blocks_without_auto_adjust(client, app):
    from app import db
    with app.app_context():
        u = User(username='collision_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        c = Contract(
            user_id=u.id,
            category='Fixed Energy Plan',
            amount=100.0,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.flush()

        p1 = PriceEntry(
            contract_id=c.id,
            amount=100.0,
            currency='EUR',
            valid_from=datetime.date(2025, 1, 1),
            valid_to=datetime.date(2025, 12, 31),
            is_current=True,
            note='Fixed 2025 Tariff',
        )
        db.session.add(p1)
        db.session.commit()
        c_id = c.id

    client.post('/login', data={'username': 'collision_user', 'password': 'pass123'}, follow_redirects=True)

    # Try to add an overlapping price WITHOUT auto_adjust
    resp = client.post(f'/contracts/{c_id}/price-entry', data={
        'amount': '120.00',
        'currency': 'EUR',
        'valid_from': '2025-06-01',
        'valid_to': '2025-10-31',
        'note': 'Colliding summer rate',
        # auto_adjust not sent -> False
    }, follow_redirects=True)

    assert resp.status_code == 200
    # Overlap error message should be displayed
    content = resp.data.decode('utf-8')
    assert ('Gültigkeitszeitraum' in content or 'überschneidet sich' in content)

    with app.app_context():
        c = db.session.get(Contract, c_id)
        # Still only 1 price entry
        assert len(c.price_history) == 1
        assert c.price_history[0].amount == 100.0


def test_price_collision_auto_adjust_success(client, app):
    from app import db
    with app.app_context():
        u = User(username='adjust_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        c = Contract(
            user_id=u.id,
            category='Cloud Storage',
            amount=10.0,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.flush()

        p1 = PriceEntry(
            contract_id=c.id,
            amount=10.0,
            currency='EUR',
            valid_from=datetime.date(2025, 1, 1),
            valid_to=datetime.date(2025, 12, 31),
            is_current=True,
        )
        db.session.add(p1)
        db.session.commit()
        c_id = c.id
        p1_id = p1.id

    client.post('/login', data={'username': 'adjust_user', 'password': 'pass123'}, follow_redirects=True)

    # Add overlapping price WITH auto_adjust=y
    resp = client.post(f'/contracts/{c_id}/price-entry', data={
        'amount': '12.00',
        'currency': 'EUR',
        'valid_from': '2025-06-01',
        'valid_to': '2025-10-31',
        'auto_adjust': 'y',
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, c_id)
        assert len(c.price_history) == 2

        p1 = db.session.get(PriceEntry, p1_id)
        # Previous price clipped to 2025-05-31
        assert p1.valid_to == datetime.date(2025, 5, 31)
        assert p1.is_current is False


def test_delete_contract_cascade(client, app):
    from app import db
    with app.app_context():
        u = User(username='del_c_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        c = Contract(
            user_id=u.id,
            category='Service to Delete',
            amount=25.0,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.flush()
        p = PriceEntry(
            contract_id=c.id,
            amount=25.0,
            currency='EUR',
            valid_from=datetime.date(2025, 1, 1),
            is_current=True,
        )
        db.session.add(p)
        db.session.commit()
        c_id = c.id
        p_id = p.id

    client.post('/login', data={'username': 'del_c_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/contracts/{c_id}/delete', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Contract, c_id) is None
        assert db.session.get(PriceEntry, p_id) is None


def test_delete_provider_preserves_contract(client, app):
    from app import db
    with app.app_context():
        u = User(username='prov_keep_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        prov = Provider(user_id=u.id, name='Independent ISP')
        db.session.add(prov)
        db.session.flush()

        c = Contract(
            user_id=u.id,
            provider_id=prov.id,
            category='ISP Fiber',
            amount=50.0,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()
        prov_id = prov.id
        c_id = c.id

    client.post('/login', data={'username': 'prov_keep_user', 'password': 'pass123'}, follow_redirects=True)

    # Delete provider
    resp = client.post(f'/providers/{prov_id}/delete', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Provider, prov_id) is None
        c = db.session.get(Contract, c_id)
        assert c is not None
        assert c.provider_id is None


def test_interactive_tag_sync_and_creation(client, app):
    from app import db
    with app.app_context():
        u = User(username='tag_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        # Pre-existing tag
        t1 = Tag(user_id=u.id, name='Internet', color='#0d6efd')
        db.session.add(t1)
        db.session.commit()
        u_id = u.id

    client.post('/login', data={'username': 'tag_user', 'password': 'pass123'}, follow_redirects=True)

    # Post new contract with pre-existing tag plus new free-text tags
    resp = client.post('/contracts', data={
        'category': 'Car Insurance',
        'amount': '80.00',
        'currency': 'EUR',
        'frequency': 'yearly',
        'tags': 'Internet, Versicherung, Auto',
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        c = Contract.query.filter_by(category='Car Insurance', user_id=u_id).first()
        assert c is not None
        tag_names = {t.name for t in c.tags}
        assert tag_names == {'Internet', 'Versicherung', 'Auto'}

        # Verify new tags exist in database
        v_tag = Tag.query.filter_by(user_id=u_id, name='Versicherung').first()
        assert v_tag is not None
        assert v_tag.color.startswith('#')

        # Test detail route provides all_tags
        c_id = c.id

    resp_detail = client.get(f'/contracts/{c_id}')
    assert resp_detail.status_code == 200
    assert b'Versicherung' in resp_detail.data
    assert b'data-available-tags' in resp_detail.data
    assert b'tag-picker-inline' in resp_detail.data


def test_next_billing_date_calculation():
    from datetime import date
    from app.models import add_months, calculate_next_billing_date, Frequency, Contract
    # 1. Test add_months
    assert add_months(date(2024, 1, 15), 1) == date(2024, 2, 15)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # 2024 is leap year
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)  # 2023 is non-leap
    assert add_months(date(2024, 11, 10), 3) == date(2025, 2, 10)

    # 2. Test calculate_next_billing_date
    # Future anchor: returns anchor
    assert calculate_next_billing_date(date(2026, 12, 1), Frequency.monthly, date(2026, 9, 1)) == date(2026, 12, 1)

    # Past anchor monthly:
    assert calculate_next_billing_date(date(2024, 1, 15), Frequency.monthly, date(2026, 9, 5)) == date(2026, 9, 15)
    assert calculate_next_billing_date(date(2024, 1, 15), Frequency.monthly, date(2026, 9, 20)) == date(2026, 10, 15)

    # Past anchor yearly:
    assert calculate_next_billing_date(date(2022, 3, 15), Frequency.yearly, date(2026, 9, 5)) == date(2027, 3, 15)
    assert calculate_next_billing_date(date(2022, 11, 15), Frequency.yearly, date(2026, 9, 5)) == date(2026, 11, 15)

    # Past anchor quarterly:
    assert calculate_next_billing_date(date(2024, 1, 10), Frequency.quarterly, date(2026, 9, 5)) == date(2026, 10, 10)

    # Past anchor weekly:
    assert calculate_next_billing_date(date(2026, 8, 1), Frequency.weekly, date(2026, 9, 1)) == date(2026, 9, 5)

    # 3. Test Contract model integration with end_date
    c = Contract(
        billing_anchor_date=date(2024, 1, 15),
        frequency=Frequency.monthly,
        end_date=None,
    )
    assert c.get_next_billing_date(as_of=date(2026, 9, 5)) == date(2026, 9, 15)

    # Contract ended in the past:
    c_ended = Contract(
        billing_anchor_date=date(2024, 1, 15),
        frequency=Frequency.monthly,
        end_date=date(2025, 1, 1),
    )
    assert c_ended.get_next_billing_date(as_of=date(2026, 9, 5)) is None

    # Next billing would be after end_date:
    c_ending_soon = Contract(
        billing_anchor_date=date(2024, 1, 15),
        frequency=Frequency.monthly,
        end_date=date(2026, 9, 10),
    )
    assert c_ending_soon.get_next_billing_date(as_of=date(2026, 9, 5)) is None

    # No anchor date and no start date:
    c_no_anchor = Contract(billing_anchor_date=None, start_date=None, frequency=Frequency.monthly)
    assert c_no_anchor.get_next_billing_date(as_of=date(2026, 9, 5)) is None

    # Fallback to start_date when anchor is None:
    c_start_only = Contract(billing_anchor_date=None, start_date=date(2024, 1, 15), frequency=Frequency.monthly)
    assert c_start_only.get_next_billing_date(as_of=date(2026, 9, 5)) == date(2026, 9, 15)


def test_contract_creation_defaults_anchor_to_start_date(client, app):
    """When creating a contract without explicit billing_anchor_date, it defaults to start_date."""
    from app import db
    with app.app_context():
        user = User(username='anchor_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(user)
        db.session.commit()
        u_id = user.id

    client.post('/login', data={'username': 'anchor_user', 'password': 'pass123'}, follow_redirects=True)

    resp = client.post('/contracts', data={
        'title': 'Legacy Contract 2020',
        'category': 'Old Insurance',
        'amount': '45.00',
        'currency': 'EUR',
        'frequency': 'monthly',
        'start_date': '2020-10-25',
        'billing_anchor_date': '',  # Omitted by user
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        c = Contract.query.filter_by(title='Legacy Contract 2020', user_id=u_id).first()
        assert c is not None
        assert c.start_date == datetime.date(2020, 10, 25)
        assert c.billing_anchor_date == datetime.date(2020, 10, 25)
        # Next billing date is dynamically in September 2026
        next_bill = c.get_next_billing_date(as_of=datetime.date(2026, 9, 6))
        assert next_bill == datetime.date(2026, 9, 25)



def test_contract_remaining_term_and_cancellation_properties(monkeypatch):
    from datetime import date, timedelta
    from app.models import Contract, Frequency

    # Fix today to 2026-09-05
    fixed_today = date(2026, 9, 5)

    # 1. Open-ended contract
    c_open = Contract(end_date=None, cancellation_notice_amount=1, cancellation_notice_unit="months")
    assert c_open.days_until_end is None
    assert c_open.cancellation_deadline is None
    assert c_open.days_until_cancellation_deadline is None
    assert c_open.cancellation_status == "none"
    assert c_open.get_remaining_term_human(as_of=fixed_today) == "unlimited"

    # 2. Fixed-term contract ending in future with months notice
    # end_date = 2026-12-31, notice = 3 months -> deadline = 2026-09-30
    c_future = Contract(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        cancellation_notice_amount=3,
        cancellation_notice_unit="months",
    )
    assert c_future.cancellation_deadline == date(2026, 9, 30)

    # Monkeypatch date.today in models module if needed or test with explicit methods
    import app.models as models_module
    class MockDate(date):
        @classmethod
        def today(cls):
            return fixed_today

    monkeypatch.setattr(models_module, "date", MockDate)

    # days until end: 2026-12-31 - 2026-09-05 = 117 days
    assert c_future.days_until_end == 117
    # days until deadline: 2026-09-30 - 2026-09-05 = 25 days -> urgent
    assert c_future.days_until_cancellation_deadline == 25
    assert c_future.cancellation_status == "urgent"
    assert c_future.remaining_term_human == "3m"

    # 3. Safe cancellation status (>30 days)
    c_safe = Contract(
        end_date=date(2027, 6, 30),
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )
    # deadline = 2027-05-30, days > 30 -> safe
    assert c_safe.cancellation_status == "safe"
    assert c_safe.remaining_term_human == "9m"

    # 4. Due today
    c_today = Contract(
        end_date=date(2026, 10, 5),
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )
    # deadline = 2026-09-05, days = 0 -> due_today
    assert c_today.cancellation_deadline == date(2026, 9, 5)
    assert c_today.days_until_cancellation_deadline == 0
    assert c_today.cancellation_status == "due_today"

    # 5. Missed deadline (deadline passed, contract still active)
    c_missed = Contract(
        end_date=date(2026, 9, 20),
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )
    # deadline = 2026-08-20, days < 0 -> missed
    assert c_missed.days_until_cancellation_deadline < 0
    assert c_missed.cancellation_status == "missed"
    assert c_missed.remaining_term_human == "15d"

    # 6. Contract ended in past
    c_past = Contract(
        end_date=date(2026, 8, 1),
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )
    assert c_past.cancellation_status == "ended"
    assert c_past.remaining_term_human == "ended"

    # 7. Canceled or archived contract -> cancellation deadline and alert are suppressed
    c_canceled = Contract(
        status=ContractStatus.canceled,
        end_date=date(2026, 12, 31),
        cancellation_notice_amount=3,
        cancellation_notice_unit="months",
    )
    assert c_canceled.cancellation_deadline is None
    assert c_canceled.days_until_cancellation_deadline is None
    assert c_canceled.cancellation_status == "none"

    c_archived = Contract(
        status=ContractStatus.archived,
        end_date=date(2026, 12, 31),
        cancellation_notice_amount=3,
        cancellation_notice_unit="months",
    )
    assert c_archived.cancellation_deadline is None
    assert c_archived.days_until_cancellation_deadline is None
    assert c_archived.cancellation_status == "none"

    # 6b. Scheduled contract (starts in future) should compute cancellation deadline and safe status
    c_scheduled = Contract(
        status=ContractStatus.scheduled,
        start_date=date.today() + timedelta(days=40),
        initial_term_months=12,
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
        renewal_type="monthly_rolling",
    )
    assert c_scheduled.cancellation_deadline is not None
    assert c_scheduled.days_until_cancellation_deadline > 30
    assert c_scheduled.cancellation_status == "safe"

    # 7. Weeks and days notice units
    c_weeks = Contract(
        end_date=date(2026, 10, 1),
        cancellation_notice_amount=2,
        cancellation_notice_unit="weeks",
    )
    assert c_weeks.cancellation_deadline == date(2026, 9, 17)

    c_days = Contract(
        end_date=date(2026, 10, 1),
        cancellation_notice_amount=10,
        cancellation_notice_unit="days",
    )
    assert c_days.cancellation_deadline == date(2026, 9, 21)

    # 8. Remaining term human with years and months
    c_years = Contract(end_date=date(2028, 3, 5))
    # 2028-03-05 - 2026-09-05 = 547 days -> 1y 6m
    assert "1y" in c_years.remaining_term_human


def test_contract_detail_view_renders_cost_summary(client, app):
    from datetime import date
    from app import db
    from app.models import User, Contract, ContractStatus, Frequency
    with app.app_context():
        user = User(username="cost_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Fiber Internet",
            amount=50.0,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=date(2025, 1, 1),
            end_date=date(2026, 12, 31),
            billing_anchor_date=date(2025, 1, 1),
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
        )
        db.session.add(c)
        db.session.commit()
        c_id = c.id

    client.post("/login", data={"username": "cost_user", "password": "pass123"}, follow_redirects=True)
    
    # English default
    resp = client.get(f"/contracts/{c_id}")
    assert resp.status_code == 200
    assert b"Cost Overview" in resp.data or b"Total Lifetime Cost" in resp.data
    assert b"Remaining Term" in resp.data

    # German locale
    resp_de = client.get(f"/contracts/{c_id}?lang=de")
    assert resp_de.status_code == 200
    assert b"Kosten\xc3\xbcbersicht" in resp_de.data or b"Gesamtkosten" in resp_de.data
    assert b"Restlaufzeit" in resp_de.data

    # Verify all modular modals are rendered
    html = resp_de.get_data(as_text=True)
    assert 'id="editContractModal"' in html
    assert 'id="extendContractModal"' in html
    assert 'id="addPriceModal"' in html
    assert 'id="confirmCancellationModal"' in html
    assert 'id="deleteContractModal"' in html
    assert 'contract-term-group' in html
    assert 'combobox-container' in html
    assert 'tag-picker-inline' in html


def test_fixed_term_contract_streamlined_view(client, app):
    """Verify that contracts with renewal_type='none' have a streamlined view without redundant cancellation rows."""
    from datetime import date, timedelta
    from werkzeug.security import generate_password_hash
    from app.models import User, Contract, ContractStatus, Frequency
    from app import db

    with app.app_context():
        user = User(username="streamline_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        # Fixed term contract (loan / lease)
        c_fixed = Contract(
            user_id=user.id,
            title="Kredit Baufinanzierung",
            category="Finanzen",
            amount=500.0,
            currency="EUR",
            frequency=Frequency.monthly,
            start_date=date(2024, 1, 1),
            end_date=date.today() + timedelta(days=9429),
            renewal_type="none",
            status=ContractStatus.active,
        )

        # Rolling contract
        c_rolling = Contract(
            user_id=user.id,
            title="Handyvertrag",
            category="Telekommunikation",
            amount=29.99,
            currency="EUR",
            frequency=Frequency.monthly,
            start_date=date(2025, 1, 1),
            initial_term_months=24,
            initial_term_end_date=date(2027, 1, 1),
            renewal_type="monthly_rolling",
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        db.session.add_all([c_fixed, c_rolling])
        db.session.commit()
        fixed_id = c_fixed.id
        rolling_id = c_rolling.id

    client.post("/login", data={"username": "streamline_user", "password": "pass123"}, follow_redirects=True)

    # 1. View fixed-term contract (German)
    resp_fixed = client.get(f"/contracts/{fixed_id}?lang=de")
    assert resp_fixed.status_code == 200
    html_fixed = resp_fixed.get_data(as_text=True)

    # Must contain "Feste Laufzeit" badge and "Keine Kündigung erforderlich"
    assert "Feste Laufzeit" in html_fixed
    assert "Keine Kündigung erforderlich" in html_fixed
    # Must contain human-readable days duration (25 Jahre)
    assert "25 Jahre" in html_fixed
    # Must NOT render the rollover 4-box row
    assert "Monatlich rollierend" not in html_fixed
    assert "Feste Periode" not in html_fixed

    # 2. View rolling contract (German)
    resp_rolling = client.get(f"/contracts/{rolling_id}?lang=de")
    assert resp_rolling.status_code == 200
    html_rolling = resp_rolling.get_data(as_text=True)

    # Rolling contract MUST display the rollover row with initial term and rolling renewal
    assert "24 Monate" in html_rolling
    assert "Monatlich rollierend" in html_rolling


def test_fixed_period_renewal_cost_summary_view(client, app):
    """Verify that a contract with expired initial term and fixed period renewal displays period commitment and VVG notice."""
    with app.app_context():
        user = User(
            username="kfz_user",
            hashed_password=generate_password_hash("pass123"),
            currency="EUR",
        )
        db.session.add(user)
        db.session.commit()

        c_kfz = Contract(
            user_id=user.id,
            title="KFZ Versicherung Allianz",
            category="Versicherung",
            amount=509.27,
            currency="EUR",
            frequency=Frequency.yearly,
            start_date=date(2021, 1, 1),
            billing_anchor_date=date(2021, 1, 1),
            initial_term_months=12,
            initial_term_end_date=date(2021, 12, 31),
            renewal_type="fixed_period",
            renewal_period_months=12,
            cancellation_target_period="end_of_year",
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            status=ContractStatus.active,
        )
        # Add price history
        p1 = PriceEntry(
            contract=c_kfz,
            amount=509.27,
            valid_from=date(2021, 1, 1),
            note="Initialer Beitrag",
        )
        db.session.add_all([c_kfz, p1])
        db.session.commit()
        kfz_id = c_kfz.id

    client.post("/login", data={"username": "kfz_user", "password": "pass123"}, follow_redirects=True)
    resp = client.get(f"/contracts/{kfz_id}?lang=de")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Must show Aktuelle Periodenbindung instead of Garantierte Mindestbindung
    assert "Aktuelle Periodenbindung" in html
    assert "509.27 EUR" in html
    # Must show Feste 12-Monats-Bindung badge
    assert "Feste 12-Monats-Bindung" in html
    # Must NOT show "Vertrag rolliert"
    assert "Vertrag rolliert" not in html
    # Must show clean annual subtitle instead of "... danach"
    assert "Künftige 12 Monate" in html
    assert "Hochgerechnet p. a. danach" not in html
    # Must show VVG notice in price history section
    assert "§ 40 VVG" in html
    assert "Sonderkündigungsrecht" in html

    # Current commitment period checks for KFZ (past initial term)
    # Old historical 2021 date must NOT appear under open-ended end date:
    assert "Erstbindung erfüllt am 31.12.2021" not in html
    # Under Unlimited, no duplicate period text:
    assert "Aktuelle Periode: bis" not in html
    # Box 1 must have compact Erfüllt badge without long overflow:
    assert "Erfüllt" in html
    # Box 4 must show Nächstmögliches Vertragsende and 31.12.2026:
    assert "Nächstmögliches Vertragsende" in html
    assert "31.12.2026" in html


def test_contract_detail_active_initial_term_display(client, app):
    from datetime import date, timedelta
    with app.app_context():
        user = User(
            username="active_user",
            hashed_password=generate_password_hash("pass123"),
            currency="EUR",
        )
        db.session.add(user)
        db.session.commit()

        # Active contract in initial term (e.g. 24 months, ends in 180 days)
        future_end = date.today() + timedelta(days=180)
        c_active = Contract(
            user_id=user.id,
            title="Telekom Handyvertrag",
            category="Mobilfunk",
            amount=49.99,
            currency="EUR",
            frequency=Frequency.monthly,
            start_date=date.today() - timedelta(days=180),
            initial_term_months=12,
            initial_term_end_date=future_end,
            renewal_type="monthly_rolling",
            status=ContractStatus.active,
        )
        db.session.add(c_active)
        db.session.commit()
        cid = c_active.id

    client.post("/login", data={"username": "active_user", "password": "pass123"}, follow_redirects=True)
    resp = client.get(f"/contracts/{cid}?lang=de")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Box 1: Compact Aktiv badge
    assert "Aktiv" in html

    # Box 4: Nächstmögliches Vertragsende with initial term end date and badge
    assert "Nächstmögliches Vertragsende" in html
    assert future_end.strftime("%d.%m.%Y") in html

    # No duplicate text under Unbefristet
    assert "Erstbindung: bis" not in html
    assert "Telekom Handyvertrag" in html


def test_contract_creation_with_price_tiers(client, app):
    """Test contract creation with promotional price tiers (e.g. DAZN 24m @ 24.99 then 44.99)."""
    import json
    with app.app_context():
        user = User(username="tier_create_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

    client.post("/login", data={"username": "tier_create_user", "password": "pass123"}, follow_redirects=True)

    tiers = [
        {"months": 24, "amount": 24.99, "note": "Rabattphase (24 Monate)"},
        {"months": None, "amount": 44.99, "note": "Standardpreis nach Mindestlaufzeit"},
    ]

    resp = client.post("/contracts", data={
        "category": "Streaming",
        "title": "DAZN 2-Jahres-Abo",
        "amount": "24.99",
        "currency": "EUR",
        "frequency": "monthly",
        "start_date": "2026-01-01",
        "initial_term_months": 24,
        "renewal_type": "monthly_rolling",
        "cancellation_notice_amount": 1,
        "cancellation_notice_unit": "months",
        "price_tiers_json": json.dumps(tiers),
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        c = Contract.query.filter_by(title="DAZN 2-Jahres-Abo").first()
        assert c is not None
        assert len(c.price_history) == 2

        p_promo = next(p for p in c.price_history if p.valid_to is not None)
        p_std = next(p for p in c.price_history if p.valid_to is None)

        assert p_promo.amount == 24.99
        assert p_promo.valid_from == datetime.date(2026, 1, 1)
        assert p_promo.valid_to == datetime.date(2027, 12, 31)

        assert p_std.amount == 44.99
        assert p_std.valid_from == datetime.date(2028, 1, 1)


def test_contract_extension_with_price_tiers(client, app):
    """Test premature contract extension with multi-tier promotional pricing."""
    import json
    with app.app_context():
        user = User(username="tier_ext_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Internet & Mobilfunk",
            title="Vodafone Cable VVL",
            amount=39.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=datetime.date(2025, 1, 1),
            initial_term_months=24,
            initial_term_end_date=datetime.date(2026, 12, 31),
            renewal_type="monthly_rolling",
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    client.post("/login", data={"username": "tier_ext_user", "password": "pass123"}, follow_redirects=True)

    # Extend by 24 months with 6 months @ 19.99, 18 months @ 29.99, then 49.99 ongoing
    vvl_tiers = [
        {"months": 6, "amount": 19.99, "note": "VVL Rabattphase 1"},
        {"months": 18, "amount": 29.99, "note": "VVL Rabattphase 2"},
        {"months": None, "amount": 49.99, "note": "Standardpreis nach VVL"},
    ]

    resp = client.post(f"/contracts/{cid}/extend", data={
        "extension_months": "24",
        "extension_start_mode": "append",
        "price_tiers_json": json.dumps(vvl_tiers),
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, cid)
        assert c.initial_term_end_date == datetime.date(2028, 12, 31)
        # Should have the 3 VVL tiers
        vvl_entries = sorted([p for p in c.price_history if "VVL" in (p.note or "") or "Standardpreis" in (p.note or "")], key=lambda x: x.valid_from)
        assert len(vvl_entries) == 3

        assert vvl_entries[0].amount == 19.99
        assert vvl_entries[0].valid_from == datetime.date(2026, 12, 31)
        assert vvl_entries[1].amount == 29.99
        assert vvl_entries[2].amount == 49.99


def test_contract_modals_render_price_tiers_and_extension_buttons(client, app):
    """Test that contract modal and extension modal render the new UI elements in the DOM."""
    with app.app_context():
        user = User(username="ui_tier_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Streaming",
            title="DAZN Test",
            amount=24.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=datetime.date(2026, 1, 1),
            initial_term_months=24,
            initial_term_end_date=datetime.date(2027, 12, 31),
            renewal_type="monthly_rolling",
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    client.post("/login", data={"username": "ui_tier_user", "password": "pass123"}, follow_redirects=True)

    # 1. Test contracts index modal
    resp_index = client.get("/contracts?lang=de")
    assert resp_index.status_code == 200
    html_index = resp_index.get_data(as_text=True)
    assert "price-tier-component" in html_index
    assert "toggle-price-tiers-btn" in html_index
    assert "Befristete Rabattstaffel" in html_index
    assert "price-tiers-json-input" in html_index

    # 2. Test contract detail extension modal
    resp_detail = client.get(f"/contracts/{cid}?lang=de")
    assert resp_detail.status_code == 200
    html_detail = resp_detail.get_data(as_text=True)
    assert "extendContractModal" in html_detail
    assert "extension-period-btn-group" in html_detail
    assert "extMonths12" in html_detail
    assert "extMonths24" in html_detail
    assert "extMonthsCustom" in html_detail
    assert "Freies Datum" in html_detail
    assert "custom_end_date" in html_detail
    assert "custom_date" in html_detail
    assert "custom_start_date" in html_detail
    assert "single-amount-wrapper" in html_detail


def test_contract_extension_with_custom_start_date(client, app):
    """Test extending a contract with a custom start date in the future."""
    with app.app_context():
        user = User(username="custom_start_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Internet",
            title="Custom Start DSL",
            amount=39.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=datetime.date(2025, 1, 1),
            initial_term_months=24,
            initial_term_end_date=datetime.date(2026, 12, 31),
            renewal_type="monthly_rolling",
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    client.post("/login", data={"username": "custom_start_user", "password": "pass123"}, follow_redirects=True)

    # Extend with custom start date: 2026-11-01 for 24 months, new amount 44.99
    resp = client.post(f"/contracts/{cid}/extend", data={
        "extension_months": "24",
        "extension_start_mode": "custom_date",
        "custom_start_date": "2026-11-01",
        "new_amount": "44.99",
        "note": "Tarifwechsel vereinbart ab 01.11.2026",
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "erfolgreich um 24 Monate" in html

    with app.app_context():
        c = db.session.get(Contract, cid)
        # 24 months from 2026-11-01 is 2028-11-01 (exact target period)
        assert c.initial_term_end_date == datetime.date(2028, 11, 1)

        # Price entry should start at 2026-11-01
        latest_price = [p for p in c.price_history if p.amount == 44.99]
        assert len(latest_price) == 1
        assert latest_price[0].valid_from == datetime.date(2026, 11, 1)


def test_contract_extension_failsafe_empty_custom_start_date(client, app):
    """Test Failsafe 1: Choosing custom_date mode without providing a date is rejected."""
    with app.app_context():
        user = User(username="empty_date_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Mobilfunk",
            title="Telekom Allnet",
            amount=29.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=datetime.date(2025, 1, 1),
            initial_term_months=24,
            initial_term_end_date=datetime.date(2026, 12, 31),
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    client.post("/login", data={"username": "empty_date_user", "password": "pass123"}, follow_redirects=True)

    resp = client.post(f"/contracts/{cid}/extend", data={
        "extension_months": "24",
        "extension_start_mode": "custom_date",
        "custom_start_date": "",
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Bitte gib ein g" in html and "ltiges Startdatum" in html

    with app.app_context():
        c = db.session.get(Contract, cid)
        # Unchanged
        assert c.initial_term_end_date == datetime.date(2026, 12, 31)


def test_contract_extension_failsafe_end_before_start(client, app):
    """Test Failsafe 2: Choosing custom end date <= custom start date is rejected."""
    with app.app_context():
        user = User(username="invalid_range_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Streaming",
            title="Video Portal",
            amount=9.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=datetime.date(2025, 1, 1),
            initial_term_months=12,
            initial_term_end_date=datetime.date(2025, 12, 31),
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    client.post("/login", data={"username": "invalid_range_user", "password": "pass123"}, follow_redirects=True)

    # Submit custom_end_date (2026-06-01) <= custom_start_date (2026-07-01)
    resp = client.post(f"/contracts/{cid}/extend", data={
        "extension_months": "custom",
        "custom_end_date": "2026-06-01",
        "extension_start_mode": "custom_date",
        "custom_start_date": "2026-07-01",
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Das neue Mindestende muss nach dem Startdatum der Verl" in html

    with app.app_context():
        c = db.session.get(Contract, cid)
        # Unchanged
        assert c.initial_term_end_date == datetime.date(2025, 12, 31)


def test_contract_extension_with_tiers_strictly_ignores_single_amount(client, app):
    """Test that when price tiers are submitted, any single new_amount value is completely ignored."""
    with app.app_context():
        user = User(username="strict_tier_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        c = Contract(
            user_id=user.id,
            category="Streaming",
            title="Netflix Tier Test",
            amount=17.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=datetime.date(2025, 1, 1),
            initial_term_months=12,
            initial_term_end_date=datetime.date(2025, 12, 31),
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

    client.post("/login", data={"username": "strict_tier_user", "password": "pass123"}, follow_redirects=True)

    tiers = [
        {"months": 12, "amount": 12.99, "note": "Rabattjahr"},
        {"months": None, "amount": 19.99, "note": "Folgepreis regulär"},
    ]

    # Submit BOTH price_tiers_json AND new_amount (which might happen if not disabled)
    resp = client.post(f"/contracts/{cid}/extend", data={
        "extension_months": "12",
        "extension_start_mode": "append",
        "new_amount": "99.99",
        "price_tiers_json": json.dumps(tiers),
    }, follow_redirects=True)

    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, cid)
        # Verify 99.99 is nowhere in price history
        amounts = [p.amount for p in c.price_history]
        assert 99.99 not in amounts
        assert 12.99 in amounts
        assert 19.99 in amounts

        # Verify system note does not mention 99.99
        notes_content = [n.content for n in c.notes_list]
        combined_notes = " ".join(notes_content)
        assert "99.99" not in combined_notes
        assert "Preisstaffel mit 2 Stufen" in combined_notes










