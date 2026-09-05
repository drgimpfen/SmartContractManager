import pytest
from app import db
from app.models import User, Contract, Provider, Note, Tag, ContractStatus
from app.services.contract_service import prune_orphaned_tags, sync_contract_tags


@pytest.fixture
def test_user(app):
    with app.app_context():
        u = User(username="note_user", hashed_password="pw")
        db.session.add(u)
        db.session.commit()
        uid = u.id
    return uid


@pytest.fixture
def other_user(app):
    with app.app_context():
        u = User(username="other_note_user", hashed_password="pw")
        db.session.add(u)
        db.session.commit()
        uid = u.id
    return uid


def test_contract_note_lifecycle(app, client, test_user):
    """Test adding, viewing, and deleting notes on a contract."""
    with app.app_context():
        with client.session_transaction() as sess:
            sess['_user_id'] = str(test_user)

        c = Contract(
            user_id=test_user,
            title="Streaming Abo",
            category="Streaming",
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()
        contract_id = c.id

    # 1. Add note
    resp = client.post(
        f'/contracts/{contract_id}/notes',
        data={'content': 'Called support to ask about upcoming price changes.'},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Notiz erfolgreich hinzugef" in resp.data or b"Called support" in resp.data

    with app.app_context():
        notes = Note.query.filter_by(contract_id=contract_id).all()
        assert len(notes) == 1
        assert notes[0].content == 'Called support to ask about upcoming price changes.'
        note_id = notes[0].id

    # 2. Delete note
    del_resp = client.post(
        f'/contracts/{contract_id}/notes/{note_id}/delete',
        follow_redirects=True,
    )
    assert del_resp.status_code == 200

    with app.app_context():
        notes_after = Note.query.filter_by(contract_id=contract_id).all()
        assert len(notes_after) == 0


def test_provider_note_lifecycle(app, client, test_user):
    """Test adding, viewing, and deleting notes on a provider."""
    with app.app_context():
        with client.session_transaction() as sess:
            sess['_user_id'] = str(test_user)

        p = Provider(
            user_id=test_user,
            name="Telekom AG",
            customer_number="KD-998877",
        )
        db.session.add(p)
        db.session.commit()
        provider_id = p.id

    # 1. Add note
    resp = client.post(
        f'/providers/{provider_id}/notes',
        data={'content': 'Support Hotline pin: 1234.'},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        notes = Note.query.filter_by(provider_id=provider_id).all()
        assert len(notes) == 1
        assert notes[0].content == 'Support Hotline pin: 1234.'
        note_id = notes[0].id

    # 2. Delete note
    del_resp = client.post(
        f'/providers/{provider_id}/notes/{note_id}/delete',
        follow_redirects=True,
    )
    assert del_resp.status_code == 200

    with app.app_context():
        notes_after = Note.query.filter_by(provider_id=provider_id).all()
        assert len(notes_after) == 0


def test_note_authorization_protection(app, client, test_user, other_user):
    """User B cannot view or delete User A's notes."""
    with app.app_context():
        c = Contract(
            user_id=test_user,
            title="Private Contract",
            category="Insurance",
            status=ContractStatus.active,
        )
        db.session.add(c)
        db.session.commit()
        contract_id = c.id

        n = Note(
            user_id=test_user,
            contract_id=contract_id,
            content="Sensitive data",
        )
        db.session.add(n)
        db.session.commit()
        note_id = n.id

    # Log in as other_user
    with client.session_transaction() as sess:
        sess['_user_id'] = str(other_user)

    # Cannot add note to someone else's contract (404)
    add_resp = client.post(
        f'/contracts/{contract_id}/notes',
        data={'content': 'Malicious note'},
    )
    assert add_resp.status_code == 404

    # Cannot delete someone else's note
    del_resp = client.post(
        f'/contracts/{contract_id}/notes/{note_id}/delete',
    )
    assert del_resp.status_code == 404

    with app.app_context():
        n_db = db.session.get(Note, note_id)
        assert n_db is not None
        assert n_db.content == "Sensitive data"


def test_cascade_delete_notes(app, test_user):
    """Deleting a contract or provider cascades to its notes."""
    with app.app_context():
        p = Provider(user_id=test_user, name="Provider With Note")
        db.session.add(p)
        db.session.commit()
        p_note = Note(user_id=test_user, provider_id=p.id, content="Provider note")
        db.session.add(p_note)

        c = Contract(user_id=test_user, title="Contract With Note", category="Misc")
        db.session.add(c)
        db.session.commit()
        c_note = Note(user_id=test_user, contract_id=c.id, content="Contract note")
        db.session.add(c_note)
        db.session.commit()

        p_id = p.id
        c_id = c.id

        # Delete contract
        db.session.delete(c)
        db.session.commit()
        assert Note.query.filter_by(contract_id=c_id).count() == 0

        # Delete provider
        db.session.delete(p)
        db.session.commit()
        assert Note.query.filter_by(provider_id=p_id).count() == 0


def test_tag_garbage_collection(app, test_user):
    """Orphaned tags are pruned when no contracts reference them."""
    with app.app_context():
        c1 = Contract(user_id=test_user, title="C1", category="Cat")
        c2 = Contract(user_id=test_user, title="C2", category="Cat")
        db.session.add_all([c1, c2])
        db.session.commit()

        # Add tags: Shared, UniqueC1, UniqueC2
        sync_contract_tags(c1, test_user, "Shared, UniqueC1")
        sync_contract_tags(c2, test_user, "Shared, UniqueC2")
        db.session.commit()

        assert Tag.query.filter_by(user_id=test_user).count() == 3

        # Update c1 to only have Shared -> UniqueC1 becomes orphaned and pruned
        sync_contract_tags(c1, test_user, "Shared")
        db.session.commit()

        tags = [t.name for t in Tag.query.filter_by(user_id=test_user).all()]
        assert "UniqueC1" not in tags
        assert "Shared" in tags
        assert "UniqueC2" in tags

        # Manual prune test
        prune_orphaned_tags(test_user)
        assert Tag.query.filter_by(user_id=test_user).count() == 2
