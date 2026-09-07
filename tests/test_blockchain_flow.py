from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_db, get_password_hash
from app.main import app
from app.services.bottle_service import BottleService
from blockchain import add_block_for_event, is_chain_valid
from database import Base, Event, User


def _create_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _bottle_payload(**overrides):
    data = {
        "qr_code": "BOT-TEST-1",
        "product_name": "Aguardiente",
        "acta_number": "ACTA-1",
        "unique_code": "BOT-TEST-1",
        "distributor_company": "Distribuidora Andina",
        "barcode": "7701234567890",
        "consumption_department": "Cundinamarca",
        "alcohol_degree": "29%",
        "query_website": "https://consulta.example",
        "acta_date": "2026-09-07",
        "product_capacity": "750 ml",
        "print_lot_number": "LOT-01",
        "print_consecutive": "0001",
    }
    data.update(overrides)
    return data


def test_blockchain_hash_and_validation():
    session = _create_session()
    user = User(username="tester", password_hash="x", role="manufacturer")
    session.add(user)
    session.commit()

    event = Event(
        event_type="REGISTERED",
        user_id=user.id,
        bottle_id=None,
        payload={"unique_code": "BOT-000001"},
        event_time=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(event)
    session.commit()

    block = add_block_for_event(session, event)
    assert block.index == 0
    assert block.previous_hash is None
    assert block.hash == block.calculate_hash()
    assert is_chain_valid(session) is True


def test_duplicate_bottle_is_rejected():
    session = _create_session()
    user = User(username="mfr", password_hash="x", role="manufacturer")
    session.add(user)
    session.commit()
    service = BottleService(session, user.id)

    first = service.register_bottle(_bottle_payload())
    second = service.register_bottle(_bottle_payload())
    assert first is not None
    assert second is None


def test_state_machine_registered_distributed_consumed():
    session = _create_session()
    user = User(username="mfr", password_hash="x", role="manufacturer")
    session.add(user)
    session.commit()
    service = BottleService(session, user.id)
    bottle = service.register_bottle(_bottle_payload(unique_code="BOT-TEST-2", qr_code="BOT-TEST-2"))

    assert bottle is not None
    assert service.consume_bottle(bottle.id, user_id=user.id) is None
    assert service.distribute_bottle(bottle.id, target_user_id=user.id) is not None
    assert service.distribute_bottle(bottle.id, target_user_id=user.id) is None
    assert service.consume_bottle(bottle.id, user_id=user.id) is not None
    assert service.consume_bottle(bottle.id, user_id=user.id) is None


def test_list_bottles_by_code():
    session = _create_session()
    user = User(username="mfr", password_hash="x", role="manufacturer")
    session.add(user)
    session.commit()
    service = BottleService(session, user.id)
    service.register_bottle(_bottle_payload(unique_code="ABC-1", qr_code="ABC-1"))
    service.register_bottle(_bottle_payload(unique_code="ABC-2", qr_code="ABC-2"))
    found = service.list_bottles("ABC-1")
    assert len(found) == 1
    assert found[0].unique_code == "ABC-1"


def test_roles_are_enforced():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    db.add_all(
        [
            User(username="manufacturer", password_hash=get_password_hash("manufacturer123"), role="manufacturer"),
            User(username="distributor", password_hash=get_password_hash("distributor123"), role="distributor"),
            User(username="consumer", password_hash=get_password_hash("consumer123"), role="consumer"),
        ]
    )
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        def login(username: str, password: str) -> str:
            res = client.post("/auth/login", data={"username": username, "password": password})
            assert res.status_code == 200
            return res.json()["access_token"]

        consumer_token = login("consumer", "consumer123")
        denied = client.post(
            "/api/bottles/register",
            headers={"Authorization": f"Bearer {consumer_token}"},
            json=_bottle_payload(),
        )
        assert denied.status_code == 403

        manufacturer_token = login("manufacturer", "manufacturer123")
        created = client.post(
            "/api/bottles/register",
            headers={"Authorization": f"Bearer {manufacturer_token}"},
            json=_bottle_payload(),
        )
        assert created.status_code == 200

        listed = client.get(
            "/api/bottles",
            params={"unique_code": "BOT-TEST-1"},
            headers={"Authorization": f"Bearer {manufacturer_token}"},
        )
        assert listed.status_code == 200
        assert listed.json()["bottles"][0]["product_name"] == "Aguardiente"

    app.dependency_overrides.clear()
