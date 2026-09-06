import datetime
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Contract, PriceEntry, Frequency, ContractStatus
from app.services.contract_service import add_price_entry, sync_contract_prices, delete_price_entry, apply_price_tiers
from app.services.financial_service import FinancialService


def test_price_entry_dynamic_status_properties(app):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="pe_dyn_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        c = Contract(
            user_id=u.id,
            category="Music Streaming",
            amount=14.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()

        # Past price
        p_past = PriceEntry(
            contract_id=c.id,
            amount=9.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=100),
            valid_to=today - datetime.timedelta(days=1),
            is_current=False,
        )
        # Current price
        p_curr = PriceEntry(
            contract_id=c.id,
            amount=14.99,
            currency="EUR",
            valid_from=today,
            valid_to=today + datetime.timedelta(days=20),
            is_current=True,
        )
        # Future price
        p_fut = PriceEntry(
            contract_id=c.id,
            amount=19.99,
            currency="EUR",
            valid_from=today + datetime.timedelta(days=21),
            valid_to=None,
            is_current=False,
        )
        db.session.add_all([p_past, p_curr, p_fut])
        db.session.commit()

        # Test PriceEntry dynamic properties
        assert p_past.status == "past"
        assert p_past.is_past is True
        assert p_past.is_future is False
        assert p_past.is_currently_active is False

        assert p_curr.status == "current"
        assert p_curr.is_currently_active is True
        assert p_curr.is_future is False
        assert p_curr.is_past is False

        assert p_fut.status == "future"
        assert p_fut.is_future is True
        assert p_fut.is_currently_active is False
        assert p_fut.is_past is False

        # Test Contract dynamic properties
        assert c.current_price_entry.id == p_curr.id
        assert c.current_amount == 14.99
        assert c.current_currency == "EUR"
        assert len(c.upcoming_price_entries) == 1
        assert c.next_price_change.id == p_fut.id

        # Price delta: 19.99 vs 14.99 -> +5.00 (+33.3%)
        delta = c.price_delta_to_next
        assert delta is not None
        assert delta["diff_amount"] == 5.00
        assert delta["is_increase"] is True
        assert delta["is_reduction"] is False
        assert delta["diff_percent"] == 33.4 or delta["diff_percent"] == 33.3


def test_future_price_addition_preserves_current_price_flag(app):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="future_flag_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        c = Contract(
            user_id=u.id,
            category="Video Streaming",
            amount=44.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=today - datetime.timedelta(days=200),
            billing_anchor_date=today + datetime.timedelta(days=23),
        )
        db.session.add(c)
        db.session.commit()

        # Initial open-ended price entry
        p1 = PriceEntry(
            contract_id=c.id,
            amount=44.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=200),
            valid_to=None,
            is_current=True,
        )
        db.session.add(p1)
        db.session.commit()

        # Add future price starting in 23 days (e.g. 24.99 EUR) with auto_adjust=True
        future_start = today + datetime.timedelta(days=23)
        success, err, new_price = add_price_entry(
            contract=c,
            amount=24.99,
            currency="EUR",
            valid_from=future_start,
            valid_to=None,
            auto_adjust=True,
        )
        assert success is True
        assert new_price is not None

        # Re-query
        c = db.session.get(Contract, c.id)
        p1 = db.session.get(PriceEntry, p1.id)

        # p1 should now be capped to day before future_start, BUT STILL CURRENT TODAY!
        assert p1.valid_to == future_start - datetime.timedelta(days=1)
        assert p1.is_current is True
        assert c.amount == 44.99

        # new_price should not be current today
        assert new_price.is_current is False

        # Next billing is on future_start, so amount_on_next_billing is 24.99!
        assert c.amount_on_next_billing == 24.99


def test_financial_service_forward_12m_open_ended_projection(app):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="fin_proj_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        # Monthly contract billing on day today + 23 days
        anchor = today + datetime.timedelta(days=23)
        c = Contract(
            user_id=u.id,
            category="Fiber Internet",
            amount=44.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=today - datetime.timedelta(days=365),
            billing_anchor_date=anchor,
        )
        db.session.add(c)
        db.session.commit()

        # Current price until anchor - 1 day
        p_curr = PriceEntry(
            contract_id=c.id,
            amount=44.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=365),
            valid_to=anchor - datetime.timedelta(days=1),
            is_current=True,
        )
        # Future price starting on anchor
        p_fut = PriceEntry(
            contract_id=c.id,
            amount=24.99,
            currency="EUR",
            valid_from=anchor,
            valid_to=None,
            is_current=False,
        )
        db.session.add_all([p_curr, p_fut])
        db.session.commit()

        fin_service = FinancialService()
        summary = fin_service.calculate_contract_cost_summary(c, as_of=today)

        # In the next 12 months, all 12 payments fall on or after `anchor`
        # Each payment is 24.99 EUR, so annual_amount should be 12 * 24.99 = 299.88 EUR
        assert summary["is_fixed_term"] is False
        assert summary["annual_amount"] == round(12 * 24.99, 2)


def test_delete_price_entry_restores_preceding_range(app, client):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="del_pe_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()
        u_id = u.id

        c = Contract(
            user_id=u.id,
            category="Mobile Phone",
            amount=30.00,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()
        c_id = c.id

        # p1 was initially open-ended, then capped when future price was added
        fut_date = today + datetime.timedelta(days=30)
        p1 = PriceEntry(
            contract_id=c.id,
            amount=30.00,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=100),
            valid_to=fut_date - datetime.timedelta(days=1),
            is_current=True,
        )
        p2 = PriceEntry(
            contract_id=c.id,
            amount=40.00,
            currency="EUR",
            valid_from=fut_date,
            valid_to=None,
            is_current=False,
        )
        db.session.add_all([p1, p2])
        db.session.commit()
        p1_id = p1.id
        p2_id = p2.id

    client.post("/login", data={"username": "del_pe_user", "password": "pass123"}, follow_redirects=True)

    # Verify the delete modal is properly rendered in the HTML before deletion
    detail_resp = client.get(f"/contracts/{c_id}")
    assert detail_resp.status_code == 200
    detail_html = detail_resp.get_data(as_text=True)
    assert f'id="deletePriceModal{p2_id}"' in detail_html
    assert f'data-bs-target="#deletePriceModal{p2_id}"' in detail_html

    # Delete future price entry p2
    resp = client.post(f"/contracts/{c_id}/price-entry/{p2_id}/delete", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        c = db.session.get(Contract, c_id)
        p1 = db.session.get(PriceEntry, p1_id)
        p2 = db.session.get(PriceEntry, p2_id)

        assert p2 is None
        # p1 should have its valid_to restored to None because p2 was open-ended
        assert p1.valid_to is None
        assert p1.is_current is True
        assert c.amount == 30.00


def test_ui_renders_scheduled_price_banner_and_list_badge(app, client):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="ui_price_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        fut_date = today + datetime.timedelta(days=20)
        c = Contract(
            user_id=u.id,
            category="Game Pass",
            amount=16.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            billing_anchor_date=fut_date,
        )
        db.session.add(c)
        db.session.commit()
        c_id = c.id

        p1 = PriceEntry(
            contract_id=c.id,
            amount=16.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=60),
            valid_to=fut_date - datetime.timedelta(days=1),
            is_current=True,
        )
        p2 = PriceEntry(
            contract_id=c.id,
            amount=12.99,
            currency="EUR",
            valid_from=fut_date,
            valid_to=None,
            is_current=False,
            note="Rabattaktion",
        )
        db.session.add_all([p1, p2])
        db.session.commit()

    client.post("/login", data={"username": "ui_price_user", "password": "pass123"}, follow_redirects=True)

    # Check contract list view: should contain indicator badge
    resp_list = client.get("/contracts?lang=de")
    assert resp_list.status_code == 200
    assert b"12.99 EUR" in resp_list.data

    # Check contract detail view: should contain scheduled banner and badges
    resp_detail = client.get(f"/contracts/{c_id}?lang=de")
    assert resp_detail.status_code == 200
    assert "Geplante Preisanpassung".encode("utf-8") in resp_detail.data
    assert "F\xc3\xa4lliger Betrag: 12.99 EUR".encode("utf-8") in resp_detail.data or b"12.99 EUR" in resp_detail.data
    assert "Rabattaktion".encode("utf-8") in resp_detail.data


def test_get_contract_price_timeline_chart_data(app):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="chart_test_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        c = Contract(
            user_id=u.id,
            category="Cloud Storage",
            amount=44.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()

        fin_service = FinancialService()

        # Case 1: No explicit price_history entries
        data_single = fin_service.get_contract_price_timeline_chart(c)
        assert data_single["has_multiple"] is False
        assert data_single["currency"] == "EUR"
        assert len(data_single["amounts"]) == 1
        assert data_single["stats"]["min_amount"] == 44.99

        # Case 2: Multiple entries with past, current, and future
        p1 = PriceEntry(
            contract_id=c.id,
            amount=14.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=300),
            valid_to=today - datetime.timedelta(days=101),
            is_current=False,
            note="Einstiegspreis",
        )
        p2 = PriceEntry(
            contract_id=c.id,
            amount=44.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=100),
            valid_to=today + datetime.timedelta(days=20),
            is_current=True,
            note="Preisanpassung",
        )
        p3 = PriceEntry(
            contract_id=c.id,
            amount=24.99,
            currency="EUR",
            valid_from=today + datetime.timedelta(days=21),
            valid_to=None,
            is_current=False,
            note="Treuerabatt",
        )
        db.session.add_all([p1, p2, p3])
        db.session.commit()

        c = db.session.get(Contract, c.id)
        chart_data = fin_service.get_contract_price_timeline_chart(c)

        assert chart_data["has_multiple"] is True
        assert chart_data["has_future"] is True
        assert chart_data["amounts"] == [14.99, 44.99, 44.99, 24.99]
        assert chart_data["point_statuses"] == ["past", "current", "current", "future"]
        assert chart_data["is_today"] == [False, False, True, False]
        assert chart_data["notes"] == ["Einstiegspreis", "Preisanpassung", "", "Treuerabatt"]
        assert chart_data["stats"]["initial_amount"] == 14.99
        assert chart_data["stats"]["current_amount"] == 44.99
        assert chart_data["stats"]["min_amount"] == 14.99
        assert chart_data["stats"]["max_amount"] == 44.99
        assert chart_data["stats"]["change_since_start_amount"] == 30.00
        assert chart_data["stats"]["is_increase"] is True


def test_price_timeline_extends_to_today_for_open_ended_contracts(app):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="timeline_today_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        c = Contract(
            user_id=u.id,
            category="Mobile Data",
            amount=10.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()

        # Past price from 2022 to 2024
        p1 = PriceEntry(
            contract_id=c.id,
            amount=8.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=600),
            valid_to=today - datetime.timedelta(days=201),
            is_current=False,
            note="Initialer Preis",
        )
        # Current price since 200 days ago, ongoing (valid_to=None)
        p2 = PriceEntry(
            contract_id=c.id,
            amount=10.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=200),
            valid_to=None,
            is_current=True,
            note="Mehr Datenvolumen",
        )
        db.session.add_all([p1, p2])
        db.session.commit()

        fin_service = FinancialService()
        c = db.session.get(Contract, c.id)
        chart_data = fin_service.get_contract_price_timeline_chart(c)

        # Must have 3 points: past start, current start, and TODAY
        assert chart_data["has_multiple"] is True
        assert chart_data["has_future"] is False
        assert len(chart_data["amounts"]) == 3
        assert chart_data["amounts"] == [8.99, 10.99, 10.99]
        assert chart_data["point_statuses"] == ["past", "current", "current"]
        assert chart_data["is_today"] == [False, False, True]
        assert chart_data["labels"][2] == today.strftime("%d.%m.%Y")
        assert chart_data["stats"]["initial_amount"] == 8.99
        assert chart_data["stats"]["current_amount"] == 10.99

        # Case: Canceled contract ending in the past stops at contract.end_date
        past_end = today - datetime.timedelta(days=50)
        c.status = ContractStatus.canceled
        c.end_date = past_end
        db.session.commit()

        chart_data_canceled = fin_service.get_contract_price_timeline_chart(c)
        assert len(chart_data_canceled["amounts"]) == 3
        assert chart_data_canceled["amounts"] == [8.99, 10.99, 10.99]
        assert chart_data_canceled["labels"][2] == past_end.strftime("%d.%m.%Y")
        assert chart_data_canceled["is_today"][2] is False


def test_ui_renders_price_timeline_chart_and_kpis(app, client):
    today = datetime.date.today()
    with app.app_context():
        u = User(username="ui_chart_user", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        c = Contract(
            user_id=u.id,
            category="Netflix Streaming",
            amount=17.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()
        c_id = c.id

        p1 = PriceEntry(
            contract_id=c.id,
            amount=11.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=200),
            valid_to=today - datetime.timedelta(days=51),
            is_current=False,
            note="Starttarif",
        )
        p2 = PriceEntry(
            contract_id=c.id,
            amount=17.99,
            currency="EUR",
            valid_from=today - datetime.timedelta(days=50),
            valid_to=None,
            is_current=True,
            note="4K Upgrade",
        )
        db.session.add_all([p1, p2])
        db.session.commit()

    client.post("/login", data={"username": "ui_chart_user", "password": "pass123"}, follow_redirects=True)

    resp = client.get(f"/contracts/{c_id}?lang=de")
    assert resp.status_code == 200
    # Checks canvas and script data
    assert b"priceTimelineChart" in resp.data
    assert b"price-chart-data" in resp.data
    # Checks KPI stat labels
    assert "Startpreis" in resp.text
    assert "Höchstpreis" in resp.text
    assert "11.99 EUR" in resp.text
    assert "17.99 EUR" in resp.text


def test_apply_price_tiers_two_steps(app):
    """Test standard 2-step promotional model (e.g. 24 months @ 24.99, then 44.99 ongoing)."""
    with app.app_context():
        u = User(username="tier_user_1", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        start = datetime.date(2026, 1, 1)
        c = Contract(
            user_id=u.id,
            category="Streaming",
            title="DAZN 2-Jahresabo",
            amount=24.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=start,
        )
        db.session.add(c)
        db.session.commit()

        tiers = [
            {"months": 24, "amount": 24.99, "note": "Rabattphase (24 Monate)"},
            {"months": None, "amount": 44.99, "note": "Standardpreis nach Mindestlaufzeit"},
        ]

        entries = apply_price_tiers(c, base_date=start, tiers=tiers, currency="EUR")
        assert len(entries) == 2

        e1 = entries[0]
        assert e1.amount == 24.99
        assert e1.valid_from == datetime.date(2026, 1, 1)
        assert e1.valid_to == datetime.date(2027, 12, 31)

        e2 = entries[1]
        assert e2.amount == 44.99
        assert e2.valid_from == datetime.date(2028, 1, 1)
        assert e2.valid_to is None


def test_apply_price_tiers_three_steps(app):
    """Test 3-step promotional model (e.g. 6 months @ 9.99, 18 months @ 29.99, then 44.99 ongoing)."""
    with app.app_context():
        u = User(username="tier_user_2", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        start = datetime.date(2026, 3, 1)
        c = Contract(
            user_id=u.id,
            category="Internet & Mobilfunk",
            title="DSL 250",
            amount=9.99,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
            start_date=start,
        )
        db.session.add(c)
        db.session.commit()

        tiers = [
            {"months": 6, "amount": 9.99, "note": "Monate 1-6 Sparpreis"},
            {"months": 18, "amount": 29.99, "note": "Monate 7-24 Regulär"},
            {"months": None, "amount": 44.99, "note": "Ab Monat 25 Standard"},
        ]

        entries = apply_price_tiers(c, base_date=start, tiers=tiers, currency="EUR")
        assert len(entries) == 3

        # Step 1: 2026-03-01 to 2026-08-31
        assert entries[0].amount == 9.99
        assert entries[0].valid_from == datetime.date(2026, 3, 1)
        assert entries[0].valid_to == datetime.date(2026, 8, 31)

        # Step 2: 2026-09-01 to 2028-02-29
        assert entries[1].amount == 29.99
        assert entries[1].valid_from == datetime.date(2026, 9, 1)
        assert entries[1].valid_to == datetime.date(2028, 2, 29)

        # Step 3: from 2028-03-01 onward
        assert entries[2].amount == 44.99
        assert entries[2].valid_from == datetime.date(2028, 3, 1)
        assert entries[2].valid_to is None


def test_apply_price_tiers_validation(app):
    """Test validation and fallback for empty or invalid tier lists."""
    with app.app_context():
        u = User(username="tier_user_3", hashed_password=generate_password_hash("pass123"))
        db.session.add(u)
        db.session.commit()

        c = Contract(
            user_id=u.id,
            category="Software",
            title="SaaS Sub",
            amount=50.0,
            currency="EUR",
            frequency=Frequency.monthly,
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()

        # Empty list
        assert apply_price_tiers(c, datetime.date.today(), []) == []
        # Negative amount filtered out
        assert apply_price_tiers(c, datetime.date.today(), [{"months": 6, "amount": -10.0}]) == []


