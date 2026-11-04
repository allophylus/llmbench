#!/usr/bin/env python3
"""build_pages_overview.py -- fill the root index.html's generated blocks.

index.html is hand-maintained (the sortable table, the views, the copy); four parts of it
are generated from data so they can never drift:

  * the sticky topbar, between <!-- topbar:start --> and <!-- topbar:end -->,
    from scripts/site_nav.py (the one list of nav items);
  * the matched-context speed matrix at #speed-sweep, between <!-- sweep:start --> and
    <!-- sweep:end -->, from benchmarks/ctx-sweep/ via scripts/sweep_data.py;
  * the accelerator ablation at #ablation, between <!-- ablation:start --> and
    <!-- ablation:end -->, from benchmarks/ablation/ via scripts/build_pages_ablation.py;
  * the methodology + raw downloads at #method, between <!-- method:start --> and
    <!-- method:end -->, from data/results.json via scripts/build_pages_method.py.

Nothing else in index.html is touched. Run order: this script, then scripts/build_pages.py
(games/chat), then scripts/check_nav.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_nav  # noqa: E402
import sweep_data  # noqa: E402
import build_pages_ablation  # noqa: E402
import build_pages_method  # noqa: E402

ROOT = site_nav.ROOT
PATH = os.path.join(ROOT, "index.html")
TOP_A, TOP_B = "<!-- topbar:start", "<!-- topbar:end -->"
SW_A, SW_B = "<!-- sweep:start", "<!-- sweep:end -->"
AB_A, AB_B = "<!-- ablation:start", "<!-- ablation:end -->"
ME_A, ME_B = "<!-- method:start", "<!-- method:end -->"
MM_A, MM_B = "<!-- method:models:start", "<!-- method:models:end -->"
CSS_START, CSS_END = "/* sweep-matrix:start */", "/* sweep-matrix:end */"

ABLATION_CSS = """
.abl-h{font:600 15px/1.3 var(--sans);color:var(--fg);margin:0 0 .4rem}
.abl-t{font:600 12px/1 var(--mono);letter-spacing:.07em;text-transform:uppercase;color:var(--fg-faint);margin:1.4rem 0 .6rem}
"""

METHOD_CSS = """
#method .table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:8px 0 14px;max-width:100%}
#method code{font:12px/1.45 var(--mono);color:var(--fg);background:#111821;padding:1px 4px;border-radius:4px}
.method-tbl table,.method-tbl thead,.method-tbl tbody,.method-tbl tr{display:revert}
.method-tbl table{display:table;table-layout:auto;width:100%;min-width:520px;border-collapse:collapse;background:var(--panel)}
.method-tbl thead{display:table-header-group}.method-tbl tbody{display:table-row-group}
.method-tbl tr{display:table-row}
.method-tbl th,.method-tbl td{display:table-cell;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left;font-size:13px}
.method-tbl thead th{background:#1b2431;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
.method-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono);white-space:nowrap}
.method-tbl td.mode{white-space:nowrap}
h3.rawh{font-size:14px;margin:20px 0 6px;color:var(--fg)}
ul.findings{margin:.5rem 0 1rem;padding-left:1.1rem;max-width:95ch}
ul.findings li{color:var(--fg-dim);margin:.35rem 0;line-height:1.5}
ul.findings li strong,.findings b{color:var(--fg)}
ul.findings li.meta,ul.findings li .meta{color:var(--fg-faint);font-size:12.5px}
ul.methodul{margin:.5rem 0 1rem;padding-left:1.1rem;max-width:95ch}
ul.methodul li{color:var(--fg-dim);margin:.35rem 0;line-height:1.5}
#method .dl{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
#method .dl a{border:1px solid var(--line);border-radius:8px;padding:6px 11px;color:var(--blue,var(--accent));text-decoration:none;font:12.5px var(--mono)}
#method .dl a:hover{border-color:var(--accent-dim)}
#method ul{margin:.4rem 0 .8rem;padding-left:1.2rem}
@media(max-width:760px){.method-tbl table{min-width:0;font-size:12px}
 .method-tbl th,.method-tbl td{padding:6px 6px;font-size:12px;overflow-wrap:anywhere}}
"""


def splice(block, a_marker, b_marker):
    """(before, after) split around an inclusive marker pair."""
    if a_marker not in block or b_marker not in block:
        print(f"index.html: markers {a_marker!r}/{b_marker!r} missing — skipped"); return ("","")
    a = block.index(a_marker)
    b = block.index(b_marker, a) + len(b_marker)
    return block[:a], block[b:]


def replace(body, a_marker, b_marker, new):
    # a component whose markers were removed on purpose (e.g. the sweep section) must be
    # skipped, not treated as a build failure
    if a_marker not in body or b_marker not in body:
        print(f"index.html: markers {a_marker!r}/{b_marker!r} missing — component skipped")
        return body
    head, tail = splice(body, a_marker, b_marker)
    return head + new + tail


def models_section_html():
    """Method and findings for the models table itself, rendered into the text section."""
    return build_pages_method.overview_method_html() + findings_html(
        build_pages_method.overview_findings_html())


def sweep_fragment():
    return ""  # removed: Fen did not ask for a context-sweep section
    frag = sweep_data.section_html()
    # the fragment carries its own id when served standalone; index.html exposes
    # the section itself at #speed-sweep, and its headings must not collide with the
    # generic .sec anchors used elsewhere on the page
    frag = (frag.replace('<h2 class=sec>', '<h2 class=sweep-h>')
            .replace('<section class=sweep id="speed-sweep">', '<div class="sweep">')
            .replace("<section class=sweep id=speed-sweep>", '<div class="sweep">'))
    if frag.endswith("</section>"):
        frag = frag[: -len("</section>")] + "</div>"
    return frag


def findings_html(lines):
    return ("<h3 class=abl-t>Findings</h3><ul class=findings>"
            + "".join("<li>%s</li>" % x for x in lines) + "</ul>")


def sweep_block():
    return ""  # removed: Fen did not ask for a context-sweep section
    """The matrix, then its method, then what it shows — one section."""
    return sweep_fragment() + build_pages_method.sweep_method_html()


def ablation_block():
    """The arm table, then its method, then the findings it supports."""
    abl, _ = build_pages_ablation.fragment()
    return (abl + build_pages_method.ablation_method_html()
            + findings_html(build_pages_ablation.findings()))


def components():
    """(anchor, marker pair, fragment, provenance note) for every generated block."""
    abl, _ = build_pages_ablation.fragment()
    return [

        ("ablation", AB_A, AB_B, ablation_block(),
         "generated from benchmarks/ablation/ by scripts/build_pages_ablation.py — do not edit"),
        ("method", ME_A, ME_B,
         build_pages_method.overview_method_html()
         + "<h3 id=raw class=rawh>Download the raw records</h3>"
         + '<p>The machine-readable dataset is the same file the table above renders; the '
           'per-question chat JSONs are the files the Chat page is built from.</p>'
         + '<div class=dl><a href="data/results.json" download>results.json — every row</a>'
           '<a href="#raw-files">chat JSONs — per question</a>'
           '<a href="benchmarks/gapclose/RESULTS.md">gap-close results (markdown)</a></div>'
         + build_pages_method.raw_html(),
         "generated by scripts/build_pages_method.py — do not edit"),
    ]


def holds(html, anchor, marker):
    """True if the block with ``marker`` sits inside the element carrying id=anchor."""
    import re
    m = re.search(r'<section class="about" id="%s"[^>]*>' % re.escape(anchor), html)
    if not m:
        print(f"index.html: no section with id={anchor} — component skipped"); return
    i = m.end()
    return marker in html[i:html.index("</section>", i)]


def main():
    html = open(PATH, encoding="utf-8").read()

    for a_marker, b_marker in ((TOP_A, TOP_B), (SW_A, SW_B), (AB_A, AB_B), (ME_A, ME_B),
                               (MM_A, MM_B)):
        splice(html, a_marker, b_marker)  # validate before writing anything
    splice(html, CSS_START, CSS_END)

    html = replace(html, TOP_A, TOP_B,
                   TOP_A + " (generated by scripts/site_nav.py — run scripts/build_pages_overview.py) -->\n"
                   + site_nav.render_topbar("", "overview", style="site") + "\n" + TOP_B)

    for anchor, a_marker, b_marker, frag, note in components():
        html = replace(html, a_marker, b_marker,
                       a_marker + " (" + note + ") -->\n" + frag + "\n" + b_marker)

    html = replace(html, CSS_START, CSS_END,
                   CSS_START + sweep_data.hard_css() + ABLATION_CSS + METHOD_CSS + CSS_END)

    for anchor, a_marker, _b, _f, _n in components():
        if not holds(html, anchor, a_marker):
            print(f"index.html: {a_marker!r} not inside #{anchor} — skipped"); return

    open(PATH, "w", encoding="utf-8").write(html)
    print("index.html: nav + %d generated blocks refreshed (each inside its #anchor)"
          % len(components()))


if __name__ == "__main__":
    main()
