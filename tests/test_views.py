import datetime
import pytest
from werkzeug.security import generate_password_hash
from app.models import User, Contract, ContractStatus, Frequency


def test_unauthenticated_redirect(client):
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_login_page_renders_mobile_elements(client):
    response = client.get('/login')
    assert response.status_code == 200
    # Must contain mobile viewport meta tag
    assert b'name="viewport"' in response.data
    # Must contain Bootstrap 5 and Bootstrap Icons
    assert b'bootstrap.min.css' in response.data
    assert b'bootstrap-icons' in response.data
    # Must contain form fields
    assert b'name="username"' in response.data
    assert b'name="password"' in response.data
    # Ensure no sidebar exists on login page
    assert b'sidebarOffcanvas' not in response.data


def test_language_switch_endpoint(client):
    # Testing /set-language/de
    response = client.get('/set-language/de?next=/login', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'] == '/login'
    cookies = response.headers.getlist('Set-Cookie')
    assert any('lang=de' in c for c in cookies)


def test_authenticated_dashboard_renders_top_navbar(client, app):
    from app import db
    with app.app_context():
        user = User(username='viewuser', hashed_password=generate_password_hash('securepassword'))
        db.session.add(user)
        db.session.commit()

    # Login with valid length password
    login_resp = client.post('/login', data={'username': 'viewuser', 'password': 'securepassword'}, follow_redirects=True)
    assert login_resp.status_code == 200

    # Access dashboard
    response = client.get('/')
    assert response.status_code == 200
    # Verify top navbar exists with mobile-first hamburger toggle
    assert b'id="mainNavbar"' in response.data
    assert b'navbar-expand-lg' in response.data
    assert b'data-bs-target="#mainNavbar"' in response.data
    # Verify navigation links
    assert b'/contracts' in response.data
    assert b'/providers' in response.data
    # Verify username rendered in user menu
    assert b'viewuser' in response.data
    # Ensure no sidebar is present (Option 1)
    assert b'sidebarOffcanvas' not in response.data


def test_contracts_page_renders_comboboxes(client, app):
    from app import db
    with app.app_context():
        user = User(username='combouser', hashed_password=generate_password_hash('pass123'))
        db.session.add(user)
        db.session.commit()
        contract = Contract(
            user_id=user.id,
            title='Netflix Standard',
            category='Streaming',
            payment_method='PayPal',
            amount=12.99,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            billing_anchor_date=datetime.date(2025, 1, 1),
        )
        db.session.add(contract)
        db.session.commit()

    client.post('/login', data={'username': 'combouser', 'password': 'pass123'}, follow_redirects=True)
    resp = client.get('/contracts')
    assert resp.status_code == 200
    # Verify seamless combobox inputs exist
    assert b'class="form-control pe-5 combobox-input"' in resp.data
    assert b'name="category"' in resp.data
    assert b'name="payment_method"' in resp.data
    # Verify integrated chevron toggle buttons exist
    assert b'combobox-toggle' in resp.data
    assert b'bi-chevron-down' in resp.data
    assert b'combobox-container' in resp.data
    # Verify user entries and suggestions are in the dropdown menus
    assert b'class="dropdown-item combobox-select-item"' in resp.data
    assert b'combobox.js' in resp.data
    # Verify obsolete datalist elements are removed
    assert b'<datalist id="categoryOptions">' not in resp.data
    assert b'<datalist id="paymentMethodOptions">' not in resp.data


def test_contract_detail_renders_comboboxes(client, app):
    from app import db
    with app.app_context():
        user = User(username='combouser2', hashed_password=generate_password_hash('pass123'))
        db.session.add(user)
        db.session.commit()
        contract = Contract(
            user_id=user.id,
            title='Spotify Premium',
            category='Music',
            payment_method='Kreditkarte',
            amount=9.99,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            billing_anchor_date=datetime.date(2025, 1, 1),
        )
        db.session.add(contract)
        db.session.commit()
        cid = contract.id

    client.post('/login', data={'username': 'combouser2', 'password': 'pass123'}, follow_redirects=True)
    resp = client.get(f'/contracts/{cid}')
    assert resp.status_code == 200
    assert b'class="form-control pe-5 combobox-input"' in resp.data
    assert b'name="category"' in resp.data
    assert b'name="payment_method"' in resp.data
    assert b'combobox-toggle' in resp.data
    assert b'bi-chevron-down' in resp.data
    assert b'combobox-container' in resp.data
    assert b'Music' in resp.data
    assert b'Kreditkarte' in resp.data
    assert b'<datalist id="categoryOptions">' not in resp.data
    assert b'<datalist id="paymentMethodOptions">' not in resp.data


def test_contracts_page_category_filtering_and_split_columns(client, app):
    from app import db
    with app.app_context():
        user = User(username='catuser', hashed_password=generate_password_hash('pass123'))
        db.session.add(user)
        db.session.commit()
        c1 = Contract(
            user_id=user.id,
            title='Disney Plus VIP',
            category='Streaming',
            amount=17.99,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            billing_anchor_date=datetime.date(2025, 1, 1),
        )
        c2 = Contract(
            user_id=user.id,
            title='HUK Coburg',
            category='Versicherung',
            amount=45.00,
            currency='EUR',
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            billing_anchor_date=datetime.date(2025, 1, 1),
        )
        db.session.add_all([c1, c2])
        db.session.commit()

    client.post('/login', data={'username': 'catuser', 'password': 'pass123'}, follow_redirects=True)

    # 1. Unfiltered request should display both and category dropdown
    resp = client.get('/contracts')
    assert resp.status_code == 200
    assert b'Disney Plus VIP' in resp.data
    assert b'HUK Coburg' in resp.data
    assert b'name="category"' in resp.data
    assert b'<option value="Streaming"' in resp.data
    assert b'<option value="Versicherung"' in resp.data

    # 2. Filter by category=Streaming
    resp_stream = client.get('/contracts?category=Streaming')
    assert resp_stream.status_code == 200
    assert b'Disney Plus VIP' in resp_stream.data
    assert b'HUK Coburg' not in resp_stream.data

    # 3. Filter by category=Versicherung
    resp_vers = client.get('/contracts?category=Versicherung')
    assert resp_vers.status_code == 200
    assert b'HUK Coburg' in resp_vers.data
    assert b'Disney Plus VIP' not in resp_vers.data


