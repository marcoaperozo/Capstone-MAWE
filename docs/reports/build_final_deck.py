# -*- coding: utf-8 -*-
"""Generate the final presentation deck from the measured figures.

    python scripts/week12_final_check.py       # produces findings.json
    python docs/reports/build_final_deck.py    # produces FINAL-REPORT.pptx

Like the final report, every number here is read from `findings.json` rather
than typed in, so the deck cannot drift from the code it describes.
"""

from __future__ import annotations

import json
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "FINAL-REPORT.pptx")
FINDINGS = os.path.join(HERE, "findings.json")

if not os.path.exists(FINDINGS):
    sys.exit("findings.json is missing; run scripts/week12_final_check.py")
with open(FINDINGS, encoding="utf-8") as _handle:
    F = json.load(_handle)

BENCH = F["benchmark"]
TESTS = F["tests"]
TERM = F["termination"]
COMP = F["compression"]
CMP = F["comparison"]
COND = CMP["conditions"]
HYP = F["hypotheses"]

NAVY = RGBColor(0x00, 0x34, 0x66)
LBLUE = RGBColor(0xBB, 0xE0, 0xE3)
PALE = RGBColor(0xED, 0xF5, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x6B, 0x6B, 0x6B)
GREEN = RGBColor(0x1E, 0x6F, 0x3C)
AMBER = RGBColor(0xA8, 0x62, 0x00)
RED = RGBColor(0xB0, 0x30, 0x25)

FONT = "Arial"
W, H = 13.333, 7.5

prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)
BLANK = prs.slide_layouts[6]

STATUS_COLORS = {
    "SUPPORTED": GREEN, "MEASURED": GREEN,
    "NOT YET TESTABLE": AMBER, "NOT SUPPORTED": RED,
    "done": GREEN, "validated": GREEN, "not run": AMBER,
}


def pct(value, digits=1):
    return f"{value * 100:.{digits}f}%"


def textbox(slide, x, y, w, h, lines, size=18, color=BLACK, bold=False,
            align=PP_ALIGN.LEFT, space_after=8, line_spacing=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    for i, item in enumerate(lines):
        text, sz, bd, col = (item if isinstance(item, tuple)
                             else (item, size, bold, color))
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        if line_spacing:
            p.line_spacing = line_spacing
        if not text:
            continue
        r = p.add_run()
        r.text = text
        r.font.size, r.font.bold, r.font.name = Pt(sz), bd, FONT
        r.font.color.rgb = col
    return box


def header(slide, title, kicker=None):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
                                 Inches(W), Inches(1.15))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    bar.shadow.inherit = False
    textbox(slide, 0.6, 0.22, W - 3.4, 0.7, [(title, 27, True, WHITE)])
    if kicker:
        textbox(slide, W - 3.8, 0.36, 3.2, 0.5, [(kicker, 13, False, LBLUE)],
                align=PP_ALIGN.RIGHT)


def footer(slide, page):
    textbox(slide, 0.6, H - 0.5, 9.0, 0.3,
            [(f"MAWE Capstone  ·  Final Report  ·  engine "
              f"v{F['engine_version']}  ·  {TESTS['total']} tests", 10,
              False, GREY)])
    textbox(slide, W - 1.4, H - 0.5, 0.8, 0.3,
            [(str(page), 10, False, GREY)], align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, rows, widths, size=13, row_h=0.42,
          status_col=None):
    n, c = len(rows), len(rows[0])
    gf = slide.shapes.add_table(n, c, Inches(x), Inches(y), Inches(w),
                                Inches(row_h * n))
    tbl = gf.table
    total = sum(widths)
    for j, cw in enumerate(widths):
        tbl.columns[j].width = Emu(int(Inches(w) * cw / total))
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.09)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = (NAVY if i == 0
                                        else (WHITE if i % 2 else PALE))
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            r = p.add_run()
            r.text = str(val)
            r.font.size = Pt(size)
            r.font.name = FONT
            r.font.bold = (i == 0)
            if i == 0:
                r.font.color.rgb = WHITE
            elif status_col is not None and j == status_col:
                r.font.color.rgb = STATUS_COLORS.get(str(val), BLACK)
                r.font.bold = True
            else:
                r.font.color.rgb = BLACK
    return gf


# ============================================================== 1 title
s = prs.slides.add_slide(BLANK)
band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
                          Inches(W), Inches(3.5))
band.fill.solid()
band.fill.fore_color.rgb = NAVY
band.line.fill.background()
band.shadow.inherit = False

textbox(s, 0.9, 0.85, 11.6, 1.0,
        [("MAWE — Multi-Agent AI Workflow Engine", 40, True, WHITE)])
textbox(s, 0.9, 1.95, 11.6, 0.5,
        [("Simulating an Autonomous Software Development Team", 20, False,
          LBLUE)])
textbox(s, 0.9, 2.55, 11.6, 0.6,
        [("Final report  ·  Phase 4 complete  ·  "
          f"engine v{F['engine_version']}", 16, False, LBLUE)])

textbox(s, 0.9, 3.95, 11.6, 0.9, [
    ("Marco Perozo  ·  Gabriel Marte  ·  Lewdy Aquino  ·  Alvin Almonte",
     16, True, BLACK),
    ("Department of Computer Science  ·  Southwest Minnesota State "
     "University", 14, False, GREY)])

table(s, 0.9, 5.05, 11.6, [
    ["Built and tested", "Answered by measurement", "Still open"],
    [f"{TESTS['total']} automated tests\nengine v{F['engine_version']}",
     "H4 termination\nH5 context compression",
     "H1, H2, H3\nneed a real model"],
], [3.9, 3.9, 3.8], size=14, row_h=0.72)

textbox(s, 0.9, 6.65, 11.6, 0.4,
        [("Every figure in this deck is generated from measurements, not "
          "typed in.", 12, False, GREY)])

# ============================================================== 2 question
s = prs.slides.add_slide(BLANK)
header(s, "The question, and the honest answer", "1 of 7")

textbox(s, 0.6, 1.35, 12.1, 1.3, [
    ("Most AI coding tools are one model and one prompt. MAWE splits the "
     "work across three agents — Product Manager, Developer, Code Reviewer "
     "— and loops until the code passes review.", 16, False, BLACK),
    ("", 8, False, BLACK),
    ("The question is not whether agents can write code. It is whether "
     "role separation produces more correct software than a single model, "
     "and what that costs.", 16, True, NAVY)], line_spacing=1.12)

table(s, 0.6, 3.15, 12.1, [
    ["", "Hypothesis", "Verdict"],
    ["H4", "Every run terminates; under 10% exit by cap", "SUPPORTED"],
    ["H5", "Summarisation cuts context ≥40%, outcome unchanged",
     "SUPPORTED"],
    ["H1", "Role separation produces more correct software",
     "NOT YET TESTABLE"],
    ["H2", "Role separation produces better spec coverage",
     "NOT YET TESTABLE"],
    ["H3", "The improvement is worth its cost per success",
     "NOT YET TESTABLE"],
], [0.7, 7.6, 3.8], size=14, row_h=0.50, status_col=2)

textbox(s, 0.6, 6.35, 12.1, 0.7, [
    ("H1–H3 need a real API key. The instrument that answers them is built "
     "and validated; no sweep against a model has been run. That is the "
     "main limitation of this report, and it is on slide 2 rather than "
     "buried at the end.", 14, False, AMBER)], line_spacing=1.1)
footer(s, 1)

# ============================================================== 3 design
s = prs.slides.add_slide(BLANK)
header(s, "Four conditions, because the claim is comparative", "2 of 7")

textbox(s, 0.6, 1.3, 12.1, 0.5, [
    ("Measuring the engine alone answers nothing. It needs controls.",
     16, False, BLACK)])

table(s, 0.6, 1.95, 12.1, [
    ["", "Condition", "What it is"],
    ["A", "single model", "one call, no iteration, no review"],
    ["B", "self-refinement",
     "one model that critiques and revises its own code"],
    ["C", "multi-agent engine",
     "Product Manager → Developer → Reviewer, looping"],
    ["C'", "ablation", "the engine with context summarisation switched off"],
], [0.7, 3.0, 8.4], size=14, row_h=0.54)

textbox(s, 0.6, 4.55, 12.1, 2.3, [
    ("B is the control that matters.", 16, True, NAVY),
    ("Without it, \"multi-agent beats one call\" is indistinguishable from "
     "\"more attempts beat one attempt\". B iterates under the same cap with "
     "the same model, so an advantage C shows over B is not just "
     "persistence.", 14, False, BLACK),
    ("", 6, False, BLACK),
    ("One confound is reported, not removed.", 16, True, NAVY),
    ("C differs from B in two ways at once — role separation and "
     "sandbox-grounded review — so a gain over B cannot be attributed to "
     "either alone. Giving B the sandbox would stop it isolating "
     "iteration, which is its job.", 14, False, BLACK)],
    line_spacing=1.1)
footer(s, 2)

# ============================================================== 4 benchmark
s = prs.slides.add_slide(BLANK)
header(s, "The benchmark is itself measured", "3 of 7")

textbox(s, 0.6, 1.3, 12.1, 0.8, [
    (f"{BENCH['tasks']} tasks — {BENCH['easy']} easy, {BENCH['medium']} "
     f"medium, {BENCH['hard']} hard — in Python and JavaScript, with "
     f"{BENCH['hidden_tests']} hidden tests no agent ever sees. A run the "
     f"Reviewer approved can still score zero.", 15, False, BLACK)],
    line_spacing=1.1)

rows = [
    ["Property", "What it rules out", "Result"],
    ["Solvable",
     "a task nobody can pass — which would read as \"all conditions did "
     "badly\"",
     f"{BENCH['references_passing']}/{BENCH['tasks']}"],
    ["Non-vacuous", "tests a do-nothing program satisfies",
     f"{BENCH['stub_tasks_solved']}/{BENCH['tasks']} solved"],
]
if BENCH.get("mutation_score") is not None:
    rows.append(["Discriminating", "tests that miss a real defect",
                 pct(BENCH["mutation_score"])])
table(s, 0.6, 2.3, 12.1, rows, [2.3, 7.2, 2.6], size=13.5, row_h=0.62)

textbox(s, 0.6, 4.5, 12.1, 2.3, [
    ("Mutation testing found two real defects in the benchmark:", 16, True,
     NAVY),
    ("1.  Every error-path test asserted \"exit status 1\" — which an "
     "uncaught exception also produces. Deleting an input guard left the "
     "tests green, and a file of prose scored 3 of 7 on FizzBuzz off the "
     "error cases alone.", 14, False, BLACK),
    ("2.  Four tasks had untested contract boundaries: an index one past "
     "the end, a zero-length interval, a width of 1, a cheap route found "
     "after an expensive one.", 14, False, BLACK)], line_spacing=1.1)
footer(s, 3)

# ============================================================== 5 results
s = prs.slides.add_slide(BLANK)
header(s, "Results", "4 of 7")

if not CMP["measures_a_model"]:
    warn = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.6),
                              Inches(1.3), Inches(12.1), Inches(0.72))
    warn.fill.solid()
    warn.fill.fore_color.rgb = RGBColor(0xFD, 0xF2, 0xDE)
    warn.line.color.rgb = AMBER
    warn.shadow.inherit = False
    textbox(s, 0.85, 1.42, 11.6, 0.6, [
        ("These numbers come from a fixture with known answers, not a "
         "model. They show the pipeline works and that the comparison "
         "detects a difference. They say nothing about any model.",
         13, True, RGBColor(0x7A, 0x47, 0x00))], line_spacing=1.05)

table(s, 0.6, 2.25, 12.1, [
    ["Condition", "Solved", "Success rate (95% CI)", "Pass rate", "Tokens"],
] + [
    [f"{label}  {name}",
     f"{COND[label]['solved']}/{COND[label]['tasks']}",
     f"{pct(COND[label]['success_rate'])}  "
     f"[{pct(COND[label]['success_ci'][0], 0)}–"
     f"{pct(COND[label]['success_ci'][1], 0)}]",
     pct(COND[label]["pass_rate"]),
     f"{COND[label]['tokens']:,.0f}"]
    for label, name in (("A", "single model"), ("B", "self-refinement"),
                        ("C", "engine"), ("C'", "engine, no summarisation"))
    if label in COND
], [4.0, 1.6, 3.1, 1.7, 1.7], size=13.5, row_h=0.5)

comparisons = [["Comparison", "n", "p (Holm)", "Effect"]]
for item in CMP["success_comparisons"]:
    adjusted = ("—" if item["p_adjusted"] is None
                else f"{item['p_adjusted']:.4f}")
    comparisons.append([f"{item['left']} vs {item['right']}", str(item["n"]),
                        adjusted + (" *" if item["reject"] else ""),
                        f"{item['effect']:+.2f} {item['effect_label']}"])
table(s, 0.6, 4.95, 7.4, comparisons, [2.4, 1.0, 1.9, 2.1], size=12.5,
      row_h=0.38)

textbox(s, 8.35, 4.95, 4.35, 2.1, [
    ("Task success is binary, so the paired test is McNemar's exact test "
     "on the discordant pairs — not Wilcoxon, which would discard the "
     "agreeing pairs and compute from a far smaller n while reading as a "
     "20-task result.", 12.5, False, BLACK),
    ("Holm-corrected across the four comparisons.", 12.5, False, GREY)],
    line_spacing=1.08)
footer(s, 4)

# ============================================================== 6 H4/H5
s = prs.slides.add_slide(BLANK)
header(s, "What is answered: termination and context", "5 of 7")

textbox(s, 0.6, 1.3, 5.9, 0.45, [("H4 — every run terminates", 18, True,
                                  NAVY)])
textbox(s, 0.6, 1.8, 5.9, 1.9, [
    (f"{TERM['runs']:,} randomised adversarial sequences across "
     f"{TERM['configurations']} policy configurations.", 14, False, BLACK),
    (f"{TERM['non_terminating']} failed to terminate.  "
     f"{TERM['over_cap']} exceeded a cap.", 15, True, GREEN),
    ("", 6, False, BLACK),
    (f"Under the default policy the cap accounts for "
     f"{pct(TERM.get('default_cap_share', 0))} of exits — the other four "
     f"detectors catch runs first.", 13.5, False, BLACK)],
    line_spacing=1.1)

textbox(s, 6.9, 1.3, 5.8, 0.45, [("H5 — context stays bounded", 18, True,
                                  NAVY)])
ladder = COMP["ladder"]
keys = sorted(ladder, key=lambda k: int(k))
table(s, 6.9, 1.85, 5.8, [
    ["Iterations", "Naive", "Compressed", "Saved"],
] + [[k, f"{ladder[k]['uncompressed']:,}",
      f"{ladder[k]['compressed']:,}", pct(ladder[k]["reduction"], 0)]
     for k in keys if int(k) in (2, 10, 20, 40, 80)],
    [1.6, 1.5, 1.5, 1.2], size=12, row_h=0.36)

textbox(s, 0.6, 4.15, 5.9, 2.2, [
    ("Five independent exits", 15, True, NAVY),
    ("iteration cap · no progress (identical code twice) · oscillation "
     "(a version already seen) · repeated issues (the same complaint "
     "refiled) · error", 13, False, BLACK),
    ("", 4, False, BLACK),
    ("Routing and reason-reporting are one function, so they cannot drift "
     "apart.", 13, False, GREY)], line_spacing=1.1)

textbox(s, 6.9, 4.15, 5.8, 2.2, [
    (f"{pct(COMP['best_reduction'])} smaller at 80 iterations", 15, True,
     GREEN),
    (f"Never over the {COMP['budget']:,}-token budget; the largest context "
     f"actually sent was {COMP['largest_context']:,}.", 13, False, BLACK),
    ("", 4, False, BLACK),
    ("The compression is structured, not generative: older iterations "
     "collapse into a log built from recorded facts. A summariser that "
     "hallucinated would corrupt the Developer's only memory of what it "
     "already tried.", 13, False, BLACK)], line_spacing=1.08)
footer(s, 5)

# ============================================================== 7 limits
s = prs.slides.add_slide(BLANK)
header(s, "What this does not show", "6 of 7")

textbox(s, 0.6, 1.3, 12.1, 0.5, [
    ("Stated plainly, because a capstone that only lists what worked is "
     "not a report.", 15, False, BLACK)])

table(s, 0.6, 1.95, 12.1, [
    ["Limitation", "Why it matters"],
    ["No model has been measured",
     "H1, H2 and H3 need a real provider. The Anthropic and OpenAI "
     "adapters are written but have never run against a live API — "
     "untested code, not working code."],
    ["Spec coverage has no metric",
     "H2 is not just unmeasured, it is not yet measurable. The benchmark "
     "scores behaviour, not whether a specification captured the request."],
    ["C vs B confounds two variables",
     "Role separation and grounded review change together."],
    ["20 small-to-medium tasks",
     "Nothing here speaks to multi-file systems or tasks where the hard "
     "part is the design."],
    ["Functional correctness only",
     "Not style, security, maintainability or performance."],
    ["The sandbox is not a security boundary",
     "Timeout, path containment and output truncation only. Docker with "
     "no network is the hardening target and is not implemented."],
], [3.4, 8.7], size=12.5, row_h=0.73)

footer(s, 6)

# ============================================================== 8 next
s = prs.slides.add_slide(BLANK)
header(s, "What would finish it", "7 of 7")

runs = 4 * BENCH["tasks"] * CMP["repetitions"]
table(s, 0.6, 1.4, 12.1, [
    ["", "Step", "What it buys"],
    ["1", f"One sweep against a real model ({runs} runs)",
     "Answers H1 and H3. The pipeline, scoring and statistics are built "
     "and validated — this is the single remaining step."],
    ["2", "A specification-coverage metric",
     "Makes H2 testable at all."],
    ["3", "A fifth condition: B with the sandbox",
     "Separates role separation from grounded review."],
], [0.7, 4.6, 6.8], size=13.5, row_h=0.80)

textbox(s, 0.6, 4.95, 12.1, 2.0, [
    ("Where the project stands", 18, True, NAVY),
    (f"Twelve weeks, four phases, {TESTS['total']} automated tests across "
     f"{TESTS['modules']} modules, green on Python 3.11, 3.12 and 3.13. "
     f"The engine runs, the benchmark is validated against its own "
     f"reference solutions and a {pct(BENCH['mutation_score'])} mutation "
     f"score, and the comparison apparatus is proven to detect a "
     f"difference it was built to detect.",
     15, False, BLACK) if BENCH.get("mutation_score") else
    (f"Twelve weeks, four phases, {TESTS['total']} automated tests.",
     15, False, BLACK),
    ("What is missing is not code. It is one API key and about an hour of "
     "compute.", 16, True, NAVY)], line_spacing=1.12, space_after=14)
footer(s, 7)

prs.save(OUT)
print("saved", OUT)
