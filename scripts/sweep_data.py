#!/usr/bin/env python3
"""sweep_data.py -- the matched-context speed matrix, rendered from benchmarks/ctx-sweep/.

There is no standalone "context sweep" page any more: the matrix lives inside the
Overview's Speed view (scripts/build_pages_overview.py), between the speed table and the
notes. This module is the only renderer, so the numbers have one owner.

Source of truth: benchmarks/ctx-sweep/sweep.json (written by benchmarks/ctx-sweep/ctx_sweep.py),
plus the per-model <slug>.json files beside it. Nothing here is typed by hand: every number
(prefill t/s, decode t/s, prompt tokens, seconds, VRAM, context, argv) is read from a
measured cell. A cell that did not measure is printed as "not measured", never filled.

Layout (one fragment, injected into the overview):
  * summary  -- one row per model, five rungs (4K ... 256K), each cell "prefill / decode" t/s,
                then largest context that loaded, peak VRAM at the top rung, notes.
  * detail   -- inside a <details>: one row per (model, rung) with prompt tokens, prefill t/s,
                prefill s, decode t/s, generated tokens, peak VRAM, server argv.
  * method   -- what was held fixed per cell, and how "context" is defined here.

Visitor text only: host directories, private addresses, model file paths and user names in
the recorded argv are stripped before they reach the page.
"""
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "benchmarks", "ctx-sweep")
SWEEP = os.path.join(SRC, "sweep.json")
ANCHOR = "speed-sweep"

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


def esc(s):
    return html.escape(str("" if s is None else s), quote=True)


def num(v, nd):
    return "—" if v is None else f"{v:,.{nd}f}"


def scrub(argv):
    """Strip host-specific detail from a recorded command line."""
    if not argv:
        return ""
    toks = str(argv).split()
    kept = [t for i, t in enumerate(toks)
            if (toks[i - 1] if i else "") not in ("--host", "--port")]
    out = []
    for i, t in enumerate(kept):
        prev = kept[i - 1] if i else ""
        if prev in ("-m", "--model", "--mmproj", "-md", "--model-draft"):
            out.append("<model file>")
            continue
        if re.search(r"/home/|/root/|\b\d{1,3}(?:\.\d{1,3}){3}\b|0\.0\.0\.0|localhost", t):
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


def sweep_cells(data):
    """The measured summary columns the overview table can show per model row.

    Returns {slug: {rung:int -> cell dict with status:'ok'}}.
    """
    out = {}
    for slug, cells in (data or {}).items():
        ok = {}
        for k, c in (cells or {}).items():
            try:
                r = int(k)
            except (TypeError, ValueError):
                continue
            if c and c.get("status") == "ok" and c.get("prefill_tps") is not None:
                ok[r] = c
        out[slug] = ok
    return out


def cell(c):
    if not c or c.get("status") != "ok" or c.get("prefill_tps") is None:
        return "<td class='cell dim'>not<br>measured</td>"
    return ("<td class=cell><b>%s</b><span>%s</span></td>"
            % (num(c.get("prefill_tps"), 1), num(c.get("decode_tps"), 2)))


def notes_for(slug, cells, rungs):
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
    return "; ".join(out)


def summary_table():
    d, data, rungs, slugs = load()
    rungs = [int(r) for r in rungs]
    srows = []
    for slug in slugs:
        cells = data.get(slug) or {}
        nm, quant = LABEL.get(slug, (slug, ""))
        note = notes_for(slug, cells, rungs)
        row = ["<td class=model><b>%s</b>%s%s</td>"
               % (esc(nm), ("<span class=q>%s</span>" % esc(quant)) if quant else "",
                  ('<span class=mnote>%s</span>' % esc(note)) if note else "")]
        for r in rungs:
            row.append(cell(cells.get(str(r))))
        loaded = [r for r in rungs if (cells.get(str(r)) or {}).get("status") == "ok"]
        top = cells.get(str(TOP)) or {}
        row.append("<td class=lm>%s</td>" % esc(RUNG_NAME.get(max(loaded)) if loaded else "none"))
        row.append("<td class=lm>%s</td>" % ("—" if top.get("vram_peak_gib") is None
                                             else num(top.get("vram_peak_gib"), 2) + " GiB"))
        row.append('<td class=note-label><span class=mnote>%s</span></td>' % esc(note))
        srows.append("<tr>" + "".join(row) + "</tr>")
    rung_hdr = "".join(
        "<th class='cell'>%s<span class=mini>prefill t/s · decode t/s</span></th>" % RUNG_NAME[r]
        for r in rungs)
    colgroup = ("<colgroup><col class=c-model>%s<col class=c-lm><col class=c-lm><col></colgroup>"
                % ("<col class=c-rung>" * len(rungs)))
    return ("<div class=scroll><table id=sweep-summary>" + colgroup + "<thead><tr><th>Model</th>%s"
            "<th class=lm>%s</th><th class=lm>%s</th>"
            "<th>Notes</th></tr></thead><tbody>%s</tbody></table></div>"
            % (rung_hdr, "Largest ctx that loaded", "Peak VRAM at %s" % RUNG_NAME[TOP],
               "".join(srows)))


def detail_table():
    d, data, rungs, slugs = load()
    rungs = [int(r) for r in rungs]
    drows = []
    for slug in slugs:
        cells = data.get(slug) or {}
        nm, quant = LABEL.get(slug, (slug, ""))
        live = [r for r in rungs if str(r) in cells]
        if not live:
            drows.append("<tr class=bad-row><td class=model><b>%s</b></td><td>—</td>"
                         "<td class=note>not measured</td></tr>" % esc(nm))
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
    return ("<div class=scroll><table id=sweep-detail><thead><tr><th>Model</th>"
            "<th class=num>Rung</th><th class=num>Prompt tokens</th><th class=num>Prefill t/s</th>"
            "<th class=num>Prefill s</th><th class=num>Decode t/s</th>"
            "<th class=num>Generated tokens</th><th class=num>Peak VRAM GiB</th>"
            "<th>Server argv</th></tr></thead><tbody>%s</tbody></table></div>" % "".join(drows))


def section_html():
    """The whole matrix as one fragment, anchored at #speed-sweep inside the Speed view."""
    d, data, rungs, slugs = load()
    rungs = [int(r) for r in rungs]
    n_cells = sum(1 for s in slugs for r in rungs
                  if ((data.get(s) or {}).get(str(r)) or {}).get("status") == "ok")
    n_all = len(slugs) * len(rungs)
    gen = esc((d.get("generated") or "")[:10])
    return (
        f"<section class=sweep id={ANCHOR}>"
        "<h2 class=sec>Speed by context — matched server context and prompt length</h2>"
        f"<p class=sub>One model per row, five contexts across: {', '.join(RUNG_NAME[r] for r in rungs)}. "
        "Each cell is <b>prefill t/s</b> (how fast the prompt is ingested) over <b>decode t/s</b> "
        "(generation speed once the model answers). Server context and prompt length are matched "
        "in every cell — a 4K cell really is a 4K server serving a ~3.6K-token prompt, and 256K "
        "is a 256K server serving a ~256K prompt, on the same 32&nbsp;GiB card. These are separate, "
        "matched-context measurements, not a restatement of the per-row probes above, and the two "
        "should not be quoted side by side.</p>"
        f"<p class=meta>Top line of each cell: prompt processing (prefill) tokens/s. "
        "Second line: generation (decode) tokens/s. Largest ctx loaded and peak VRAM are read from "
        "the 256K cell where it exists. %d of %d cells measured; a failed or missing cell is shown "
        "as “not measured” rather than guessed.</p>" % (n_cells, n_all)
        + summary_table()
        + "<p class=meta>Prompt tokens is what the server counted for the calibrated prompt; "
          "prefill s and decode t/s come from the server's own timings for that one request; "
          "generated tokens is the length actually produced (the probe asks for 64 and disables "
          "end-of-sequence so every cell is timed over the same span); peak VRAM is the maximum of a "
          "1&nbsp;Hz device-memory sample during the cell.</p>"
        + "<details class=sweep-detail><summary>Per-cell detail — every number above, with its inputs "
          f"({n_cells} measured cells)</summary>" + detail_table()
        + "<p class=meta>Expand <b>argv</b> in a row to see the exact flags the server was started "
          "with — the model file and install path are reduced for privacy; every flag is verbatim.</p>"
          "</details>"
        "<details class=sweep-method><summary>How the context sweep was measured</summary>"
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
        "model plus a combined sweep file, all cells checked in. "
        + (("Measured " + gen + ". ") if gen else "")
        + "Rendered from those files by <code>scripts/sweep_data.py</code>.</p>"
        "</details></section>")


def hard_css():
    """Scoped rules for the fragment; the shared style.css has no grid for these tables."""
    return """
.sweep .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;border:1px solid var(--line);border-radius:10px;background:var(--panel);margin:10px 0}
#sweep-summary>thead,#sweep-detail>thead{display:table-header-group}
#sweep-summary>tbody,#sweep-detail>tbody{display:table-row-group}
#sweep-summary tr,#sweep-detail tr{display:table-row}
#sweep-summary th,#sweep-summary td,#sweep-detail th,#sweep-detail td{display:table-cell}
#sweep-summary col.c-model{width:11em}
#sweep-summary col.c-rung{width:4.4em}
#sweep-summary col.c-lm{width:4.4em}
#sweep-detail{width:auto;min-width:100%}
#sweep-summary th,#sweep-summary td,#sweep-detail th,#sweep-detail td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:middle;text-align:left;white-space:nowrap}
#sweep-summary td.cell{text-align:right}
#sweep-summary td.cell b{font-variant-numeric:tabular-nums}
#sweep-summary thead th,#sweep-detail thead th{display:table-cell;background:#1b2431;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);font-weight:600}
#sweep-summary tbody tr:nth-child(even) td,#sweep-detail tbody tr:nth-child(even) td{background:#131a24}
#sweep-summary{table-layout:fixed;width:100%}
#sweep-summary tbody td:first-child{width:13em;white-space:normal;position:sticky;left:0;z-index:2;background:var(--panel);box-shadow:1px 0 0 var(--line);overflow-wrap:break-word}
#sweep-summary tbody tr:nth-child(even) td:first-child{background:#131a24}
#sweep-summary thead th:first-child{position:sticky;left:0;z-index:3;background:#1b2431}
#sweep-summary tbody tr:nth-child(even) td.model{background:#131a24}

#sweep-summary thead th.cell{white-space:normal}

#sweep-summary td.note-label{white-space:normal;font-size:11.5px;color:var(--gold);overflow-wrap:break-word}
#sweep-summary td.note-label .mnote{white-space:normal}
td.model .q{display:block;color:var(--faint);font-size:11px;font-weight:400}
td.cell{text-align:right;font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace}
td.cell b{font-weight:600;color:var(--fg)}
td.cell span{display:block;color:var(--dim);font-size:11.5px}
.sweep thead th.cell span.mini{display:none}
#sweep-summary td.cell span{display:block;color:var(--dim);font-size:11.5px}
#sweep-summary thead th{white-space:normal}
#sweep-summary td.model .mnote{display:block;color:var(--gold);font-size:11px;line-height:1.35;margin-top:3px;white-space:normal}
td.lm,th.lm{font-variant-numeric:tabular-nums;color:var(--dim)}
.dim{color:var(--faint)}
.sweep-detail summary,.sweep-method summary{cursor:pointer;color:var(--blue);font-size:13px;margin:12px 0 6px}
#sweep-detail td.argv pre{white-space:pre-wrap;word-break:break-word;font:11px/1.4 ui-monospace,monospace;color:var(--dim);background:#111821;border:1px solid var(--line);border-radius:6px;padding:7px;margin:6px 0 0;max-width:520px}
.sweep ul{margin:6px 0 10px;padding-left:20px}
.sweep li{color:var(--dim);max-width:92ch}
.sweep code{font:12px/1.45 ui-monospace,monospace;color:var(--fg);background:#111821;padding:1px 4px;border-radius:4px}
@media(max-width:760px){
 #sweep-summary,#sweep-detail{font-size:11.5px}
 #sweep-summary th,#sweep-summary td,#sweep-detail th,#sweep-detail td{padding:5px 7px}
 #sweep-summary tbody td:first-child,#sweep-summary thead th:first-child{width:8.5em;max-width:8.5em}
 
 .sweep thead th.cell span.mini{display:block;font-weight:400;font-size:9px;letter-spacing:.02em;text-transform:uppercase;color:var(--faint)}
 #sweep-detail thead{display:none}
 #sweep-detail tr{display:block;border-bottom:1px solid var(--line)}
 #sweep-detail td{display:block;border-bottom:0;padding:2px 8px}
 #sweep-detail td:not(.model):before{content:attr(data-l) " ";color:var(--faint);font-size:11px}
}
"""


def main():
    """Print the fragment; verify every measured value made it in."""
    fragment = section_html()
    d, data, rungs, _ = load()
    missing = []
    for slug, cells in d.get("data", {}).items():
        for rung, c in cells.items():
            if c.get("status") != "ok":
                continue
            for v in (f"{c['prompt_n']:,}", f"{c['prefill_tps']:,.1f}",
                      f"{c['prefill_s']:,.1f}", f"{c['decode_tps']:,.2f}",
                      f"{c['vram_peak_gib']:,.2f}", scrub(c.get("server_argv_str"))):
                if esc(v) not in fragment:
                    missing.append((slug, rung, v))
    print(fragment)
    if missing:
        print("MISSING VALUES:", missing)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
