from __future__ import annotations

from sqlalchemy.orm import Session

from blockchain import add_block_for_event
from database import (
    STATUS_CONSUMED,
    STATUS_DISTRIBUTED,
    STATUS_REGISTERED,
    Bottle,
    Event,
    can_transition,
    utc_now,
)


def serialize_bottle(bottle: Bottle) -> dict:
    return {
        "id": bottle.id,
        "qr_code": bottle.qr_code,
        "product_name": bottle.product_name,
        "acta_number": bottle.acta_number,
        "unique_code": bottle.unique_code,
        "distributor_company": bottle.distributor_company,
        "barcode": bottle.barcode,
        "consumption_department": bottle.consumption_department,
        "alcohol_degree": bottle.alcohol_degree,
        "query_website": bottle.query_website,
        "acta_date": bottle.acta_date,
        "product_capacity": bottle.product_capacity,
        "print_lot_number": bottle.print_lot_number,
        "print_consecutive": bottle.print_consecutive,
        "status": bottle.status,
    }


class BottleService:
    def __init__(self, db: Session, actor_id: int):
        self.db = db
        self.actor_id = actor_id

    def register_bottle(self, data: dict) -> Bottle | None:
        unique_code = (data.get("unique_code") or "").strip()
        if not unique_code:
            return None
        if self.db.query(Bottle).filter(Bottle.unique_code == unique_code).first():
            return None

        qr_code = (data.get("qr_code") or "").strip() or unique_code
        bottle = Bottle(
            qr_code=qr_code,
            product_name=(data.get("product_name") or "").strip(),
            acta_number=(data.get("acta_number") or "").strip(),
            unique_code=unique_code,
            distributor_company=(data.get("distributor_company") or "").strip(),
            barcode=(data.get("barcode") or "").strip(),
            consumption_department=(data.get("consumption_department") or "").strip(),
            alcohol_degree=(data.get("alcohol_degree") or "").strip(),
            query_website=(data.get("query_website") or "").strip(),
            acta_date=(data.get("acta_date") or "").strip(),
            product_capacity=(data.get("product_capacity") or "").strip(),
            print_lot_number=(data.get("print_lot_number") or "").strip(),
            print_consecutive=(data.get("print_consecutive") or "").strip(),
            status=STATUS_REGISTERED,
            created_by=self.actor_id,
            created_at=utc_now(),
        )
        self.db.add(bottle)
        self.db.flush()

        event = Event(
            event_type="REGISTERED",
            user_id=self.actor_id,
            bottle_id=bottle.id,
            payload=serialize_bottle(bottle),
            event_time=utc_now(),
        )
        self.db.add(event)
        self.db.flush()
        add_block_for_event(self.db, event)
        self.db.commit()
        return bottle

    def distribute_bottle(self, bottle_id: int, target_user_id: int) -> Bottle | None:
        bottle = self.db.query(Bottle).filter(Bottle.id == bottle_id).first()
        if not bottle or not can_transition(bottle.status, STATUS_DISTRIBUTED):
            return None

        bottle.status = STATUS_DISTRIBUTED
        event = Event(
            event_type="DISTRIBUTED",
            user_id=target_user_id,
            bottle_id=bottle.id,
            payload={"from_user_id": self.actor_id, "to_user_id": target_user_id},
            event_time=utc_now(),
        )
        self.db.add(event)
        self.db.flush()
        add_block_for_event(self.db, event)
        self.db.commit()
        return bottle

    def consume_bottle(self, bottle_id: int, user_id: int) -> Bottle | None:
        bottle = self.db.query(Bottle).filter(Bottle.id == bottle_id).first()
        if not bottle or not can_transition(bottle.status, STATUS_CONSUMED):
            return None

        bottle.status = STATUS_CONSUMED
        event = Event(
            event_type="CONSUMED",
            user_id=user_id,
            bottle_id=bottle.id,
            payload={"consumed_by": user_id},
            event_time=utc_now(),
        )
        self.db.add(event)
        self.db.flush()
        add_block_for_event(self.db, event)
        self.db.commit()
        return bottle

    def list_bottles(self, unique_code: str | None = None) -> list[Bottle]:
        query = self.db.query(Bottle).order_by(Bottle.id.desc())
        if unique_code:
            query = query.filter(Bottle.unique_code == unique_code.strip())
        return query.all()

    def get_by_code(self, unique_code: str) -> Bottle | None:
        return self.db.query(Bottle).filter(Bottle.unique_code == unique_code.strip()).first()
