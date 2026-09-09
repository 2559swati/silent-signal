"""Phase 13 attestation-gated decryption (AWS KMS + Nitro attestation).

Security model (real AWS mechanism, no local fakes):

    Enclave -> signed attestation document (PCRs incl. PCR0 = EIF image
              digest) -> parent vsock proxy -> KMS Decrypt with the
              `Recipient` attestation document -> KMS compares the document
              PCRs against kms:RecipientAttestation:PCR* / ImageSha384
              condition keys in infra/kms-key-policy.json ->
              matching (approved EIF) ALLOWED, anything else DENIED.

What this module does and does NOT do:
- Local helpers ONLY: load/inspect the key policy file, validate PCR0
  placeholder format, and check whether a PCR0 value is pinned in the
  policy. These NEVER decide trust -- KMS decides on real hardware.
- `decrypt_data_key()` documents the production call path and raises
  RequiresAWSKMS locally: there is deliberately NO local code path that
  "approves" a PCR0 string comparison as attestation (that would be fake).
- No AWS credentials live here or in the enclave. The enclave never calls
  KMS directly; the parent instance calls KMS over its normal network path
  (IAM role on the parent) with the enclave attestation attached via the
  Nitro Enclaves SDK / vsock proxy. See infra/README-attestation.md.
"""

import json
import os
import re

# Placeholder marker: the checked-in policy pins no real measurement until
# an approved EIF is built and its PCR0 recorded via `nitro-cli describe-eif`.
PLACEHOLDER_MARKER = "REPLACE_WITH_REAL_PCR0"

# KMS key policy location (repo-relative default).
DEFAULT_POLICY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "infra", "kms-key-policy.json"
)

# PCR values are lower-case hex digests (SHA-384 PCRs are 96 hex chars).
_PCR_HEX_RE = re.compile(r"^[0-9a-f]{48,256}$")


class RequiresAWSKMS(RuntimeError):
    """Attestation-gated KMS decryption needs real AWS (key + Nitro host)."""


def is_placeholder(value: str | None) -> bool:
    """True when a PCR slot still holds the checked-in placeholder."""
    return not value or PLACEHOLDER_MARKER in value


def validate_pcr0_format(pcr0: str) -> bool:
    """Loose format check for a PCR0 hex digest (NOT an attestation check).

    Returns True for plausible lower-case hex digests. Placeholders and
    garbage return False. Passing this says nothing about trust.
    """
    if not isinstance(pcr0, str):
        return False
    return bool(_PCR_HEX_RE.match(pcr0.strip()))


def load_policy(path: str | None = None) -> dict:
    """Load and JSON-validate the KMS key policy file."""
    resolved = os.path.abspath(path or DEFAULT_POLICY_PATH)
    with open(resolved, "r", encoding="utf-8") as fh:
        policy = json.load(fh)
    if not isinstance(policy, dict) or "Statement" not in policy:
        raise ValueError(f"KMS policy at {resolved} is not a policy document")
    return policy


def policy_condition_keys(policy: dict) -> set[str]:
    """All kms:RecipientAttestation:* condition keys used in the policy."""
    keys: set[str] = set()
    for stmt in policy.get("Statement", []):
        condition = stmt.get("Condition", {})
        for _op, mapping in condition.items():
            if isinstance(mapping, dict):
                keys.update(k for k in mapping if str(k).startswith("kms:"))
    return keys


def policy_pins_pcr0(policy: dict, pcr0: str) -> bool:
    """Whether the policy pins exactly this PCR0 value.

    LOCAL policy-inspection helper for operators/tests. NOT attestation:
    the real allow/deny decision is made by KMS on hardware.
    """
    target = (pcr0 or "").strip().lower()
    for stmt in policy.get("Statement", []):
        condition = stmt.get("Condition", {})
        for _op, mapping in condition.items():
            if not isinstance(mapping, dict):
                continue
            for key, value in mapping.items():
                if key in ("kms:RecipientAttestation:PCR0",
                           "kms:RecipientAttestation:ImageSha384"):
                    pinned = value if isinstance(value, list) else [value]
                    if any(str(v).strip().lower() == target for v in pinned):
                        return True
    return False


def decrypt_data_key(*, key_id: str | None = None) -> bytes:  # noqa: ARG001
    """Production path: attestation-gated KMS Decrypt of the data key.

    On the Nitro parent this is performed with the enclave attestation
    document attached as the KMS `Recipient` (Nitro Enclaves SDK
    `kms-decrypt` over the vsock proxy), authorized by the KMS key policy.
    Locally there is no attestation document and no KMS key, so this
    ALWAYS raises RequiresAWSKMS -- it never returns a key and never
    approves a local PCR0 string as "attested".
    """
    raise RequiresAWSKMS(
        "Attestation-gated KMS decryption requires a real AWS KMS key and "
        "a Nitro Enclave host (see infra/README-attestation.md). "
        "Refusing to return key material without hardware attestation."
    )
