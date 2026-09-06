from datetime import date, timedelta
from flask_login import login_user
from werkzeug.security import generate_password_hash
import pytest

from app import db
from app.models import User, Provider, Contract, ContractStatus, Frequency


def test_dashboard_unauthenticated_redirect(client):
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_dashboard_empty_state(app, client):
    with app.app_context():
        user = User(
            username="empty_user",
            hashed_password=generate_password_hash("password123"),
            currency="EUR",
        )
        db.session.add(user)
        db.session.commit()

    # Login
    client.post('/login', data={'username': 'empty_user', 'password': 'password123'}, follow_redirects=True)

    resp = client.get('/')
    assert resp.status_code == 200
    assert b'id="budgetValueDisplay"' in resp.data
    assert b'0.00 EUR' in resp.data
    # Empty contracts state: canvases should not be rendered
    assert b'<canvas id="cashflowChart"' not in resp.data
    assert b'<canvas id="categoryChart"' not in resp.data


def test_dashboard_populated_with_financial_metrics_and_charts(app, client, mocker):
    with app.app_context():
        user = User(
            username="finance_user",
            hashed_password=generate_password_hash("password123"),
            currency="EUR",
        )
        db.session.add(user)
        db.session.flush()

        prov = Provider(user_id=user.id, name="Telekom Provider")
        db.session.add(prov)
        db.session.flush()

        # Contract 1: Monthly active, 45 EUR
        c1 = Contract(
            user_id=user.id,
            provider_id=prov.id,
            category="Internet",
            status=ContractStatus.active,
            contract_number="TEL-001",
            amount=45.0,
            currency="EUR",
            frequency=Frequency.monthly,
            billing_anchor_date=date(2026, 1, 1),
            cancellation_notice_amount=1,
            cancellation_notice_unit="months",
            end_date=date(2028, 1, 1), # far future
        )

        # Contract 2: Quarterly active, 90 EUR (30 EUR/mo)
        c2 = Contract(
            user_id=user.id,
            provider_id=prov.id,
            category="Insurance",
            status=ContractStatus.active,
            contract_number="INS-002",
            amount=90.0,
            currency="EUR",
            frequency=Frequency.quarterly,
            billing_anchor_date=date(2026, 1, 15),
            cancellation_notice_amount=30,
            cancellation_notice_unit="days",
            end_date=date.today() + timedelta(days=10), # Critical deadline!
        )

        # Contract 3: Missing cancellation notice
        c3 = Contract(
            user_id=user.id,
            provider_id=prov.id,
            title="Fitness Club",
            category="Gym",
            status=ContractStatus.active,
            contract_number="GYM-003",
            amount=20.0,
            currency="EUR",
            frequency=Frequency.monthly,
            billing_anchor_date=date(2026, 1, 1),
            renewal_type="monthly_rolling",
            cancellation_notice_amount=0, # missing notice!
        )

        # Contract 4: Fixed-term contract without notice period (should not be in missing notice)
        c4 = Contract(
            user_id=user.id,
            provider_id=prov.id,
            title="Life Insurance",
            category="Insurance",
            status=ContractStatus.active,
            contract_number="LIFE-004",
            amount=50.0,
            currency="EUR",
            frequency=Frequency.monthly,
            billing_anchor_date=date(2026, 1, 1),
            end_date=date(2052, 6, 30),
            renewal_type="none",
            cancellation_notice_amount=0,
        )

        db.session.add_all([c1, c2, c3, c4])
        db.session.commit()
        c2_id = c2.id
        c3_id = c3.id

    # Login
    client.post('/login', data={'username': 'finance_user', 'password': 'password123'}, follow_redirects=True)

    resp = client.get('/')
    assert resp.status_code == 200

    html = resp.data.decode('utf-8')

    # Monthly budget: 45 + 30 + 20 + 50 = 145.00 EUR
    assert '145.00 EUR' in html
    assert 'budgetValueDisplay' in html
    assert 'budgetLabelDisplay' in html

    # Option A toggle buttons
    assert 'budget-toggle-btn' in html

    # Charts rendered
    assert 'id="cashflowChart"' in html
    assert 'id="categoryChart"' in html
    assert ('Committed Obligations' in html or 'Verbindliche Verpflichtungen' in html)
    assert ('Flexible Payments' in html or 'Flexible Zahlungen' in html)

    # Critical reminders section has INS-002 and link
    assert 'INS-002' in html
    assert f'href="/contracts/{c2_id}"' in html

    # Missing notice section has GYM-003, title Fitness Club, link, and excludes fixed-term LIFE-004
    assert 'GYM-003' in html
    assert 'Fitness Club' in html
    assert f'href="/contracts/{c3_id}"' in html
    assert 'LIFE-004' not in html

    # Verify modular contract creation modal component is rendered
    assert 'id="addContractModal"' in html
    assert 'name="title"' in html
    assert 'combobox-container' in html
    assert 'contract-term-group' in html
    assert 'name="tags"' in html
