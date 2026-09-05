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

