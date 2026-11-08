"""Code tables for the ABN Lookup bulk extract (readme v2.6 / BulkExtract.xsd).

Entity type codes are *not* hard-coded: every bulk extract record carries its
own ``EntityTypeText``, so the local index derives the code table from the data
it was built from (see ``LocalIndex.entity_types``).
"""

from __future__ import annotations

BULK_EXTRACT_SCHEMA_VERSION = "2.6"

ABN_STATUS = {
    "ACT": "Active",
    "CAN": "Cancelled",
}

GST_STATUS = {
    "ACT": "Registered for GST (from the GST status date)",
    "CAN": "GST registration cancelled (from the GST status date)",
    "NON": "Not registered for GST",
}

NAME_TYPES = {
    "MN": "Main name: the legal name of a non-individual entity.",
    "LGL": "Legal name of an individual (sole trader).",
    "BN": "Business name registered with ASIC (current registered business names).",
    "TRD": (
        "Trading name. Legacy: the ABR stopped accepting new or updated trading "
        "names in 2012, so these can be stale and are not verified."
    ),
    "OTN": "Other name recorded against the ABN.",
    "DGR": "Name of a Deductible Gift Recipient fund held by the ABN.",
}

# Bulk-extract state codes. "AAT" (Australian Antarctic Territory) appears in
# register data; "" means no state was recorded.
STATES = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT", "AAT")

# Searched unless the caller asks otherwise. TRD is left out because the ABR
# recommends avoiding trading names (not updated since 2012).
DEFAULT_SEARCH_NAME_TYPES = ("MN", "LGL", "BN", "OTN", "DGR")

# The web services agreement forbids suggesting Commonwealth endorsement or
# affiliation, and provides the data "as is".
DISCLAIMER = (
    "abr-mcp is an unofficial, independent client. It is not affiliated with, endorsed "
    "or approved by the Australian Business Register, the Australian Taxation Office or "
    "the Commonwealth of Australia. ABR data is provided by the Commonwealth 'as is', "
    "without warranty that it is correct, accurate or up to date."
)

# Display order for an ABN's names: legal identity first, legacy names last.
NAME_TYPE_RANK = {"MN": 0, "LGL": 0, "BN": 1, "DGR": 2, "OTN": 3, "TRD": 4}

LICENCE = {
    "licence": "Creative Commons Attribution 3.0 Australia (CC BY 3.0 AU)",
    "licence_url": "https://creativecommons.org/licenses/by/3.0/au/",
    "attribution": (
        "Contains ABN Lookup data from the Australian Business Register "
        "(ABN Bulk Extract, data.gov.au), licensed under CC BY 3.0 AU."
    ),
    "dataset_url": "https://data.gov.au/data/dataset/abn-bulk-extract",
}

WEB_SERVICES_TERMS = {
    "service": "ABN Lookup web services (abr.business.gov.au)",
    "terms_url": "https://abr.business.gov.au/Tools/WebServices",
    "note": (
        "Live ABR data, used under the ABN Lookup web services agreement for the configured "
        "GUID. Not cached or stored by abr-mcp."
    ),
}
