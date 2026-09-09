from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TEEStatusResponse(BaseModel):
    """Current TEE provider/mode/status (GET /api/security/tee-status)."""

    mode: str = Field(..., description="Active provider mode: 'demo' or 'nitro'")
    healthy: bool = Field(..., description="Provider operational health (not attestation)")
    description: str = Field(..., description="Human-readable provider description")

    model_config = ConfigDict(from_attributes=True)


class AttestationResponse(BaseModel):
    """Current attestation state (GET /api/security/attestation)."""

    attested: bool = Field(..., description="Hardware-backed attestation active (false without verified Nitro hardware)")
    pcr0: Optional[str] = Field(None, description="Enclave measurement (real PCR0 only when hardware-attested; operator placeholder otherwise)")

    model_config = ConfigDict(from_attributes=True)
