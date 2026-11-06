# ABR MCP

<!-- mcp-name: io.github.DeepCivic/abr-mcp -->

An [MCP](https://modelcontextprotocol.io) server that gives any LLM client
reliable access to **Australian Business Register** (ABN Lookup) data.

> **Unofficial.** abr-mcp is an independent client. It is not affiliated with,
> endorsed or approved by the Australian Business Register (ABR), the ATO or
> the Commonwealth of Australia. See [Terms of use](#terms-of-use).

| Tool | Purpose |
| --- | --- |
| `validate_abn` / `validate_acn` | Offline format and check-digit validation, with diagnostics for spreadsheet damage. |
| `lookup_abn` | Full ABR record for one ABN: status, entity name/type, ACN, GST, DGR, business names, location. |
| `lookup_abns` | Validate and look up up to 1,000 ABNs in one call, for joining a dataset to the register. |
| `lookup_acn` | ABN record(s) for a company's ACN. |
| `search_names` | Candidate ABNs for a name (exact normalised match, then all-words prefix match). |
| `register_status` | Which backends are available, extract date/age, completeness, licence. |
| `explain_codes` | ABN/GST status, name-type, state and entity-type code tables. |

## Quick start

1. Register for your own free ABN Lookup web services GUID at
   [abr.business.gov.au/Tools/WebServices](https://abr.business.gov.au/Tools/WebServices).
   The ABR emails you the GUID, a key that looks like
   `1a2b3c4d-1234-5678-9abc-def012345678`. Every web-service method requires
   one. (You don't need one to search the ABN Lookup *website*, but that
   isn't an API.) No GUID yet? The validation tools work without one, and the
   [offline index](#offline-index-optional) needs none.
2. Add the server to your MCP client. It needs [uv](https://docs.astral.sh/uv/);
   `uvx` fetches and runs the server, with no separate install step.

**Claude Desktop / Claude Code** (`mcpServers`):

```json
{
  "mcpServers": {
    "abr": {
      "command": "uvx",
      "args": ["abr-mcp"],
      "env": { "ABR_GUID": "your-guid" }
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "abr": {
      "command": "uvx",
      "args": ["abr-mcp"],
      "env": { "ABR_GUID": "${input:abr_guid}" }
    }
  },
  "inputs": [{ "id": "abr_guid", "type": "promptString", "description": "ABN Lookup GUID", "password": true }]
}
```

Until the package is on PyPI, replace `"args": ["abr-mcp"]` with
`"args": ["--from", "git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/abr-mcp", "abr-mcp"]`.

**Claude Desktop one-click install:** download `abr-mcp-<version>.mcpb` from
the [releases](https://github.com/DeepCivic/civic-lab/releases) and open it.
Desktop asks for the GUID and stores it securely.

The validation tools work with no GUID and no index.

## Offline index (optional)

For offline use, bulk joins, or freedom from web-service rate limits, build a
local index from the weekly [ABN Bulk Extract](https://data.gov.au/data/dataset/abn-bulk-extract):

```bash
uvx abr-mcp update-index     # ~1 GB download, ~15 min build, ~7 GB index
uvx abr-mcp status
```

`update-index` downloads the extract from data.gov.au, builds the index and
deletes the download. If the published extract hasn't changed since the last
build, it does nothing, so it is safe to run on a schedule (for example, a
weekly cron job). The index goes to `$ABR_INDEX_PATH`, or by default
`~/.local/share/abr-mcp/abr.sqlite` (`%LOCALAPPDATA%\abr-mcp\abr.sqlite` on
Windows).

With both backends configured, the default `source="auto"` answers from the
index and falls back to the live service for ABNs newer than the extract.
`source="local"` and `source="web"` force one backend.

What a build guarantees:

- **Atomic.** The index is written to a temporary file and moved into place
  only when every check passes. A failed build leaves the old index working.
- **Verified.** Each file's parsed record count must match its declared
  `RecordCount`, so a truncated download fails loudly.
- **Complete, or labelled partial.** All 20 extract files are required.
  `build-index --allow-partial` accepts gaps, and lookups then report "not in
  this partial index" instead of implying the ABN is unregistered.
- **One row per ABN.** If an ABN appears twice, the latest record wins.

`abr-mcp download DIR` and `abr-mcp build-index PATH...` do the two steps
separately, for zips or XML files you already have.

On Windows, stop the server before rebuilding the index, because Windows can't
replace a file that is open.

## Docker

The image holds no data and defaults to a stdio server, like the
[reference servers](https://github.com/modelcontextprotocol/servers). A named
volume holds the index:

```bash
docker run --rm -v abr-data:/data ghcr.io/deepcivic/abr-mcp update-index   # optional
```

```json
{
  "mcpServers": {
    "abr": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "ABR_GUID", "-v", "abr-data:/data:ro", "ghcr.io/deepcivic/abr-mcp"],
      "env": { "ABR_GUID": "your-guid" }
    }
  }
}
```

## Remote (streamable HTTP)

```bash
abr-mcp serve --http                                     # 127.0.0.1:8000/mcp
docker run --rm -p 8000:8000 -v abr-data:/data:ro ghcr.io/deepcivic/abr-mcp serve --http
```

HTTP mode is stateless, so it scales horizontally and suits hosts such as
Cloud Run, Fly, or AWS Bedrock AgentCore. AgentCore needs `linux/arm64`, which
the published image includes. `HOST` and `PORT` override the bind address.
Outside a container it binds to loopback by default.

**The server has no authentication of its own.** If you expose it with
`ABR_GUID` set, anyone who can reach it is using your GUID. Put it behind your
platform's authentication (for example AgentCore inbound auth, Cloud Run IAM,
or a reverse proxy). Alternatively, run it with only the local index, which
contains public data.

## Using ABR data reliably

These rules are built into the tools. They come from DeepCivic's
grants/procurement analysis and from the Womblex `ingest-abn` register ingest,
both of which ran over the full extract:

- **Validate, then join on ABN.** An ABN that fails its checksum cannot be
  registered, so it is reported as invalid and no lookup is made. Exact ABN
  joins are deterministic. Name matching is not.
- **Spreadsheets damage identifiers.** `51824753556.0`, `5.18E+10` and
  `ABN: 51-824-753-556` are all normalised. An ACN that lost its leading zeros
  gets a *reported* zero-padded candidate. It is never silently assumed.
- **Names are candidates, not identity.** `search_names` compares a
  normalised key: case, punctuation and accents are folded, `&` becomes
  `AND`, and a leading `THE` / `THE TRUSTEE FOR` and legal-form words (`PTY`,
  `LTD`, `LIMITED`, `INC`, `P/L`) are ignored. Geography words and `CO` are
  kept, because they distinguish real entities. Confirm any hit with
  `lookup_abn`.
- **Know the name types.** `MN` is a non-individual's legal name and `LGL`
  an individual's. `BN` names are current ASIC-registered business names.
  `TRD` trading names are legacy. The ABR "recommend[s] that you avoid using
  trading names as these have not been updated since 2012", so `search_names`
  leaves them out unless you pass `name_types` including `TRD`. `lookup_abn`
  still lists them, labelled as legacy.
- **The extract is a snapshot of current details.** Every response carries
  `provenance.extract_date`. Use `source="web"` when currency matters (for
  example, checking a supplier is active today).
- **What ABR data cannot tell you.** It does not show ownership, control or
  parent companies. The state and postcode are the main business location,
  not a registered office. A foreign entity can hold an Australian ABN, so an
  ABN does not make an entity Australian-owned.

## Example

`lookup_abn("11 123 456 780")` against the synthetic test fixture (abridged):

```json
{
  "found": true,
  "record": {
    "abn": "11123456780",
    "abn_formatted": "11 123 456 780",
    "abn_status": "ACT",
    "abn_status_text": "Active",
    "abn_status_from": "2005-07-01",
    "entity_name": "EXAMPLE WIDGETS PTY LTD",
    "entity_type_code": "PRV",
    "entity_type": "Australian Private Company",
    "business_names": ["WIDGETS DIRECT"],
    "trading_names": ["Widgets & Co"],
    "state": "VIC",
    "postcode": "3000",
    "gst": {"status": "ACT", "from": "2005-07-01", "registered": true},
    "acn": "123456780",
    "acn_checksum_valid": true,
    "abn_embeds_acn": true,
    "dgr_endorsed": false
  },
  "provenance": {
    "source": "abr_bulk_extract",
    "extract_date": "2026-10-28",
    "extract_age_days": 9,
    "index_complete": true,
    "licence": "Creative Commons Attribution 3.0 Australia (CC BY 3.0 AU)",
    "attribution": "Contains ABN Lookup data from the Australian Business Register ..."
  },
  "caveats": ["Bulk extract data is a weekly snapshot ...", "Trading name. Legacy: ...", "State/postcode is the main business location ..."]
}
```

## Development

```bash
cd mcp-servers/abr-mcp
uv venv && uv pip install -e ".[dev]"
uv run pytest                          # synthetic data only; no network
ABR_LIVE=1 uv run pytest -m live       # live ABN Lookup (add ABR_GUID for real lookups)
npx @modelcontextprotocol/inspector uv run abr-mcp
```

CI ([mcp-servers.yml](../../.github/workflows/mcp-servers.yml)) tests every
server in `mcp-servers/` on Linux, macOS and Windows, on Python 3.10 and 3.13,
and at the lowest declared dependency versions. It also launches each server
over stdio and lists its tools.

## Releasing

Push a tag named `abr-mcp-v<version>` that matches `pyproject.toml`.
[mcp-release.yml](../../.github/workflows/mcp-release.yml) then publishes:

- the package to PyPI, through trusted publishing;
- the `amd64`/`arm64` image to `ghcr.io/deepcivic/abr-mcp`;
- the `.mcpb` bundle to the GitHub release;
- [server.json](server.json) to the [MCP Registry](https://registry.modelcontextprotocol.io).

Bump the version in `pyproject.toml`, `src/abr_mcp/__init__.py`,
`server.json` and `manifest.json`. A test fails if they disagree.

## Terms of use

Using the live web services means you accept the
[ABN Lookup Web Services Agreement](https://abr.business.gov.au/Tools/WebServicesAgreement)
for your own GUID. Here is how abr-mcp is designed to fit it, and what remains
your responsibility:

| Agreement / ABR guidance | How abr-mcp handles it |
| --- | --- |
| A GUID is issued to you under a **non-transferable** licence. | No GUID ships with abr-mcp. Each user or deployment registers its own. A hosted HTTP server spends its operator's GUID, so put it behind authentication (see [Remote](#remote-streamable-http)). |
| Do not suggest the Commonwealth **endorses or is affiliated** with you. | Named and described as an unofficial client. The disclaimer appears in the server instructions, `register_status`, this README and [NOTICE](NOTICE). |
| Do not use the services in a **false, misleading or deceptive** way. | Every answer carries `provenance` (web service or bulk extract, with dates), and name matches are labelled as candidates. |
| **Withdrawn** details must be deleted when you're notified. | Web responses are never cached or stored. The local index is rebuilt from scratch by each `update-index`, which drops anything withdrawn from the extract. Anything *you* store from answers remains your responsibility. |
| Data is provided **as is**, with no warranty that it is correct or current. | Surfaced in the disclaimer, and as `extract_date` / `extract_age_days` on local answers. |
| The ABR recommends **avoiding trading names**. | Excluded from name search by default. Labelled as legacy in lookups. |
| No published rate limit. Name searches default to 200 results. | Web batch lookups run one at a time, capped at 25 per call. Web name searches request at most 200 results. For volume, use the offline index rather than the live service. |
| You may provide **relevant extracts** to third parties, at your own risk. | Answers are extracts. Keep your contact details with the ABR current so you receive its notices. |

The bulk extract is a separate dataset, published under CC BY 3.0 AU (below).
The offline index needs no GUID and no agreement.

## Licensing

Code: Apache License 2.0 ([LICENSE](LICENSE)), as part of [civic-lab](../../).

Data: this package bundles **no** register data. The ABN Bulk Extract is
published by the Australian Business Register under
[CC BY 3.0 AU](https://creativecommons.org/licenses/by/3.0/au/). If you share
an index or outputs built from it, keep the attribution that tools return in
`provenance.attribution`. Web-service data is used under the ABN Lookup web
services terms for your GUID. See [NOTICE](NOTICE).
