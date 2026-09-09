# pyrefly: ignore [missing-import]
"""Phase 13 tests: KMS key policy + attestation-gated decryption (LOCAL).

Everything here runs locally: policy-file validation (real AWS condition
keys, valid JSON, least privilege, placeholder honesty) and the guarantee
that no local code path can fake attestation. Real allow/deny behavior
requires an AWS KMS key + Nitro EC2 host and is marked requires_kms /
requires_nitro (skipped locally, never claimed as passed).
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.tee import kms as kms_mod  # noqa: E402
from app.tee.kms import (  # noqa: E402
    PLACEHOLDER_MARKER,
    RequiresAWSKMS,
    decrypt_data_key,
    is_placeholder,
    load_policy,
    policy_condition_keys,
    policy_pins_pcr0,
    validate_pcr0_format,
)
from app.tee.nitro import NitroTEEProvider  # noqa: E402

POLICY_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "infra", "kms-key-policy.json")
)

# Condition keys documented by AWS for Nitro Enclave attestation
# (KMS Developer Guide: "Condition keys for Nitro Enclaves").
ALLOWED_ATTESTATION_KEYS = {
    "kms:RecipientAttestation:ImageSha384",
} | {f"kms:RecipientAttestation:PCR{i}" for i in range(9)}

REAL_PCR0_EXAMPLE = "a" * 96  # 96 lower-case hex chars: plausible PCR0 shape


def test_policy_is_valid_json_with_statements():
    policy = load_policy(POLICY_FILE)
    assert policy["Version"] == "2012-10-17"
    assert isinstance(policy["Statement"], list) and policy["Statement"]
    # File on disk parses identically (no hidden divergence).
    with open(POLICY_FILE, "r", encoding="utf-8") as fh:
        assert json.load(fh) == policy


def test_policy_uses_only_real_condition_keys():
    """No invented condition keys: every kms:* key must be AWS-documented."""
    policy = load_policy(POLICY_FILE)
    keys = policy_condition_keys(policy)
    assert "kms:RecipientAttestation:PCR0" in keys
    assert "kms:RecipientAttestation:ImageSha384" in keys
    unknown = {k for k in keys if k not in ALLOWED_ATTESTATION_KEYS}
    assert not unknown, f"invented/undocumented condition keys: {unknown}"


def test_policy_uses_case_insensitive_pcr_comparison():
    """PCR hex digests must compare with StringEqualsIgnoreCase (AWS docs)."""
    policy = load_policy(POLICY_FILE)
    found = False
    for stmt in policy["Statement"]:
        condition = stmt.get("Condition", {})
        for op, mapping in condition.items():
            if isinstance(mapping, dict) and any(
                k.startswith("kms:RecipientAttestation:") for k in mapping
            ):
                assert op == "StringEqualsIgnoreCase", f"operator {op!r} is wrong"
                found = True
    assert found


def test_policy_least_privilege():
    """The enclave statement allows kms:Decrypt only -- no kms:*, no extras."""
    policy = load_policy(POLICY_FILE)
    for stmt in policy["Statement"]:
        condition = stmt.get("Condition", {})
        is_enclave_stmt = any(
            isinstance(m, dict)
            and any(k.startswith("kms:RecipientAttestation:") for k in m)
            for m in condition.values()
        )
        if not is_enclave_stmt:
            continue
        actions = stmt["Action"] if isinstance(stmt["Action"], list) else [stmt["Action"]]
        assert "kms:Decrypt" in actions
        assert "kms:*" not in actions
        for unrelated in ("kms:Encrypt", "kms:CreateKey", "kms:PutKeyPolicy",
                          "kms:GenerateDataKey", "kms:GenerateRandom",
                          "kms:ScheduleKeyDeletion", "iam:*", "s3:*"):
            assert unrelated not in actions, f"unrelated permission {unrelated}"


def test_policy_placeholder_is_honest():
    """Checked-in policy authorizes NOTHING: placeholder, clearly labelled."""
    with open(POLICY_FILE, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert PLACEHOLDER_MARKER in text
    assert "REPLACE_WITH_REAL_PCR0" in text
    # No real-looking PCR0 hex digest is pinned anywhere in the file.
    assert not re.search(r"\b[0-9a-f]{96}\b", text), "a real-looking PCR0 is pinned!"
    assert is_placeholder("REPLACE_WITH_REAL_PCR0_FROM_APPROVED_EIF")
    assert not is_placeholder(REAL_PCR0_EXAMPLE)
    assert not validate_pcr0_format("REPLACE_WITH_REAL_PCR0_FROM_APPROVED_EIF")


def test_pcr0_format_validation():
    assert validate_pcr0_format(REAL_PCR0_EXAMPLE)
    assert validate_pcr0_format("B" * 96) is False  # upper-case is not canonical
    for bad in ("", "xyz", "a" * 95 + "G", None, 123):
        assert validate_pcr0_format(bad) is False  # type: ignore[arg-type]


def test_policy_pins_pcr0_lookup():
    policy = load_policy(POLICY_FILE)
    # Placeholder value is not a trusted measurement.
    assert policy_pins_pcr0(policy, REAL_PCR0_EXAMPLE) is False
    pinned = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Condition": {"StringEqualsIgnoreCase": {
                "kms:RecipientAttestation:PCR0": REAL_PCR0_EXAMPLE}},
        }],
    }
    assert policy_pins_pcr0(pinned, REAL_PCR0_EXAMPLE) is True
    assert policy_pins_pcr0(pinned, "b" * 96) is False


def test_decrypt_refuses_without_hardware():
    """Local decrypt_data_key NEVER returns key material: no fake gating."""
    with pytest.raises(RequiresAWSKMS):
        decrypt_data_key(key_id="arn:aws:kms:eu-west-1:123456789012:key/abc")


def test_no_local_pcr0_string_check_grants_attestation(monkeypatch):
    """Even the 'right' PCR0 string must not flip attested to True locally."""
    monkeypatch.delenv("NITRO_REAL_PCR0", raising=False)
    monkeypatch.setenv("NITRO_PCR0", REAL_PCR0_EXAMPLE)
    att = NitroTEEProvider().get_attestation_status()
    assert att.attested is False  # placeholder shape, still unverified


def test_kms_module_has_no_credentials_or_telemetry():
    """Static guard: kms.py must not embed secrets or log telemetry."""
    with open(kms_mod.__file__, "r", encoding="utf-8") as fh:
        src = fh.read().lower()
    for banned in ("akia", "aws_secret", "aws_secret_access_key", "private_key",
                   "plaintext telemetry", "print("):
        assert banned not in src, f"kms.py contains {banned!r}"


@pytest.mark.requires_kms
def test_real_kms_allow_for_approved_eif():
    pytest.skip("REQUIRES AWS KMS: attested Decrypt with approved-EIF PCR0 needed")


@pytest.mark.requires_kms
def test_real_kms_deny_for_unapproved_eif():
    pytest.skip("REQUIRES AWS KMS: unapproved EIF / missing attestation must be denied")
