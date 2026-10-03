from fastapi import FastAPI
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


app = FastAPI(
    title="Agrivisor Ingestion API",
    version="1.0.0",
    description="Trusted telemetry ingestion service for Agrivisor devices.",
)


class TelemetryPayload(BaseModel):
    device_id: UUID
    message_id: UUID
    recorded_at: datetime

    moisture: float
    temperature: float
    ph: float
    ec: float
    n: float
    p: float
    k: float


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryPayload):
    return {
        "status": "received",
        "message_id": str(payload.message_id),
    }
