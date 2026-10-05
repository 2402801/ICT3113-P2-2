import time
import uuid

from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from categories import CATEGORIES
from classifier import OLLAMA_MODEL, OLLAMA_THINK, classify_detailed
from database import Ticket, RequestMetric, get_db, init_db
from logging_setup import configure_logging, format_fields
from prompt import PROMPT_VERSION

app = FastAPI(title="Ticket Triage Service")
access_logger = configure_logging()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_epoch_ms = int(time.time() * 1000)
    start = time.perf_counter()
    request_id = uuid.uuid4().hex[:12]
    # Handlers add ticket/Ollama details to this dict; it is shared through the request scope.
    request.state.log_fields = {}
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        fields = {
            "client": request.client.host if request.client else "-",
            "req_id": request_id,
            "start_ms": start_epoch_ms,
            "run": request.headers.get("x-run-id", "-"),
            "model": OLLAMA_MODEL,
            **request.state.log_fields,
        }
        access_logger.info(
            "%s %s %s %.2fms %s",
            request.method,
            request.url.path,
            status_code,
            latency_ms,
            format_fields(fields),
        )


class TicketIn(BaseModel):
    narrative: str = Field(..., min_length=1)


class TicketOut(BaseModel):
    id: int
    category: str
    narrative: str
    classification_latency_ms: float


def _record_metric(db: Session, endpoint: str, status_code: int, latency_ms: float) -> None:
    db.add(RequestMetric(endpoint=endpoint, status_code=status_code, latency_ms=latency_ms))
    db.commit()


@app.post("/tickets", response_model=TicketOut)
def create_ticket(ticket: TicketIn, request: Request, db: Session = Depends(get_db)):
    start = time.perf_counter()
    status_code = 200
    try:
        result = classify_detailed(ticket.narrative)
    except Exception as exc:
        status_code = 502
        request.state.log_fields.update(getattr(exc, "ollama", {}), error=type(exc).__name__)
        _record_metric(db, "/tickets", status_code, (time.perf_counter() - start) * 1000)
        raise HTTPException(status_code=502, detail=f"Classification backend error: {exc}")

    latency_ms = (time.perf_counter() - start) * 1000

    db_ticket = Ticket(
        narrative=ticket.narrative,
        category=result.category,
        classification_latency_ms=latency_ms,
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)

    request.state.log_fields.update(
        ticket_id=db_ticket.id, category=db_ticket.category, **result.ollama
    )
    _record_metric(db, "/tickets", status_code, latency_ms)

    return TicketOut(
        id=db_ticket.id,
        category=db_ticket.category,
        narrative=db_ticket.narrative,
        classification_latency_ms=latency_ms,
    )


@app.get("/search")
def search_tickets(q: str = "", db: Session = Depends(get_db)):
    start = time.perf_counter()

    query = db.query(Ticket)
    if q:
        query = query.filter(Ticket.narrative.ilike(f"%{q}%"))
    results = query.order_by(Ticket.id).all()

    latency_ms = (time.perf_counter() - start) * 1000
    _record_metric(db, "/search", 200, latency_ms)

    return {
        "count": len(results),
        "results": [
            {
                "id": t.id,
                "category": t.category,
                "narrative": t.narrative,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in results
        ],
    }


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    start = time.perf_counter()

    rows = (
        db.query(Ticket.category, func.count(Ticket.id))
        .group_by(Ticket.category)
        .all()
    )
    counts = {category: 0 for category in CATEGORIES}
    for category, count in rows:
        counts[category] = count

    latency_ms = (time.perf_counter() - start) * 1000
    _record_metric(db, "/stats", 200, latency_ms)

    return {"counts": counts, "total": sum(counts.values())}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "prompt_version": PROMPT_VERSION,
        "think": OLLAMA_THINK,
    }
