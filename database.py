from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = "sqlite:///./bottle_traceability.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

STATUS_REGISTERED = "registered"
STATUS_DISTRIBUTED = "distributed"
STATUS_CONSUMED = "consumed"
VALID_TRANSITIONS = {
    STATUS_REGISTERED: {STATUS_DISTRIBUTED},
    STATUS_DISTRIBUTED: {STATUS_CONSUMED},
    STATUS_CONSUMED: set(),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    events: Mapped[list["Event"]] = relationship(back_populates="user")
    bottles: Mapped[list["Bottle"]] = relationship(back_populates="creator")


class Bottle(Base):
    __tablename__ = "bottles"
    __table_args__ = (UniqueConstraint("unique_code", name="uq_bottle_unique_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    qr_code: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    acta_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    unique_code: Mapped[str] = mapped_column(String(80), nullable=False)
    distributor_company: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    barcode: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    consumption_department: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    alcohol_degree: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    query_website: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    acta_date: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    product_capacity: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    print_lot_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    print_consecutive: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_REGISTERED)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    creator: Mapped[User] = relationship(back_populates="bottles")
    events: Mapped[list["Event"]] = relationship(back_populates="bottle")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    bottle_id: Mapped[int | None] = mapped_column(ForeignKey("bottles.id"), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict, nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="events")
    bottle: Mapped[Bottle | None] = relationship(back_populates="events")
    block: Mapped["Block | None"] = relationship(back_populates="event", uselist=False)


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nonce: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True, nullable=False)

    event: Mapped[Event] = relationship(back_populates="block")

    def calculate_hash(self) -> str:
        import hashlib

        raw = (
            f"{self.index}{self.timestamp.isoformat()}{self.data_hash}{self.previous_hash or ''}{self.nonce}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


def _ensure_bottle_columns() -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        inspector_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(bottles)")).fetchall()}
    if not inspector_columns:
        return

    extras = {
        "qr_code": "VARCHAR(255) DEFAULT ''",
        "acta_number": "VARCHAR(80) DEFAULT ''",
        "distributor_company": "VARCHAR(150) DEFAULT ''",
        "barcode": "VARCHAR(80) DEFAULT ''",
        "consumption_department": "VARCHAR(80) DEFAULT ''",
        "alcohol_degree": "VARCHAR(40) DEFAULT ''",
        "query_website": "VARCHAR(255) DEFAULT ''",
        "acta_date": "VARCHAR(40) DEFAULT ''",
        "product_capacity": "VARCHAR(40) DEFAULT ''",
        "print_lot_number": "VARCHAR(80) DEFAULT ''",
        "print_consecutive": "VARCHAR(80) DEFAULT ''",
    }
    with engine.begin() as conn:
        for name, ddl in extras.items():
            if name not in inspector_columns:
                conn.execute(text(f"ALTER TABLE bottles ADD COLUMN {name} {ddl}"))


def _ensure_block_columns() -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        inspector_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(blocks)"))}
    if inspector_columns and "nonce" not in inspector_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE blocks ADD COLUMN nonce INTEGER NOT NULL DEFAULT 0"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _ensure_bottle_columns()
        _ensure_block_columns()


if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada.")
