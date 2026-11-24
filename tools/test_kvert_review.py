"""Regression tests for the reviewed KVERT publication path; no network or real data writes."""
import contextlib
import io
import re
import sys
import unittest
from unittest.mock import patch

import kvert_server as kvert


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.volcanoes = [{"id": "gvp-%d" % i, "nameRu": "Гора %d" % i, "gvpNumber": i}
                          for i in range(20)]
        self.old = {"forecastDate": "2026-11-11", "version": 7, "items": [], "source": "KVERT"}
        self.pairs = [(v["nameRu"].upper(), "green") for v in self.volcanoes]

    def run_cli(self, args):
        output = io.StringIO()
        files = {"activity.json": self.old, "tools/volcano_names.json": {"items": self.volcanoes},
                 "updates.json": {"files": {"activity": 7}}}
        with patch.object(sys, "argv", ["kvert_server.py"] + args), \
             patch.object(kvert, "text_of", return_value="fixture"), \
             patch.object(kvert, "parse", return_value=("2026-11-24", self.pairs)), \
             patch.object(kvert, "load", side_effect=files.__getitem__), \
             patch.object(kvert, "save") as save, contextlib.redirect_stdout(output):
            code = kvert.main()
        return code, output.getvalue(), save.call_args_list

    def test_default_and_preview_are_read_only(self):
        for args in ([], ["--показать"]):
            code, output, writes = self.run_cli(args)
            self.assertEqual(code, 0)
            self.assertEqual(writes, [])
            self.assertRegex(output, r"SHA-256: [a-f0-9]{64}")
            self.assertIn("Гора 19", output)

    def test_approval_binds_the_exact_date_and_codes(self):
        _, output, _ = self.run_cli([])
        digest = re.search(r"SHA-256: ([a-f0-9]{64})", output).group(1)
        code, _, writes = self.run_cli(["--approve", digest])
        self.assertEqual(code, 0)
        self.assertEqual([args[0][0] for args in writes], ["activity.json", "updates.json"])
        self.assertEqual(writes[0][0][1]["version"], 8)
        self.pairs[1] = (self.pairs[1][0], "red")
        with self.assertRaisesRegex(SystemExit, "Отпечаток"):
            self.run_cli(["--approve", digest])

    def test_reject_duplicate_or_unknown_volcano(self):
        self.pairs.append(self.pairs[0])
        with self.assertRaisesRegex(SystemExit, "повтор"):
            self.run_cli([])
        self.pairs[-1] = ("НЕИЗВЕСТНАЯ", "orange")
        with self.assertRaisesRegex(SystemExit, "несопоставленные"):
            self.run_cli([])


if __name__ == "__main__":
    unittest.main(verbosity=2)
