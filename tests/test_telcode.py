import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "telcode" / "scripts" / "telcode.py"
spec = importlib.util.spec_from_file_location("telcode", SCRIPT)
assert spec and spec.loader
telcode = importlib.util.module_from_spec(spec)
sys.modules["telcode"] = telcode
spec.loader.exec_module(telcode)


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = telcode.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class DataIntegrity(unittest.TestCase):
    def test_tables_are_well_formed(self) -> None:
        for path in (telcode.ASSETS / "codes").glob("*.json"):
            with self.subTest(table=path.name):
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(raw["family"], path.stem)
                codes = [c["code"] for c in raw["codes"]]
                self.assertEqual(len(codes), len(set(codes)), "duplicate codes")
                self.assertTrue(all(c["name"].strip() for c in raw["codes"]), "empty name")
                self.assertTrue(all(r["from"] <= r["to"] for r in raw["ranges"]), "inverted range")

    def test_expected_tables_are_present(self) -> None:
        self.assertEqual([t.family for t in telcode.load_tables()], list(telcode.TABLE_ORDER))

    def test_every_note_points_at_a_known_code(self) -> None:
        notes = json.loads((telcode.ASSETS / "notes.json").read_text(encoding="utf-8"))
        tables = {t.family: t for t in telcode.load_tables()}
        for family, by_code in notes.items():
            for code in by_code:
                with self.subTest(family=family, code=code):
                    self.assertIn(int(code), tables[family].codes)


class Lookup(unittest.TestCase):
    def test_same_number_in_two_diameter_tables(self) -> None:
        code, out, _ = run("5001", "--json")
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertTrue(result["ambiguous"])
        names = {m["table"]: m["name"] for m in result["matches"]}
        self.assertEqual(names["diameter-result"], "DIAMETER_AVP_UNSUPPORTED")
        self.assertEqual(names["diameter-experimental-3gpp"], "DIAMETER_ERROR_USER_UNKNOWN")

    def test_table_prefix_filter(self) -> None:
        _, out, _ = run("27", "--table", "map", "--json")
        result = json.loads(out)
        self.assertFalse(result["ambiguous"])
        self.assertEqual(result["matches"][0]["name"], "absentSubscriber")

    def test_unassigned_code_reports_reserved_range_and_class(self) -> None:
        _, out, _ = run("5430", "-t", "diameter-exp", "--json")
        match = json.loads(out)["matches"][0]
        self.assertIsNone(match["name"])
        self.assertEqual(match["class"], "Permanent Failure")
        self.assertEqual(match["ranges"], ["Reserved for 3GPP TS 29.272"])

    def test_hex_input(self) -> None:
        _, out, _ = run("0x0b", "-t", "sccp", "--json")
        self.assertEqual(json.loads(out)["matches"][0]["name"], "SCCP failure")

    def test_not_found_exits_1(self) -> None:
        code, _, err = run("-t", "q850", "200")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_unknown_table_is_a_usage_error(self) -> None:
        code, _, err = run("1", "-t", "gtp")
        self.assertEqual(code, 2)
        self.assertIn("no table starts with", err)


class Search(unittest.TestCase):
    def test_camel_case_and_snake_case_names(self) -> None:
        _, out, _ = run("search", "absent", "subscriber", "--json")
        found = {(m["table"], m["code"]) for m in json.loads(out)["matches"]}
        self.assertIn(("map-error", 6), found)
        self.assertIn(("map-error", 27), found)
        self.assertIn(("q850-cause", 20), found)

    def test_search_by_specification(self) -> None:
        _, out, _ = run("search", "29.272", "--json")
        codes = {m["code"] for m in json.loads(out)["matches"]}
        self.assertTrue({4181, 5420, 5421, 5422, 5423} <= codes)

    def test_no_match_exits_1(self) -> None:
        code, _, _ = run("search", "zzzz-not-a-code")
        self.assertEqual(code, 1)


class Imsi(unittest.TestCase):
    def test_both_mnc_lengths_by_default(self) -> None:
        self.assertEqual(
            telcode.split_imsi("262011234567890", None),
            [
                {"mcc": "262", "mnc": "01", "msin": "1234567890"},
                {"mcc": "262", "mnc": "011", "msin": "234567890"},
            ],
        )

    def test_known_mnc_length(self) -> None:
        self.assertEqual(telcode.split_imsi("310410123456789", 3), [{"mcc": "310", "mnc": "410", "msin": "123456789"}])

    def test_rejects_non_digits_and_bad_length(self) -> None:
        for bad in ("12ab56789", "12345", "1234567890123456"):
            with self.subTest(imsi=bad), self.assertRaises(telcode.UsageError):
                telcode.split_imsi(bad, None)


class Tbcd(unittest.TestCase):
    def test_even_digit_count(self) -> None:
        self.assertEqual(telcode.decode_tbcd("62 02 10 21 43 65 87 09"), "2620011234567890")

    def test_imsi_with_filler(self) -> None:
        # IMSI 262011234567890 has 15 digits, so 'f' fills the high nibble of the last octet.
        self.assertEqual(telcode.decode_tbcd("62:02:11:32:54:76:98:f0"), "262011234567890")

    def test_special_digits(self) -> None:
        self.assertEqual(telcode.decode_tbcd("0xba"), "*#")
        self.assertEqual(telcode.decode_tbcd("dc fe"), "abc")

    def test_trailing_padding_octets(self) -> None:
        self.assertEqual(telcode.decode_tbcd("21 f3 ff ff"), "123")

    def test_rejects_bad_input(self) -> None:
        for bad in ("1f23", "123", "zz", ""):
            with self.subTest(hex=bad), self.assertRaises(telcode.UsageError):
                telcode.decode_tbcd(bad)


if __name__ == "__main__":
    unittest.main()
