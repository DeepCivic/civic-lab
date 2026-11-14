# Sanctions MCP (Australia)

An [MCP](https://modelcontextprotocol.io) server that screens people, organisations, vessels and
sponsors against two Australian sources, from **locally held, versioned snapshots**:

- the **DFAT Consolidated List** (sanctions designations), and
- the **ABF Register of Sanctioned Sponsors** (sponsors sanctioned for breaching their obligations).

> **Unofficial, and not legal advice.** sanctions-au is an independent tool, not affiliated with or
> endorsed by DFAT, the ABF or the Commonwealth. It returns *potential matches* with reasons. It never
> says a subject is or is not sanctioned, and "no match" does not clear anyone. See [Terms of use](#terms-of-use).

| Tool | Purpose |
| --- | --- |
| `screen_subject` | Screen one subject against DFAT, the ABF, or both. Name, aliases, date of birth, country, address, passport or other identifier, IMO, ABN/ACN, ABF date range. |
| `screen_batch` | Up to 100 subjects in one call, for onboarding, supplier review and rescreening. |
| `get_record` | The full stored record behind a match, including every DFAT alias. |
| `dataset_status` | Installed dataset versions, age, staleness, record counts and source hashes. |

## Quick start

1. Install [uv](https://docs.astral.sh/uv/), then fetch the data once (this is the only step that uses the network):

   ```bash
   SANCTIONS="uvx --from git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/sanctions-au sanctions-au"
   $SANCTIONS refresh
   ```

2. Add the server to your MCP client (`mcpServers` in Claude Desktop / Claude Code):

   ```json
   { "mcpServers": { "sanctions": { "command": "uvx", "args": ["--from",
     "git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/sanctions-au", "sanctions-au"] } } }
   ```

Screening makes **no network call**. Nothing about a subject leaves the machine, so it can run air-gapped:
refresh elsewhere, then copy the data directory (`SANCTIONS_DATA_DIR`) across.

## Refreshing the data

`sanctions-au refresh` fetches both sources, parses and checks them, and stores each as a new snapshot.
Run it on a schedule you control. `--source dfat|abf` does one. If a site refuses an automated download, save
the file in a browser and import it: `refresh --dfat-file FILE` (the `.xlsx`) or `--abf-file FILE` (the saved JSON response).

- **Versioned.** Each refresh that changes the data makes a new snapshot, `snapshots/<source>/<time>-<hash>/`, and its
  id is the `dataset_version` quoted in every result.
- **Immutable and traceable.** A snapshot holds the source file exactly as received, the parsed records and a
  `meta.json` with the SHA-256 of both, read-only once written. Nothing edits it afterwards.
- **A bad refresh changes nothing.** A changed layout, an unrecognised row, an empty result, or a drop to under half the
  current record count (a likely broken download; `--force` overrides) fails the refresh and leaves the current dataset
  untouched. A damaged snapshot fails its hash check on load and is reported, never screened against.
- **Staleness is measured from the last confirmation**, not the last change, so an unchanged list is not "stale" just
  because nothing was published. Warnings appear after 7 days (DFAT) and 35 days (ABF); override with
  `SANCTIONS_DFAT_MAX_AGE_DAYS` and `SANCTIONS_ABF_MAX_AGE_DAYS`.

## How matching works

Deterministic and rule-based: the same input and datasets always give the same result. No model, no learned
weights, no probability. Every match says why it was returned.

| Name tier | Rule |
| --- | --- |
| exact | Same name ignoring case, accents and punctuation; or ignoring company-type words (Pty, Ltd, Inc, ...); or the same words in a different order |
| words | Every word of the shorter name appears in the longer one (at least two words) |
| similar | Similar spelling (at least 90% of characters agree) |

**Confidence** is `high`, `medium` or `low`: a summary of how many independent checks agree, not a probability.
A name alone never reaches `high`. A matching identifier (IMO, passport number, ABN) does. Date-of-birth year, country
and address words each raise a name match one step. A contradiction (a birth year not among those listed, a different
citizenship, a different ABN) lowers it one step and is listed in `conflicts`. What could not be compared is listed in `notes`.

Each source returns one status: `potential_match`, `no_match`, `insufficient_information` (with what to add),
`not_applicable` (vessels are not on the ABF register) or `dataset_unavailable`. `overall` is `incomplete`, never
`no_match`, when any source could not be screened in full.

An abridged result:

```json
{ "overall": "potential_match",
  "dfat": { "status": "potential_match", "dataset_version": "dfat:20261114T102307Z-42e6b75747",
    "matches": [ { "confidence": "high", "confidence_basis": "agreeing on: country, date_of_birth, name; no conflicts found",
      "matched_on": [ { "field": "name", "method": "same name after ignoring case, accents and punctuation" } ],
      "conflicts": [], "record": { "id": "2", "name": "...", "type": "Individual" } } ] },
  "abf": { "status": "no_match", "dataset_version": "abf:..." },
  "warnings": ["The ABF updates its register monthly. A sponsor sanctioned recently may not appear yet."] }
```

## What the sources do and do not say

- **DFAT.** One listing has a primary name and any number of aliases and original-script names; aliases are screened too.
  Date of birth is free text ("Approximately 1963", ranges, several dates), so **only the year is compared**. Passport
  and other identifiers are free text inside `additional_information` and are matched as a substring, at least six
  characters long.
- **ABF.** The register updates **monthly**: a sponsor sanctioned recently may not appear yet. A trailing `*` on a
  sponsor name means an Administrative Review Tribunal review is pending; it is returned as `pending_review`. The register has no
  record id, so ids are hashes of the published row and change when the ABF edits it. ABN is a field; ACN is not,
  though the ABN field holds 9 digits (probably an ACN) on a few records, and an ACN match there is reported as unconfirmed.
- **Neither source is a complete picture of a person's or company's exposure.** Related parties, ownership and
  control are not in either dataset.

## Docker

The image holds no data and defaults to a stdio server:

```bash
docker run --rm -v sanctions-data:/data ghcr.io/deepcivic/sanctions-au refresh
```

```json
{ "mcpServers": { "sanctions": { "command": "docker",
  "args": ["run", "-i", "--rm", "--network", "none", "-v", "sanctions-data:/data:ro", "ghcr.io/deepcivic/sanctions-au"] } } }
```

`--network none` is safe because screening never needs the network. `serve --http` serves streamable HTTP
(stateless, `/mcp`) on `HOST:PORT`, loopback by default. **It has no authentication of its own**: put it behind your
platform's authentication.

## Terms of use

Unofficial software, provided as is. Confirm any match against the current DFAT and ABF publications before acting.
Check the reuse terms of both publications before redistributing data (see [NOTICE](NOTICE)).

## Development

```bash
cd mcp-servers/sanctions-au
uv venv && uv pip install -e ".[dev]"
uv run pytest        # synthetic, invented data only; no network
```
