"""Small offline tests for the publication analysis outputs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def load_analysis_module(name: str):
    path = ROOT / "analysis" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            claims[
                "post_hoc_secondary_successes_per_weighted_total_proxy_relative_difference"
            ],
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
        self.assertEqual(report["records_checked"], 16)
        snell = next(item for item in report["records"] if item["key"] == "snell2024testtime")
        self.assertEqual(
            snell["expected_source_identifier"],
            "1b623663fd9b874366f3ce019fdfdd44",
        )

    def test_publication_terminology_and_evidence(self) -> None:
        paired = (ROOT / "paper" / "tables" / "table4_paired_outcomes.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn("Paired pass-rate difference", paired)
        stale_label = "Paired " + "risk difference"
        self.assertNotIn(stale_label, paired)

        evidence = (ROOT / "docs" / "MBPP_VERIFIER_FAILURE_ROOT_CAUSE.md").read_text(
            encoding="utf-8"
        )
        for task_id in (106, 124, 252, 255, 580, 720):
            self.assertIn(f"Mbpp/{task_id}", evidence)
        self.assertIn("strongly inferred", evidence.lower())

    def test_default_reproduction_preserves_release_figures_and_uses_lf(self) -> None:
        artifacts = load_analysis_module("make_publication_artifacts")
        figures = sorted((ROOT / "paper" / "figures").glob("figure*.png"))
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in figures}
        artifacts.main()
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in figures}
        self.assertEqual(before, after)
        generated = [
            ROOT / "results" / "recalculated_claims.json",
            *(ROOT / "paper" / "tables").glob("table*.tex"),
        ]
        for path in generated:
            self.assertNotIn(b"\r\n", path.read_bytes(), str(path))

    def test_canonical_pdf_contains_expected_tables_and_corrections(self) -> None:
        text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(
                ROOT / "paper" / "Verification-Gated-Local-Model-Cascading.pdf"
            ).pages
        )
        normalized = " ".join(
            text.translate(
                str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})
            ).split()
        )
        for number in range(1, 4):
            self.assertIn(f"Table {number}:", text)
        self.assertIn("oracle-gated complementarity study", normalized)
        self.assertIn("architecturally asymmetric", normalized)
        self.assertIn("tier-use composition, not an efficiency metric", normalized)
        self.assertIn(
            "Verification-Gated Local Model Cascading", normalized
        )


if __name__ == "__main__":
    unittest.main()
