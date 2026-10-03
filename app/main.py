import os
import hashlib
import secrets
from uuid import UUID
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from supabase import create_client, Client


app = FastAPI(
    title="Agrivisor Ingestion API",
    version="1.2.0",
    description="Trusted telemetry ingestion service for Agrivisor devices.",
)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PROVISIONING_KEY = os.getenv("PROVISIONING_KEY")


if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL environment variable is missing")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY environment variable is missing")

if not PROVISIONING_KEY:
    raise RuntimeError("PROVISIONING_KEY environment variable is missing")


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


class ProvisionRequest(BaseModel):
    device_id: UUID
    credential: str


@app.get("/health")
def health():
    return {"status": "ok"}


def hash_credential(credential: str) -> str:
    return hashlib.sha256(
        credential.encode("utf-8")
    ).hexdigest()


@app.post("/api/provision")
def provision_device(
    request: ProvisionRequest,
    x_provisioning_key: str = Header(default=""),
):
    if not secrets.compare_digest(
        x_provisioning_key,
        PROVISIONING_KEY,
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    if len(request.credential) < 32:
        raise HTTPException(
            status_code=400,
            detail="Credential must be at least 32 characters.",
        )

    try:
        result = (
            supabase
            .table("devices")
            .update(
                {
                    "auth_token_hash": hash_credential(
                        request.credential
                    )
                }
            )
            .eq("id", str(request.device_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Device not found.",
            )

        return {
            "status": "provisioned",
            "device_id": str(request.device_id),
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Device provisioning failed.",
        )


@app.post("/api/telemetry")
def receive_telemetry(
    payload: TelemetryPayload,
    authorization: str = Header(default=""),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing device credential.",
        )

    credential = authorization[7:].strip()

    if not credential:
        raise HTTPException(
            status_code=401,
            detail="Missing device credential.",
        )

    try:
        device_result = (
            supabase
            .table("devices")
            .select("id, auth_token_hash")
            .eq("id", str(payload.device_id))
            .maybe_single()
            .execute()
        )

        device = device_result.data

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Device lookup failed.",
        )

    if not device or not device.get("auth_token_hash"):
        raise HTTPException(
            status_code=401,
            detail="Device not provisioned.",
        )

    supplied_hash = hash_credential(credential)

    if not secrets.compare_digest(
        supplied_hash,
        device["auth_token_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid device credential.",
        )

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
        result = (
            supabase
            .table("sensor_readings")
            .insert(row)
            .execute()
        )

        return {
            "status": "received",
            "message_id": str(payload.message_id),
        }

    except Exception as exc:
        error_text = str(exc)

        if (
            "duplicate" in error_text.lower()
            or "23505" in error_text
        ):
            return {
                "status": "already_received",
                "message_id": str(payload.message_id),
            }

        raise HTTPException(
            status_code=500,
            detail="Telemetry could not be stored.",
        )
