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
        'status': 'archived',
        'tags': 'TV, Entertainment',
        'notes': 'Canceled due to price increase',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, c_id)
        assert c.category == 'Premium Streaming'
        assert c.frequency == Frequency.yearly
        assert c.status == ContractStatus.archived
        assert c.notes == 'Canceled due to price increase'
        assert len(c.tags) == 2


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
