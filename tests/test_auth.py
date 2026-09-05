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
