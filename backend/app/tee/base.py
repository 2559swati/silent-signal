"""Phase 11 TEE provider abstraction (Blueprint Section 14).

Defines the provider-agnostic contract for TEE-backed analysis. Today the
only implementation is DemoTEEProvider (demo adapter around the real
in-process Phase 4-5 engines); Phase 12 may add a NitroTEEProvider behind
the same interface selected via TEE_MODE. No Demo/Nitro specifics belong
in this module.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class AssetAnalysis:
    """Result of analyzing one asset through a TEE provider."""

    asset_id: str
    asset_external_code: str
    day: date
    anomaly_score: float
    fusion_score: float
    smoothed_fusion_score: float
    fusion_status: str
    persistence_score: float
    risk_score: float
    risk_level: str
    provider_mode: str


@dataclass(frozen=True)
class TEEStatus:
    """Operational status of the active TEE provider."""

    mode: str
    healthy: bool
    description: str


@dataclass(frozen=True)
class AttestationStatus:
    """Attestation state. Only a hardware-backed provider may report True."""

    attested: bool
    pcr0: Optional[str]


class TEEProvider(ABC):
    """Abstract interface for TEE-backed asset analysis."""

    @property
    @abstractmethod
    def mode(self) -> str:
        """Provider mode identifier (e.g. 'demo')."""
        raise NotImplementedError

    @abstractmethod
    def analyze_asset(self, asset_id: str, db) -> AssetAnalysis:
        """Analyze one asset (external code or UUID) via this provider."""
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> TEEStatus:
        """Current provider operational status."""
        raise NotImplementedError

    @abstractmethod
    def get_attestation_status(self) -> AttestationStatus:
        """Current attestation state."""
        raise NotImplementedError
