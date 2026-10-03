import os
from uuid import UUID
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client, Client


app = FastAPI(
    title="Agrivisor Ingestion API",
    version="1.1.0",
    description="Trusted telemetry ingestion service for Agrivisor devices.",
)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL environment variable is missing")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY environment variable is missing")


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)


class TelemetryPayload(BaseModel):
    device_id: UUID
    message_id: UUID
    recorded_at: datetime

    moisture: float = Field(..., finite=True)
    temperature: float = Field(..., finite=True)
    ph: float = Field(..., finite=True)
    ec: float = Field(..., finite=True)
    n: float = Field(..., finite=True)
    p: float = Field(..., finite=True)
    k: float = Field(..., finite=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryPayload):

    row = {
        "device_id": str(payload.device_id),
        "message_id": str(payload.message_id),
        "recorded_at": payload.recorded_at.isoformat(),
        "moisture": payload.moisture,
        "temperature": payload.temperature,
        "ph": payload.ph,
        "ec": payload.ec,
        "n": payload.n,
        "p": payload.p,
        "k": payload.k,
    }

    try:
        supabase.table("sensor_readings").insert(row).execute()

        return {
            "status": "received",
            "message_id": str(payload.message_id),
        }

    except Exception as exc:
        error_text = str(exc)

        if "duplicate" in error_text.lower() or "23505" in error_text:
            return {
                "status": "already_received",
                "message_id": str(payload.message_id),
            }

        raise HTTPException(
            status_code=500,
            detail="Telemetry could not be stored.",
        )
