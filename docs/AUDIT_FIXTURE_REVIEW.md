# Snapshot audit: reviewed synthetic fixtures

Reviewed September 26 and October 4, 2026, from baselines `317406a` and
`1ce97b1`.

The 15 reported credential-literal findings across 13 unit-test files
are deliberate synthetic inputs for redaction and malformed-feedback tests.
Review included the surrounding assertions: they verify removal, rejection,
redacted restoration, or withholding of an original-byte preservation claim.
No real credential was identified among these 15 findings. That statement is not
a claim that the entire repository or its history contains no secrets.

The tests remain unchanged. Their exact exceptions are recorded with individual
reasons in [audit_fixture_reviews.json](../scripts/audit_fixture_reviews.json).
The manifest stores no matched values. The audit still prints the locations as
`REVIEWED synthetic fixture` rather than silently hiding them.

## Exception boundaries

Each exception binds an exact unit-test path, the credential-literal rule, SHA-256
of the complete source line (excluding its line ending), and one expected match.
Moving lines within the same file is allowed; changing their content is not.
Additional matches, changed content, and missing/stale exceptions fail the audit.
Invalid or missing manifests also fail. Exceptions cannot target production files,
archive members, private-key rules, token rules, or whole folders.

Do not regenerate this manifest automatically to make an audit pass. Review the
test and its assertions, document why the value is synthetic, and submit an
explicit manifest change through a PR. Do not put real credentials into test
fixtures. If an actual secret is discovered, handle revocation and exposure
review separately rather than adding an exception.

## Verification and limitations

Run `python scripts/audit_github_snapshot.py` from the checkout. Exit zero means
no unresolved findings under the scanner's current rules, not security certification.
The scanner remains heuristic: it scans the current Git-listed snapshot, not Git
history; it skips some binary/large content and does not recursively unpack nested
archives. The existing pattern scope is unchanged.

The hardware-free `test_snapshot_audit.py` regression tests cover exact matches,
line endings, changed values, duplicate matches, different files, archive labels,
stale entries, malformed manifests, token detection, and value-free output.
They are included in the existing CI selection. Full snapshot scanning remains a
separate review; CI does not represent that full scan as a security gate.
