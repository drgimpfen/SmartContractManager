import datetime
import pytest
from werkzeug.security import generate_password_hash
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


