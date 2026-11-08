"""Streaming parser for the ABN Lookup bulk extract XML.

The extract is 20 files (``yyyymmddPublicNN.xml``, ~620 MB each, ~12 GB in
total) usually distributed as two zips (``public_split_1_10.zip``,
``public_split_11_20.zip``). This module reads ``.xml`` files, ``.zip``
archives (members are streamed, never extracted to disk) and directories of
either, at constant memory.

Projection follows the Womblex ``ingest-abn`` register ingest, which has run
over the full extract (20M records / 27.8M names): values are verbatim
strings, absent optionals are ``""`` (never ``None``), the display name is the
``MN`` main name for non-individuals and the ``LGL`` individual name for
individuals, and ``GivenName`` (0..2 in the schema) stays as separate parts.

Tolerated schema edges: ``DGR`` with no fund name (endorsement of the entity
itself) and no ``status``; empty ``ASICNumber``; empty ``State``.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

RECORD_FIELDS = (
    "abn",
    "abn_status",
    "abn_status_from_date",
    "record_last_updated_date",
    "replaced",
    "entity_type_ind",
    "entity_type_text",
    "name_type",
    "display_name",
    "name_title",
    "given_name_1",
    "given_name_2",
    "family_name",
    "state",
    "postcode",
    "asic_number",
    "asic_number_type",
    "gst_status",
    "gst_status_from_date",
)


@dataclass
class TransferInfo:
    file_sequence_number: str = ""
    record_count: str = ""
    extract_time: str = ""
    error: str = ""


@dataclass
class AbrRecord:
    record: dict[str, str]
    # (name_type, name_text)
    names: list[tuple[str, str]] = field(default_factory=list)
    # (status_from_date, status, fund_name)
    dgr: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class Source:
    """One bulk extract XML stream: a file on disk or a member of a zip."""

    label: str
    path: Path
    member: str | None = None

    def open(self) -> IO[bytes]:
        if self.member is None:
            return open(self.path, "rb")
        zf = zipfile.ZipFile(self.path)
        stream = zf.open(self.member)
        # Close the archive with the stream.
        orig_close = stream.close

        def _close() -> None:
            orig_close()
            zf.close()

        stream.close = _close  # type: ignore[method-assign]
        return stream

    def size(self) -> int:
        if self.member is None:
            return self.path.stat().st_size
        with zipfile.ZipFile(self.path) as zf:
            return zf.getinfo(self.member).file_size


def discover_sources(paths: list[str | os.PathLike[str]]) -> list[Source]:
    """Expand files / zips / directories into an ordered list of XML sources."""
    found: list[Source] = []

    def add_zip(p: Path) -> None:
        with zipfile.ZipFile(p) as zf:
            for name in sorted(zf.namelist()):
                if name.lower().endswith(".xml") and not name.endswith("/"):
                    found.append(Source(label=f"{p.name}!{name}", path=p, member=name))

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() == ".xml":
                    found.append(Source(label=str(child.relative_to(p)), path=child))
                elif child.is_file() and child.suffix.lower() == ".zip":
                    add_zip(child)
        elif p.is_file() and p.suffix.lower() == ".zip":
            add_zip(p)
        elif p.is_file():
            found.append(Source(label=p.name, path=p))
        else:
            raise FileNotFoundError(f"No such file or directory: {p}")
    return found


def _text(elem: ET.Element | None, path: str | None = None) -> str:
    node = elem if path is None or elem is None else elem.find(path)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def parse_abr(elem: ET.Element) -> AbrRecord:
    """Project one ``<ABR>`` element."""
    rec = dict.fromkeys(RECORD_FIELDS, "")
    rec["record_last_updated_date"] = elem.get("recordLastUpdatedDate", "")
    rec["replaced"] = elem.get("replaced", "")

    abn_el = elem.find("ABN")
    if abn_el is not None:
        rec["abn"] = _text(abn_el)
        rec["abn_status"] = abn_el.get("status", "")
        rec["abn_status_from_date"] = abn_el.get("ABNStatusFromDate", "")

    rec["entity_type_ind"] = _text(elem, "EntityType/EntityTypeInd")
    rec["entity_type_text"] = _text(elem, "EntityType/EntityTypeText")

    out = AbrRecord(record=rec)

    main = elem.find("MainEntity")
    legal = elem.find("LegalEntity")
    entity = main if main is not None else legal
    if entity is not None:
        rec["state"] = _text(entity, "BusinessAddress/AddressDetails/State")
        rec["postcode"] = _text(entity, "BusinessAddress/AddressDetails/Postcode")

    if main is not None:
        name_el = main.find("NonIndividualName")
        if name_el is not None:
            rec["name_type"] = name_el.get("type", "")
            rec["display_name"] = _text(name_el, "NonIndividualNameText")
    elif legal is not None:
        name_el = legal.find("IndividualName")
        if name_el is not None:
            rec["name_type"] = name_el.get("type", "")
            rec["name_title"] = _text(name_el, "NameTitle")
            givens = [g for g in (_text(g) for g in name_el.findall("GivenName")) if g]
            rec["given_name_1"] = givens[0] if givens else ""
            # Schema caps GivenName at two; fold any extras rather than drop them.
            rec["given_name_2"] = " ".join(givens[1:])
            rec["family_name"] = _text(name_el, "FamilyName")
            rec["display_name"] = " ".join(p for p in (*givens, rec["family_name"]) if p)

    if rec["display_name"]:
        out.names.append((rec["name_type"], rec["display_name"]))

    asic = elem.find("ASICNumber")
    if asic is not None:
        rec["asic_number"] = _text(asic)
        rec["asic_number_type"] = asic.get("ASICNumberType", "")

    gst = elem.find("GST")
    if gst is not None:
        rec["gst_status"] = gst.get("status", "")
        rec["gst_status_from_date"] = gst.get("GSTStatusFromDate", "")

    for dgr in elem.findall("DGR"):
        fund = _text(dgr, "NonIndividualName/NonIndividualNameText")
        out.dgr.append((dgr.get("DGRStatusFromDate", ""), dgr.get("status", ""), fund))
        if fund:
            name_el = dgr.find("NonIndividualName")
            ntype = name_el.get("type", "DGR") if name_el is not None else "DGR"
            out.names.append((ntype or "DGR", fund))

    for other in elem.findall("OtherEntity"):
        name_el = other.find("NonIndividualName")
        text = _text(name_el, "NonIndividualNameText") if name_el is not None else ""
        if text and name_el is not None:
            out.names.append((name_el.get("type", ""), text))

    return out


class NotABulkExtract(ValueError):
    """Root element is not ``<Transfer>``."""


def iter_extract(stream: IO[bytes]) -> Iterator[TransferInfo | AbrRecord]:
    """Yield the file's ``TransferInfo`` (first) and then each ``AbrRecord``.

    Memory is constant: processed elements are cleared from the root.
    """
    parser = ET.iterparse(stream, events=("start", "end"))
    _, root = next(parser)
    if root.tag != "Transfer":
        raise NotABulkExtract(f"root element is <{root.tag}>, not <Transfer>")
    info = TransferInfo(error=root.get("error", ""))
    info_sent = False
    for event, elem in parser:
        if event != "end":
            continue
        if elem.tag == "TransferInfo":
            info.file_sequence_number = _text(elem, "FileSequenceNumber")
            info.record_count = _text(elem, "RecordCount")
            info.extract_time = _text(elem, "ExtractTime")
            info_sent = True
            yield info
            root.clear()
        elif elem.tag == "ABR":
            if not info_sent:
                info_sent = True
                yield info
            yield parse_abr(elem)
            root.clear()
    if not info_sent:
        yield info


def records_from(stream: IO[bytes]) -> tuple[TransferInfo, list[AbrRecord]]:
    """Parse a whole (small) extract into memory. For tests and tooling."""
    info = TransferInfo()
    out: list[AbrRecord] = []
    for item in iter_extract(stream):
        if isinstance(item, TransferInfo):
            info = item
        else:
            out.append(item)
    return info, out

