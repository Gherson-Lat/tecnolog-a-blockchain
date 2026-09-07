from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import Block, Event


def _normalize_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(tzinfo=None)


def _serialize_event_for_hash(event: Event) -> str:
    payload = {
        "id": event.id,
        "event_type": event.event_type,
        "user_id": event.user_id,
        "bottle_id": event.bottle_id,
        "payload": event.payload or {},
        "event_time": _normalize_utc(event.event_time).isoformat(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_event_data_hash(event: Event) -> str:
    return hashlib.sha256(_serialize_event_for_hash(event).encode("utf-8")).hexdigest()


def mine_block_hash(
    index: int,
    timestamp: datetime,
    data_hash: str,
    previous_hash: str | None,
    difficulty: str = "0000",
) -> tuple[str, int]:
    timestamp_value = _normalize_utc(timestamp).isoformat()
    nonce = 0
    while True:
        raw = f"{index}{timestamp_value}{data_hash}{previous_hash or ''}{nonce}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if digest.startswith(difficulty):
            return digest, nonce
        nonce += 1


def compute_block_hash(
    index: int,
    timestamp: datetime,
    data_hash: str,
    previous_hash: str | None,
    nonce: int = 0,
) -> str:
    timestamp_value = _normalize_utc(timestamp).isoformat()
    raw = f"{index}{timestamp_value}{data_hash}{previous_hash or ''}{nonce}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_block_for_event(session: Session, event: Event, commit: bool = True) -> Block:
    last_block = session.query(Block).order_by(Block.index.desc()).first()
    index = (last_block.index + 1) if last_block else 0
    previous_hash = last_block.hash if last_block else None
    data_hash = compute_event_data_hash(event)
    timestamp = _normalize_utc(datetime.now(timezone.utc))
    block_hash, nonce = mine_block_hash(index, timestamp, data_hash, previous_hash, difficulty="0000")

    block = Block(
        index=index,
        timestamp=timestamp,
        data_hash=data_hash,
        previous_hash=previous_hash,
        nonce=nonce,
        hash=block_hash,
        event_id=event.id,
    )
    session.add(block)
    if commit:
        session.commit()
    return block


def is_chain_valid(session: Session) -> bool:
    blocks = session.query(Block).order_by(Block.index.asc()).all()
    for idx, block in enumerate(blocks):
        if block.index != idx:
            return False
        expected_previous = blocks[idx - 1].hash if idx > 0 else None
        if block.previous_hash != expected_previous:
            return False

        calculated_hash = compute_block_hash(
            block.index,
            block.timestamp,
            block.data_hash,
            block.previous_hash,
            block.nonce,
        )
        if block.hash != calculated_hash:
            return False
        if not block.hash.startswith("0000"):
            return False

        event = session.query(Event).filter(Event.id == block.event_id).first()
        if event is None:
            return False
        if block.data_hash != compute_event_data_hash(event):
            return False

    return True
