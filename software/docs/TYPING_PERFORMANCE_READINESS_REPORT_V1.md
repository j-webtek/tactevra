# Typing Performance Readiness Report V1

## Scope and disposition

PC8 is complete as a synthetic, zero-I/O performance qualification. The
retained campaign contains 450 observations: 50 iterations for each of nine
required scenarios. It opened no transport, generated no controller command,
and had no physical authority. It does not establish real typing speed,
installed-workcell safety, contact reliability, or controller tracking.

The canonical report is
`software/ai/eval/typing_performance_report_v1.json`. Its embedded content
SHA-256 is
`a43a25056cff135d8756fbe7b15160b7a9ad0b49964e21e0c16a6c5eb2df291c`;
the retained file SHA-256, including its final newline, is
`024c5111810e9d0a5b67ea78389d2c7e5d19041ba31960fb3fcb495be98f74f6`.

These identities reflect the later FREEZE-013 qualification-basis rebind in
commit `baa5745a966284bb94204307f1d37994e4e5bf3c`. The retained measurements
and dispositions did not change. The earlier identities remain in the
append-only evidence ledger as historical evidence from the original PC8
retention; they are not the identities of the current canonical file.

## Measured software results

| Measure | Retained result | Interpretation |
|---|---:|---|
| Observations | 450 | 50 per required scenario |
| Total process CPU p50 / p95 / p99 | 2.766 / 9.094 / 10.000 s | Offline planning-path CPU, not wall-clock typing speed |
| IK CPU p50 / p95 / p99 | 2.641 / 8.953 / 9.859 s | Dominant measured software bottleneck |
| Peak process working set | 72.99 MiB | Passes the 256 MiB PC0 ceiling |
| Maximum action count | 16 | Passes the 128-action PC0 ceiling |
| Maximum collision samples | 178 | Passes the 4,096-sample PC0 ceiling |
| Maximum serialized receipt | 1,522 bytes | Passes the 2 MiB PC0 ceiling |
| Cold misses / warm revalidated hits | 50 / 50 | Cache scenario accounting is complete |
| Forced rejections | 50 of 50 | Malformed inputs fail before later stages |

Preview validation and encoding correctly measure zero in this campaign. The
honest installed-collision-evidence boundary blocks the shadow route before
either stage, so inventing downstream timing would be misleading.

## Route-packaging result

For the identical synthetic `ROBOT` target sequence, the direct-hover route has
a predicted median duration of 11.657399955 seconds and the park-between-keys
baseline has a predicted median duration of 12.807750444 seconds. The direct
route is 8.98 percent shorter under the frozen simulation assumptions. This is
a trajectory-duration prediction only; it is not a measured arm movement or a
typing-rate claim.

The optimization is retained because it changes route packaging rather than
bypassing admission. Fresh validation, IK, collision evidence, dynamics, permit
policy, and execution authority remain mandatory downstream.

## Bottleneck and next optimization order

IK dominates measured CPU and should be the first software optimization target.
Any proposed acceleration must preserve byte-equivalent receipts and schedule
hashes under the existing cache-equivalence, replay, fault, and property tests.
The next useful work is therefore profiling and bounded optimization of IK
candidate generation or reuse—not weakening geometry or safety checks.

No additional synthetic speed claim can close the operational gate. Physical
readiness still requires installed collision geometry, measured camera/board/
robot/tool transforms, observed current state, controller tracking and settling
evidence, contact/debounce qualification, and independent outcome verification.

## Reproduction and verification

Run the campaign once in a clean workspace where the report does not already
exist:

```text
python software/scripts/run_typing_performance_campaign_v1.py --iterations 50
```

The generator refuses to overwrite retained evidence. Repository tests bind
the exact file and embedded hashes, all scenario counts, all resource ceiling
dispositions, direct-versus-park ordering, forced rejection, and zero authority.
