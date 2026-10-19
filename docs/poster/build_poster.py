# -*- coding: utf-8 -*-
"""Build the MAWE URC poster from urc-poster-template.pptx."""
import copy, math
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR

SRC = r'C:\Users\marco\Downloads\urc-poster-template.pptx'
import sys
OUT = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.pptx') else 'MAWE-URC-Poster.pptx'

NAVY = RGBColor(0x00, 0x34, 0x66)
LBLUE = RGBColor(0xBB, 0xE0, 0xE3)
PALE = RGBColor(0xDA, 0xED, 0xEF)
BLACK = RGBColor(0x00, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREY = RGBColor(0x55, 0x55, 0x55)
FONT = 'Arial Narrow'

COLX = [0.75, 12.55, 24.36, 36.16]
COLW = 10.92
TOP = 5.50
BOTTOM = 35.30
HDR_H = 0.67
GAP_AFTER_HDR = 0.12
GAP_AFTER_BODY = 0.40

prs = Presentation(SRC)
slide = prs.slides[0]
shapes = slide.shapes

# keep a copy of the navy header-bar XML as a prototype, then strip the template content
proto = None
for sh in list(shapes):
    if sh.name == 'Text Box 7':
        proto = copy.deepcopy(sh._element)
        break

KEEP = {'Picture 42', 'Graphic 2', 'Rectangle 5'}
for sh in list(shapes):
    if sh.name not in KEEP:
        sh._element.getparent().remove(sh._element)

# drop the orphaned legacy VML drawing / OLE fallback left behind by the deleted group
_ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
for _tag in ('p:legacyDrawing', 'p:controls'):
    for _el in slide._element.findall(_tag, _ns):
        _el.getparent().remove(_el)

# ---------------------------------------------------------------- title
title = next(sh for sh in shapes if sh.name == 'Rectangle 5')
title.left, title.top = Inches(9.0), Inches(0.85)
title.width, title.height = Inches(32.3), Inches(3.7)
tf = title.text_frame
tf.word_wrap = True
tf.clear()
TITLE_LINES = [
    ('Multi-Agent AI Workflow Engine', 80, True, 'Arial Black', NAVY),
    ('Simulating an Autonomous Software Development Team', 44, False, FONT, BLACK),
    ('Marco Perozo  \u2022  Gabriel Marte  \u2022  Lewdy Aquino  \u2022  Alvin Almonte', 34, True, FONT, BLACK),
    ('Department of Computer Science  ·  Southwest Minnesota State University  ·  Capstone Project, Fall 2026', 26, False, FONT, GREY),
]
for i, (txt, sz, bold, face, col) in enumerate(TITLE_LINES):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = txt
    r.font.size, r.font.bold, r.font.name = Pt(sz), bold, face
    r.font.color.rgb = col

# ---------------------------------------------------------------- helpers
def add_header(text, col, y, width=COLW, x=None):
    el = copy.deepcopy(proto)
    shapes._spTree.append(el)
    sh = shapes[-1]
    sh.left = Inches(x if x is not None else COLX[col])
    sh.top, sh.width, sh.height = Inches(y), Inches(width), Inches(HDR_H)
    t = sh.text_frame
    t.clear()
    t.word_wrap = True
    r = t.paragraphs[0].add_run()
    r.text = '   ' + text
    r.font.size, r.font.bold, r.font.name = Pt(32), True, FONT
    r.font.color.rgb = WHITE
    return y + HDR_H + GAP_AFTER_HDR


def est_height(lines, width_in):
    h = 0.10
    for txt, sz, bold, bullet, col in lines:
        if not txt:
            h += sz / 72.0 * 0.5
            continue
        eff = width_in - (0.34 if bullet else 0.0)
        cpl = max(12, int(eff / (0.425 * sz / 72.0)))
        h += math.ceil(len(txt) / cpl) * (sz / 72.0 * 1.22) + 0.075
    return h + 0.16


def norm_lines(lines, size):
    out = []
    for ln in lines:
        txt = ln[0]
        sz = ln[1] if len(ln) > 1 and ln[1] else size
        bold = ln[2] if len(ln) > 2 else False
        bullet = ln[3] if len(ln) > 3 else False
        col = ln[4] if len(ln) > 4 else BLACK
        out.append((txt, sz, bold, bullet, col))
    return out


def add_body(lines, col, y, width=COLW, x=None, fill=None, size=28, center=False):
    ln = norm_lines(lines, size)
    h = est_height(ln, width - 0.45)
    left = Inches(x if x is not None else COLX[col])
    box = shapes.add_textbox(left, Inches(y), Inches(width), Inches(h))
    t = box.text_frame
    t.word_wrap = True
    t.margin_left = Inches(0.18)
    t.margin_right = Inches(0.18)
    t.margin_top = Inches(0.09)
    t.margin_bottom = Inches(0.09)
    if fill is not None:
        box.fill.solid()
        box.fill.fore_color.rgb = fill
        box.line.color.rgb = NAVY
        box.line.width = Pt(2)
    else:
        box.fill.background()
        box.line.fill.background()
    first = True
    for txt, sz, bold, bullet, colr in ln:
        p = t.paragraphs[0] if first else t.add_paragraph()
        first = False
        p.space_after = Pt(5)
        if center:
            p.alignment = PP_ALIGN.CENTER
        if bullet:
            pPr = p._p.get_or_add_pPr()
            pPr.set('marL', str(int(0.34 * 914400)))
            pPr.set('indent', str(int(-0.34 * 914400)))
            txt = '\u25aa  ' + txt
        if txt:
            r = p.add_run()
            r.text = txt
            r.font.size, r.font.bold, r.font.name = Pt(sz), bold, FONT
            r.font.color.rgb = colr
    return y + h + GAP_AFTER_BODY


def section(head, lines, col, y, **kw):
    y2 = add_body(lines, col, add_header(head, col, y), **kw)
    print(f'   [col{col+1}] {head}: {y:.2f} -> {y2:.2f}  ({y2-y:.2f} in)')
    return y2


def add_table(rows, col, y, widths, size=22, head_fill=NAVY, width=COLW):
    """rows[0] is the header row. widths are relative."""
    nrow, ncol = len(rows), len(rows[0])
    tot = sum(widths)
    rh = size / 72.0 * 1.75
    h = rh * nrow
    gf = shapes.add_table(nrow, ncol, Inches(COLX[col]), Inches(y),
                          Inches(width), Inches(h))
    tbl = gf.table
    for j, w in enumerate(widths):
        tbl.columns[j].width = Inches(width * w / tot)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(rh)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = Inches(0.10)
            cell.margin_right = Inches(0.10)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = head_fill if i == 0 else (
                WHITE if i % 2 else PALE)
            tfc = cell.text_frame
            tfc.word_wrap = True
            p = tfc.paragraphs[0]
            r = p.add_run()
            r.text = str(val)
            r.font.size = Pt(size)
            r.font.bold = (i == 0)
            r.font.name = FONT
            r.font.color.rgb = WHITE if i == 0 else BLACK
            if j > 0:
                p.alignment = PP_ALIGN.CENTER
    return y + h + GAP_AFTER_BODY


B, S, XS, M = 28, 24, 22, 26
y = {0: TOP, 1: TOP, 2: TOP, 3: TOP}

# ============================== COLUMN 1 ==============================
y[0] = section('Introduction & Problem Statement', [
    ('Large Language Models (LLMs) can now generate source code from natural-language '
     'descriptions, and tools such as GitHub Copilot and ChatGPT are used daily by '
     'developers (Chen et al., 2021). Almost all of them are built around one model '
     'receiving one prompt: a single pass in which the model must understand the request, '
     'design the solution, write the code and verify it all at once.', B),
    ('', 10),
    ('Three limitations follow:', B, True),
    ('Single-model limits. One pass over a large, multi-step task produces incomplete or '
     'incorrect results on anything non-trivial.', B, False, True),
    ('Lack of teamwork. Real software needs a product manager to clarify, a developer to '
     'build and QA to verify. A single prompt collapses these perspectives and loses the '
     'checks and balances that make teams effective.', B, False, True),
    ('Lack of iteration. Standard prompts do not reliably self-correct against predefined '
     'requirements (Madaan et al., 2023); detecting and fixing errors falls to the human.',
     B, False, True),
], 0, y[0])

y[0] = add_body([
    ('RESEARCH QUESTION', S, True, False, NAVY),
    ('Does a structured, role-based multi-agent workflow (PM \u2192 Developer \u2192 '
     'Reviewer with an iteration loop) produce more correct and more requirement-compliant '
     'software than a single LLM given the same task \u2014 and at what cost in tokens '
     'and time?', S),
], 0, y[0], fill=LBLUE)

y[0] = section('Goal & Objectives', [
    ('Goal. Design, implement and evaluate an engine that simulates an autonomous software '
     'development team and turns a simple prompt into working, reviewed code through a '
     'controlled iteration loop.', B),
    ('', 10),
    ('Build the orchestration pipeline as a LangGraph state graph.', B, False, True),
    ('Implement PM, Developer and Reviewer agents, each producing a well-defined artifact '
     '(spec, code, review report).', B, False, True),
    ('Engineer loop prevention so the review/fix cycle always terminates.', B, False, True),
    ('Implement memory management (rolling summarization and pruning).', B, False, True),
    ('Persist every run, message, spec, code version, review and metric.', B, False, True),
    ('Evaluate against a single-model baseline on \u2265 20 hidden-test tasks.', B, False, True),
], 0, y[0])

y[0] = section('Related Work', [
    ('Agentic frameworks show that decomposing a problem across cooperating LLMs improves '
     'quality on complex tasks: AutoGen provides a general multi-agent conversation layer '
     '(Wu et al., 2024); MetaGPT encodes standard operating procedures for software roles '
     '(Hong et al., 2024); ChatDev organises agents into a virtual software company '
     '(Qian et al., 2024). Self-Refine (Madaan et al., 2023) and Reflexion (Shinn et al., '
     '2023) show that iterative self-feedback raises output quality, and SWE-bench '
     '(Jimenez et al., 2024) supplies a rigorous hidden-test evaluation protocol.', S),
    ('', 8),
    ('Gap addressed. These systems report capability, but rarely report guaranteed '
     'termination or cost per successful task. MAWE makes the control flow explicit and '
     'testable, and measures cost-per-success directly.', S, True),
], 0, y[0])

# ============================== COLUMN 2 ==============================
y[1] = add_header('System Architecture', 1, y[1])

DIAG = [
    ('User prompt', '"Build a snake game"', LBLUE),
    ('PM Agent', 'Structured spec + acceptance criteria', WHITE),
    ('Developer Agent', 'Python / JavaScript source files', WHITE),
    ('Reviewer Agent', 'Runs code + tests in Docker sandbox', WHITE),
    ('Finalize', 'Code, spec, review history, metrics', LBLUE),
]
dx, dw = COLX[1] + 0.20, COLW - 1.95
bh, gap = 1.10, 0.42
dy = y[1]
box_tops = []
for i, (head, sub, fillc) in enumerate(DIAG):
    b = shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                         Inches(dx), Inches(dy), Inches(dw), Inches(bh))
    b.fill.solid()
    b.fill.fore_color.rgb = fillc
    b.line.color.rgb = NAVY
    b.line.width = Pt(3)
    b.shadow.inherit = False
    t = b.text_frame
    t.word_wrap = True
    t.margin_top = Inches(0.04)
    t.margin_bottom = Inches(0.04)
    p = t.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = head
    r.font.size, r.font.bold, r.font.name = Pt(27), True, FONT
    r.font.color.rgb = NAVY
    p2 = t.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = sub
    r2.font.size, r2.font.name = Pt(20), FONT
    r2.font.color.rgb = BLACK
    box_tops.append(dy)
    if i < len(DIAG) - 1:
        a = shapes.add_shape(MSO_SHAPE.DOWN_ARROW,
                             Inches(dx + dw / 2 - 0.26), Inches(dy + bh + 0.05),
                             Inches(0.52), Inches(gap - 0.10))
        a.fill.solid()
        a.fill.fore_color.rgb = NAVY
        a.line.fill.background()
        a.shadow.inherit = False
    dy += bh + gap
diag_bottom = dy - gap

# feedback loop: Reviewer -> Developer, routed through the right-hand gutter
RED = RGBColor(0xC0, 0x39, 0x2B)
fb_y1 = box_tops[3] + bh / 2          # Reviewer
fb_y2 = box_tops[2] + bh / 2          # Developer
rx = dx + dw + 0.50
segs = [(dx + dw, fb_y1, rx, fb_y1), (rx, fb_y1, rx, fb_y2), (rx, fb_y2, dx + dw, fb_y2)]
for k, (x1, y1, x2, y2) in enumerate(segs):
    c = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                             Inches(x2), Inches(y2))
    c.line.color.rgb = RED
    c.line.width = Pt(5)
    if k == len(segs) - 1:
        lnEl = c.line._get_or_add_ln()
        tail = lnEl.makeelement(
            '{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd',
            {'type': 'triangle', 'w': 'lg', 'len': 'lg'})
        lnEl.append(tail)

lbl = shapes.add_textbox(Inches(rx + 0.08), Inches((fb_y1 + fb_y2) / 2 - 0.80),
                         Inches(COLX[1] + COLW - rx - 0.08), Inches(1.60))
lbl.fill.background()
lbl.line.fill.background()
lbl.text_frame.word_wrap = True
lbl.text_frame.margin_left = Inches(0.02)
lbl.text_frame.margin_right = Inches(0.02)
for k, txt in enumerate(['reject ∧', 'iter < max', '∧ progress']):
    pp = lbl.text_frame.paragraphs[0] if k == 0 else lbl.text_frame.add_paragraph()
    pp.alignment = PP_ALIGN.CENTER
    rr = pp.add_run()
    rr.text = txt
    rr.font.size, rr.font.bold, rr.font.name = Pt(16), True, FONT
    rr.font.color.rgb = RED

y[1] = diag_bottom + 0.45
y[1] = add_body([
    ('Six layers. Orchestration (LangGraph state graph) \u00b7 Agent (role prompts and '
     'tools) \u00b7 Safety (iteration caps, exit conditions, fallback routing) \u00b7 '
     'Memory (summarization and pruning) \u00b7 Persistence (SQLAlchemy / SQLite \u2192 '
     'PostgreSQL) \u00b7 Evaluation (benchmarks against a single-model baseline).', S),
], 1, y[1], fill=PALE)

y[1] = section('Methodology', [
    ('Development process. Four two-week Agile sprints; every change goes through a '
     'GitHub pull request reviewed by a teammate; GitHub Actions runs the unit-test suite '
     'on each push; 15-minute weekly stand-ups on a Kanban board.', M),
    ('', 8),
    ('Workflow as a state graph. Nodes are agent steps (plan, develop, review, summarize, '
     'finalize); edges are routing rules evaluated on the current state, which makes the '
     'control flow explicit, testable and easy to visualise.', M),
    ('', 8),
    ('START \u2192 PM.plan \u2192 Dev.implement \u2192 Reviewer.review \u2192 '
     '[approve \u2192 finalize] | [reject \u2227 iter < max \u2227 progress \u2192 '
     'Dev.implement] | [reject \u2227 (iter = max \u2228 no progress) \u2192 '
     'finalize_with_warnings] \u2192 END', XS, True, False, NAVY),
    ('', 8),
    ('Testing strategy. Unit tests for routing, loop-prevention rules, summarization and '
     'database access; integration tests over the full pipeline with a mocked LLM for '
     'determinism; end-to-end runs with real LLM calls before each milestone.', M),
], 1, y[1])

y[1] = section('Loop Prevention & Memory Management', [
    ('The two failure modes that break autonomous agent pipelines are non-termination and '
     'context growth. Both are engineered against explicitly.', M),
    ('', 8),
    ('Four termination mechanisms', S, True, False, NAVY),
    ('Hard iteration cap \u2014 configurable, default 5.', M, False, True),
    ('Severity threshold \u2014 only critical and major issues cause rejection; minor '
     'issues are reported but do not block approval.', M, False, True),
    ('No-progress detection \u2014 a SHA-256 hash of the Developer output exits the loop '
     'when the same code or the same issue list repeats.', M, False, True),
    ('Fallback routing \u2014 on exit without approval the engine finalizes the best '
     'version with a warnings report rather than failing.', M, False, True),
    ('', 8),
    ('Memory strategy', S, True, False, NAVY),
    ('Only the latest spec, latest code and latest review stay in full context; older '
     'iterations are compressed into a compact progress log stored in memory_summaries, '
     'while every raw message is still persisted in the database so nothing is lost for '
     'later analysis.', M),
], 1, y[1])


# ============================== COLUMN 3 ==============================
y[2] = section('Database Design', [
    ('The database is the system\u2019s memory of record: every run is fully traceable '
     'from the original prompt through each code version to the final metrics. The schema '
     'is in third normal form, written with SQLAlchemy so SQLite (development) migrates to '
     'PostgreSQL unchanged.', S),
], 2, y[2])

y[2] = add_table([
    ['Table', 'Purpose'],
    ['users / projects', 'Owner and the original idea prompt'],
    ['agents', 'Role, model, system prompt, version'],
    ['runs', 'Mode, status, iterations, tokens, cost'],
    ['messages', 'Every agent-to-agent exchange'],
    ['specifications', 'Versioned PM spec + acceptance criteria'],
    ['code_artifacts', 'Each file per iteration + SHA-256 hash'],
    ['reviews', 'Verdict, severity, tests passed/failed'],
    ['memory_summaries', 'Compressed context, tokens before/after'],
    ['benchmark_tasks', 'Prompt, difficulty, hidden tests'],
    ['evaluation_results', 'Metric name and value per run'],
], 2, y[2], widths=[1.0, 1.55], size=21)

y[2] = add_body([
    ('USER \u2500\u2500< PROJECT \u2500\u2500< RUN \u2500\u2500< { MESSAGE >\u2500\u2500 '
     'AGENT, SPECIFICATION, CODE_ARTIFACT, REVIEW, MEMORY_SUMMARY, EVALUATION_RESULT } '
     '\u00b7 BENCHMARK_TASK \u2500\u2500< RUN', XS, True, False, NAVY),
], 2, y[2], fill=LBLUE)

y[2] = section('Implementation Status', [
    ('Stack. Python 3.11+ \u00b7 LangGraph \u00b7 OpenAI / Anthropic / Google API SDKs '
     '\u00b7 Docker sandbox with no network and CPU, memory and time limits \u00b7 pytest '
     'and Jest \u00b7 SQLAlchemy over SQLite \u2192 PostgreSQL \u00b7 FastAPI \u00b7 '
     'Git and GitHub Actions. No GPU is required: all models run in the cloud via API.', S),
], 2, y[2])

y[2] = add_table([
    ['Phase', 'Weeks', 'Milestone', 'Status'],
    ['1. Setup & prototyping', '1\u20132', 'M1 pipeline running', 'M1 met'],
    ['2. Role implementation', '3\u20135', 'M2 full PM/Dev/QA loop', 'Planned'],
    ['3. Memory & state', '6\u20138', 'M3 engine v1.0', 'Planned'],
    ['4. Testing & evaluation', '9\u201312', 'M4 benchmark + report', 'Planned'],
], 2, y[2], widths=[1.35, 0.55, 1.35, 0.8], size=21)

y[2] = section('Experimental Evaluation', [
    ('Design. The same benchmark tasks are solved under four conditions using the same '
     'underlying model and temperature, so that any difference is attributable to the '
     'workflow rather than the model.', S),
    ('', 6),
    ('A \u2014 Single model (baseline): one call, one answer.', S, False, True),
    ('B \u2014 Single model with self-refinement: the same model writes, then reviews and '
     'fixes its own code under the same iteration cap.', S, False, True),
    ('C \u2014 MAWE (proposed): PM \u2192 Dev \u2192 Reviewer with loop prevention and '
     'memory management.', S, False, True),
    ('C\u2032 \u2014 Ablation: MAWE with summarization disabled.', S, False, True),
    ('', 6),
    ('Benchmark. \u2265 20 Python and JavaScript tasks with hidden tests the agents never '
     'see \u2014 7 easy, 8 medium, 5 hard. Three repetitions per task per condition '
     '(\u2248 240 runs) to account for LLM non-determinism; means reported with 95% '
     'confidence intervals and tested with a paired t-test or Wilcoxon signed-rank test.', S),
    ('', 6),
    ('Metrics. Hidden-test pass rate, task success rate, specification coverage, '
     'iterations used, total tokens, estimated cost, latency, termination reason and '
     'context reduction from summarization.', S),
], 2, y[2])


# ============================== COLUMN 4 ==============================
y[3] = add_header('Preliminary Results', 3, y[3])
y[3] = add_body([
    ('Milestone M1 (Week 2). The engine runs end to end against a scripted mock LLM, so '
     'the orchestration, loop-prevention and persistence layers can be measured with no '
     'API cost and with repeatable results. These numbers characterise the ENGINE, not '
     'model quality; code-quality benchmarks against real LLMs run in Phase 4.', XS),
], 3, y[3])

y[3] = add_table([
    ['Scenario', 'Iter.', 'Termination', 'Tokens', 'Calls'],
    ['Reject, reject, approve', '2', 'approved', '1,002', '6'],
    ['Developer returns identical code', '2', 'no_progress', '863', '5'],
    ['Reviewer never approves', '5', 'iteration_cap', '2,099', '12'],
], 3, y[3], widths=[2.1, 0.5, 1.15, 0.7, 0.5], size=19)

y[3] = add_body([
    ('3 / 3 runs terminated — no hang, no manual stop. All three exit paths fire: '
     'severity threshold, code-hash no-progress detection and the hard iteration cap. '
     '20 messages, 3 specifications, 9 code artifacts and 8 reviews persisted to SQLite '
     'and queryable per run.', XS, True, False, NAVY),
], 3, y[3], fill=LBLUE)

y[3] = add_table([
    ['Phase 4 template', 'Pass rate', 'Task success', 'Cost / success'],
    ['A — Single model', '—', '—', '—'],
    ['B — Self-refinement', '—', '—', '—'],
    ['C — MAWE', '—', '—', '—'],
    ['C′ — No summarization', '—', '—', '—'],
], 3, y[3], widths=[1.6, 0.85, 0.95, 1.0], size=19)

y[3] = section('Discussion & Conclusions', [
    ('MAWE is expected to improve correctness and requirement coverage, most visibly on '
     'medium and hard tasks where a single prompt tends to miss requirements or ship '
     'untested bugs. The price is higher token usage and latency, since each iteration '
     'adds at least two model calls. The question is therefore not \u201cis it better?\u201d '
     'but \u201cis the improvement worth the cost?\u201d \u2014 which cost per successful '
     'task answers directly.', S),
    ('', 6),
    ('Condition B isolates iteration from role separation. If C still wins, that is '
     'evidence that an independent reviewer is worth more than a model checking its own '
     'work \u2014 the same reason real teams separate development from QA.', S),
    ('', 6),
    ('Limitations. The Reviewer is itself an LLM and can approve incorrect code, which is '
     'why scoring uses hidden tests instead of its verdict; tasks are small to medium, so '
     'conclusions may not transfer to large multi-module systems; results depend on the '
     'model family; and the budget limits repetitions to three per task.', S),
], 3, y[3])

y[3] = section('References', [
    ('Chen, M., Tworek, J., Jun, H., Yuan, Q., Pinto, H. P. de O., Kaplan, J., \u2026 '
     'Zaremba, W. (2021). Evaluating large language models trained on code. '
     'arXiv:2107.03374.', 19),
    ('Hong, S., Zhuge, M., Chen, J., Zheng, X., Cheng, Y., Wang, J., \u2026 Schmidhuber, '
     'J. (2024). MetaGPT: Meta programming for a multi-agent collaborative framework. '
     'International Conference on Learning Representations (ICLR 2024).', 19),
    ('Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., & Narasimhan, K. '
     '(2024). SWE-bench: Can language models resolve real-world GitHub issues? '
     'International Conference on Learning Representations (ICLR 2024).', 19),
    ('Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., \u2026 '
     'Clark, P. (2023). Self-Refine: Iterative refinement with self-feedback. Advances in '
     'Neural Information Processing Systems, 36.', 19),
    ('Qian, C., Liu, W., Liu, H., Chen, N., Dang, Y., Li, J., \u2026 Sun, M. (2024). '
     'ChatDev: Communicative agents for software development. Proceedings of the 62nd '
     'Annual Meeting of the Association for Computational Linguistics, 15174\u201315186.', 19),
    ('Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023). Reflexion: '
     'Language agents with verbal reinforcement learning. Advances in Neural Information '
     'Processing Systems, 36.', 19),
    ('Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., \u2026 Wang, C. (2024). '
     'AutoGen: Enabling next-generation LLM applications via multi-agent conversation. '
     'Conference on Language Modeling (COLM 2024).', 19),
], 3, y[3])

y[3] = section('Acknowledgements', [
    ('We thank Dr. Hezy for supervising this capstone project and for feedback on the '
     'proposal and evaluation design, and the maintainers of the LangGraph and CrewAI '
     'open-source projects whose tooling this work builds on.', S),
], 3, y[3])

prs.save(OUT)

# PowerPoint "repairs" a dangling OLE/SmartArt relationship by materialising a stray
# picture on the slide, so drop every slide relationship the slide XML no longer uses.
import re as _re, os as _os, zipfile as _zipfile

def _clean_rels(path):
    from lxml import etree as _et
    RNS = "http://schemas.openxmlformats.org/package/2006/relationships"
    zin = _zipfile.ZipFile(path)
    parts = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    zin.close()
    src = dict(parts)
    slide = src["ppt/slides/slide1.xml"].decode("utf8")
    used = set(_re.findall('r:(?:id|embed|link|pict|dm|lo|qs|cs)="([^"]+)"', slide))
    root = _et.fromstring(src["ppt/slides/_rels/slide1.xml.rels"])
    dropped = 0
    for rel in list(root):
        rid = rel.get("Id")
        typ = rel.get("Type", "").rsplit("/", 1)[-1]
        if rid not in used and typ not in ("slideLayout", "notesSlide"):
            root.remove(rel)
            dropped += 1
    new = _et.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    tmp = path + ".tmp"
    zout = _zipfile.ZipFile(tmp, "w", _zipfile.ZIP_DEFLATED)
    for name, data in parts:
        if name == "ppt/slides/_rels/slide1.xml.rels":
            data = new
        zout.writestr(name, data)
    zout.close()
    _os.replace(tmp, path)
    print("slide relationships: kept %d, dropped %d orphans" % (len(root), dropped))

_clean_rels(OUT)

for c in range(4):
    flag = 'OVERFLOW' if y[c] > BOTTOM else 'ok'
    print(f'column {c + 1}: bottom at {y[c]:.2f} in (limit {BOTTOM})  -> {flag}')
print('saved', OUT)
