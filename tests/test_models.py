import pytest
from app.models import User, Contract, Provider, ContractStatus

def test_user_model(app):
    from app import db
    user = User(username="testuser", hashed_password="hashed_password")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        
        saved_user = db.session.get(User, user.id)
        assert saved_user.username == "testuser"
        assert saved_user.timezone == "Europe/Berlin"

def test_contract_model(app):
    from app import db
    with app.app_context():
        user = User(username="contractuser", hashed_password="pw")
        db.session.add(user)
        db.session.commit()

        contract = Contract(
            user_id=user.id,
            category="Internet",
            status=ContractStatus.active,
            amount=39.99
        )
        db.session.add(contract)
        db.session.commit()

        saved_contract = db.session.get(Contract, contract.id)
        assert saved_contract.amount == 39.99
        assert saved_contract.status == ContractStatus.active
