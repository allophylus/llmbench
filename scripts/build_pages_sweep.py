#!/usr/bin/env python3
"""build_pages_sweep.py — the "context sweep" tab (/sweep/).

Source of truth: benchmarks/ctx-sweep/sweep.json (written by benchmarks/ctx-sweep/ctx_sweep.py)
and the per-model <slug>.json files beside it. Nothing on this page is typed by hand:
every number (prefill t/s, decode t/s, prompt tokens, seconds, VRAM, context, argv) is read
from a measured cell. A cell that did not measure is printed as "not measured", never filled.

Layout:
  * summary  — one row per model, five rungs (4K … 256K), each cell "prefill / decode" t/s,
               then largest context that loaded, peak VRAM at the top rung, notes.
  * detail   — one row per (model, rung): prompt tokens, prefill t/s, prefill s, decode t/s,
               generated tokens, peak VRAM, server argv. This is where a summary cell is proved.
  * method   — what was held fixed per cell, and how "context" is defined here.

Visitor text only: host directories, private addresses, model file paths and user names in
the recorded argv are stripped before they reach the page.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_nav import render_nav, render_topbar, render_brand, TOPBAR_CSS  # noqa: E402  single source of truth for the nav

SRC = os.path.join(ROOT, "benchmarks", "ctx-sweep")
SWEEP = os.path.join(SRC, "sweep.json")
OUTDIR = os.path.join(ROOT, "sweep")
OUT = os.path.join(OUTDIR, "index.html")

# display metadata only (name + quant); numbers always come from the JSON
LABEL = {
    "qwen3-6-35b-a3b-ud-q4km": ("Qwen3.6-35B-A3B", "Q4_K_M"),
    "qwen3-8-27b-q4km": ("Qwen3.8-27B", "Q4_K_M"),
    "qwen3-8-27b-q4-0": ("Qwen3.8-27B", "Q4_0"),
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": ("NEO-MAX MTP 27B", "Q4_K_M"),
    "huihui-abl-q4-k-m": ("Huihui abliterated 27B", "Q4_K_M"),
    "ornith-1-5-35b-a3b-q4-k-m": ("Ornith-1.5-35B-A3B", "Q4_K_M"),
    "lfm3-1-7b-q4-k-m": ("LFM3-1.7B", "Q4_K_M"),
}
ORDER = list(LABEL)
RUNGS = [4096, 32768, 65536, 131072, 262144]
RUNG_NAME = {4096: "4K", 32768: "32K", 65536: "64K", 131072: "128K", 262144: "256K"}
TOP = RUNGS[-1]

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:clip}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}
h2.sec{margin:30px 0 8px;font-size:14px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--dim);margin:0 0 14px;max-width:88ch}
p,li{color:var(--dim);max-width:88ch}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;border:1px solid var(--line);border-radius:10px;background:var(--panel);margin-bottom:6px}
/* These tables are pure grids. Every display role is stated explicitly (and the shared
   site CSS is not loaded here), so nothing can re-shape a cell into a card. */
#sweep-summary,#sweep-detail{display:table;table-layout:auto;width:max-content;min-width:100%;border-collapse:separate;border-spacing:0;background:var(--panel);font-size:13px}
#sweep-summary > thead,#sweep-detail > thead{display:table-header-group}
#sweep-summary > tbody,#sweep-detail > tbody{display:table-row-group}
#sweep-summary tr,#sweep-detail tr{display:table-row}
#sweep-summary th,#sweep-summary td,#sweep-detail th,#sweep-detail td{display:table-cell;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:middle;text-align:left;white-space:nowrap}
#sweep-summary thead th,#sweep-detail thead th{background:#1b2431;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);font-weight:600}
#sweep-summary tbody tr:nth-child(even) td{background:#131a24}
#sweep-summary{table-layout:fixed}
#sweep-summary td.model{width:16em;white-space:nowrap;position:sticky;left:0;z-index:2;background:var(--panel);box-shadow:1px 0 0 var(--line)}
#sweep-summary thead th:first-child{width:16em;position:sticky;left:0;z-index:3;background:#1b2431}
#sweep-summary tbody tr:nth-child(even) td.model{background:#131a24}
#sweep-summary thead th.cell{width:5.6em;white-space:normal}
#sweep-summary td.cell{width:5.6em}
#sweep-summary td.lm{width:8.5em}
#sweep-summary thead th.lm{width:8.5em}
#sweep-summary td.note-label{white-space:normal}
#sweep-summary td.note-label .mnote{border:0;padding:0;font-size:12px}
#sweep-summary td.note-label .mnote{display:block;white-space:normal;font-weight:400;color:var(--gold);font-size:12px;max-width:20em}
#sweep-summary td.model .mnote{display:none}
td.model .q{display:block;color:var(--faint);font-size:11px;font-weight:400}
.mnote{display:block;font-size:11.5px;line-height:1.4;color:var(--gold);white-space:normal}
td.model b{font-weight:600}
td.cell{text-align:right;font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace}
td.cell b{font-weight:600;color:var(--fg)}
td.cell span{display:block;color:var(--dim);font-size:12px}
th.cell span.mini{display:none;font-weight:400;font-size:10px;letter-spacing:.04em;text-transform:uppercase;color:var(--faint)}
td.lm,th.lm{white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--dim)}
#sweep-summary td.note,#sweep-detail td.note{font-size:12px;white-space:normal;overflow-wrap:break-word;max-width:22em;color:var(--dim)}
#sweep-detail td.argv{padding:6px 10px}
details{margin:0}
summary{cursor:pointer;color:var(--blue);font-size:12px}
pre{white-space:pre-wrap;word-break:break-word;font:11px/1.4 ui-monospace,monospace;color:var(--dim);background:#111821;border:1px solid var(--line);border-radius:6px;padding:7px;margin:6px 0 0;max-width:560px}
code{font:12px/1.45 ui-monospace,monospace;color:var(--fg);background:#111821;padding:1px 4px;border-radius:4px}
.dim{color:var(--faint)}
.callout{border-left:3px solid var(--gold);background:#1a1f27;padding:10px 14px;border-radius:6px;margin:14px 0}
.callout b{color:var(--gold)}
.meta{color:var(--faint);font-size:12px}
@media(max-width:760px){
 .wrap{padding:18px 10px 48px}
 h1{font-size:20px}
 #sweep-summary,#sweep-detail{font-size:12px}
 #sweep-summary th,#sweep-summary td,#sweep-detail th,#sweep-detail td{padding:6px 8px}
 #sweep-summary td.model{width:10em;white-space:normal}
 #sweep-summary thead th:first-child{width:10em;white-space:normal}
 #sweep-summary td.model .mnote{display:block;white-space:normal;margin-top:3px}
 #sweep-summary td.note-label{display:none}
 #sweep-summary thead th:last-child{display:none}
 #sweep-summary thead th.cell{width:4.8em;white-space:normal}
 #sweep-summary td.cell{width:4.8em}
 #sweep-summary thead th.cell span.mini{display:block}
 #sweep-detail thead{display:none}
 td.cell span{font-size:11px}
 /* detail table on a phone: one line per cell, each carrying its own column label */
 #sweep-detail thead{display:none}
 #sweep-detail tr{display:block;border-bottom:1px solid var(--line);padding:5px 0}
 #sweep-detail td{display:block;border-bottom:0;padding:2px 8px}
 #sweep-detail td:not(.model):not(.note):before{content:attr(data-l) " ";display:inline;color:var(--faint);font-size:11px;letter-spacing:.03em}
 #sweep-detail td.model{position:static;box-shadow:none;border-bottom:1px solid var(--line);padding:6px 8px 2px}
}"""

TOPBAR = render_topbar("../", "sweep")


def esc(s):
    return html.escape(str("" if s is None else s), quote=True)


def num(v, nd):
    return "—" if v is None else f"{v:,.{nd}f}"


def scrub(argv):
    """Strip host-specific detail from a recorded command line.

    argv records the exact invocation on the bench box. Visitors get the same flags with the
    directory prefix removed from the binary, the model path reduced to <model file>, and any
    home-directory path, bind address or host/port pair dropped entirely rather than rewritten.
    """
    if not argv:
        return ""
    toks = str(argv).split()
    # --host / --port carry the bench box's local bind address; the page never shows it
    kept = [t for i, t in enumerate(toks)
            if (toks[i - 1] if i else "") not in ("--host", "--port")]
    out = []
    for i, t in enumerate(kept):
        prev = kept[i - 1] if i else ""
        if prev in ("-m", "--model", "--mmproj", "-md", "--model-draft"):
            out.append("<model file>")
            continue
        if re.search(r"/home/|/root/|\b\d{1,3}(?:\.\d{1,3}){3}\b|0\.0\.0\.0|localhost",
                     t):
            if t.startswith("/") and re.search(r"/llama-(?:server|cli)$", t):
                out.append("llama-server")
            continue
        if t.startswith("/"):
            continue
        out.append(t)
    return " ".join(out)


def load():
    d = json.load(open(SWEEP, encoding="utf-8"))
    data = d.get("data") or {}
    rungs = d.get("rungs") or RUNGS
    slugs = [s for s in ORDER if s in data] + [s for s in data if s not in ORDER]
    return d, data, rungs, slugs


def cell(c):
    """A measured cell -> prefill b + decode span; anything else stays visibly unfilled."""
    if not c or c.get("status") != "ok" or c.get("prefill_tps") is None:
        return "<td class='cell dim'>not<br>measured</td>"
    return ("<td class=cell><b>%s</b><span>%s</span></td>"
            % (num(c.get("prefill_tps"), 1), num(c.get("decode_tps"), 2)))


def notes_for(slug, cells, rungs):
    """Short, evidence-based notes; empty when there is nothing honest to say."""
    out = []
    loaded = [r for r in rungs if (cells.get(str(r)) or {}).get("status") == "ok"]
    missing = [r for r in rungs if r not in loaded]
    if missing:
        out.append("did not load at " + ", ".join(RUNG_NAME.get(r, str(r)) for r in missing))
    for r in rungs:
        c = cells.get(str(r)) or {}
        if c.get("status") == "ok":
            if c.get("ctx_arg_matches") is False or \
                    (c.get("n_ctx_server") not in (None, r)):
                out.append("context check failed at " + RUNG_NAME.get(r, str(r)))
                break
    if slug == "lfm3-1-7b-q4-k-m":
        out.append("separate server build: the newer stable build rejects this architecture; "
                   "context cache reuse is unsupported there, and its server reports and "
                   "disables it, so its flags differ slightly from the rest")
    if out:
        return "; ".join(out)
    return "<span class=dim>—</span>"


def build():
    d, data, rungs, slugs = load()
    rungs = [int(r) for r in rungs]

    # ---- summary: one row per model
    srows = []
    for slug in slugs:
        cells = data.get(slug) or {}
        nm, quant = LABEL.get(slug, (slug, ""))
        note = notes_for(slug, cells, rungs)
        note = "" if note.startswith("<span class=dim>") else note
        row = ["<td class=model><b>%s</b>%s%s</td>"
               % (esc(nm), ("<span class=q>%s</span>" % esc(quant)) if quant else "",
                  ('<span class=mnote>%s</span>' % note) if note else "")]
        for r in rungs:
            row.append(cell(cells.get(str(r))))
        loaded = [r for r in rungs if (cells.get(str(r)) or {}).get("status") == "ok"]
        top = cells.get(str(TOP)) or {}
        row.append("<td class=lm>%s</td>" % (esc(RUNG_NAME.get(max(loaded)) if loaded else "none")))
        row.append("<td class=lm>%s</td>" % ("—" if top.get("vram_peak_gib") is None
                                              else num(top.get("vram_peak_gib"), 2) + " GiB"))
        row.append('<td class=note-label><span class=mnote>%s</span></td>' % note)
        srows.append("<tr>" + "".join(row) + "</tr>")

    rung_hdr = "".join(
        "<th class='cell'>%s<span class=mini>prefill t/s · decode t/s</span></th>" % RUNG_NAME[r]
        for r in rungs)
    summary = ("<div class=scroll><table id=sweep-summary class=grid><thead><tr><th>Model</th>%s"
               "<th class=lm>%s</th><th class=lm>%s</th>"
               "<th>Notes</th></tr></thead><tbody>%s</tbody></table></div>"
               % (rung_hdr, "Largest ctx that loaded", "Peak VRAM at %s" % RUNG_NAME[TOP], "".join(srows)))

    # ---- detail: one row per (model, rung)
    drows = []
    for slug in slugs:
        cells = data.get(slug) or {}
        nm, quant = LABEL.get(slug, (slug, ""))
        live = [r for r in rungs if str(r) in cells]
        if not live:
            drows.append("<tr class=bad-row><td class=model><b>%s</b></td><td>—</td>"
                         "<td class=note colspan=7>not measured</td></tr>" % esc(nm))
            continue
        for idx, r in enumerate(live):
            c = cells[str(r)] or {}
            ok = c.get("status") == "ok"
            if idx == 0:
                head = ("<td class=model rowspan=%d><b>%s</b>%s</td>"
                        % (len(live), esc(nm), ("<span class=q>%s</span>" % esc(quant)) if quant else ""))
            else:
                head = ""
            tds = [
                head,
                "<td class=num data-l='%s'>%s</td>" % ("Rung", RUNG_NAME.get(r, r)),
                "<td class=num data-l='%s'>%s</td>" % ("Prompt tokens", num(c.get("prompt_n"), 0) if ok else "—"),
                "<td class=num data-l='%s'>%s</td>" % ("Prefill t/s", num(c.get("prefill_tps"), 1) if ok else "—"),
                "<td class=num data-l='%s'>%s</td>" % ("Prefill s", num(c.get("prefill_s"), 1) if ok else "—"),
                "<td class=num data-l='%s'>%s</td>" % ("Decode t/s", num(c.get("decode_tps"), 2) if ok else "—"),
                "<td class=num data-l='%s'>%s</td>" % ("Generated tokens", num(c.get("predicted_n"), 0) if ok else "—"),
                "<td class=num data-l='%s'>%s</td>" % ("Peak VRAM GiB", num(c.get("vram_peak_gib"), 2) if ok else "—"),
                "<td class=argv data-l='Server argv'>%s</td>" % (
                    ("<details><summary>argv</summary><pre>%s</pre></details>"
                     % esc(scrub(c.get("server_argv_str"))))
                    if ok and c.get("server_argv_str") else "<span class=dim>—</span>"),
            ]
            drows.append("<tr>" + "".join(tds) + "</tr>")

    detail = ("<div class=scroll><table id=sweep-detail class=grid><thead><tr><th>Model</th>"
              "<th class=num>Rung</th><th class=num>Prompt tokens</th><th class=num>Prefill t/s</th>"
              "<th class=num>Prefill s</th><th class=num>Decode t/s</th>"
              "<th class=num>Generated tokens</th><th class=num>Peak VRAM GiB</th>"
              "<th>Server argv</th></tr></thead><tbody>%s</tbody></table></div>" % "".join(drows))

    n_cells = sum(1 for s in slugs for r in rungs
                  if ((data.get(s) or {}).get(str(r)) or {}).get("status") == "ok")
    n_all = len(slugs) * len(rungs)
    gen = esc((d.get("generated") or "")[:10])

    body = (
        "<p class=sub>One model per row, five contexts across: %s. Each cell is "
        "<b>prefill t/s</b> (how fast the prompt is ingested) over <b>decode t/s</b> "
        "(generation speed once the model answers). Server context and prompt length are matched "
        "in every cell — a 4K cell really is a 4K server serving a ~3.6K-token prompt, and 256K "
        "is a 256K server serving a ~256K prompt, on the same 32&nbsp;GiB card.</p>"
        % (", ".join(RUNG_NAME[r] for r in rungs))
        + "<div class=callout><b>This replaces the old A/B/C speed columns.</b> Those mixed two "
          "definitions of “context”: sometimes the server's <code>-c</code> flag, sometimes only the "
          "client prompt sent to a server started far larger. Here the server is restarted at each rung "
          "and the single prompt is calibrated to that rung, so the column heading means the same thing "
          "on both sides. Numbers from the older speed views are not comparable to these and should "
          "not be quoted side by side.</div>"
        "<h2 class=sec>Speed by context — %d models × %d contexts</h2>" % (len(slugs), len(rungs))
        + summary
        + "<p class=meta>Top line of each cell: prompt processing (prefill) tokens/s. "
          "Second line: generation (decode) tokens/s. Largest ctx loaded and peak VRAM are read from "
          "the 256K cell where it exists. %d of %d cells measured; a failed or missing cell is shown "
          "as “not measured” rather than guessed.</p>" % (n_cells, n_all)
        + "<h2 class=sec>Per-cell detail — every number above, with its inputs</h2>"
        + detail
        + "<p class=meta>Prompt tokens is what the server counted for the calibrated prompt; "
          "prefill s and decode t/s come from the server's own timings for that one request; "
          "generated tokens is the length actually produced (the probe asks for 64 and disables "
          "end-of-sequence so every cell is timed over the same span); peak VRAM is the maximum of a "
          "1&nbsp;Hz device-memory sample during the cell. Expand <b>argv</b> to see the exact flags the "
          "server was started with — the model file and install path are reduced for privacy; every flag "
          "is verbatim.</p>"
        + "<h2 class=sec>Method</h2>"
        "<ul>"
        "<li><b>Matched by construction.</b> For each cell the server is stopped, restarted with "
        "<code>-c &lt;ctx&gt;</code>, and one prompt is built and calibrated with the model's own "
        "<code>/tokenize</code> to <code>ctx − 512</code> tokens before it is sent. The 512-token "
        "headroom leaves room for the reply.</li>"
        "<li><b>One cold request per cell.</b> Temperature 0, top-k 1, prompt cache disabled, no "
        "streaming, a 64-token cap. The same request is used for every model and rung, so the columns "
        "are comparable down and across the table.</li>"
        "<li><b>Validity checks, per cell.</b> The context reported by the live server equals the rung; "
        "the <code>-c</code> argument is read back from the running process; the prompt lands within "
        "0.2 percent of the target; the reply stops at the 64-token cap (finish reason "
        "<code>length</code>) — i.e. the model really did generate, not answer in two tokens.</li>"
        "<li><b>GPU state.</b> Every other model server is stopped before a cell and device memory is "
        "sampled at 1&nbsp;Hz; the peak covers weights, caches for that rung, and the reply.</li>"
        "<li><b>Failures are recorded, never substituted.</b> Cells that did not measure are printed "
        "as such.</li>"
        "<li><b>Read the columns as a curve, not a leaderboard.</b> Part of the run shared the card "
        "with another job, so absolute prefill rates carry roughly ±5 percent extra noise; rung-to-rung "
        "ratios within a row are the reliable signal. Decode degrades with context on every model, "
        "but the size of the drop is a property of the model and its cache settings.</li>"
        "</ul>"
        "<p class=meta>Source: <code>benchmarks/ctx-sweep/</code> in the source repo — one JSON per "
        "model plus a combined sweep file, all cells checked in. %s. Rendered from those files by "
        "<code>scripts/build_pages_sweep.py</code>.</p>" % (("Measured " + gen) if gen else ""))

    title = "context sweep — speed vs context"
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>context sweep — llmbench</title><style>" + CSS + TOPBAR_CSS + "</style></head>"
            "<body>" + render_brand() + TOPBAR + "<div class=wrap><h1>" + esc(title) + "</h1>" + body
            + "</div></body></html>")
    os.makedirs(OUTDIR, exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print("sweep page:", OUT, "| models:", len(slugs), "| cells:", n_cells, "/", n_all)


def main():
    """Build the page; exit non-zero if any cell did not make it into the HTML."""
    build()
    html_text = open(OUT, encoding="utf-8").read()
    d, data, rungs, _ = load()
    missing = []
    for slug, cells in d.get("data", {}).items():
        for rung, c in cells.items():
            if c.get("status") != "ok":
                continue
            for v in (f"{c['prompt_n']:,}", f"{c['prefill_tps']:,.1f}",
                      f"{c['prefill_s']:,.1f}", f"{c['decode_tps']:,.2f}",
                      f"{c['vram_peak_gib']:,.2f}", scrub(c.get("server_argv_str"))):
                if esc(v) not in html_text:
                    missing.append((slug, rung, v))
    if missing:
        print("MISSING VALUES IN PAGE:", missing)
        return 1
    print("verified: every measured value from benchmarks/ctx-sweep is present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
