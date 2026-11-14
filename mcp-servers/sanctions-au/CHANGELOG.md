# Changelog

## 0.2.0

Adds twelve GLEIF LEI tools, rebuilt in Python from olgasafonova/gleif-mcp-server: `lei_lookup`,
`validate_lei`, `batch_lei_lookup`, `search_entity`, `search_by_bic`, `search_by_isin`, `search_by_country`,
`get_relationships`, `autocomplete`, `get_lei_issuer`, `list_lei_issuers`, `get_reporting_exceptions`. Off, and not offered to the
client, unless `SANCTIONS_ENABLE_GLEIF=1`, because they send queries to api.gleif.org. Screening can likewise be
switched off with `SANCTIONS_ENABLE_SCREENING=0`; each group is independent. Fixes the upstream defects recorded in
[docs/gleif-upstream-notes.md](docs/gleif-upstream-notes.md): the reporting-exceptions URL and field names, the
ISIN path, relationship field names, and 8-character BIC lookups.

Screening and data-capture fixes: refreshing an unchanged source now repairs a damaged current snapshot
instead of reconfirming it; an identifier matches only as a whole number, never as part of a longer one;
IMO numbers and ABNs are compared as digits only; a date of birth typed as a date in the DFAT workbook
keeps its year; an unreadable workbook cell fails the refresh with a report instead of a traceback; one
invalid subject in `screen_batch` is reported as `invalid_input` without failing the batch; and each
response reads the datasets once, so its results and `dataset_versions` always agree. GLEIF:
`list_lei_issuers` pages past 200, and `autocomplete` tolerates a suggestion with no record.

## 0.1.0

First release. Screens subjects against the DFAT Consolidated List and the ABF Register of
Sanctioned Sponsors from local, versioned, immutable snapshots. Four tools: `screen_subject`,
`screen_batch`, `get_record`, `dataset_status`. Refresh is a separate CLI command.
