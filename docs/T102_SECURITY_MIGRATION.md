# T102 security migration

**Status:** Source-level hardening; physical execution remains unqualified.

The reviewed-motion bridge now derives exactly one T102 goal from the sealed
review. Callers must stop passing a goal list and supply an independently
approved physical T102 command profile before review construction. The
repository's synthetic profile cannot satisfy that requirement.

External native T102 authority records now include the exact `review_sha256`.
Both that review hash and `issuer_key_id` are covered by the Ed25519 signature.
Previously issued records and signatures cannot be reused. An independent
issuer must inspect the reviewed evidence and sign a fresh record with the
updated schema. Keep its private signing key outside the execution process.

The Windows serial adapter requires a process-local execution grant from the
native sink before it opens the pinned COM port. The sink checks the exact
`MotionPermit`, machine-pinned public keyring, and durable one-use ledger before
granting that open. The ledger spends the global authority ID first, so a
process crash cannot make it available to another consumption receipt.

## Physical deployment gate

Physical T102 execution remains blocked until all of these are reviewed and
installed:

1. An independent issuer and administrator-controlled public keyring.
2. A protected ledger service, or equivalent OS-enforced writer boundary,
   outside the application account's ability to edit or delete spent markers.
3. A dedicated execution identity with exclusive COM-device access and no
   untrusted Python code or plugins in its process.
4. Retained physical controller and command-path evidence for the hand target,
   speed, acceleration, and exact reviewed trajectory.
5. Fresh independent review and physical qualification of the current serial
   adapter. The archived ARM-054 packet describes an earlier candidate.

Validate the offline boundary with the native T102 unit and integration tests
and the full `scripts/ci/offline_checks.py test` gate. The tests do not replace
the OS access-control audit or real controller evidence.

## Rollback

Do not restore the former permissive serial or authority API while the T102 COM
device is accessible to the application account. If this change must be
reverted, first revoke that access and hold physical T102 execution. Retained
historical review packets remain immutable; they do not approve this adapter.
