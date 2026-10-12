#!/usr/bin/env python3
"""telcode: offline lookup for mobile core signalling codes.

Looks up Diameter Result-Code and 3GPP Experimental-Result-Code values, 5G and
4G NAS causes (5GMM, 5GSM, EMM, ESM), GTPv2-C and PFCP causes, GSM MAP errors,
SCCP return causes, Q.850 cause values and SIP response codes. Also splits IMSIs
and decodes TBCD. Standard library only, Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parent.parent / "assets"
COMMANDS = ("code", "search", "imsi", "tbcd", "tables")
TABLE_ORDER = (
    "diameter-result",
    "diameter-experimental-3gpp",
    "5gmm-cause",
    "5gsm-cause",
    "emm-cause",
    "esm-cause",
    "gtpv2c-cause",
    "pfcp-cause",
    "map-error",
    "sccp-return-cause",
    "q850-cause",
    "sip-response",
)
# TS 29.002 TBCD-STRING: nibbles 0-9 are digits, 1010..1110 are '*', '#', 'a', 'b', 'c', 1111 is filler.
TBCD_DIGITS = "0123456789*#abc"
MNC_NOTE = (
    "The IMSI does not encode the MNC length. The SIM states it in EF_AD (3GPP TS 31.102); "
    "pass --mnc-len 2 or 3 when you know it."
)
EXAMPLES = """\
examples:
  telcode 5001                    every table that defines 5001
  telcode 27 --table map          only the GSM MAP errors
  telcode search absent           codes whose name contains "absent"
  telcode search 29.272           codes specified in TS 29.272 (S6a/S6d)
  telcode imsi 262011234567890    MCC, MNC and MSIN
  telcode tbcd 62 02 10 32 54 f6  TBCD bytes from a trace to digits
  telcode tables                  the tables and where they come from
"""


class UsageError(Exception):
    pass


@dataclass(frozen=True)
class Code:
    code: int
    name: str
    ref: str


@dataclass(frozen=True)
class Range:
    low: int
    high: int
    name: str
    is_class: bool


@dataclass(frozen=True)
class Table:
    family: str
    title: str
    source: str
    url: str
    codes: dict[int, Code]
    ranges: tuple[Range, ...]
    notes: dict[int, str]

    def class_of(self, code: int) -> str | None:
        return next((r.name for r in self.ranges if r.is_class and r.low <= code <= r.high), None)

    def ranges_of(self, code: int) -> list[str]:
        return [r.name for r in self.ranges if not r.is_class and r.low <= code <= r.high]

    def covers(self, code: int) -> bool:
        return any(r.low <= code <= r.high for r in self.ranges)


@dataclass(frozen=True)
class Match:
    table: Table
    code: int
    entry: Code | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table.family,
            "title": self.table.title,
            "code": self.code,
            "name": self.entry.name if self.entry else None,
            "ref": self.entry.ref if self.entry else None,
            "class": self.table.class_of(self.code),
            "ranges": self.table.ranges_of(self.code),
            "note": self.table.notes.get(self.code),
            "source": self.table.source,
        }


def load_tables(assets: Path = ASSETS) -> list[Table]:
    notes = json.loads((assets / "notes.json").read_text(encoding="utf-8"))
    tables = []
    for path in (assets / "codes").glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        family = raw["family"]
        tables.append(
            Table(
                family=family,
                title=raw["title"],
                source=raw["source"],
                url=raw["url"],
                codes={c["code"]: Code(c["code"], c["name"], c["ref"]) for c in raw["codes"]},
                ranges=tuple(Range(r["from"], r["to"], r["name"], r.get("class", False)) for r in raw["ranges"]),
                notes={int(k): v for k, v in notes.get(family, {}).items()},
            )
        )
    order = {name: i for i, name in enumerate(TABLE_ORDER)}
    return sorted(tables, key=lambda t: (order.get(t.family, len(order)), t.family))


def select_tables(tables: list[Table], prefix: str | None) -> list[Table]:
    if not prefix:
        return tables
    chosen = [t for t in tables if t.family.startswith(prefix.lower())]
    if not chosen:
        names = ", ".join(t.family for t in tables)
        raise UsageError(f"no table starts with {prefix!r}; tables: {names}")
    return chosen


def parse_code(text: str) -> int:
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
    except ValueError:
        raise UsageError(f"not a number: {text!r}") from None


def lookup(tables: list[Table], code: int) -> list[Match]:
    """Exact matches; failing that, the tables whose classes or reserved ranges cover the code."""
    exact = [Match(t, code, t.codes[code]) for t in tables if code in t.codes]
    if exact:
        return exact
    return [Match(t, code, None) for t in tables if t.covers(code)]


def normalize(text: str) -> str:
    """'absentSubscriberSM' and 'DIAMETER_ERROR_ABSENT_USER' become space separated lower case words."""
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return re.sub(r"[\s_-]+", " ", text).lower()


def search(tables: list[Table], words: list[str]) -> list[Match]:
    terms = normalize(" ".join(words)).split()
    return [
        Match(t, entry.code, entry)
        for t in tables
        for entry in sorted(t.codes.values(), key=lambda e: e.code)
        if all(term in normalize(f"{entry.name} {entry.ref}") for term in terms)
    ]


def split_imsi(imsi: str, mnc_len: int | None) -> list[dict[str, str]]:
    if not re.fullmatch(r"[0-9]{6,15}", imsi):
        raise UsageError("an IMSI is 6 to 15 decimal digits")
    splits = []
    for n in [mnc_len] if mnc_len else [2, 3]:
        if len(imsi) <= 3 + n:
            raise UsageError(f"{imsi} is too short for a {n} digit MNC")
        splits.append({"mcc": imsi[:3], "mnc": imsi[3 : 3 + n], "msin": imsi[3 + n :]})
    return splits


def decode_tbcd(text: str) -> str:
    hexstr = re.sub(r"[\s:.-]", "", text.lower())
    hexstr = hexstr.removeprefix("0x")
    if not re.fullmatch(r"(?:[0-9a-f]{2})+", hexstr):
        raise UsageError("TBCD input is whole octets in hex, for example: 62 02 10 32 54 f6")
    nibbles = []
    for i in range(0, len(hexstr), 2):
        octet = int(hexstr[i : i + 2], 16)
        nibbles += [octet & 0x0F, octet >> 4]  # the low nibble holds the first digit
    digits = []
    for i, nibble in enumerate(nibbles):
        if nibble == 0xF:
            if any(n != 0xF for n in nibbles[i + 1 :]):
                raise UsageError("filler nibble 'f' in the middle of the TBCD data")
            break
        digits.append(TBCD_DIGITS[nibble])
    return "".join(digits)


def wrap(label: str, text: str, indent: int = 4) -> str:
    prefix = " " * indent + label
    return textwrap.fill(text, width=100, initial_indent=prefix, subsequent_indent=" " * len(prefix))


def render_match(m: Match, show_note: bool = True) -> list[str]:
    details = []
    cls = m.table.class_of(m.code)
    if cls:
        details.append(f"class: {cls}")
    details += m.table.ranges_of(m.code)
    if m.entry and m.entry.ref:
        details.append(f"ref: {m.entry.ref}")
    lines = [f"    {m.entry.name if m.entry else '(not assigned)'}"]
    if details:
        lines.append("    " + " | ".join(details))
    note = m.table.notes.get(m.code)
    if show_note and note:
        lines.append(wrap("note: ", note))
    return lines


def cmd_code(args: argparse.Namespace, tables: list[Table]) -> int:
    code = parse_code(args.code)
    matches = lookup(select_tables(tables, args.table), code)
    ambiguous = len(matches) > 1
    if args.json:
        print(json.dumps({"code": code, "ambiguous": ambiguous, "matches": [m.to_dict() for m in matches]}, indent=2))
        return 0 if matches else 1
    if not matches:
        print(f"{code}: not found in any table", file=sys.stderr)
        return 1
    print(code)
    for m in matches:
        print(f"  {m.table.title}")
        print("\n".join(render_match(m)))
    if ambiguous:
        print(
            wrap(
                "",
                f"More than one table uses {code}: the protocol or AVP it came from decides which one applies. "
                "Use --table to narrow it down.",
                indent=0,
            )
        )
    return 0


def cmd_search(args: argparse.Namespace, tables: list[Table]) -> int:
    matches = search(select_tables(tables, args.table), args.words)
    if args.json:
        print(json.dumps({"query": " ".join(args.words), "matches": [m.to_dict() for m in matches]}, indent=2))
        return 0 if matches else 1
    if not matches:
        print(f"no code name matches {' '.join(args.words)!r}", file=sys.stderr)
        return 1
    title = None
    for m in matches:
        if m.table.title != title:
            title = m.table.title
            print(title)
        ref = f"  ({m.entry.ref})" if m.entry and m.entry.ref else ""
        print(f"  {m.code:>5}  {m.entry.name if m.entry else ''}{ref}")
    return 0


def cmd_imsi(args: argparse.Namespace, _tables: list[Table]) -> int:
    splits = split_imsi(args.imsi, args.mnc_len)
    if args.json:
        print(json.dumps({"imsi": args.imsi, "splits": splits, "note": None if args.mnc_len else MNC_NOTE}, indent=2))
        return 0
    print(f"IMSI {args.imsi}")
    for s in splits:
        print(f"  MNC length {len(s['mnc'])}:  MCC {s['mcc']}  MNC {s['mnc']:<3}  MSIN {s['msin']}")
    if not args.mnc_len:
        print(wrap("", MNC_NOTE, indent=0))
    return 0


def cmd_tbcd(args: argparse.Namespace, _tables: list[Table]) -> int:
    raw = " ".join(args.hex)
    digits = decode_tbcd(raw)
    if args.json:
        print(json.dumps({"hex": raw, "digits": digits}, indent=2))
    else:
        print(digits)
    return 0


def cmd_tables(args: argparse.Namespace, tables: list[Table]) -> int:
    rows = [
        {"table": t.family, "title": t.title, "codes": len(t.codes), "source": t.source, "url": t.url} for t in tables
    ]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        print(f"{r['table']}  ({r['codes']} codes)\n  {r['title']}\n  {r['source']}\n  {r['url']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    parser = argparse.ArgumentParser(
        prog="telcode",
        description="Offline lookup for mobile core signalling codes.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser(
        "code", parents=[common], help="look up a code (the default when the first argument is a number)"
    )
    p.add_argument("code", help="decimal, or hex with a 0x prefix")
    p.add_argument(
        "-t",
        "--table",
        help="only tables whose name starts with this: diameter, 5gmm, 5gsm, emm, esm, gtp, pfcp, map, sccp, q850, sip",
    )
    p.set_defaults(handler=cmd_code)
    p = sub.add_parser("search", parents=[common], help="find codes by name or specification")
    p.add_argument("words", nargs="+")
    p.add_argument("-t", "--table", help="only tables whose name starts with this")
    p.set_defaults(handler=cmd_search)
    p = sub.add_parser("imsi", parents=[common], help="split an IMSI into MCC, MNC and MSIN")
    p.add_argument("imsi")
    p.add_argument("--mnc-len", type=int, choices=(2, 3), help="MNC length, when known")
    p.set_defaults(handler=cmd_imsi)
    p = sub.add_parser("tbcd", parents=[common], help="decode TBCD octets (IMSI, MSISDN, GT digits) to digits")
    p.add_argument("hex", nargs="+", help="hex octets, separators allowed")
    p.set_defaults(handler=cmd_tbcd)
    p = sub.add_parser("tables", parents=[common], help="list the tables and their sources")
    p.set_defaults(handler=cmd_tables)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    first = next((a for a in argv if not a.startswith("-")), None)
    if first is not None and first not in COMMANDS:
        argv.insert(0, "code")
    args = build_parser().parse_args(argv)
    try:
        result: int = args.handler(args, load_tables())
    except UsageError as err:
        print(f"telcode: error: {err}", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
