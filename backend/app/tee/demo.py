"""Phase 11 Demo TEE provider.

DemoTEEProvider is an INTENTIONALLY NON-PRODUCTION adapter: it executes
the REAL existing Phase 4 (fusion) / Phase 5 (risk) services in-process
and reports their genuine results. It performs NO hardware-backed
execution and therefore ALWAYS reports attested=False with pcr0=None --
there is no code path that can claim otherwise. Do not mistake
healthy=True (the adapter functions) for attestation (it never attests).
"""

from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.fusion_results import FusionResult
from app.models.risk_results import RiskResult
from app.services.risk_engine import compute_asset_risk
from app.tee.base import AssetAnalysis, AttestationStatus, TEEProvider, TEEStatus

DEMO_MODE = "demo"


class DemoTEEProvider(TEEProvider):
    """Demo adapter around the real in-process analysis services."""

    @property
    def mode(self) -> str:
        return DEMO_MODE

    def analyze_asset(self, asset_id: str, db: Session) -> AssetAnalysis:
        """Analyze via the existing Phase 4-5 services (in-process).

        Accepts an external code (e.g. SL-1042) or UUID. Runs the real
        Phase 5 per-asset risk computation (deterministic idempotent
        upsert through the existing engine) and returns the latest
        persisted fusion + risk evidence. No duplicated calculations.
        """
        asset = db.query(Asset).filter(Asset.external_code == asset_id).one_or_none()
        if asset is None:
            asset = db.query(Asset).filter(Asset.id == asset_id).one_or_none()
        if asset is None:
            raise ValueError(f"unknown asset {asset_id}")
        compute_asset_risk(asset.id, db)
        fusion = (
            db.query(FusionResult)
            .filter(FusionResult.asset_id == asset.id)
            .order_by(FusionResult.day.desc())
            .first()
        )
        risk = (
            db.query(RiskResult)
            .filter(RiskResult.asset_id == asset.id)
            .order_by(RiskResult.day.desc())
            .first()
        )
        if fusion is None or risk is None:
            raise RuntimeError("Phase 4/5 evidence missing; run the fusion and risk pipelines first")
        return AssetAnalysis(
            asset_id=str(asset.id),
            asset_external_code=asset.external_code,
            day=fusion.day,
            anomaly_score=risk.anomaly_score,
            fusion_score=risk.fusion_score,
            smoothed_fusion_score=risk.smoothed_fusion_score,
            fusion_status=fusion.status,
            persistence_score=risk.persistence_score,
            risk_score=risk.risk_score,
            risk_level=risk.risk_level,
            provider_mode=self.mode,
        )

    def get_status(self) -> TEEStatus:
        return TEEStatus(
            mode=self.mode,
            healthy=True,
            description=(
                "Demo TEE provider: real in-process Phase 4-5 analysis, "
                "no hardware-backed execution."
            ),
        )

    def get_attestation_status(self) -> AttestationStatus:
        # HARD REQUIREMENT: demo NEVER attests. Constant False/None on all
        # paths -- no measurements, no enclave IDs, no crypto claims.
        return AttestationStatus(attested=False, pcr0=None)
