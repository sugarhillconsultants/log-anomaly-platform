"""
app/main.py

The flagship piece: a production-shaped serving API for the log-anomaly
classifier, tying together:
  - The actual fine-tuned, registered model from Project 2
    (Reproducible Fine-Tuning Pipeline) — not a placeholder.
  - JWT authentication and an async database (the piece Project 3's
    showcase app deliberately left out, to keep that project focused
    on infrastructure).
  - Background tasks for audit logging and anomaly alerting.
  - The same test-gated CI/CD and dual-cloud deployment pattern from
    Project 3, plus real canary rollback wired to a live metrics check
    (see deploy/canary_rollback.py), not a documented stub.
"""

from contextlib import asynccontextmanager
from typing import Optional
from functools import lru_cache

from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import authenticate_user, create_access_token, get_current_user, Token
from database import init_db, get_db, LogEventRecord
from background import write_audit_log, send_alert_if_anomalous

# The actual registered model from Project 2 — this is the real tie-in
# between the two projects, not a shared placeholder.
MODEL_REPO_ID = "oromeop/log-classifier-tiny"
MODEL_REVISION = "v1.0.0"  # pinned to the tagged version the gate approved


@lru_cache(maxsize=1)
def get_classifier():
    """Loads the real fine-tuned model once per process. Falls back to
    None (handled gracefully downstream) if the Hub is unreachable at
    startup, rather than crashing the whole app."""
    try:
        from transformers import pipeline
        return pipeline(
            "text-classification",
            model=MODEL_REPO_ID,
            revision=MODEL_REVISION,
        )
    except Exception as e:
        print(f"Warning: could not load model {MODEL_REPO_ID}@{MODEL_REVISION}: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    get_classifier()  # warm the model cache at startup, not on first request
    yield


app = FastAPI(title="Log Anomaly Detection Platform", lifespan=lifespan)


class LogEventIn(BaseModel):
    text: str = Field(..., min_length=1, description="Raw log line to classify")
    source: Optional[str] = Field(default="unknown", description="Origin system")


class LogEventOut(BaseModel):
    event_id: int
    text: str
    predicted_label: str
    confidence: float

    class Config:
        from_attributes = True


def classify(text: str) -> tuple[str, float]:
    classifier = get_classifier()
    if classifier is None:
        return "unavailable", 0.0
    result = classifier(text, truncation=True)[0]
    label = result["label"]
    # Model was trained with label 0 = normal, 1 = security_anomaly, but
    # the Hub pipeline may return raw LABEL_0/LABEL_1 depending on config.
    if label in ("LABEL_1", "1", "security_anomaly"):
        label = "security_anomaly"
    else:
        label = "normal"
    return label, float(result["score"])


@app.get("/")
def read_root():
    return {
        "message": "Log Anomaly Detection Platform is running",
        "model": f"{MODEL_REPO_ID}@{MODEL_REVISION}",
        "model_loaded": get_classifier() is not None,
    }


@app.get("/health")
def health():
    return {"status": "healthy" if get_classifier() is not None else "degraded"}


@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/events/{event_id}", response_model=LogEventOut)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    result = await db.execute(select(LogEventRecord).where(LogEventRecord.id == event_id))
    record = result.scalar_one_or_none()
    if record is None:
        return LogEventOut(event_id=event_id, text="", predicted_label="not_found", confidence=0.0)
    return record


@app.post("/events", response_model=LogEventOut, status_code=201)
async def create_event(
    payload: LogEventIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    label, confidence = classify(payload.text)

    record = LogEventRecord(text=payload.text, predicted_label=label, confidence=confidence)
    db.add(record)
    await db.commit()
    await db.refresh(record)

    background_tasks.add_task(write_audit_log, record.id, label, current_user)
    background_tasks.add_task(send_alert_if_anomalous, record.id, label, confidence)

    return record


class RecentFeaturesOut(BaseModel):
    """The real numeric signals available for drift detection against a
    TEXT classifier — confidence and text length. This intentionally
    replaces an earlier, incorrect assumption (in the observability
    project's original baseline builder) that this model used tabular
    features like `is_off_hours` — it doesn't; those belonged to a
    different project's simpler sklearn model, not this fine-tuned
    text classifier. Confidence and text length are what's actually
    available here, so those are what drift gets measured on."""
    n: int
    confidence: list[float]
    text_length: list[int]
    predicted_labels: list[str]


@app.get("/events/recent-features", response_model=RecentFeaturesOut)
async def get_recent_features(
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Feeds Project 4 (Model Observability Dashboard)'s drift detection
    with real production data — confidence scores and text lengths from
    the most recent classified events, in place of the hardcoded
    psi_score=0.0 placeholder that project's workflow originally used."""
    result = await db.execute(
        select(LogEventRecord).order_by(LogEventRecord.created_at.desc()).limit(limit)
    )
    records = result.scalars().all()

    return RecentFeaturesOut(
        n=len(records),
        confidence=[r.confidence for r in records],
        text_length=[len(r.text) for r in records],
        predicted_labels=[r.predicted_label for r in records],
    )
