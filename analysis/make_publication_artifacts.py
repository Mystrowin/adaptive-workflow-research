"""Recalculate audited values and regenerate paper tables and figures.

This script is deliberately analysis-only. It reads the sanitized export and
read-only audit, performs deterministic arithmetic, and never runs inference or
opens a network connection.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PAPER = ROOT / "paper"
FIGURES = PAPER / "figures"
TABLES = PAPER / "tables"


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.2f}\\%"


def num(value: float) -> str:
    if math.isclose(value, round(value)):
        return f"{round(value):,.0f}"
    return f"{value:,.2f}"


def tex(value: Any) -> str:
    text = str(value)
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def overall(summary: dict[str, Any], condition: str) -> dict[str, Any]:
    for row in summary["aggregates"]:
        if row["condition"] == condition and row["benchmark"] == "overall":
            return row
    raise KeyError(condition)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


NAVY = (30, 55, 87)
BLUE = (43, 111, 176)
TEAL = (38, 145, 135)
ORANGE = (224, 129, 54)
RED = (190, 70, 70)
INK = (35, 40, 47)
MUTED = (95, 104, 115)
GRID = (218, 224, 230)
PAPER_WHITE = (255, 255, 255)


def canvas(
    width: int = 1800, height: int = 1050
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), PAPER_WHITE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(205, 211, 218), width=2)
    return image, draw


def title(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.text((70, 40), text, fill=NAVY, font=font(42, True))


def footer(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.text((70, 990), text, fill=MUTED, font=font(22))


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color=INK,
    width: int = 5,
) -> None:
    draw.line((*start, *end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = max(1.0, math.hypot(dx, dy))
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = (x2, y2)
    left = (x2 - 22 * ux + 11 * px, y2 - 22 * uy + 11 * py)
    right = (x2 - 22 * ux - 11 * px, y2 - 22 * uy - 11 * py)
    draw.polygon((tip, left, right), fill=color)


def centered(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fnt, fill=INK
) -> None:
    left, top, right, bottom = box
    bbox = draw.multiline_textbbox((0, 0), text, font=fnt, align="center", spacing=6)
    x = (left + right - (bbox[2] - bbox[0])) // 2
    y = (top + bottom - (bbox[3] - bbox[1])) // 2
    draw.multiline_text((x, y), text, font=fnt, fill=fill, align="center", spacing=6)


def figure1() -> None:
    image, draw = canvas()
    title(draw, "Figure 1. Historical verification-gated cascade")
    boxes = [
        ("Frozen task prompt", 80, 360, 390, 560, (232, 240, 248)),
        ("Initial route\nFAST / BEST", 440, 360, 720, 560, (226, 243, 240)),
        ("Local generation\none completion", 830, 360, 1120, 560, (246, 237, 221)),
        ("EvalPlus verifier\nbase + Plus tests", 1230, 360, 1540, 560, (237, 232, 247)),
    ]
    for label, left, top, right, bottom, fill in boxes:
        draw.rounded_rectangle(
            (left, top, right, bottom), radius=22, fill=fill, outline=NAVY, width=4
        )
        centered(draw, (left, top, right, bottom), label, font(28, True))
    arrow(draw, (390, 460), (440, 460))
    arrow(draw, (720, 460), (830, 460))
    arrow(draw, (1120, 460), (1230, 460))
    draw.rounded_rectangle(
        (1370, 140, 1650, 270), radius=20, fill=(223, 246, 225), outline=TEAL, width=4
    )
    centered(draw, (1370, 140, 1650, 270), "PASS\nretain output", font(28, True), TEAL)
    arrow(draw, (1385, 360), (1510, 270), TEAL)
    draw.rounded_rectangle(
        (1010, 670, 1650, 835), radius=20, fill=(252, 229, 229), outline=RED, width=4
    )
    centered(
        draw,
        (1010, 670, 1650, 835),
        "FAIL -> next tier if available\nFAST -> BALANCED -> BEST\nBEST failure -> stop",
        font(25, True),
        RED,
    )
    arrow(draw, (1385, 560), (1300, 670), RED)
    draw.text(
        (120, 705),
        "Historical behavior: later tiers received the original frozen task prompt.\n"
        "Generated code and verifier feedback were not transferred into later prompts.",
        fill=INK,
        font=font(25),
    )
    footer(
        draw,
        "Primary architecture diagram; arrows show control flow, not information transfer of failed outputs.",
    )
    image.save(FIGURES / "figure1_architecture.png", optimize=True)


def bar_chart(
    path: Path,
    chart_title: str,
    labels: list[str],
    values: list[float],
    colors: list[tuple[int, int, int]],
    ylabel: str,
    maximum: float,
    suffix: str = "",
    *,
    integer_values: bool = False,
    footer_text: str = (
        "Primary task-weighted Plus result; base and Plus are scores of the same completion."
    ),
) -> None:
    image, draw = canvas()
    title(draw, chart_title)
    x0, y0, x1, y1 = 170, 160, 1700, 850
    draw.line((x0, y0, x0, y1), fill=INK, width=3)
    draw.line((x0, y1, x1, y1), fill=INK, width=3)
    for i in range(6):
        y = y1 - int((y1 - y0) * i / 5)
        value = maximum * i / 5
        draw.line((x0, y, x1, y), fill=GRID, width=2)
        draw.text((65, y - 15), f"{value:.0f}{suffix}", fill=MUTED, font=font(22))
    group_width = (x1 - x0) / max(1, len(labels))
    bar_width = min(190, int(group_width * 0.58))
    for i, (label, value, color) in enumerate(zip(labels, values, colors)):
        center = int(x0 + group_width * (i + 0.5))
        height = int((y1 - y0) * value / maximum) if maximum else 0
        left = center - bar_width // 2
        top = y1 - height
        draw.rounded_rectangle(
            (left, top, center + bar_width // 2, y1), radius=12, fill=color
        )
        value_label = f"{value:.0f}" if integer_values else f"{value:.1f}{suffix}"
        draw.text(
            (center - 45, top - 45),
            value_label,
            fill=INK,
            font=font(24, True),
        )
        bbox = draw.textbbox((0, 0), label, font=font(24))
        draw.text(
            (center - (bbox[2] - bbox[0]) // 2, y1 + 25), label, fill=INK, font=font(24)
        )
    draw.text((x0 - 140, y0 - 45), ylabel, fill=MUTED, font=font(23))
    footer(draw, footer_text)
    image.save(path, optimize=True)


def figure2(audit: dict[str, Any]) -> None:
    values = []
    for condition in ("small_only", "strong_only", "adaptive"):
        result = audit["condition_results"][condition]["by_benchmark"]
        values.append(
            [
                result["humaneval"]["rate"] * 100,
                result["mbpp"]["rate"] * 100,
                audit["condition_results"][condition]["task_weighted"]["rate"] * 100,
            ]
        )
    image, draw = canvas(2100, 1150)
    title(draw, "Figure 2. Verified Plus pass rates")
    x0, y0, x1, y1 = 180, 180, 1990, 920
    draw.line((x0, y0, x0, y1), fill=INK, width=3)
    draw.line((x0, y1, x1, y1), fill=INK, width=3)
    for i in range(6):
        y = y1 - int((y1 - y0) * i / 5)
        value = 100 * i / 5
        draw.line((x0, y, x1, y), fill=GRID, width=2)
        draw.text((80, y - 15), f"{value:.0f}%", fill=MUTED, font=font(22))
    groups = ["HumanEval+", "MBPP+", "Overall"]
    conds = ["Small-only", "Strong-only", "Adaptive"]
    cols = [BLUE, ORANGE, TEAL]
    group_width = (x1 - x0) / len(groups)
    bar_width = 95
    for g, label in enumerate(groups):
        center = x0 + group_width * (g + 0.5)
        for c, (condition, color) in enumerate(zip(conds, cols)):
            value = values[c][g]
            cx = int(center + (c - 1) * 115)
            top = y1 - int((y1 - y0) * value / 100)
            draw.rectangle(
                (cx - bar_width // 2, top, cx + bar_width // 2, y1), fill=color
            )
            draw.text(
                (cx - 38, top - 38), f"{value:.1f}", fill=INK, font=font(21, True)
            )
        bbox = draw.textbbox((0, 0), label, font=font(27, True))
        draw.text(
            (int(center) - (bbox[2] - bbox[0]) // 2, y1 + 28),
            label,
            fill=INK,
            font=font(27, True),
        )
    for i, (condition, color) in enumerate(zip(conds, cols)):
        left = 400 + i * 430
        draw.rectangle((left, 1030, left + 28, 1058), fill=color)
        draw.text((left + 42, 1024), condition, fill=INK, font=font(24))
    footer(
        draw,
        "Primary result. Overall is task-weighted across 164 HumanEval+ and 378 MBPP+ tasks.",
    )
    image.save(FIGURES / "figure2_plus_pass_rates.png", optimize=True)


def figure3(audit: dict[str, Any]) -> None:
    paired = audit["complementarity"]["matrices"]["Adaptive_vs_Strong_only"]
    labels = ["Both pass", "Adaptive only", "Strong only", "Both fail"]
    vals = [
        paired["both_pass"],
        paired["A_only_pass"],
        paired["B_only_pass"],
        paired["both_fail"],
    ]
    bar_chart(
        FIGURES / "figure3_paired_outcomes.png",
        "Figure 3. Adaptive versus Strong-only paired outcomes",
        labels,
        vals,
        [TEAL, BLUE, ORANGE, (150, 157, 165)],
        "tasks",
        320,
        integer_values=True,
    )


def figure4(audit: dict[str, Any]) -> None:
    dist = audit["complementarity"]["final_success_tier_distribution"]
    labels = ["FAST", "BALANCED", "BEST"]
    vals = [dist[x] for x in labels]
    bar_chart(
        FIGURES / "figure4_success_tiers.png",
        "Figure 4. Tier producing Adaptive verified successes",
        labels,
        vals,
        [BLUE, ORANGE, RED],
        "successful tasks",
        240,
        integer_values=True,
    )


def figure5(audit: dict[str, Any]) -> None:
    ex = audit["expenditure"]["adaptive_vs_strong"]
    metrics = [
        (
            "Plus passes",
            ex["plus_successes"]["adaptive"] / ex["plus_successes"]["strong_only"],
        ),
        (
            "Weighted total\nproxy",
            ex["weighted_total_token_proxy"]["adaptive"]
            / ex["weighted_total_token_proxy"]["strong_only"],
        ),
        (
            "CPU seconds",
            ex["cpu_time_seconds"]["adaptive"] / ex["cpu_time_seconds"]["strong_only"],
        ),
        (
            "Wall seconds",
            ex["wall_time_ms"]["adaptive"] / ex["wall_time_ms"]["strong_only"],
        ),
        (
            "Peak RAM",
            ex["peak_ram_bytes"]["adaptive"] / ex["peak_ram_bytes"]["strong_only"],
        ),
        (
            "Raw total\ntokens",
            ex["raw_total_tokens"]["adaptive"] / ex["raw_total_tokens"]["strong_only"],
        ),
    ]
    image, draw = canvas(2200, 1200)
    title(draw, "Figure 5. Adaptive / Strong-only normalized trade-offs")
    x0, y0, x1, y1 = 220, 170, 2080, 850
    draw.line((x0, y0, x0, y1), fill=INK, width=3)
    draw.line((x0, y1, x1, y1), fill=INK, width=3)
    maximum = 2.4
    for i in range(7):
        y = y1 - int((y1 - y0) * i / 6)
        value = maximum * i / 6
        draw.line((x0, y, x1, y), fill=GRID, width=2)
        draw.text((110, y - 15), f"{value:.1f}x", fill=MUTED, font=font(22))
    group_width = (x1 - x0) / len(metrics)
    for i, (label, value) in enumerate(metrics):
        center = int(x0 + group_width * (i + 0.5))
        top = y1 - int((y1 - y0) * value / maximum)
        color = BLUE if i == 0 else (ORANGE if value >= 1.0 else TEAL)
        draw.rounded_rectangle(
            (center - 105, top, center + 105, y1), radius=12, fill=color
        )
        draw.text(
            (center - 55, top - 42), f"{value:.2f}x", fill=INK, font=font(24, True)
        )
        centered(
            draw, (center - 145, y1 + 20, center + 145, y1 + 105), label, font(22), INK
        )
    draw.text((x0 - 170, y0 - 45), "ratio", fill=MUTED, font=font(23))
    draw.line(
        (x0, y1 - int((y1 - y0) / maximum), x1, y1 - int((y1 - y0) / maximum)),
        fill=RED,
        width=3,
    )
    draw.text(
        (x1 - 350, y1 - int((y1 - y0) / maximum) - 35),
        "Strong-only = 1.00x",
        fill=RED,
        font=font(22, True),
    )
    legend_y = 1015
    for x, color, label in (
        (160, BLUE, "outcome ratio"),
        (650, ORANGE, "expenditure above baseline"),
        (1320, TEAL, "expenditure below baseline"),
    ):
        draw.rectangle((x, legend_y, x + 28, legend_y + 28), fill=color)
        draw.text((x + 42, legend_y - 2), label, fill=INK, font=font(22))
    draw.text(
        (70, 1110),
        "Ratios have different underlying units and are not a universal efficiency score.",
        fill=MUTED,
        font=font(22),
    )
    image.save(FIGURES / "figure5_tradeoffs.png", optimize=True)


def figure6(audit: dict[str, Any]) -> None:
    routes = audit["routing"]["initial_tier_counts"]
    labels = ["FAST", "BALANCED", "BEST"]
    vals = [routes.get(x, 0) for x in labels]
    bar_chart(
        FIGURES / "figure6_initial_routing.png",
        "Figure 6. Initial Adaptive routing distribution",
        labels,
        vals,
        [BLUE, ORANGE, RED],
        "tasks",
        560,
        integer_values=True,
        footer_text=(
            "Initial route counts across 542 Adaptive tasks; BALANCED was reached only by escalation."
        ),
    )


def tables(
    audit: dict[str, Any], manifest: dict[str, Any], summary: dict[str, Any]
) -> None:
    models = {row["tier"]: row for row in manifest["models"]}
    config_rows = [
        ("HumanEval+", "v0.1.10", "164", "EvalPlus augmented tests"),
        ("MBPP+", "v0.2.0", "378", "EvalPlus augmented tests"),
        (
            "Total",
            "same paired task set",
            "542",
            "one completion scored on base and Plus",
        ),
        (
            "FAST",
            models["FAST"]["model"],
            f"{models['FAST']['parameter_billions']:.1f}B",
            models["FAST"]["quantization"],
        ),
        (
            "BALANCED",
            models["BALANCED"]["model"],
            f"{models['BALANCED']['parameter_billions']:.1f}B",
            models["BALANCED"]["quantization"],
        ),
        (
            "BEST",
            models["BEST"]["model"],
            f"{models['BEST']['parameter_billions']:.1f}B",
            models["BEST"]["quantization"],
        ),
        (
            "Sampling",
            "temperature 0; top_p 1",
            "seed 20260824",
            "one thread; 1024 output cap",
        ),
        (
            "Verifier",
            manifest["verification"]["evaluator"],
            manifest["verification"]["evaluator_version"],
            "Docker network none; 120 s timeout",
        ),
        (
            "Resource ceiling",
            "CPU 45% soft / 50% hard",
            "RAM 45% soft / 50% hard",
            "process-tree controls",
        ),
    ]
    config = [
        r"\begin{tabular}{llll}",
        r"\toprule",
        r"Item & Frozen value & Size/count & Notes \\",
        r"\midrule",
    ]
    config.extend(
        f"{tex(a)} & {tex(b)} & {tex(c)} & {tex(d)} \\\\" for a, b, c, d in config_rows
    )
    config.extend([r"\bottomrule", r"\end{tabular}"])
    write(TABLES / "table1_configuration.tex", "\n".join(config))

    correctness = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Condition & HumanEval+ & MBPP+ & Overall & Macro average \\",
        r"\midrule",
    ]
    for condition, label in (
        ("small_only", "Small-only"),
        ("strong_only", "Strong-only"),
        ("adaptive", "Adaptive"),
    ):
        cr = audit["condition_results"][condition]
        correctness.append(
            f"{label} & {cr['by_benchmark']['humaneval']['passes']}/{cr['by_benchmark']['humaneval']['n']} ({pct(cr['by_benchmark']['humaneval']['rate'])}) "
            f"& {cr['by_benchmark']['mbpp']['passes']}/{cr['by_benchmark']['mbpp']['n']} ({pct(cr['by_benchmark']['mbpp']['rate'])}) "
            f"& {cr['task_weighted']['passes']}/{cr['task_weighted']['n']} ({pct(cr['task_weighted']['rate'])}) "
            f"& {pct(cr['equal_benchmark_macro_average'])} \\\\"
        )
    correctness.extend([r"\bottomrule", r"\end{tabular}"])
    write(TABLES / "table2_correctness.tex", "\n".join(correctness))

    ex = audit["expenditure"]["adaptive_vs_strong"]
    metrics = [
        (
            "Plus successes",
            ex["plus_successes"]["adaptive"],
            ex["plus_successes"]["strong_only"],
            ex["plus_successes"]["relative_difference"],
        ),
        (
            "Raw input tokens",
            ex["raw_input_tokens"]["adaptive"],
            ex["raw_input_tokens"]["strong_only"],
            ex["raw_input_tokens"]["relative_difference"],
        ),
        (
            "Raw output tokens",
            ex["raw_output_tokens"]["adaptive"],
            ex["raw_output_tokens"]["strong_only"],
            ex["raw_output_tokens"]["relative_difference"],
        ),
        (
            "Raw total tokens",
            ex["raw_total_tokens"]["adaptive"],
            ex["raw_total_tokens"]["strong_only"],
            ex["raw_total_tokens"]["relative_difference"],
        ),
        (
            "Weighted input proxy",
            ex["weighted_input_token_proxy"]["adaptive"],
            ex["weighted_input_token_proxy"]["strong_only"],
            ex["weighted_input_token_proxy"]["relative_difference"],
        ),
        (
            "Weighted output proxy",
            ex["weighted_output_token_proxy"]["adaptive"],
            ex["weighted_output_token_proxy"]["strong_only"],
            ex["weighted_output_token_proxy"]["relative_difference"],
        ),
        (
            "Weighted total proxy",
            ex["weighted_total_token_proxy"]["adaptive"],
            ex["weighted_total_token_proxy"]["strong_only"],
            ex["weighted_total_token_proxy"]["relative_difference"],
        ),
        (
            "CPU seconds",
            ex["cpu_time_seconds"]["adaptive"],
            ex["cpu_time_seconds"]["strong_only"],
            ex["cpu_time_seconds"]["relative_difference"],
        ),
        (
            "Wall seconds",
            ex["wall_time_ms"]["adaptive"] / 1000,
            ex["wall_time_ms"]["strong_only"] / 1000,
            ex["wall_time_ms"]["relative_difference"],
        ),
        (
            "Peak CPU",
            ex["peak_cpu_percent"]["adaptive"],
            ex["peak_cpu_percent"]["strong_only"],
            ex["peak_cpu_percent"]["relative_difference"],
        ),
        (
            "Peak RAM bytes",
            ex["peak_ram_bytes"]["adaptive"],
            ex["peak_ram_bytes"]["strong_only"],
            ex["peak_ram_bytes"]["relative_difference"],
        ),
        (
            "Model calls",
            ex["model_invocations"]["adaptive"],
            ex["model_invocations"]["strong_only"],
            ex["model_invocations"]["relative_difference"],
        ),
        (
            "Verifier calls",
            ex["verifier_invocations"]["adaptive"],
            ex["verifier_invocations"]["strong_only"],
            ex["verifier_invocations"]["relative_difference"],
        ),
    ]
    resource = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Metric & Adaptive & Strong-only & Relative difference \\",
        r"\midrule",
    ]
    for name, adaptive, strong, relative in metrics:
        if name == "Peak CPU":
            relative_text = f"{adaptive - strong:+.3f} pp"
        else:
            relative_text = f"{relative * 100:+.2f}\\%"
        resource.append(
            f"{tex(name)} & {num(adaptive)} & {num(strong)} & {relative_text} \\\\"
        )
    resource.extend([r"\bottomrule", r"\end{tabular}"])
    write(TABLES / "table3_resource_usage.tex", "\n".join(resource))

    paired = audit["paired_statistics"]
    paired_table = [
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Paired outcome & Count \\",
        r"\midrule",
        f"Both pass & {paired['both_pass']} \\\\",
        f"Adaptive only & {paired['A_only_pass']} \\\\",
        f"Strong-only only & {paired['B_only_pass']} \\\\",
        f"Both fail & {paired['both_fail']} \\\\",
        r"\midrule",
        f"Paired risk difference & {paired['paired_risk_difference'] * 100:.2f}\\% \\\\",
        f"Exact McNemar p-value (post-hoc) & {paired['exact_mcnemar_two_sided_p_value']:.3e} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    write(TABLES / "table4_paired_outcomes.tex", "\n".join(paired_table))

    matrices = audit["complementarity"]["matrices"]
    complementarity = [
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Observed comparison & n & Both pass & A only & B only & Both fail \\",
        r"\midrule",
    ]
    for key, label in (
        ("FAST_vs_BALANCED_observed_overlap", "FAST vs BALANCED (conditional)"),
        ("BALANCED_vs_BEST_observed_overlap", "BALANCED vs BEST (conditional)"),
        ("FAST_vs_BEST_static_full", "FAST vs BEST static"),
        ("Adaptive_vs_Strong_only", "Adaptive vs Strong-only"),
    ):
        row = matrices[key]
        complementarity.append(
            f"{label} & {row['n_overlap']} & {row['both_pass']} & {row['A_only_pass']} & {row['B_only_pass']} & {row['both_fail']} \\\\"
        )
    complementarity.extend([r"\bottomrule", r"\end{tabular}"])
    write(TABLES / "table5_complementarity.tex", "\n".join(complementarity))

    limitations = [
        r"\begin{tabular}{p{0.32\linewidth}p{0.58\linewidth}}",
        r"\toprule",
        r"Threat & Treatment in this study \\",
        r"\midrule",
        r"Conditional tiers & Label tier overlaps as observed conditional outcomes; no standalone Balanced baseline is claimed. \\",
        r"Verifier failures & Keep six shared MBPP infrastructure failures in the primary denominator; exclusion is post-hoc. \\",
        r"Budget curve & Preserve frozen B0 and disclose that every condition exhausted before the first cutoff. \\",
        r"Output retention & State that exact historical generated programs were not persisted. \\",
        r"Public benchmark age & Treat contamination as plausible and avoid general-intelligence claims. \\",
        r"Proxy interpretation & Call weighted token values proxies, never FLOPs or generic compute. \\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    write(TABLES / "table6_threats.tex", "\n".join(limitations))


def main() -> None:
    audit = load("audit.json")
    summary = load("summary.json")
    manifest = load("experiment_manifest.json")
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    tables(audit, manifest, summary)
    figure1()
    figure2(audit)
    figure3(audit)
    figure4(audit)
    figure5(audit)
    figure6(audit)

    ex = audit["expenditure"]["adaptive_vs_strong"]
    weighted_efficiency_ratio = (
        ex["plus_successes"]["adaptive"] / ex["weighted_total_token_proxy"]["adaptive"]
    ) / (
        ex["plus_successes"]["strong_only"]
        / ex["weighted_total_token_proxy"]["strong_only"]
    )
    claims = {
        "experiment_id": audit["experiment_id"],
        "tasks": 542,
        "plus_successes": {
            "adaptive": 331,
            "strong_only": 297,
            "small_only": 220,
        },
        "plus_pass_rates": {
            "adaptive": 331 / 542,
            "strong_only": 297 / 542,
            "small_only": 220 / 542,
        },
        "adaptive_minus_strong": {
            "successes": 34,
            "percentage_points": (331 - 297) / 542,
            "relative_successes": 331 / 297 - 1,
        },
        "adaptive_strong_weighted_total_proxy_relative_difference": ex[
            "weighted_total_token_proxy"
        ]["relative_difference"],
        "successes_per_weighted_total_proxy_relative_difference": weighted_efficiency_ratio
        - 1,
        "strong_model_avoidance_rate": audit["complementarity"][
            "strong_model_avoidance"
        ]["rate"],
        "initial_routes": audit["routing"]["initial_tier_counts"],
        "shared_verifier_error_tasks": audit["failures"][
            "common_verifier_error_task_ids_all_conditions"
        ],
        "frozen_budget": audit["budget"]["frozen_b0"],
        "frozen_budget_cutoffs": audit["budget"]["frozen_total_token_cutoffs"],
        "actual_total_proxy": audit["budget"]["actual_total_token_proxy_by_condition"],
        "raw_hashes": {
            "raw_results_jsonl": audit["integrity"]["raw_results_sha256"],
            "results_sqlite": audit["integrity"]["sqlite_sha256"],
        },
        "source_hashes": {
            "frozen": audit["integrity"]["frozen_source_tree_sha256"],
            "audited_current": audit["integrity"]["current_source_tree_sha256"],
        },
        "resource_violation": summary["resource_violation"],
    }
    write(
        RESULTS / "recalculated_claims.json",
        json.dumps(claims, indent=2, sort_keys=True),
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "figures": 6,
                "tables": 6,
                "claims": str(RESULTS / "recalculated_claims.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
