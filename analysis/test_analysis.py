"""Small offline tests for the publication analysis outputs."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


class PublicationAnalysisTests(unittest.TestCase):
    def test_headline_counts_and_rates(self) -> None:
        claims = json.loads(
            (ROOT / "results" / "recalculated_claims.json").read_text(encoding="utf-8")
        )
        self.assertEqual(claims["tasks"], 542)
        self.assertEqual(
            claims["plus_successes"],
            {"adaptive": 331, "small_only": 220, "strong_only": 297},
        )
        self.assertAlmostEqual(claims["plus_pass_rates"]["adaptive"], 331 / 542)
        self.assertAlmostEqual(
            claims["successes_per_weighted_total_proxy_relative_difference"],
            0.10647039124792723,
        )

    def test_all_tables_and_figures_exist(self) -> None:
        expected_tables = [
            "table1_configuration.tex",
            "table2_correctness.tex",
            "table3_resource_usage.tex",
            "table4_paired_outcomes.tex",
            "table5_complementarity.tex",
            "table6_threats.tex",
        ]
        for name in expected_tables:
            self.assertTrue((ROOT / "paper" / "tables" / name).exists())
        tables = list((ROOT / "paper" / "tables").glob("table*.tex"))
        figures = list((ROOT / "paper" / "figures").glob("figure*.png"))
        self.assertEqual(len(tables), 6)
        self.assertEqual(len(figures), 6)
        self.assertTrue(all(path.stat().st_size > 100 for path in tables + figures))

    def test_reference_validation_passed(self) -> None:
        report = json.loads(
            (ROOT / "results" / "reference_validation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["records_checked"], 12)

    def test_fallback_pdf_contains_all_numbered_tables(self) -> None:
        text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(ROOT / "paper" / "paper.pdf").pages
        )
        normalized = " ".join(text.split())
        for number in range(1, 7):
            self.assertIn(f"Table {number}.", text)
        self.assertIn("Observed conditional tier overlaps", text)
        self.assertIn("Threats to validity and treatment", text)
        self.assertIn(
            "Verification-Gated Model Cascading for Local Coding Inference", normalized
        )


if __name__ == "__main__":
    unittest.main()
