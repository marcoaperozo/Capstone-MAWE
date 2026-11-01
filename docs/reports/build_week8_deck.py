# -*- coding: utf-8 -*-
"""Generate the Week 8 progress report deck.

    python docs/reports/build_week8_deck.py

Numbers come from the test suite and the milestone scripts in scripts/.
"""

from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "WEEK8-PROGRESS-REPORT.pptx")

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
    textbox(slide, 0.6, 0.22, W - 3.4, 0.7, [(title, 28, True, WHITE)])
    if kicker:
        textbox(slide, W - 3.8, 0.36, 3.2, 0.5, [(kicker, 13, False, LBLUE)],
                align=PP_ALIGN.RIGHT)


def footer(slide, page):
    textbox(slide, 0.6, H - 0.52, 8.0, 0.3,
            [("MAWE Capstone  ·  Progress Report  ·  Week 8 of 12  "
              "·  engine v1.0", 10, False, GREY)])
    textbox(slide, W - 1.4, H - 0.52, 0.8, 0.3,
            [(str(page), 10, False, GREY)], align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, rows, widths, size=13, row_h=0.42,
          status_col=None, status_colors=None):
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
            cell.fill.fore_color.rgb = NAVY if i == 0 else (WHITE if i % 2 else PALE)
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
            elif status_col is not None and j == status_col and status_colors:
                r.font.color.rgb = status_colors.get(str(val), BLACK)
                r.font.bold = True
            else:
                r.font.color.rgb = BLACK
    return gf


def card(slide, x, y, w, h, title, body, accent=NAVY, title_size=14,
         body_size=12):
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                 Inches(w), Inches(h))
    box.fill.solid()
    box.fill.fore_color.rgb = PALE
    box.line.color.rgb = accent
    box.line.width = Pt(1.25)
    box.shadow.inherit = False
    box.text_frame.text = ""
    textbox(slide, x + 0.2, y + 0.14, w - 0.4, 0.4,
            [(title, title_size, True, accent)])
    textbox(slide, x + 0.2, y + 0.58, w - 0.4, h - 0.72,
            [(body, body_size, False, BLACK)], line_spacing=1.1)


# =========================================================== 1 · title
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
                        Inches(W), Inches(H))
bg.fill.solid()
bg.fill.fore_color.rgb = NAVY
bg.line.fill.background()
bg.shadow.inherit = False

textbox(s, 1.0, 1.7, 11.3, 1.0,
        [("Multi-Agent AI Workflow Engine", 46, True, WHITE)])
textbox(s, 1.0, 2.7, 11.3, 0.5,
        [("Simulating an Autonomous Software Development Team", 21, False, LBLUE)])
rule = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(3.4),
                          Inches(2.4), Inches(0.05))
rule.fill.solid()
rule.fill.fore_color.rgb = LBLUE
rule.line.fill.background()
rule.shadow.inherit = False

textbox(s, 1.0, 3.7, 11.3, 1.4, [
    ("PROGRESS REPORT  ·  END OF WEEK 8 OF 12", 16, True, WHITE),
    ("", 8, False, WHITE),
    ("Marco Perozo  ·  Gabriel Marte  ·  Lewdy Aquino  ·  Alvin Almonte",
     15, False, LBLUE),
    ("Department of Computer Science  ·  Southwest Minnesota State University",
     13, False, LBLUE),
], space_after=4)

textbox(s, 1.0, 5.65, 11.3, 0.9, [
    ("Repository", 12, True, LBLUE),
    ("github.com/marcoaperozo/Capstone-MAWE", 18, True, WHITE),
], space_after=3)

textbox(s, 1.0, H - 0.78, 11.3, 0.4,
        [("Phases 1–3 complete  ·  engine v1.0  ·  "
          "273 automated tests passing  ·  evaluation phase next",
          12, False, LBLUE)])

# =================================================== 2 · where we are
s = prs.slides.add_slide(BLANK)
header(s, "Where the project stands", "Week 8 of 12")
textbox(s, 0.6, 1.4, 12.1, 0.5, [
    ("Three of the four phases are complete and on schedule. The engine is "
     "feature-complete for the research question; what remains is measuring "
     "it against a real model.", 16, False, BLACK)], line_spacing=1.15)

table(s, 0.6, 2.25, 12.1, [
    ["Phase", "Weeks", "Deliverable", "Status"],
    ["1 · Setup & prototyping", "1–2",
     "Repository, CI, database schema, pipeline on a state graph (M1)",
     "COMPLETE"],
    ["2 · Role implementation", "3–5",
     "Product Manager, Developer and Code Reviewer agents (M2)", "COMPLETE"],
    ["3 · Memory & state", "6–8",
     "Loop hardening, context compression, integration suite, web UI (M3)",
     "COMPLETE"],
    ["4 · Testing & evaluation", "9–12",
     "Benchmark suite, single-model baseline, final report (M4)", "NEXT"],
], [2.5, 0.8, 6.1, 1.3], size=13, row_h=0.6, status_col=3,
    status_colors={"COMPLETE": GREEN, "NEXT": AMBER})

card(s, 0.6, 5.1, 3.85, 1.75, "M1 – M3 all met",
     "The three-role pipeline runs end to end, provably terminates, stays "
     "inside a token budget, and every run is fully traceable.", GREEN)
card(s, 4.72, 5.1, 3.85, 1.75, "Engine v1.0",
     "273 automated tests, green on Python 3.11, 3.12 and 3.13. No API key "
     "needed and no cost per run.", GREEN)
card(s, 8.85, 5.1, 3.85, 1.75, "What is left",
     "Phase 4: a 20-task benchmark with hidden tests, a single-model "
     "baseline, and the cost-per-success comparison.", AMBER)
footer(s, 2)

# ================================================ 3 · what changed 5-8
s = prs.slides.add_slide(BLANK)
header(s, "What was delivered in Weeks 5 to 8", "Commit history")
textbox(s, 0.6, 1.4, 12.1, 0.4, [
    ("One commit per week, each carrying that week's milestone result in its "
     "message.", 15, False, BLACK)])

table(s, 0.6, 2.0, 12.1, [
    ["Week", "Deliverable", "What it means in practice", "Tests"],
    ["5", "Code Reviewer agent (M2)",
     "The specification now carries executable checks. The Reviewer runs them "
     "in the sandbox and the measurement overrides what the model claims.",
     "145"],
    ["6", "Loop-prevention hardening",
     "Routing and reporting unified into one policy function; two new "
     "detectors (oscillation, repeated issues); 100,000-run stress sweep.",
     "210"],
    ["7", "Context compression",
     "Latest iteration kept in full, older ones collapsed into a progress "
     "log under an explicit token budget.", "243"],
    ["8", "Integration, web UI, v1.0 (M3)",
     "Whole-stack integration suite, optional FastAPI front end, and a "
     "30-point check that every layer still works together.", "273"],
], [0.6, 2.9, 7.2, 0.8], size=12.5, row_h=0.95)

textbox(s, 0.6, 6.25, 12.1, 0.6, [
    ("Next: Weeks 9–12 build the benchmark suite and run the comparison "
     "against a single model.", 14, True, NAVY)], line_spacing=1.15)
footer(s, 3)

# ====================================== 4 · the reviewer contribution
s = prs.slides.add_slide(BLANK)
header(s, "Making the Reviewer more than a second opinion", "Week 5")
textbox(s, 0.6, 1.4, 12.1, 0.75, [
    ("An acceptance criterion written in English can simply be claimed to pass "
     "by a model that never ran anything. So the Product Manager also emits "
     "executable checks — an invocation and the output it must produce — "
     "and the Reviewer runs them in the sandbox before forming a verdict.",
     15, False, BLACK)], line_spacing=1.15)

table(s, 0.6, 2.35, 12.1, [
    ["Situation", "What the engine does"],
    ["Model approves, but a check failed",
     "Overridden to REJECT. Escalated to critical on a crash or timeout."],
    ["Model rejects, all checks pass, every criterion covered",
     "Downgraded to MINOR, so a reviewer objecting to naming cannot stall the loop."],
    ["Model rejects, all checks pass, some criteria uncovered",
     "Severity STANDS — a criterion nobody tested may genuinely be unmet."],
    ["Model output unparseable",
     "Verdict comes from the execution evidence alone."],
], [4.9, 7.2], size=13, row_h=0.56)

card(s, 0.6, 5.1, 5.9, 1.75, "Demonstrated, not asserted",
     "Scripted to always approve, the Reviewer still rejected code whose "
     "rounding was wrong — a defect only visible by running it. The "
     "Developer fixed it and approval required all three checks to pass.",
     GREEN)
card(s, 6.8, 5.1, 5.9, 1.75, "A flaw this surfaced",
     "The downgrade originally fired whenever all checks passed, even when "
     "most criteria had none. That quietly reintroduced false approval. It "
     "now requires full criterion coverage.", RED)
footer(s, 4)

# ============================================ 5 · loop prevention
s = prs.slides.add_slide(BLANK)
header(s, "Making the loop stop — five mechanisms", "Week 6")
textbox(s, 0.6, 1.4, 12.1, 0.55, [
    ("All of the policy lives in one pure function of the run state, so every "
     "branch is testable without calling a model — and a randomised stress "
     "sweep can drive 100,000 sequences through it in about a second.",
     15, False, BLACK)], line_spacing=1.15)

MECH = [
    ("1 · Hard iteration cap",
     "Configurable ceiling, default five. The backstop that always holds."),
    ("2 · Severity threshold",
     "Only critical and major block approval, so trivia cannot stall the loop."),
    ("3 · No-progress detection",
     "Two consecutive identical file hashes mean the Developer is not "
     "responding to feedback."),
    ("4 · Oscillation detection  (new)",
     "A hash seen earlier, not just immediately before. Catches A → B → A "
     "cycling, invisible to mechanism 3."),
    ("5 · Repeated-issue detection  (new)",
     "A normalised fingerprint of the complaints. Renumbering or rewording "
     "the same objection is not progress."),
    ("Fallback routing",
     "Exiting without approval never fails the run: the best version is "
     "returned with a report of which mechanism fired."),
]
for i, (t, b) in enumerate(MECH):
    col, row = i % 2, i // 2
    card(s, 0.6 + col * 6.25, 2.2 + row * 1.35, 5.9, 1.2, t, b, NAVY,
         title_size=13, body_size=11.5)

band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(6.22),
                          Inches(12.1), Inches(0.62))
band.fill.solid()
band.fill.fore_color.rgb = LBLUE
band.line.color.rgb = NAVY
band.line.width = Pt(1.25)
band.shadow.inherit = False
textbox(s, 0.85, 6.31, 11.6, 0.5, [
    ("Stress result: 100,000 randomised adversarial sequences across four "
     "policy configurations. 0 failed to terminate, 0 exceeded their cap. "
     "With the cap set to 20, the detectors bounded the worst run to 8.",
     12.5, True, NAVY)], line_spacing=1.1)
footer(s, 5)

# ================================================ 6 · memory results
s = prs.slides.add_slide(BLANK)
header(s, "Keeping long runs affordable", "Week 7")
textbox(s, 0.6, 1.4, 12.1, 0.55, [
    ("The Developer prompt replayed every previous file in full, so context "
     "grew linearly while the budget did not move. Older iterations now "
     "collapse into a structured progress log.", 15, False, BLACK)],
    line_spacing=1.15)

textbox(s, 0.6, 2.1, 12.1, 0.3,
        [("Context size as a run gets longer (4,000-token budget)", 14, True, NAVY)])
table(s, 0.6, 2.5, 12.1, [
    ["Iterations", "2", "5", "10", "20", "40", "80"],
    ["Uncompressed (tokens)", "1,293", "3,260", "6,539", "13,104", "26,234",
     "52,494"],
    ["Compressed (tokens)", "688", "787", "954", "1,291", "1,966", "3,316"],
    ["Reduction", "46.8%", "75.9%", "85.4%", "90.1%", "92.5%", "93.7%"],
], [2.6, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1], size=13, row_h=0.5)

card(s, 0.6, 4.75, 5.9, 2.05, "Structured, not generative",
     "A model-written summary costs tokens, is non-deterministic, and can "
     "silently drop the detail that mattered. The fields a later iteration "
     "needs are known in advance, so they are recorded exactly and for free. "
     "The generative alternative is implemented behind the same interface for "
     "the Phase 4 comparison.", NAVY)
card(s, 6.8, 4.75, 5.9, 2.05, "H5 ablation (condition C′)",
     "End to end, with and without compression: 2,080 tokens against 513, a "
     "75.3% reduction, with an identical termination reason and iteration "
     "count. H5 targets 40%. Confirming 'no quality drop' against a real "
     "model is Phase 4 work.", GREEN)
footer(s, 6)

# ============================================ 7 · honest status
s = prs.slides.add_slide(BLANK)
header(s, "What is working — and what is not yet", "Honest status")
textbox(s, 0.6, 1.35, 12.1, 0.35, [
    ("Stated plainly so the remaining risk is visible rather than discovered "
     "later.", 14, False, BLACK)])

table(s, 0.6, 1.85, 12.1, [
    ["Component", "State", "Evidence or what remains"],
    ["Orchestration — LangGraph state graph", "Working",
     "Runs end to end; whole-stack integration suite"],
    ["Loop prevention — five mechanisms", "Working",
     "100,000 randomised runs, none exceeded its cap"],
    ["Product Manager agent", "Working",
     "Valid specs on 5/5 sample prompts, both languages"],
    ["Developer agent", "Working",
     "Complete multi-file output; placeholder content rejected"],
    ["Code Reviewer agent", "Working",
     "Verdict grounded in sandbox execution, not self-report"],
    ["Execution sandbox", "Working",
     "Timeout, crash and path escape all handled"],
    ["Context compression", "Working",
     "93.7% reduction at 80 iterations, always within budget"],
    ["Persistence — 11 tables", "Working",
     "Every run replayable and costable"],
    ["Web UI (FastAPI)", "Working",
     "Optional; the engine and CLI do not depend on it"],
    ["Real-model adapters (Anthropic, OpenAI)", "Untested",
     "Written behind the same interface; no live API call made yet — "
     "needs a key, a config change rather than a code change"],
    ["Benchmark suite and baselines", "Not started", "Weeks 9–12, as scheduled"],
], [4.3, 1.4, 6.4], size=11.5, row_h=0.42, status_col=1,
    status_colors={"Working": GREEN, "Untested": AMBER, "Not started": GREY})
footer(s, 7)

# ============================================ 8 · how to verify
s = prs.slides.add_slide(BLANK)
header(s, "How to verify any of this", "Seven commands")
textbox(s, 0.6, 1.35, 12.1, 0.35, [
    ("Clone the repository and run these. No API key, no network, no cost.",
     15, False, BLACK)])

STEPS = [
    ("pytest -q", "273 tests, about six seconds."),
    ("python -m mawe.cli \"Build a snake game\" -v", "Watch the pipeline run live."),
    ("python scripts/week5_m2_check.py",
     "The Reviewer rejects a defect it was scripted to approve."),
    ("python scripts/week6_loop_stress.py",
     "100,000 adversarial sequences; none fail to terminate."),
    ("python scripts/week7_memory_check.py",
     "Context growth with compression on and off."),
    ("python scripts/week8_m3_check.py", "30 checks across every layer."),
    ("uvicorn mawe.web.app:app", "The web front end, if FastAPI is installed."),
]
y = 1.95
for cmd, desc in STEPS:
    chip = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(y),
                              Inches(6.5), Inches(0.42))
    chip.fill.solid()
    chip.fill.fore_color.rgb = RGBColor(0x1E, 0x1E, 0x1E)
    chip.line.fill.background()
    chip.shadow.inherit = False
    tfc = chip.text_frame
    tfc.margin_left = Inches(0.14)
    rc = tfc.paragraphs[0].add_run()
    rc.text = cmd
    rc.font.size, rc.font.name = Pt(11.5), "Consolas"
    rc.font.color.rgb = RGBColor(0x7F, 0xE0, 0x8A)
    textbox(s, 7.3, y + 0.03, 5.4, 0.4, [(desc, 12, False, BLACK)],
            line_spacing=1.05)
    y += 0.62

textbox(s, 0.6, 6.5, 12.1, 0.6, [
    ("Repository:  github.com/marcoaperozo/Capstone-MAWE", 14, True, NAVY),
    ("Setup: pip install -r requirements.txt && pip install -e .   ·   "
     "full walkthrough in docs/DEMO-GUIDE.md", 11.5, False, GREY),
], space_after=2)
footer(s, 8)

prs.save(OUT)
print("saved", OUT)
