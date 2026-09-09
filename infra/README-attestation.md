# Phase 13 — KMS + Attestation-Gated Decryption

Only an approved Nitro Enclave image (pinned PCR0) may use the KMS key to
decrypt the telemetry data key. Any other image — or any caller without a
valid attestation document — is denied by KMS itself, not by our code.

## 1. KMS key setup

```bash
aws kms create-key --description "SilentSignal Nitro enclave data key"
# Note the KeyId / Arn, then attach the policy:
aws kms put-key-policy \
  --key-id <KeyId> \
  --policy-name default \
  --policy file://infra/kms-key-policy.json
```

`infra/kms-key-policy.json` is the source of truth. It uses the real AWS
condition keys `kms:RecipientAttestation:PCR0` and
`kms:RecipientAttestation:ImageSha384` (both = the EIF image digest, PCR0)
under `StringEqualsIgnoreCase`, exactly as documented in
“Condition keys for Nitro Enclaves” (KMS Developer Guide). Least
privilege: the enclave statement allows only `kms:Decrypt` for the parent
role; admin stays with the account root.

## 2. IAM permissions required

- Parent EC2 instance profile / role (default name in the policy:
  `silentsignal-nitro-parent`) must be allowed `kms:Decrypt` on the key.
  The attestation condition means the permission is usable ONLY with a
  matching attestation document — no separate IAM restriction needed.
- Operators who update the policy need `kms:PutKeyPolicy` on the key.
- No AWS credentials are placed inside the enclave image, ever.

## 3. Nitro Enclave attestation flow

1. Enclave boots from the approved EIF (PCR0 = image digest).
2. Enclave requests its signed attestation document (NSM device).
3. Parent calls KMS `Decrypt` with the attestation document in the KMS
   `Recipient` field (Nitro Enclaves SDK `kms-decrypt` via the vsock
   proxy — the enclave has no network and no credentials).
4. KMS validates the document signature, compares PCRs against the key
   policy condition keys, and returns plaintext only on match
   (`CiphertextForRecipient`; `Plaintext` is empty for attested calls).

## 4. PCR0 retrieval

```bash
nitro-cli describe-eif --eif-path silentsignal-enclave.eif
# Output "Measurements" -> PCR0 (also ImageSha384) for THIS exact EIF.
```

(`nitro-cli describe-eif --eif-path <file>` is the documented syntax.)

## 5. How PCR0 maps to the approved EIF

PCR0 is the SHA-384 digest of the enclave image file. One exact EIF
build = one PCR0. The value pinned in the KMS policy IS the approved
release: only enclaves booted from that byte-identical image produce an
attestation document that satisfies the policy.

## 6. How the KMS policy uses the trusted measurement

```json
"Condition": {
  "StringEqualsIgnoreCase": {
    "kms:RecipientAttestation:PCR0": "<real PCR0>",
    "kms:RecipientAttestation:ImageSha384": "<real PCR0>"
  }
}
```

KMS enforces this when the request carries an enclave attestation
document as `Recipient`. Requests without an attestation document cannot
satisfy the condition and are denied.

## 7. What happens when PCR0 matches

KMS returns the decrypted data key (as `CiphertextForRecipient`,
decryptable only inside the attested enclave). The parent forwards
data-key-encrypted telemetry over vsock; the enclave decrypts in memory
and returns only the minimal result
(`asset_id / risk / score / action / ...`).

## 8. What happens when PCR0 does not match

KMS denies `Decrypt` (`AccessDeniedException`). The parent surfaces a
loud error (`NitroTransportError` / HTTP 500 on the security endpoints).
There is NO fallback to demo mode and NO local string comparison that
could “approve” an untrusted image.

## 9. How to update the policy after rebuilding the EIF

Rebuilding the EIF changes PCR0, so the old policy value stops matching
(this is by design — a changed image is NOT the approved image until
re-approved):

```bash
nitro-cli describe-eif --eif-path silentsignal-enclave.eif
# copy the new PCR0 into infra/kms-key-policy.json (both PCR0 and
# ImageSha384 entries), commit, then:
aws kms put-key-policy \
  --key-id <KeyId> \
  --policy-name default \
  --policy file://infra/kms-key-policy.json
```

Treat the new EIF like a release: review the image diff, then pin.

## 10. How to test successful decryption (requires EC2 Nitro + KMS)

On the parent, with the approved enclave running:

```bash
# EncryptedSmokeTest via the Nitro Enclaves SDK kms-decrypt helper or:
aws kms decrypt \
  --key-id <KeyId> \
  --ciphertext-blob fileb://data-key.encrypted \
  --recipient ...attestation-document...
# Expect: CiphertextForRecipient present, decryptable in-enclave.
```

End-to-end: `TEE_MODE=nitro NITRO_TRANSPORT=vsock` backend call for a
known asset (e.g. SL-1042) must return the same risk level the demo
provider computes, with `/api/security/attestation` reporting the
hardware-verified PCR0.

## 11. How to test denied decryption (requires EC2 Nitro + KMS)

- Boot an enclave from a DIFFERENT (unapproved) EIF and repeat the call:
  KMS must deny (`AccessDeniedException`).
- Or call `kms:Decrypt` WITHOUT an attestation document: denied, because
  the `kms:RecipientAttestation:*` condition cannot be satisfied.
- Locally: `backend/app/tee/kms.py::decrypt_data_key` always raises
  `RequiresAWSKMS`, and `get_attestation_status()` reports
  `attested=False` — the code never claims attestation without hardware.

## 12. Which steps require actual EC2 Nitro hardware / AWS

| Step | Requires |
| --- | --- |
| `nitro-cli build-enclave` (Linux), `run/describe/terminate` | Nitro EC2 parent |
| `describe-eif` PCR0 readout | Built EIF (Linux ok) |
| Real attestation document (`/dev/nsm`) | Nitro EC2 + running enclave |
| KMS attested `Decrypt` allow/deny | AWS KMS key + Nitro host |
| `backend/tests/test_phase13_kms.py` | Local only (policy validation) |
| `decrypt_data_key()` success path | EC2 Nitro + KMS (raises locally) |

The checked-in policy pins the placeholder
`REPLACE_WITH_REAL_PCR0_...` — it authorizes NOTHING until replaced with
the real approved-EIF PCR0. Never report “PCR0 verified” until KMS has
actually allowed an attested decrypt on hardware.
