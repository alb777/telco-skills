#!/usr/bin/env python3
"""Regenerate telcode's machine-readable tables from the official sources.

Downloads the IANA registries and the latest 3GPP TS 29.230 / TS 29.002
releases, parses them with the standard library only and rewrites the JSON
files under skills/telcode/assets/codes/. The ITU-T tables (Q.850, Q.713) are small,
stable and published as PDF, so they are maintained by hand next to these.

Usage: python3 tools/update_data.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

CODES = Path(__file__).resolve().parent.parent / "skills" / "telcode" / "assets" / "codes"

IANA_AAA = "https://www.iana.org/assignments/aaa-parameters/aaa-parameters.xml"
IANA_SIP = "https://www.iana.org/assignments/sip-parameters/sip-parameters.xml"
TGPP_ARCHIVE = "https://www.3gpp.org/ftp/Specs/archive/29_series/{spec}/"

IANA_NS = "{http://www.iana.org/assignments}"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 3GPP's FTP answers 403 to the default urllib user agent.
USER_AGENT = "telcode-update-data/1.0"

Entry = dict[str, Any]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data: bytes = resp.read()
    return data


def write_family(name: str, family: dict[str, Any]) -> None:
    family["codes"].sort(key=lambda e: e["code"])
    family["ranges"].sort(key=lambda r: (r["from"], r["to"]))
    path = CODES / f"{name}.json"
    path.write_text(json.dumps(family, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(family['codes'])} codes, {len(family['ranges'])} ranges")


# IANA


def iana_ref(record: ET.Element) -> str:
    refs = []
    for xref in record.findall(f"{IANA_NS}xref"):
        data = xref.get("data", "")
        if xref.get("type") == "rfc":
            refs.append("RFC " + data.removeprefix("rfc"))
        elif data:
            refs.append(data)
    return ", ".join(refs)


def iana_registry(root: ET.Element, registry_id: str) -> ET.Element:
    for reg in root.iter(f"{IANA_NS}registry"):
        if reg.get("id") == registry_id:
            return reg
    raise SystemExit(f"IANA registry {registry_id} not found, the XML layout changed")


def parse_value(value: str) -> tuple[int, int]:
    low, _, high = value.partition("-")
    return int(low), int(high or low)


def diameter_result() -> None:
    root = ET.fromstring(fetch(IANA_AAA))
    updated = root.findtext(f"{IANA_NS}updated")
    classes = {
        "aaa-parameters-5": "Informational",
        "aaa-parameters-6": "Success",
        "aaa-parameters-7": "Protocol Error",
        "aaa-parameters-8": "Transient Failure",
        "aaa-parameters-9": "Permanent Failure",
    }
    codes: list[Entry] = []
    ranges: list[Entry] = []
    for reg_id, class_name in classes.items():
        reg = iana_registry(root, reg_id)
        low = high = None
        for record in reg.findall(f"{IANA_NS}record"):
            first, last = parse_value(record.findtext(f"{IANA_NS}value", ""))
            low = first if low is None else min(low, first)
            high = last if high is None else max(high, last)
            name = (record.findtext(f"{IANA_NS}name") or "").strip()
            if name in ("Reserved", "Unassigned"):
                ranges.append({"from": first, "to": last, "name": name})
            else:
                codes.append({"code": first, "name": name, "ref": iana_ref(record)})
        ranges.append({"from": low, "to": high, "name": class_name, "class": True})
    write_family(
        "diameter-result",
        {
            "family": "diameter-result",
            "title": "Diameter Result-Code (AVP 268)",
            "source": f"IANA AAA Parameters, Result-Code AVP Values (registry updated {updated})",
            "url": "https://www.iana.org/assignments/aaa-parameters/",
            "codes": codes,
            "ranges": ranges,
        },
    )


def sip_response() -> None:
    root = ET.fromstring(fetch(IANA_SIP))
    updated = root.findtext(f"{IANA_NS}updated")
    reg = iana_registry(root, "sip-parameters-7")
    codes = [
        {
            "code": int(record.findtext(f"{IANA_NS}value", "")),
            "name": (record.findtext(f"{IANA_NS}description") or "").strip(),
            "ref": iana_ref(record),
        }
        for record in reg.findall(f"{IANA_NS}record")
    ]
    classes = ["Provisional", "Successful", "Redirection", "Request Failure", "Server Failure", "Global Failure"]
    ranges: list[Entry] = [
        {"from": n * 100, "to": n * 100 + 99, "name": name, "class": True} for n, name in enumerate(classes, start=1)
    ]
    write_family(
        "sip-response",
        {
            "family": "sip-response",
            "title": "SIP response code",
            "source": f"IANA SIP Parameters, Response Codes (registry updated {updated})",
            "url": "https://www.iana.org/assignments/sip-parameters/",
            "codes": codes,
            "ranges": ranges,
        },
    )


# 3GPP


def latest_3gpp_docx(spec: str) -> tuple[ET.Element, str]:
    """Return the document body of the newest published version of a 3GPP spec, and its version."""
    listing = fetch(TGPP_ARCHIVE.format(spec=spec)).decode("utf-8", "replace")
    prefix = spec.replace(".", "")
    versions = set(re.findall(rf"{prefix}-([0-9a-z]{{3}})\.zip", listing))
    if not versions:
        raise SystemExit(f"no versions of TS {spec} found in the 3GPP archive listing")
    # Version digits are base 36: 'j30' is 19.3.0.
    newest = max(versions, key=lambda v: [int(c, 36) for c in v])
    archive = zipfile.ZipFile(io.BytesIO(fetch(TGPP_ARCHIVE.format(spec=spec) + f"{prefix}-{newest}.zip")))
    docx_name = next(n for n in archive.namelist() if n.endswith(".docx"))
    docx = zipfile.ZipFile(io.BytesIO(archive.read(docx_name)))
    body = ET.fromstring(docx.read("word/document.xml")).find(f"{W_NS}body")
    if body is None:
        raise SystemExit(f"TS {spec}: no document body in {docx_name}")
    version = ".".join(str(int(c, 36)) for c in newest)
    return body, version


def text_of(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.iter(f"{W_NS}t")).strip()


def cells(row: ET.Element) -> list[str]:
    return [text_of(cell) for cell in row.findall(f"{W_NS}tc")]


def spec_list(cell: str) -> str:
    """'29.209 [8],29.211 [17] ,29.214 [18]' -> '3GPP TS 29.209, 29.211, 29.214'."""
    specs = re.findall(r"\d{2}\.\d{3}", cell)
    return "3GPP TS " + ", ".join(specs)


def diameter_experimental_3gpp() -> None:
    body, version = latest_3gpp_docx("29.230")
    tables = {
        "Table 8.1.2": ("Success", 2000),
        "Table 8.1.3": ("Transient Failure", 4000),
        "Table 8.1.4": ("Permanent Failure", 5000),
    }
    note_re = re.compile(r"from (\d+) to (\d+) are reserved for (?:the )?(.+?)\.?$")
    codes: list[Entry] = []
    ranges: list[Entry] = []
    caption = ""
    for element in body:
        if element.tag == f"{W_NS}p":
            caption = text_of(element) or caption
            continue
        if element.tag != f"{W_NS}tbl":
            continue
        table = next((t for t in tables if caption.startswith(t + ":")), None)
        if table is None:
            continue
        class_name, base = tables[table]
        ranges.append({"from": base, "to": base + 999, "name": class_name, "class": True})
        spec = ""
        for row in element.findall(f"{W_NS}tr")[1:]:
            values = cells(row)
            if len(values) == 1:
                note = note_re.search(values[0])
                if not note:
                    raise SystemExit(f"{table}: unexpected note row {values[0]!r}")
                ranges.append({"from": int(note[1]), "to": int(note[2]), "name": f"Reserved for 3GPP {note[3]}"})
                spec = ""  # a note closes the group of the spec above it
                continue
            code, name, spec_cell = values
            # The spec cell is merged vertically: only the first row of a group carries it.
            spec = spec_list(spec_cell) if spec_cell else spec
            if not code:
                continue
            if not spec:
                raise SystemExit(f"{table}: code {code} has no specifying TS")
            if name.lower() in ("unassigned", "reserved"):
                ranges.append({"from": int(code), "to": int(code), "name": name.capitalize()})
            else:
                codes.append({"code": int(code), "name": name, "ref": spec})
    if len(ranges) < 3:
        raise SystemExit("TS 29.230: result code tables not found, the document layout changed")
    write_family(
        "diameter-experimental-3gpp",
        {
            "family": "diameter-experimental-3gpp",
            "title": "Diameter Experimental-Result-Code (AVP 298), 3GPP, Vendor-Id 10415",
            "source": f"3GPP TS 29.230 V{version}, tables 8.1.2 to 8.1.4",
            "url": "https://www.3gpp.org/dynareport/29230.htm",
            "codes": codes,
            "ranges": ranges,
        },
    )


def map_error() -> None:
    body, version = latest_3gpp_docx("29.002")
    # Paragraph text drops the <w:tab/> elements, so "CODE<tab>local:34" reads "CODElocal:34".
    text = "\n".join(text_of(p) for p in body.iter(f"{W_NS}p"))
    errors = re.findall(r"^([a-z][\w-]*)\s+ERROR\s*::=\s*\{(.*?)\}\s*$", text, re.S | re.M)
    codes: list[Entry] = []
    for name, block in errors:
        local = re.search(r"CODE\s*local\s*:\s*(\d+)", block)
        if not local:
            raise SystemExit(f"TS 29.002: MAP error {name} has no local code")
        codes.append({"code": int(local[1]), "name": name, "ref": "3GPP TS 29.002, MAP-Errors"})
    if len({c["code"] for c in codes}) != len(codes) or len(codes) < 50:
        raise SystemExit(f"TS 29.002: expected 50+ unique MAP error codes, parsed {len(codes)}")
    write_family(
        "map-error",
        {
            "family": "map-error",
            "title": "GSM MAP error code (TCAP ReturnError, local value)",
            "source": f"3GPP TS 29.002 V{version}, ASN.1 module MAP-Errors",
            "url": "https://www.3gpp.org/dynareport/29002.htm",
            "codes": codes,
            "ranges": [],
        },
    )


def main() -> int:
    CODES.mkdir(parents=True, exist_ok=True)
    diameter_result()
    diameter_experimental_3gpp()
    map_error()
    sip_response()
    return 0


if __name__ == "__main__":
    sys.exit(main())
