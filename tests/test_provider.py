import pytest
from werkzeug.security import generate_password_hash
from app.models import User, Provider


def test_create_provider_success(client, app):
    from app import db
    with app.app_context():
        user = User(username='provuser', hashed_password=generate_password_hash('password123'))
        db.session.add(user)
        db.session.commit()

    # Login
    client.post('/login', data={'username': 'provuser', 'password': 'password123'}, follow_redirects=True)

    # Post new provider
    response = client.post('/providers', data={
        'name': 'Telekom',
        'customer_number': 'CUST-12345',
        'email': 'support@telekom.de',
        'phone': '+4912345678',
        'website': 'https://telekom.de',
        'customer_portal': 'https://telekom.de/login',
        'cancel_url': 'https://telekom.de/kuendigung',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Telekom' in response.data

    with app.app_context():
        u = User.query.filter_by(username='provuser').first()
        prov = Provider.query.filter_by(user_id=u.id, name='Telekom').first()
        assert prov is not None
        assert prov.customer_number == 'CUST-12345'
        assert prov.email == 'support@telekom.de'


def test_create_provider_unauthenticated(client):
    response = client.post('/providers', data={'name': 'HackerCorp'}, follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_list_providers_isolated_by_user(client, app):
    from app import db
    with app.app_context():
        u1 = User(username='user_alice', hashed_password=generate_password_hash('password123'))
        u2 = User(username='user_bob', hashed_password=generate_password_hash('password123'))
        db.session.add_all([u1, u2])
        db.session.commit()

        p1 = Provider(user_id=u1.id, name='AliceProvider')
        p2 = Provider(user_id=u2.id, name='BobSecretProvider')
        db.session.add_all([p1, p2])
        db.session.commit()

    # Login as Alice
    client.post('/login', data={'username': 'user_alice', 'password': 'password123'}, follow_redirects=True)

    # Alice visits /providers
    resp = client.get('/providers')
    assert resp.status_code == 200
    assert b'AliceProvider' in resp.data
    assert b'BobSecretProvider' not in resp.data


def test_edit_provider(client, app):
    from app import db
    with app.app_context():
        u = User(username='edit_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        p = Provider(user_id=u.id, name='Old Provider Name', customer_number='OLD-123')
        db.session.add(p)
        db.session.commit()
        p_id = p.id

    client.post('/login', data={'username': 'edit_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/providers/{p_id}/edit', data={
        'name': 'New Provider Name',
        'customer_number': 'NEW-456',
        'address': 'Musterstr. 123, Berlin',
        'email': 'new@provider.de',
        'phone': '030123456',
        'website': 'https://provider.de',
        'customer_portal': 'https://portal.provider.de',
        'cancel_url': 'https://provider.de/cancel',
    }, follow_redirects=True)

    assert resp.status_code == 200
    with app.app_context():
        prov = db.session.get(Provider, p_id)
        assert prov.name == 'New Provider Name'
        assert prov.customer_number == 'NEW-456'
        assert prov.address == 'Musterstr. 123, Berlin'
        assert prov.email == 'new@provider.de'


def test_edit_provider_forbidden_for_other_user(client, app):
    from app import db
    with app.app_context():
        u1 = User(username='user_1', hashed_password=generate_password_hash('pass123'))
        u2 = User(username='user_2', hashed_password=generate_password_hash('pass123'))
        db.session.add_all([u1, u2])
        db.session.commit()
        p2 = Provider(user_id=u2.id, name='User2 Private Provider')
        db.session.add(p2)
        db.session.commit()
        p2_id = p2.id

    client.post('/login', data={'username': 'user_1', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/providers/{p2_id}/edit', data={'name': 'Hacked Provider'})
    assert resp.status_code == 404

    with app.app_context():
        prov = db.session.get(Provider, p2_id)
        assert prov.name == 'User2 Private Provider'


def test_delete_provider(client, app):
    from app import db
    with app.app_context():
        u = User(username='del_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        p = Provider(user_id=u.id, name='Provider to Delete')
        db.session.add(p)
        db.session.commit()
        p_id = p.id

    client.post('/login', data={'username': 'del_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/providers/{p_id}/delete', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Provider, p_id) is None


def test_delete_provider_forbidden_for_other_user(client, app):
    from app import db
    with app.app_context():
        u1 = User(username='del_u1', hashed_password=generate_password_hash('pass123'))
        u2 = User(username='del_u2', hashed_password=generate_password_hash('pass123'))
        db.session.add_all([u1, u2])
        db.session.commit()
        p2 = Provider(user_id=u2.id, name='Provider U2')
        db.session.add(p2)
        db.session.commit()
        p2_id = p2.id

    client.post('/login', data={'username': 'del_u1', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/providers/{p2_id}/delete')
    assert resp.status_code == 404

    with app.app_context():
        assert db.session.get(Provider, p2_id) is not None


def test_provider_detail_view_success(client, app):
    from app import db
    with app.app_context():
        u = User(username='prov_det_user', hashed_password=generate_password_hash('pass123'), currency='EUR')
        db.session.add(u)
        db.session.commit()
        p = Provider(
            user_id=u.id,
            name='Vodafone Deutschland',
            customer_number='VF-98765',
            email='service@vodafone.de',
            phone='+498001721212',
            address='Ferdinand-Braun-Platz 1, 40549 Düsseldorf',
            customer_portal='https://vodafone.de/meinvodafone',
            cancel_url='https://vodafone.de/kuendigung',
        )
        db.session.add(p)
        db.session.commit()
        p_id = p.id

    client.post('/login', data={'username': 'prov_det_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.get(f'/providers/{p_id}')
    assert resp.status_code == 200
    assert b'Vodafone Deutschland' in resp.data
    assert b'VF-98765' in resp.data
    assert b'service@vodafone.de' in resp.data
    assert b'Ferdinand-Braun-Platz 1' in resp.data
    assert b'https://vodafone.de/meinvodafone' in resp.data


def test_provider_detail_user_isolation(client, app):
    from app import db
    with app.app_context():
        u1 = User(username='u1_detail', hashed_password=generate_password_hash('pass123'))
        u2 = User(username='u2_detail', hashed_password=generate_password_hash('pass123'))
        db.session.add_all([u1, u2])
        db.session.commit()
        p2 = Provider(user_id=u2.id, name='Secret Provider U2')
        db.session.add(p2)
        db.session.commit()
        p2_id = p2.id

    client.post('/login', data={'username': 'u1_detail', 'password': 'pass123'}, follow_redirects=True)
    resp = client.get(f'/providers/{p2_id}')
    assert resp.status_code == 404


def test_provider_detail_with_contracts_and_financials(client, app):
    from app import db
    from app.models import Contract, ContractStatus, Frequency
    from datetime import date

    with app.app_context():
        u = User(username='prov_fin_user', hashed_password=generate_password_hash('pass123'), currency='EUR')
        db.session.add(u)
        db.session.commit()
        p = Provider(user_id=u.id, name='Telekom Deutschland')
        db.session.add(p)
        db.session.commit()
        p_id = p.id

        c1 = Contract(
            user_id=u.id,
            provider_id=p_id,
            category='DSL Internet',
            contract_number='DSL-111',
            status=ContractStatus.active,
            amount=39.99,
            currency='EUR',
            frequency=Frequency.monthly,
            billing_anchor_date=date(2026, 1, 1),
            start_date=date(2026, 1, 1),
        )
        c2 = Contract(
            user_id=u.id,
            provider_id=p_id,
            category='Mobilfunk 5G',
            contract_number='MOB-222',
            status=ContractStatus.active,
            amount=20.00,
            currency='EUR',
            frequency=Frequency.monthly,
            billing_anchor_date=date(2026, 1, 1),
            start_date=date(2026, 1, 1),
        )
        c3 = Contract(
            user_id=u.id,
            provider_id=p_id,
            category='Altes Festnetz',
            contract_number='OLD-333',
            status=ContractStatus.canceled,
            amount=15.00,
            currency='EUR',
            frequency=Frequency.monthly,
        )
        db.session.add_all([c1, c2, c3])
        db.session.commit()

    client.post('/login', data={'username': 'prov_fin_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.get(f'/providers/{p_id}')
    assert resp.status_code == 200
    assert b'DSL Internet' in resp.data
    assert b'Mobilfunk 5G' in resp.data
    assert b'Altes Festnetz' in resp.data
    # Monthly cost: 39.99 + 20.00 = 59.99 EUR
    assert b'59.99' in resp.data


def test_provider_detail_edit_redirect(client, app):
    from app import db
    with app.app_context():
        u = User(username='prov_redirect_user', hashed_password=generate_password_hash('pass123'))
        db.session.add(u)
        db.session.commit()
        p = Provider(user_id=u.id, name='Pre-Edit Provider')
        db.session.add(p)
        db.session.commit()
        p_id = p.id

    client.post('/login', data={'username': 'prov_redirect_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/providers/{p_id}/edit?next=/providers/{p_id}', data={
        'name': 'Updated Provider Name',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert f'/providers/{p_id}' in resp.headers['Location']


def test_provider_detail_contains_add_contract_modal(client, app):
    from app import db
    with app.app_context():
        u = User(username='prov_modal_user', hashed_password=generate_password_hash('pass123'), currency='EUR')
        db.session.add(u)
        db.session.commit()
        p = Provider(user_id=u.id, name='O2 Telefonica')
        db.session.add(p)
        db.session.commit()
        p_id = p.id

    client.post('/login', data={'username': 'prov_modal_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.get(f'/providers/{p_id}')
    assert resp.status_code == 200
    assert b'id="addContractModal"' in resp.data
    # Verify the provider option is pre-selected
    expected_option = f'<option value="{p_id}" selected>'.encode('utf-8')
    assert expected_option in resp.data


def test_contract_creation_from_provider_detail_redirects_back(client, app):
    from app import db
    with app.app_context():
        u = User(username='prov_create_user', hashed_password=generate_password_hash('pass123'), currency='EUR')
        db.session.add(u)
        db.session.commit()
        p = Provider(user_id=u.id, name='1&1 Versatel')
        db.session.add(p)
        db.session.commit()
        p_id = p.id

    client.post('/login', data={'username': 'prov_create_user', 'password': 'pass123'}, follow_redirects=True)
    resp = client.post(f'/contracts?next=/providers/{p_id}', data={
        'category': 'Glasfaser Business',
        'provider_id': p_id,
        'amount': '89.90',
        'currency': 'EUR',
        'frequency': 'monthly',
        'status': 'active',
    }, follow_redirects=False)

    # Asserts 302 redirect back to the provider details page
    assert resp.status_code == 302
    assert f'/providers/{p_id}' in resp.headers['Location']

    # Follow redirect to verify contract is displayed in provider details
    follow_resp = client.get(f'/providers/{p_id}')
    assert follow_resp.status_code == 200
    assert b'Glasfaser Business' in follow_resp.data
    assert b'89.90' in follow_resp.data



