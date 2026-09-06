import pytest
from app.models import User
from werkzeug.security import generate_password_hash

def test_login_successful(client, app):
    from app import db
    with app.app_context():
        hashed_pw = generate_password_hash("password123")
        user = User(username="testuser", hashed_password=hashed_pw)
        db.session.add(user)
        db.session.commit()

    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'password123'
    }, follow_redirects=True)
    
    assert response.status_code == 200

def test_login_failure(client, app):
    response = client.post('/login', data={
        'username': 'wronguser',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Invalid username or password' in response.data

def test_register_successful(client, app):
    response = client.post('/register', data={
        'username': 'newuser',
        'password': 'password123'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    from app import db
    with app.app_context():
        user = User.query.filter_by(username='newuser').first()
        assert user is not None


def test_login_required_redirect_and_localized_flash(client):
    # Unauthenticated access with default locale (en)
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    assert 'Please log in to access this page.' in response.get_data(as_text=True)
    assert 'alert-info' in response.get_data(as_text=True)

    # With German language cookie or header
    client.set_cookie('lang', 'de')
    response_de = client.get('/', follow_redirects=True)
    assert response_de.status_code == 200
    assert 'Bitte melden Sie sich an, um auf diese Seite zuzugreifen.' in response_de.get_data(as_text=True)
    assert 'alert-info' in response_de.get_data(as_text=True)
