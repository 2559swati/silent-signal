"""Phase 11+12 TEE provider factory.

Selects the provider from the TEE_MODE environment variable:

    TEE_MODE=demo (or missing) -> DemoTEEProvider (safe default)
    TEE_MODE=nitro             -> NitroTEEProvider (Phase 12: encrypted
                                  telemetry over framed (v)sock transport,
                                  existing fusion/risk logic in-enclave)

Unsupported modes fail loudly instead of silently pretending to be a
real provider. Nitro mode NEVER falls back to demo: transport/attestation
failures raise and are surfaced as errors.
"""

import os

from app.core.config import settings
from app.tee.base import TEEProvider
from app.tee.demo import DEMO_MODE, DemoTEEProvider
from app.tee.nitro import NITRO_MODE

SUPPORTED_MODES = frozenset({DEMO_MODE, NITRO_MODE})


class UnsupportedTEEModeError(ValueError):
    """Raised when TEE_MODE names a provider this build cannot supply."""


def resolve_mode() -> str:
    """Effective TEE mode: env TEE_MODE, else app settings, else 'demo'."""
    return (os.environ.get("TEE_MODE") or settings.TEE_MODE or DEMO_MODE).strip().lower()


def get_provider(mode: str | None = None) -> TEEProvider:
    """Return the provider for `mode` (default: resolved TEE_MODE)."""
    selected = (mode or resolve_mode()).strip().lower()
    if selected == DEMO_MODE:
        return DemoTEEProvider()
    if selected == NITRO_MODE:
        # Import here so a broken nitro module surfaces as a loud error,
        # never as a silent demo fallback.
        try:
            from app.tee.nitro import NitroTEEProvider
        except Exception as exc:
            raise UnsupportedTEEModeError(
                f"TEE_MODE='nitro' requested but NitroTEEProvider is unavailable: {exc}"
            ) from exc
        return NitroTEEProvider()
    raise UnsupportedTEEModeError(
        f"Unsupported TEE_MODE={selected!r}. Supported modes: {sorted(SUPPORTED_MODES)}."
    )
