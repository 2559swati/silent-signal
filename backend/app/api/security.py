"""Phase 11 security API.

GET /api/security/tee-status -- current provider/mode/status.
GET /api/security/attestation -- current attestation state.

Both routes resolve the provider through the TEE factory (never by
instantiating an implementation directly). In demo mode the responses
make it unambiguous that no hardware-backed attestation is active.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.security import AttestationResponse, TEEStatusResponse
from app.tee.factory import UnsupportedTEEModeError, get_provider

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/tee-status", response_model=TEEStatusResponse)
def get_tee_status():
    try:
        provider = get_provider()
    except UnsupportedTEEModeError as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    except Exception as exc:  # Nitro transport/config errors: loud 500, never demo fallback.
        return JSONResponse(status_code=500, content={"detail": f"TEE provider error: {exc}"})
    try:
        status = provider.get_status()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"TEE provider error: {exc}"})
    return TEEStatusResponse(
        mode=status.mode, healthy=status.healthy, description=status.description
    )


@router.get("/attestation", response_model=AttestationResponse)
def get_attestation():
    try:
        provider = get_provider()
    except UnsupportedTEEModeError as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"TEE provider error: {exc}"})
    try:
        att = provider.get_attestation_status()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"TEE provider error: {exc}"})
    return AttestationResponse(attested=att.attested, pcr0=att.pcr0)
