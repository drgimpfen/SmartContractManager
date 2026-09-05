import pytest
from app.models import User
from werkzeug.security import generate_password_hash


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
