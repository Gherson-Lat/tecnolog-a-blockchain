from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_db, require_role
from app.routes.auth_routes import router as auth_router
from app.schemas import BottleCreate, ConsumePayload, DistributePayload
from app.services.bottle_service import BottleService, serialize_bottle
from blockchain import is_chain_valid
from database import Block, User, init_db

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Bottle Traceability", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "role": current_user.role}


@app.get("/api/users")
def list_users(
    role: str | None = Query(default=None),
    current_user: User = Depends(require_role("manufacturer", "distributor")),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    users = query.order_by(User.id.asc()).all()
    return {"users": [{"id": u.id, "username": u.username, "role": u.role} for u in users]}


@app.post("/api/bottles/register")
def register_bottle(
    payload: BottleCreate,
    current_user: User = Depends(require_role("manufacturer")),
    db: Session = Depends(get_db),
):
    service = BottleService(db, current_user.id)
    bottle = service.register_bottle(payload.model_dump())
    if bottle is None:
        raise HTTPException(status_code=400, detail="La botella ya existe o el código único está vacío")
    return {"ok": True, "message": "Botella registrada", "bottle": serialize_bottle(bottle)}


@app.post("/api/bottles/distribute")
def distribute_bottle(
    payload: DistributePayload,
    current_user: User = Depends(require_role("distributor")),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == payload.target_user_id).first()
    if target is None or target.role != "consumer":
        raise HTTPException(status_code=400, detail="El destino debe ser un usuario consumidor")

    service = BottleService(db, current_user.id)
    bottle = service.distribute_bottle(payload.bottle_id, payload.target_user_id)
    if bottle is None:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden distribuir botellas en estado registered",
        )
    return {"ok": True, "message": "Botella distribuida", "bottle": serialize_bottle(bottle)}


@app.post("/api/bottles/consume")
def consume_bottle(
    payload: ConsumePayload,
    current_user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    service = BottleService(db, current_user.id)
    bottle = service.consume_bottle(payload.bottle_id, current_user.id)
    if bottle is None:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden consumir botellas en estado distributed",
        )
    return {"ok": True, "message": "Botella consumida", "bottle": serialize_bottle(bottle)}


@app.get("/api/bottles")
def list_bottles(
    unique_code: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BottleService(db, current_user.id)
    bottles = service.list_bottles(unique_code)
    return {"bottles": [serialize_bottle(b) for b in bottles]}


@app.get("/api/bottles/by-code/{unique_code}")
def bottle_by_code(
    unique_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BottleService(db, current_user.id)
    bottle = service.get_by_code(unique_code)
    if bottle is None:
        raise HTTPException(status_code=404, detail="Botella no encontrada")
    return {"bottle": serialize_bottle(bottle)}


@app.get("/api/chain")
def chain_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blocks = db.query(Block).order_by(Block.index.asc()).all()
    return {
        "valid": is_chain_valid(db),
        "count": len(blocks),
        "blocks": [
            {"index": b.index, "event_id": b.event_id, "previous_hash": b.previous_hash, "hash": b.hash}
            for b in blocks
        ],
    }
