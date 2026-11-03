"""Build one PDF containing every document for the presentation.

    python docs/reports/build_bundle_pdf.py

Produces docs/reports/MAWE-COMPLETE-BUNDLE.pdf: a cover page, the abstract,
the presentation script, the demo runbook, the how-it-works guide, the final
report, and then the existing poster and slide deck appended as they are.

Markdown is rendered through PyMuPDF's Story engine, so no external tool
(pandoc, LaTeX, a browser) is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from pathlib import Path as pathlib_Path

import markdown
import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "MAWE-COMPLETE-BUNDLE.pdf"

PAGE = pymupdf.paper_rect("letter")
MARGIN = 54                      # 0.75 inch
FRAME = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN)

#: Markdown documents, in reading order, with the title shown on the divider.
SECTIONS = [
    ("Abstract", "docs/reports/ABSTRACT.md"),
    ("Presentation script", "docs/FINAL-PRESENTATION-SCRIPT.md"),
    ("Demo runbook", "docs/SHOW-YOUR-PROFESSOR.md"),
    ("How it works, and how to run it", "docs/HOW-IT-WORKS.md"),
    ("Final report", "docs/reports/FINAL-REPORT.md"),
]

#: Existing PDFs appended whole, after the markdown sections.
APPENDED = [
    ("Conference poster", "docs/poster/MAWE-URC-Poster-with-results.pdf"),
    ("Slide deck", "docs/reports/FINAL-REPORT.pdf"),
]

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.45;
       color: #1a1a1a; }
h1 { font-size: 19pt; color: #003466; margin-top: 16pt; margin-bottom: 7pt; }
h2 { font-size: 14pt; color: #003466; margin-top: 15pt; margin-bottom: 5pt; }
h3 { font-size: 11.5pt; color: #003466; margin-top: 12pt; margin-bottom: 4pt; }
p  { margin-top: 0; margin-bottom: 7pt; }
li { margin-bottom: 3pt; }
code { font-family: monospace; font-size: 9.5pt; color: #7a2f00; }
pre  { font-family: monospace; font-size: 9pt; background: #f2f5f7;
       padding: 6pt; margin-bottom: 8pt; }
blockquote { margin-left: 12pt; color: #30475e; }
table { font-size: 9.5pt; margin-bottom: 9pt; }
th { background: #003466; color: #ffffff; text-align: left; padding: 4pt; }
td { padding: 4pt; border-bottom: 1px solid #cfd8dd; }
hr { margin-top: 10pt; margin-bottom: 10pt; }
"""


def to_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    return f"<html><head><style>{CSS}</style></head><body>{body}</body></html>"


def render_markdown(writer: pymupdf.DocumentWriter, html: str) -> int:
    story = pymupdf.Story(html=html, user_css=None)
    pages = 0
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(FRAME)
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages > 400:                       # runaway guard
            break
    return pages


def cover_html(sections, appended) -> str:
    rows = "".join(
        f"<tr><td>{i}</td><td>{title}</td></tr>"
        for i, (title, _) in enumerate(sections + appended, 1))
    return f"""<html><head><style>{CSS}</style></head><body>
<h1>MAWE &mdash; Multi-Agent AI Workflow Engine</h1>
<p><b>Simulating an Autonomous Software Development Team</b></p>
<p>Capstone project &middot; Department of Computer Science &middot;
Southwest Minnesota State University</p>
<p>Marco Perozo &middot; Gabriel Marte &middot; Lewdy Aquino &middot;
Alvin Almonte</p>
<hr/>
<p>Everything for the presentation, in one file.</p>
<table><tr><th>#</th><th>Document</th></tr>{rows}</table>
<hr/>
<p><b>One thing to state up front.</b> The engine, the benchmark and the
comparison are built, tested and validated. Two of the five hypotheses are
answered by measurement. The other three compare language models and have
<b>not</b> been run: that needs a paid API key. The apparatus for it is
complete.</p>
</body></html>"""


def divider_html(number: int, title: str) -> str:
    return f"""<html><head><style>{CSS}</style></head><body>
<p>&nbsp;</p><p>&nbsp;</p>
<h1>{number}. {title}</h1>
<hr/>
</body></html>"""


def main() -> int:
    missing = [p for _, p in SECTIONS + APPENDED if not (ROOT / p).exists()]
    if missing:
        print("missing inputs:", missing, file=sys.stderr)
        return 2

    import tempfile
    scratch = pathlib_Path(tempfile.gettempdir()) / "_mawe_bundle_body.pdf"
    writer = pymupdf.DocumentWriter(str(scratch))

    render_markdown(writer, cover_html(SECTIONS, APPENDED))
    for number, (title, relative) in enumerate(SECTIONS, 1):
        render_markdown(writer, divider_html(number, title))
        render_markdown(writer, to_html(ROOT / relative))
    for number, (title, _) in enumerate(APPENDED, len(SECTIONS) + 1):
        render_markdown(writer, divider_html(number, title))
    writer.close()

    # Assemble: the rendered markdown, then each appended PDF in place of the
    # divider that announces it.
    body = pymupdf.open(scratch)
    out = pymupdf.open()

    divider_pages = []
    for index in range(body.page_count):
        text = body[index].get_text()
        for number, (title, _) in enumerate(APPENDED, len(SECTIONS) + 1):
            if text.strip().startswith(f"{number}. {title}"):
                divider_pages.append((index, number))

    cut = 0
    for page_index, number in divider_pages:
        out.insert_pdf(body, from_page=cut, to_page=page_index)
        source = pymupdf.open(ROOT / APPENDED[number - len(SECTIONS) - 1][1])
        out.insert_pdf(source)
        source.close()
        cut = page_index + 1
    # only if anything is left: insert_pdf with from_page past the end
    # wraps and re-appends the final page
    if cut <= body.page_count - 1:
        out.insert_pdf(body, from_page=cut, to_page=body.page_count - 1)

    out.set_metadata({
        "title": "MAWE - complete bundle",
        "author": "Marco Perozo, Gabriel Marte, Lewdy Aquino, Alvin Almonte",
        "subject": "Multi-Agent AI Workflow Engine - capstone documentation",
    })
    out.save(OUT, deflate=True, garbage=3)
    pages = out.page_count
    out.close()
    body.close()
    try:                       # PyMuPDF can still hold the handle
        scratch.unlink(missing_ok=True)
    except OSError:
        pass

    print(f"wrote {OUT}  ({pages} pages, "
          f"{OUT.stat().st_size / 1_000_000:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
