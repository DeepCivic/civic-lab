# GLEIF: what the Go server got wrong, and what this server does instead

The GLEIF tools in sanctions-au are a Python rebuild of
[olgasafonova/gleif-mcp-server](https://github.com/olgasafonova/gleif-mcp-server) (MIT). This page
records the defects found in it, so they are not reintroduced and can be reported upstream.

Two kinds of statement appear below. **Provided by the project owner** is their account of a patch
they built and ran against the Go server, which this repository has not re-run. **Checked here** is
something observed directly against `api.gleif.org` on 2026-11-14, or read in the Go source at commit
`02660b5`. The owner's notes refer to the pinned v0.9.0 commit `3ae59c4`, which was not read here;
the code at `02660b5` has the same wrong URL.

## `get_reporting_exceptions` (provided by the project owner)

The patch fixes the pinned gleif MCP server v0.9.0 (commit `3ae59c4`) so that `get_reporting_exceptions`
returns the reporting exceptions GLEIF actually holds. Before the patch it returned `not_found` for every LEI.

**What was wrong upstream**

1. **Wrong URL.** It requested `/lei-records/{lei}/reporting-exceptions`. GLEIF doesn't serve that path and
   returns an HTML "Not Found" page. GLEIF serves two single resources instead:
   `/direct-parent-reporting-exception` and `/ultimate-parent-reporting-exception`.
2. **Wrong field names.** It decoded GLEIF's response into fields named `exceptionCategory` and
   `exceptionReason`. GLEIF sends `category`, `reason` and `reference`. Fixing only the URL would still have
   returned empty reasons.
3. **The test hid it.** The upstream test mocked the same wrong URL with an empty, list-shaped answer and never
   checked the reason, so it passed.

**What the patch changes** (2 files, +40/-14)

- `internal/gleif/client_relationships.go`: requests both GLEIF endpoints and decodes each answer with GLEIF's
  own field names. A 404 on one endpoint means that kind of exception isn't filed, so it is skipped. Any other
  error is returned as before. If neither endpoint has an exception, it still returns `not_found`, as upstream
  did, which keeps the error unchanged for callers. The tool's output keys (`count`, `exceptions[].exceptionCategory`,
  `exceptionReason`) are unchanged, so `calls.exception_reason` reads the result as it is.
- `tools/handlers_test.go`: the mock now serves GLEIF's real response shape on the real paths and returns 404
  elsewhere. The test now asserts that both exceptions come back with `NATURAL_PERSONS`.

**Checks the owner ran:** built in a `golang:1.25` container on host podman, with `gofmt` and `go vet` clean and
`go test ./...` passing. Live against GLEIF on the 25 no-parent LEIs in their plan: before the patch all 25 returned
`not_found`; after it, all 25 return both exceptions, and the reason matches the register's for every one (7
NATURAL_PERSONS, 12 NON_CONSOLIDATING, 3 NON_PUBLIC, 3 NO_KNOWN_PERSON).

**Limits stated by the owner**

- `not_found` still means two different things: the LEI doesn't exist, or it exists and simply has no exception
  filed (for example, because it reports a parent). That is upstream's existing behaviour, left as it was.
- The `golang:1.25` build image is referenced by tag, not pinned by digest, because this was a throwaway local build.
- Nothing is committed. The source and built binary are in the gitignored `tools/mcp/vendor/gleif-patch/`.
  `tools/mcp/gleif.yaml` still pins the unpatched release, and the container image the harness runs is still the
  unpatched one. Adopting the patch means building from source at the pinned commit plus this patch, recording it as a
  local modification, and reporting it upstream.

**How the Python server handles it.** It never had the bug: `Client.reporting_exceptions` requests the two real
endpoints, skips a 404 on either, returns any other error, and raises `not_found` only when neither is filed. It
keeps the Go server's output keys (`count`, `exceptions[].exceptionCategory`, `exceptionReason`) and adds
`exceptionReference` from GLEIF's `reference`. It keeps the same `not_found` contract and does not try to tell
an unknown LEI from one that files no exception; the message now says both are possible. The tests
(`tests/test_gleif.py`) serve GLEIF's real shapes on the real paths, assert the reasons, and assert that the combined
path is never requested.

**Checked here (2026-11-14).** `GET /lei-records/{lei}/reporting-exceptions` returned 404 for a known LEI. This
returned a JSON error body, not the HTML page described above; the finding is the same. Both
`/direct-parent-reporting-exception` and `/ultimate-parent-reporting-exception` returned 200 for the same LEI, with
`attributes.category`, `attributes.reason` and `attributes.reference` (plus `validFrom`, `validTo`, `lei`), and reason
`NATURAL_PERSONS`. The Python client's `reporting_exceptions` returned both against the live API.

## Other differences found while rebuilding (checked here, not reported by the owner)

| Go server | Finding | Python server |
| :--- | :--- | :--- |
| `search_by_isin` asks `/lei-issuer?filter[isin]=...` first | That path returned 404 live for a valid ISIN. The Go code only works because it falls back to `/lei-records?filter[isin]=...`, which returned the issuer | Uses `/lei-records?filter[isin]=` only |
| `get_relationships` decodes `relationshipType`, `relationshipStatus` and `relationshipPeriods[].periodType` | GLEIF sends `type`, `status` and `periods[].type`. Reading the struct tags against a live response, those fields would decode empty. This was inferred from the source; the Go server was not run | Maps GLEIF's fields into the same output keys, filled |
| `search_by_bic` passes an 8-character BIC unchanged | GLEIF stores BICs in 11-character form: `CHASUS33` returned 0 results and `CHASUS33XXX` returned the bank | Tries the 11-character primary-office form first, then the 8-character form |
| `validate_lei` returns `valid: false` when GLEIF cannot be reached | Reading the source: a reachable-but-bad LEI and an unreachable registry look the same | Adds `format_valid` and `registry_checked`, so `valid: false` with `registry_checked: false` means "could not check" |
| `get_relationships` returns an unqualified `not_found` for an LEI with no parent | Apple's LEI has no parent relationship (404) and files reporting exceptions instead | Same error, with the message pointing to `get_reporting_exceptions` |

## Where the Python server is deliberately different

- **Off by default.** Sanctions screening never leaves the machine, which the requirement it was built for depends
  on. GLEIF lookups send names and LEIs to `api.gleif.org`, so every GLEIF tool refuses to run until the operator sets
  `SANCTIONS_ENABLE_GLEIF=1`. `validate_lei` still checks format and check digits offline when off.
- No single-flight collapsing of concurrent identical requests (the Go server has it). Requests share a token-bucket
  rate limiter, retries with backoff, and a TTL cache that copies values in and out, so the rate limit still holds.
- The LEI record returns `lei`, `entity` and `registration` as GLEIF sends them, rather than a fixed projection.
- `list_lei_issuers` asks GLEIF for 200 per page. Today GLEIF lists 41 issuers.

## Not verified

- GLEIF's terms of use for the data. Check them before redistributing results.
- The owner's Go patch and their 25-LEI run, which are as reported above.
- Behaviour of the fund-manager, umbrella-fund and sub-fund relationship endpoints, which were ported from the Go
  server's paths and not exercised live.
