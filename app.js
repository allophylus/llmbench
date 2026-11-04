/* llmbench — four focused views over data/results.json.
   No framework, no build step, no external requests.

   Why views: one 24-column grid mixed speed, accuracy, memory and provenance, so
   nothing anchored and archive rows competed with reproducible ones. The same
   dataset is now shown as Speed / Accuracy / Games / Logic, each with its own
   small essential column set and an opt-in "show all columns" toggle.

   Sorting model (unchanged): click 1 ascending, click 2 descending, click 3
   clears. Numeric columns compare as numbers; blanks sort last in both
   directions. A model measured at several server contexts is ONE row with
   collapsible sub-rows, so sorting never separates its probes into fake models. */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ state */

  var state = {
    rows: [],
    view: "speed",
    sortKey: null,
    dir: 0,
    q: "",
    arch: "",
    vid: false,
    allCols: {},          /* per view, restored from localStorage */
    expanded: {}          /* model key -> true when its ctx sub-rows are open */
  };

  var LS = "llmbench:allcols:";

  /* ---------------------------------------------------------------- helpers */

  function num(v) { return (typeof v === "number" && isFinite(v)) ? v : null; }

  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;")
      .replace(/\n/g, " ");
  }

  function fmtNum(v, digits) {
    if (v === null || v === undefined) return '<span class="dash">—</span>';
    return Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: digits });
  }

  function fmtPct(v, digits) {
    if (v === null || v === undefined) return '<span class="dash">—</span>';
    return '<span class="' + (v >= 70 ? "score-hi" : "") + '">' + Number(v).toFixed(digits === undefined ? 1 : digits) + "</span>";
  }

  function fmtCtxNum(v) {
    if (v === null || v === undefined) return null;
    if (v >= 1024 * 1024) return Math.round(v / (1024 * 1024)) + "M";
    return v >= 1024 ? Math.round(v / 1024) + "k" : String(v);
  }

  function ctxText(r) {
    if (!r || !r.ctx_label) return "";
    return String(r.ctx_label).replace(/<[^>]*>/g, "");
  }

  function paramsB(s) {
    if (!s) return null;
    var m = String(s).match(/([\d.]+)\s*([BbMmKk]?)/);
    if (!m) return null;
    var n = parseFloat(m[1]);
    if (!isFinite(n)) return null;
    var u = (m[2] || "B").toUpperCase();
    return u === "M" ? n / 1000 : (u === "K" ? n / 1e6 : n);
  }

  function rowsOf(doc) {
    if (Array.isArray(doc)) return doc;
    if (doc && Array.isArray(doc.rows)) return doc.rows;
    return [];
  }

  function modelKey(r) { return String(r.slug || r.name || "").replace(/-ctx\d+k$/i, ""); }

  function hasSpeed(r) { return !!(r && r.speed); }

  function nativeProbe(r) {
    var p = num(r.prefill_tps), d = num(r.decode_tps);
    if (p === null && d === null) return null;
    return { prefill_tps: p, decode_tps: d };
  }

  function deepest(r) {
    var s = r.speed;
    if (!s || !s.deep || !s.deep.length) return null;
    var best = null;
    s.deep.forEach(function (d) { if (!best || (num(d.tokens) || 0) > (num(best.tokens) || 0)) best = d; });
    return best;
  }

  /* bucket means are computed from the measured cells only; n is always printed */
  var BUCKETS = {
    b_reasoning: { cells: ["gpqa", "aime", "livebench"] },
    b_context:   { cells: ["ctx30k", "ctx110k"] },
    b_agentic:   { cells: ["tau2", "shell", "termbench"] },
    b_knowledge: { cells: ["mmlupro", "arc", "math", "code"] }
  };

  function bucketVal(r, key) {
    var def = BUCKETS[key], vals = [];
    if (!def) return null;
    def.cells.forEach(function (c) {
      var v = num((r.cells || {})[c]);
      if (v !== null) vals.push(v);
    });
    if (!vals.length) return null;
    var sum = 0;
    vals.forEach(function (v) { sum += v; });
    return { mean: sum / vals.length, n: vals.length };
  }

  function thinkCap(r) {
    var t = r.thinking;
    if (!t || !t.caps || !t.caps.length) return null;
    var best = null;
    t.caps.forEach(function (c) { if (!best || (num(c.cap) || 0) > (num(best.cap) || 0)) best = c; });
    return best;
  }

  function thinkPct(r, which) {
    var c = thinkCap(r);
    if (!c || !c[which] || !num(c[which].n)) return null;
    return 100 * (num(c[which].correct) || 0) / c[which].n;
  }

  /* ------------------------------------------------------------- sort values */

  function value(r, key) {
    if (BUCKETS[key]) { var b = bucketVal(r, key); return b ? b.mean : null; }
    if (key === "name") return (r.name || "") + " " + (r.slug || "");
    if (key === "params") return paramsB(r.params_total);
    if (key === "quant") return r.quant || null;
    if (key === "arch") return r.arch || null;
    if (key === "ctx_label") return ctxText(r) || fmtCtxNum(num(r.context_window));
    if (key === "context_window") return num(r.context_window);
    if (key === "vram_mib") {
      if (num(r.vram_mib) !== null) return num(r.vram_mib);
      var sp = r.speed;
      return sp && num(sp.vram_gib) !== null ? sp.vram_gib * 1024 : null;
    }
    if (key === "date") return r.date || null;
    if (key === "speed_evidence") return evidenceText(r);
    if (key === "sp_prefill") return ownSpeed(r, "prefill");
    if (key === "sp_decode") return ownSpeed(r, "decode");
    if (key === "std_prefill") { var s = r.speed; return s && s.standard && !s.standard.pending ? num(s.standard.prefill_tps) : null; }
    if (key === "std_decode") { var s2 = r.speed; return s2 && s2.standard && !s2.standard.pending ? num(s2.standard.decode_tps) : null; }
    if (key === "native_prefill") { var n = nativeProbe(r); return n ? n.prefill_tps : null; }
    if (key === "native_decode") { var n2 = nativeProbe(r); return n2 ? n2.decode_tps : null; }
    if (key === "deep_prefill") { var d = deepest(r); return d ? num(d.prefill_tps) : null; }
    if (key === "deep_decode") { var d2 = deepest(r); return d2 ? num(d2.decode_tps) : null; }
    if (key === "game_build") return r.game ? num(r.game.build_s) : null;
    if (key === "game_attempts") return r.game ? num(r.game.attempts) : null;
    if (key === "game_tokens") return r.game ? num(r.game.tokens) : null;
    if (key === "game_link") return r.game ? "play" : null;
    if (key === "game_video") return videoCount(r);
    if (key === "think_off") return thinkPct(r, "off");
    if (key === "think_on") return thinkPct(r, "on");
    if (key === "think_delta") {
      var a = thinkPct(r, "on"), b2 = thinkPct(r, "off");
      return (a === null || b2 === null) ? null : a - b2;
    }
    if (r.cells && Object.prototype.hasOwnProperty.call(r.cells, key)) return num(r.cells[key]);
    return num(r[key]);
  }

  /* the row's own speed pair: standardised 30K when measured, else the native probe */
  function ownSpeed(r, which) {
    var s = r.speed, std = s && s.standard;
    if (std && !std.pending && num(std[which + "_tps"]) !== null) return num(std[which + "_tps"]);
    var n = nativeProbe(r);
    return n ? n[which + "_tps"] : null;
  }

  function evidenceText(r) {
    if (r.measurement_status) return r.measurement_status;
    if (r.speed) {
      var std = r.speed.standard || {};
      var rungs = (r.speed.deep || []).length;
      return (std.tokens ? std.tokens.toLocaleString() + " tok probe" : "live probe") +
        (rungs ? " + " + rungs + " deep rung(s)" : "") + (r.engine_build ? " · " + r.engine_build : "");
    }
    var bits = [];
    if (r.speed_flags) bits.push(r.speed_flags);
    if (r.engine_build) bits.push(r.engine_build);
    if (r.speed_measured_at) bits.push(String(r.speed_measured_at).slice(0, 10));
    return bits.join(" · ") || "";
  }

  function videoCount(r) { return Object.keys(r.videos || {}).length; }

  /* ---- per-cell video links: the video belongs on the score it proves ---- */
  var CELL_VIDEO = {
    gpqa: [/pub-gpqa25/, /gpqa25/], aime: [/pub-aime10x3/, /aime/],
    livebench: [/pub-livebench25/, /livebench/], ctx30k: [/ctx-gpqa30k/, /ctx30k/],
    ctx110k: [/ctx-gpqa110k/, /ctx110k/], tau2: [/tau2/],
    shell: [/shell10/, /shell/], termbench: [/termbench/]
  };

  function videoFor(key, vids) {
    var pats = CELL_VIDEO[key];
    if (!pats || !vids) return null;
    for (var k in vids) {
      for (var i = 0; i < pats.length; i++) if (pats[i].test(k)) return vids[k];
    }
    return null;
  }

  function featBadges(r) {
    var f = r.features || {}, out = [];
    if (f.fa) out.push('<span class="tag tag-fa" title="flash attention">FA</span>');
    if (f.mtp) out.push('<span class="tag tag-mtp" title="multi-token prediction (speculative)">MTP</span>');
    if (f.dflash) out.push('<span class="tag tag-dflash" title="DFlash speculative decoding">DFlash</span>');
    if (f.dflash2) out.push('<span class="tag tag-dflash" title="DFlash2 speculative decoding">DFlash2</span>');
    if (f.mxfp4) out.push('<span class="tag tag-quant" title="MXFP4 quantised weights">MXFP4</span>');
    return out.length ? " " + out.join("") : "";
  }

  /* ---------------------------------------------------------------- columns */

  function C(key, label, opts) {
    var o = opts || {};
    return {
      key: key, label: label,
      type: o.type || "num", group: o.group || "", sub: o.sub || "",
      cls: o.cls || "", title: o.title || "", sortable: o.sortable !== false, all: !!o.all,
      cell: o.cell
    };
  }


  /* ---- per-row extras: the context sweep and the logic traps live IN the row,
     not on their own pages. Collapsed by default so the table stays scannable. ---- */
  function rowExtras(r) {
    var parts = [];
    var RUNGS = [["4096","4K"],["32768","32K"],["65536","64K"],["131072","128K"],["262144","256K"]];
    if (r.sweep) {
      var rows = RUNGS.map(function (pair) {
        var c = r.sweep[pair[0]];
        if (!c || c.prefill == null) return "";
        return "<tr><td>" + pair[1] + "</td><td class=num>" + Number(c.prefill).toFixed(1) +
               "</td><td class=num>" + Number(c.decode).toFixed(2) +
               "</td><td class=num>" + (c.vram == null ? "—" : Number(c.vram).toFixed(2)) + "</td></tr>";
      }).join("");
      if (rows) {
        parts.push("<div class=rx-h>Context sweep — prefill / decode (t/s), server and prompt matched</div>" +
          "<table class=rx><thead><tr><th>ctx</th><th>prefill</th><th>decode</th><th>VRAM GiB</th></tr></thead><tbody>" +
          rows + "</tbody></table>");
      }
    }
    if (r.logic) {
      var fmt = function (x) { return (x && x.correct != null && x.n) ? (x.correct + "/" + x.n) : "invalid"; };
      parts.push("<div class=rx-h>Logic traps (10 everyday questions)</div>" +
        "<div class=rx-l>thinking off: <b>" + fmt(r.logic.off) + "</b> · thinking on: <b>" + fmt(r.logic.on) + "</b></div>");
    }
    if (!parts.length) return "";
    return '<details class="rowextra"><summary>context sweep + logic</summary>' + parts.join("") + "</details>";
  }

  function nameCell(r, grp) {
    var html = '<span class="name">' + esc(r.name) + "</span>" +
      (r.status === "failed" ? ' <span class="st st-failed" title="the run produced no measurement">failed</span>' : "") +
      '<span class="slug">' + esc(r.filename || r.slug) + "</span>" +
      '<span class="meta">' + esc(metaLine(r)) + "</span>" + rowExtras(r);
    if (grp && grp.subs.length) {
      var open = !!state.expanded[grp.key];
      html += '<button type="button" class="disclosure" data-expand="' + esc(grp.key) + '" aria-expanded="' + (open ? "true" : "false") +
        '">' + (open ? "▾" : "▸") + " " + grp.subs.length + " ctx variant" + (grp.subs.length > 1 ? "s" : "") + "</button>";
    }
    return html;
  }

  function subNameCell(r) {
    var label = ctxText(r) || fmtCtxNum(num(r.context_window)) || "sub";
    return '<span class="name dim">↳ ' + esc(label) + ' server</span>' +
      '<span class="slug">' + esc(r.slug || "") + "</span>";
  }

  function metaLine(r) {
    var bits = [];
    if (r.params_total) bits.push(r.params_total + (r.params_active && r.params_active !== r.params_total ? "/" + r.params_active + " active" : ""));
    if (r.quant) bits.push(r.quant);
    if (num(r.vram_mib) !== null) bits.push((r.vram_mib / 1024).toFixed(1) + " GiB VRAM");
    if (r.date) bits.push(r.date);
    var f = r.features || {};
    var flags = ["fa", "mtp", "dflash2", "dflash", "mxfp4"].filter(function (k) { return f[k]; });
    if (flags.length) bits.push(flags.join("+").toUpperCase());
    return bits.join(" · ");
  }

  function speedSourceMark(r) {
    var s = r.speed;
    if (s && s.standard && !s.standard.pending) return '<sup class="nat" title="standardised 30K probe">30K</sup>';
    if (nativeProbe(r)) return '<sup class="nat" title="one probe at this row’s own server context">·n</sup>';
    return "";
  }

  function spCell(r, which) {
    var v = ownSpeed(r, which);
    if (v === null) return '<span class="dash">—</span>';
    return fmtNum(v, which === "decode" ? 2 : 1) + speedSourceMark(r);
  }

  function bucketCell(r, key) {
    var b = bucketVal(r, key);
    if (!b) return '<span class="dash">—</span><span class="bkt-n">n=0</span>';
    return '<span class="bkt-v">' + fmtPct(b.mean) + '</span><span class="bkt-n">n=' + b.n + "</span>";
  }

  function scoreCell(r, key) {
    var v = num((r.cells || {})[key]);
    var t = fmtPct(v);
    var u = videoFor(key, r.videos);
    if (!u || v === null) return t;
    return '<a class="cellvid" href="' + esc(u) + '" target="_blank" rel="noopener" title="watch this cell">' + t + '<span class="play">▶</span></a>';
  }

  function ctxCell(r) {
    var t = ctxText(r);
    if (t) return esc(t);
    var c = fmtCtxNum(num(r.context_window));
    return c ? esc(c) : '<span class="dash">—</span>';
  }

  function vramCell(r) {
    if (num(r.vram_mib) !== null) return (r.vram_mib / 1024).toFixed(1);
    if (r.speed && num(r.speed.vram_gib) !== null) return r.speed.vram_gib.toFixed(1);
    return '<span class="dash">—</span>';
  }

  function gameLinkCell(r) {
    if (!r.game) return '<span class="dash">—</span>';
    if (r.game.url) return '<a href="' + esc(r.game.url) + '" target="_blank" rel="noopener">play ▶</a>';
    return '<span class="dash">—</span>';
  }

  function gameVideoCell(r) {
    var vids = r.videos || {};
    var keys = Object.keys(vids);
    if (!keys.length) return '<span class="dash">—</span>';
    var first = vids[keys[0]];
    return '<a class="cellvid" href="' + esc(first) + '" target="_blank" rel="noopener">watch' +
      (keys.length > 1 ? " (" + keys.length + ")" : "") + "</a>";
  }

  function thinkCell(r, which) {
    var v = thinkPct(r, which);
    if (v === null) return '<span class="dash">—</span>';
    var c = thinkCap(r);
    return '<span title="' + esc(which) + ', output cap ' + esc(c.cap) + ', n=' + esc(c[which].n) + '">' + fmtPct(v) + "</span>";
  }

  function deltaCell(r) {
    var a = thinkPct(r, "on"), b = thinkPct(r, "off");
    if (a === null || b === null) return '<span class="dash">—</span>';
    var d = a - b;
    return '<span class="' + (d > 0 ? "delta-up" : (d < 0 ? "delta-down" : "")) + '">' +
      (d > 0 ? "+" : "") + d.toFixed(1) + "</span>";
  }

  var STD_TIP = "standardised probe: one cold request on a calibrated ~30K-token prompt, server rows only";
  var DEEP_TIP = "the deepest depth probe for that server context (largest prompt)";
  var NAT_TIP = "one probe at this row’s own server context (llama-bench pp512/tg128) — a different measurement, not a restatement";

  /* Column order is significant: groups must be contiguous — the header renderer
     coalesces neighbouring columns that share a group label. */
  var VIEWS = {
    speed: {
      title: "Speed — prefill and decode rates as measured",
      sub: "One row per model, then the matched-context matrix: every model at 4K, 32K, 64K, 128K and 256K. A model served at several context windows keeps its probes as collapsible sub-rows instead of pretending to be several models.",
      hint: "Prefill (prompt processing) and decode (token generation) are tokens per second. <b>30K</b> marks the standardised probe; <b>·n</b> marks a single probe at the row’s own server context. Click a header to sort, again to reverse, a third time to clear. — means not measured, never guessed. The <a href=\"#speed-sweep\">speed-by-context matrix</a> below plans for one model per row and five server contexts.",
      legend: "<b>How to read:</b> every number here came from a live server on the R9700, not a vendor sheet. Rows with several context windows show their standardised 30K probe in the sub-rows. VRAM is the GPU’s used-memory peak during the request. The <a href=\"#speed-sweep\">speed-by-context matrix</a> replaced the old A/B/C speed columns: there the server is restarted at each rung, so the column heading means the same thing on both sides.",
      cols: [
        C("name", "Model", { type: "text", group: "Model", cls: "c-name", cell: nameCell, title: "click to sort by model" }),
        C("params", "Params", { type: "params", group: "Model", sub: "total/active", cls: "c-params", cell: function (r) {
          return esc(r.params_total || "—") + (r.params_active && r.params_active !== r.params_total ? ' <span class="act">/ ' + esc(r.params_active) + "</span>" : "");
        } }),
        C("quant", "Quant", { type: "text", group: "Model", cls: "c-quant", all: true, cell: function (r) { return '<span class="pill">' + esc(r.quant || "—") + "</span>"; } }),
        C("arch", "Arch", { type: "text", group: "Model", cls: "c-arch", all: true, cell: function (r) { return esc(r.arch || "—"); } }),
        C("ctx_label", "Server ctx", { type: "text", group: "Server", cls: "c-ctx", cell: ctxCell }),
        C("context_window", "Ctx tokens", { group: "Server", cls: "sv", all: true, cell: function (r) { return fmtCtxNum(num(r.context_window)) || '<span class="dash">—</span>'; } }),
        C("sp_prefill", "Prefill", { group: "Speed", sub: "t/s", cls: "c-sp", title: "the row’s own measurement: standardised 30K probe, else its native-ctx probe", cell: function (r) { return spCell(r, "prefill"); } }),
        C("sp_decode", "Decode", { group: "Speed", sub: "t/s", cls: "c-sp", title: "the row’s own measurement: standardised 30K probe, else its native-ctx probe", cell: function (r) { return spCell(r, "decode"); } }),
        C("std_prefill", "Prefill t/s", { group: "Standardised 30K probe", sub: "@ 30K", all: true, cls: "c-std", title: STD_TIP, cell: function (r) {
          var s = r.speed && r.speed.standard;
          if (!s) return '<span class="dash">—</span>';
          if (s.pending) return '<span class="pending">pending</span>';
          return fmtNum(num(s.prefill_tps), 1);
        } }),
        C("std_decode", "Decode t/s", { group: "Standardised 30K probe", sub: "@ 30K", all: true, cls: "c-std", title: STD_TIP, cell: function (r) {
          var s = r.speed && r.speed.standard;
          if (!s) return '<span class="dash">—</span>';
          if (s.pending) return '<span class="pending">pending</span>';
          return fmtNum(num(s.decode_tps), 2);
        } }),
        C("native_prefill", "Prefill t/s", { group: "llama-bench (native ctx)", sub: "pp512", all: true, cls: "c-nat", title: NAT_TIP, cell: function (r) {
          var n = nativeProbe(r); return n && n.prefill_tps !== null ? fmtNum(n.prefill_tps, 1) : '<span class="dash">—</span>';
        } }),
        C("native_decode", "Decode t/s", { group: "llama-bench (native ctx)", sub: "tg128", all: true, cls: "c-nat", title: NAT_TIP, cell: function (r) {
          var n = nativeProbe(r); return n && n.decode_tps !== null ? fmtNum(n.decode_tps, 2) : '<span class="dash">—</span>';
        } }),
        C("deep_prefill", "Prefill t/s", { group: "Deepest probe", sub: "largest prompt", all: true, cls: "c-deep", title: DEEP_TIP, cell: function (r) {
          var d = deepest(r); return d ? fmtNum(num(d.prefill_tps), 1) : '<span class="dash">—</span>';
        } }),
        C("deep_decode", "Decode t/s", { group: "Deepest probe", sub: "largest prompt", all: true, cls: "c-deep", title: DEEP_TIP, cell: function (r) {
          var d = deepest(r); return d ? fmtNum(num(d.decode_tps), 2) : '<span class="dash">—</span>';
        } }),
        C("vram_mib", "VRAM GiB", { group: "Memory", cls: "sv", cell: vramCell }),
        C("date", "Date", { type: "text", group: "Provenance", cls: "c-date", all: true, cell: function (r) { return esc(r.date || "—"); } }),
        C("speed_evidence", "Evidence", { type: "text", group: "Provenance", cls: "c-evidence", all: true, cell: function (r) {
          var t = evidenceText(r); return t ? '<span class="prov">' + esc(t) + "</span>" : '<span class="dash">—</span>';
        } })
      ]
    },

    accuracy: {
      title: "Accuracy — five buckets, means of the cells that were actually measured",
      sub: "Each bucket is the mean of its measured cells, with n beside it. Individual cells are one click away under “Show all columns”.",
      hint: "Percent correct on frozen prompt sets. A bucket shows the mean of the cells inside it and how many of them exist (n); <b>n=0</b> means nothing in that bucket was measured for that model. Nothing is filled in or guessed. Click a header to sort.",
      legend: "<b>Buckets:</b> Reasoning = GPQA + AIME + LiveBench · Long context = accuracy with ~30K and ~110K embedded context · Agentic = tau2 + Shell + TermBench · Knowledge = MMLU-Pro + ARC + MATH. Means are unweighted and computed only over measured cells.",
      cols: [
        C("name", "Model", { type: "text", group: "Model", cls: "c-name", cell: nameCell }),
        C("params", "Params", { type: "params", group: "Model", cls: "c-params", cell: function (r) { return esc(r.params_total || "—"); } }),
        C("quant", "Quant", { type: "text", group: "Model", cls: "c-quant", all: true, cell: function (r) { return '<span class="pill">' + esc(r.quant || "—") + "</span>"; } }),
        C("b_reasoning", "Reasoning", { group: "Bucket means", sub: "GPQA+AIME+LB", title: "mean of GPQA, AIME and LiveBench for this model", cls: "sc bkt", cell: function (r) { return bucketCell(r, "b_reasoning"); } }),
        C("b_context", "Long context", { group: "Bucket means", sub: "ctx30k+110k", title: "mean of the ~30K and ~110K embedded-context accuracy cells", cls: "sc bkt", cell: function (r) { return bucketCell(r, "b_context"); } }),
        C("b_agentic", "Agentic", { group: "Bucket means", sub: "tau2+Shell+Term", title: "mean of tau2, Shell and TermBench", cls: "sc bkt", cell: function (r) { return bucketCell(r, "b_agentic"); } }),
        C("b_knowledge", "Knowledge", { group: "Bucket means", sub: "MMLU-P+ARC+MATH", title: "mean of MMLU-Pro, ARC and MATH (measured on very few rows)", cls: "sc bkt", cell: function (r) { return bucketCell(r, "b_knowledge"); } }),
        C("gpqa", "GPQA", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "gpqa"); } }),
        C("aime", "AIME", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "aime"); } }),
        C("livebench", "LiveBench", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "livebench"); } }),
        C("ctx30k", "ctx30k", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "ctx30k"); } }),
        C("ctx110k", "ctx110k", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "ctx110k"); } }),
        C("tau2", "tau2", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "tau2"); } }),
        C("shell", "Shell", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "shell"); } }),
        C("termbench", "TermBench", { group: "Individual cells", all: true, cls: "sc", cell: function (r) { return scoreCell(r, "termbench"); } }),
        C("date", "Date", { type: "text", group: "Provenance", cls: "c-date", all: true, cell: function (r) { return esc(r.date || "—"); } })
      ]
    },

    games: {
      title: "Games — a model writes a playable browser game from one frozen prompt",
      sub: "One shot, then repair turns allowed; build time, tokens and attempts are recorded per model. A game only counts when it actually runs.",
      hint: "Build time is seconds spent generating the game; tokens are what the model spent doing it; attempts counts generation passes including repairs. <b>play</b> opens the game, <b>watch</b> the recorded render.",
      legend: "<b>Gate:</b> a game is listed only when the frozen-prompt harness produced files that run in a browser. Missing rows mean the model was not asked or produced nothing that passed.",
      cols: [
        C("name", "Model", { type: "text", group: "Model", cls: "c-name", cell: nameCell }),
        C("quant", "Quant", { type: "text", group: "Model", cls: "c-quant", all: true, cell: function (r) { return '<span class="pill">' + esc(r.quant || "—") + "</span>"; } }),
        C("arch", "Arch", { type: "text", group: "Model", cls: "c-arch", all: true, cell: function (r) { return esc(r.arch || "—"); } }),
        C("game_build", "Build s", { group: "Generation", cls: "sv", cell: function (r) {
          var v = value(r, "game_build"); return v === null ? '<span class="dash">—</span>' : fmtNum(v, 1);
        } }),
        C("game_attempts", "Attempts", { group: "Generation", cls: "sv", cell: function (r) {
          var v = value(r, "game_attempts"); return v === null ? '<span class="dash">—</span>' : fmtNum(v, 0);
        } }),
        C("game_tokens", "Tokens", { group: "Generation", cls: "sv", cell: function (r) {
          var v = value(r, "game_tokens"); return v === null ? '<span class="dash">—</span>' : fmtNum(v, 0);
        } }),
        C("game_link", "Game", { type: "text", group: "Result", sortable: false, cls: "c-game", cell: gameLinkCell }),
        C("game_video", "Video", { type: "text", group: "Result", sortable: false, cls: "c-videos", cell: gameVideoCell })
      ]
    },

  };

  /* ---------------------------------------------------------------- sorting */

  function typeOf(key) {
    var cols = allColsFor(state.view);
    for (var i = 0; i < cols.length; i++) if (cols[i].key === key) return cols[i].type;
    return "num";
  }

  function compare(a, b, key) {
    var type = typeOf(key);
    var va = value(a, key), vb = value(b, key);
    var ea = va === null || va === undefined || va === "";
    var eb = vb === null || vb === undefined || vb === "";
    if (ea && eb) return 0;
    if (ea) return 1;
    if (eb) return -1;
    if (type === "num" || type === "params") {
      var d = Number(va) - Number(vb);
      return d === 0 ? 0 : (d < 0 ? -1 : 1);
    }
    var s = String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: "base" });
    return s === 0 ? 0 : (s < 0 ? -1 : 1);
  }

  /* ---------------------------------------------------------------- filters */

  function matches(r) {
    if (state.arch && (r.arch || "") !== state.arch) return false;
    if (state.vid && !videoCount(r)) return false;
    if (!state.q) return true;
    var hay = [r.name, r.slug, r.quant, r.arch, r.params_total, r.params_active, ctxText(r)].join(" ").toLowerCase();
    return state.q.toLowerCase().split(/\s+/).filter(Boolean).every(function (t) { return hay.indexOf(t) !== -1; });
  }

  /* a model = one parent row plus the rows that differ only by server context */
  function groupsFor(rows) {
    var g = {}, order = [];
    rows.forEach(function (r) {
      var k = modelKey(r);
      if (!g[k]) { g[k] = []; order.push(k); }
      g[k].push(r);
    });
    return order.map(function (k) {
      var list = g[k], parent = null;
      list.forEach(function (r) { if (!parent && !/-ctx\d+k$/i.test(String(r.slug || ""))) parent = r; });
      if (!parent) parent = list[0];
      var subs = list.filter(function (r) { return r !== parent; });
      return { key: k, parent: parent, subs: subs };
    });
  }

  function subsForView(grp) {
    /* only show sub-rows that carry something in the current view */
    var view = state.view;
    return grp.subs.filter(function (r) {
      if (view === "speed") return hasSpeed(r) || nativeProbe(r) || r.speed;
      if (view === "accuracy") return Object.keys(r.cells || {}).some(function (k) { return num(r.cells[k]) !== null; });
      if (view === "games") return !!r.game;
      return true;
    });
  }

  /* --------------------------------------------------------------- rendering */

  function allColsFor(view) { return VIEWS[view].cols; }
  function shownCols(view) {
    var all = !!state.allCols[view];
    return allColsFor(view).filter(function (c) { return all || !c.all; });
  }

  function renderHead(cols) {
    var grp = document.getElementById("grprow"), row = document.getElementById("colrow");
    grp.innerHTML = ""; row.innerHTML = "";
    var i = 0;
    while (i < cols.length) {
      var g = cols[i].group || "";
      var span = 1;
      while (i + span < cols.length && (cols[i + span].group || "") === g) span++;
      var th = document.createElement("th");
      th.colSpan = span;
      th.className = "gcell" + (g ? "" : " gcell-empty");
      th.scope = "colgroup";
      th.textContent = g;
      grp.appendChild(th);
      i += span;
    }
    cols.forEach(function (c) {
      var th = document.createElement("th");
      th.scope = "col";
      th.className = (c.type === "num" ? "num " : "") + (c.cls || "");
      if (c.sortable !== false) {
        th.dataset.key = c.key;
        th.dataset.type = c.type;
        th.tabIndex = 0;
        th.setAttribute("role", "columnheader");
      }
      th.innerHTML = esc(c.label) + (c.sub ? '<br><span class="th-sub">' + esc(c.sub) + "</span>" : "");
      if (c.title) th.title = c.title;
      row.appendChild(th);
    });
  }

  function rowHTML(r, cols, grp, isSub) {
    var cells = cols.map(function (c) {
      var body;
      if (c.key === "name") body = isSub ? subNameCell(r) : nameCell(r, grp);
      else body = c.cell ? c.cell(r) : esc(value(r, c.key));
      var cls = ["num", c.cls || ""];
      if (c.key === "name") cls = ["c-name"];
      return '<td class="' + cls.join(" ").trim() + '" data-label="' + esc(c.label) + '">' + body + "</td>";
    }).join("");
    return '<tr class="' + (isSub ? "sub" : "model") + '" data-model="' + esc(grp.key) + '">' + cells + "</tr>";
  }

  function paint() {
    var cols = shownCols(state.view);
    var view = VIEWS[state.view];
    renderHead(cols);

    var rows = state.rows.filter(matches);
    var groups = groupsFor(rows);
    groups.forEach(function (g) { g.subs = subsForView(g); });

    if (state.sortKey && state.dir) {
      var key = state.sortKey, dir = state.dir;
      groups.sort(function (a, b) {
        var r = compare(a.parent, b.parent, key);
        return r === 0 ? 0 : (dir === 1 ? r : -r);
      });
    }

    /* archive: rows whose weights are gone stay visible, collapsed, and never mix with
       reproducible rows. Rendered only when the data actually marks some. */
    var arch = groups.filter(function (g) { return g.parent.measurement_status; });
    var live = groups.filter(function (g) { return !g.parent.measurement_status; });

    var html = "";
    live.forEach(function (g) {
      html += rowHTML(g.parent, cols, g, false);
      if (state.expanded[g.key]) {
        g.subs.forEach(function (r) { html += rowHTML(r, cols, g, true); });
      }
    });
    var archiveHTML = "";
    if (arch.length) {
      archiveHTML = '<tr class="archhead"><td colspan="' + cols.length + '">Archive — weights no longer on this machine (' + arch.length + ")" +
        '</td></tr>';
      arch.forEach(function (g) { archiveHTML += rowHTML(g.parent, cols, g, false); });
    }
    document.getElementById("rows").innerHTML = html + archiveHTML;

    document.getElementById("empty").hidden = groups.length > 0;
    document.getElementById("count").textContent =
      groups.length + " model" + (groups.length === 1 ? "" : "s") + " · " + rows.length + " row" + (rows.length === 1 ? "" : "s");
    document.getElementById("ranknote").textContent = state.sortKey
      ? "sorted by " + (labelOf(state.sortKey) || state.sortKey) + (state.dir === 1 ? " ↑" : " ↓")
      : "";

    Array.prototype.forEach.call(document.querySelectorAll("#colrow th[data-key]"), function (th) {
      if (th.dataset.key === state.sortKey && state.dir) {
        th.dataset.dir = state.dir === 1 ? "asc" : "desc";
        th.setAttribute("aria-sort", state.dir === 1 ? "ascending" : "descending");
      } else {
        delete th.dataset.dir;
        th.removeAttribute("aria-sort");
      }
    });
  }

  function labelOf(key) {
    var cols = allColsFor(state.view);
    for (var i = 0; i < cols.length; i++) if (cols[i].key === key) return cols[i].label;
    return key;
  }

  /* ------------------------------------------------------------------ views */

  function setView(v, push) {
    if (!VIEWS[v]) v = "speed";
    state.view = v;
    state.sortKey = null;
    state.dir = 0;
    var view = VIEWS[v];
    document.getElementById("tablepanel").setAttribute("aria-labelledby", "tab-" + v);
    document.getElementById("viewsub").textContent = view.sub;
    document.getElementById("viewhint").innerHTML = view.hint;
    document.getElementById("legend").innerHTML = view.legend;
    var tabs = document.querySelectorAll(".viewtab");
    Array.prototype.forEach.call(tabs, function (t) {
      var on = t.dataset.view === v;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
    });
    var all = document.getElementById("allcols");
    all.setAttribute("aria-pressed", state.allCols[v] ? "true" : "false");
    all.textContent = state.allCols[v] ? "Show essentials" : "Show all columns";
    if (push !== false) {
      try { history.replaceState(null, "", "#" + v); } catch (e) { location.hash = v; }
    }
    paint();
  }

  function wire() {
    Array.prototype.forEach.call(document.querySelectorAll(".viewtab"), function (tab, i, arr) {
      tab.addEventListener("click", function () { setView(tab.dataset.view); });
      tab.addEventListener("keydown", function (e) {
        var next = null;
        if (e.key === "ArrowRight") next = arr[(i + 1) % arr.length];
        else if (e.key === "ArrowLeft") next = arr[(i - 1 + arr.length) % arr.length];
        else if (e.key === "Home") next = arr[0];
        else if (e.key === "End") next = arr[arr.length - 1];
        if (next) { e.preventDefault(); next.focus(); setView(next.dataset.view); }
      });
    });

    document.getElementById("q").addEventListener("input", function (e) { state.q = e.target.value.trim(); paint(); });
    document.getElementById("arch").addEventListener("change", function (e) { state.arch = e.target.value; paint(); });
    document.getElementById("vid").addEventListener("change", function (e) { state.vid = e.target.checked; paint(); });
    document.getElementById("allcols").addEventListener("click", function () {
      state.allCols[state.view] = !state.allCols[state.view];
      try { localStorage.setItem(LS + state.view, state.allCols[state.view] ? "1" : "0"); } catch (e) {}
      setView(state.view, false);
    });

    document.getElementById("rows").addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button[data-expand]") : null;
      if (!b) return;
      var k = b.getAttribute("data-expand");
      state.expanded[k] = !state.expanded[k];
      paint();
    });

    document.getElementById("reset").addEventListener("click", function () {
      document.getElementById("q").value = "";
      document.getElementById("arch").value = "";
      document.getElementById("vid").checked = false;
      state.q = ""; state.arch = ""; state.vid = false;
      paint();
    });

    document.addEventListener("keydown", function (e) {
      var th = document.activeElement;
      if (!th || th.tagName !== "TH" || !th.dataset.key) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onHeaderClick(th.dataset.key); }
    });
  }

  function onHeaderClick(key) {
    if (!key) return;
    if (state.sortKey === key) {
      if (state.dir === 0) state.dir = 1;
      else if (state.dir === 1) state.dir = -1;
      else { state.dir = 0; state.sortKey = null; }
    } else {
      state.sortKey = key;
      state.dir = 1;
    }
    paint();
  }

  function bindHeaderSort() {
    /* headers are re-rendered per view, so delegate from the row */
    var row = document.getElementById("colrow");
    if (row.dataset.wired) return;
    row.dataset.wired = "1";
    row.addEventListener("click", function (e) {
      var th = e.target.closest ? e.target.closest("th[data-key]") : null;
      if (th) onHeaderClick(th.dataset.key);
    });
    row.addEventListener("keydown", function (e) {
      var th = e.target.closest ? e.target.closest("th[data-key]") : null;
      if (!th) return;
      var ths = Array.prototype.slice.call(row.querySelectorAll("th[data-key]"));
      var i = ths.indexOf(th);
      if (e.key === "ArrowRight" && ths[i + 1]) { e.preventDefault(); ths[i + 1].focus(); }
      else if (e.key === "ArrowLeft" && ths[i - 1]) { e.preventDefault(); ths[i - 1].focus(); }
    });
  }

  function fillArchSelects(rows) {
    var sel = document.getElementById("arch");
    var seen = {};
    rows.forEach(function (r) { if (r.arch) seen[r.arch] = (seen[r.arch] || 0) + 1; });
    Object.keys(seen).sort(function (a, b) { return a.localeCompare(b); }).forEach(function (k) {
      var o = document.createElement("option");
      o.value = k;
      o.textContent = (k.length > 46 ? k.slice(0, 45) + "…" : k) + " (" + seen[k] + ")";
      sel.appendChild(o);
    });
  }

  /* ---- context/speed detail table (below the views) ---- */
  function probesTable(rows) {
    var host = document.getElementById("probes");
    if (!host) return;
    var groups = {};
    rows.forEach(function (r) {
      if (!r.speed) return;
      (groups[r.name] = groups[r.name] || []).push(r);
    });
    var names = Object.keys(groups);
    if (!names.length) { host.hidden = true; return; }
    var html = "";
    names.forEach(function (n) {
      var body = "";
      groups[n].forEach(function (r) {
        var std = r.speed.standard || {};
        var rungs = r.speed.deep && r.speed.deep.length ? r.speed.deep : [];
        var depth = rungs.length ? rungs.map(function (d) {
          return '<span class="rung">' + Math.round(d.tokens).toLocaleString() + " tok: " +
            fmtNum(num(d.prefill_tps), 1) + " prefill / " + fmtNum(num(d.decode_tps), 2) + " decode</span>";
        }).join("") : '<span class="dash">none — 30K standard prompt only</span>';
        body += '<tr><td class="num">' + esc(ctxText(r) || fmtCtxNum(num(r.context_window)) || "") + "</td>" +
          '<td class="num">' + (std.pending ? '<span class="pending">pending</span>' :
            fmtNum(num(std.prefill_tps), 1) + " / " + fmtNum(num(std.decode_tps), 2) +
            ' <span class="dash">at ' + (std.tokens || 0).toLocaleString() + " tok</span>") + "</td>" +
          '<td class="num">' + depth + "</td>" +
          '<td class="num">' + (r.speed.vram_gib ? r.speed.vram_gib.toFixed(2) + " GiB" : "—") + "</td></tr>";
      });
      html += '<h3 class="probe-h">' + esc(n) + "</h3>" +
        '<div class="table-wrap probe-wrap"><table class="probe"><thead><tr>' +
        "<th>Server context</th><th>Standard 30K prompt — prefill / decode t/s</th>" +
        "<th>Deep probes — prefill / decode t/s</th><th>VRAM (peak)</th></tr></thead><tbody>" +
        body + "</tbody></table></div>";
    });
    host.innerHTML = '<h2>Context &amp; speed, per server context</h2>' +
      '<p class="probe-note">One server at a time, same flags, cold requests at temperature 0 with ' +
      "the prompt cache off; prefill and decode are the server's own <code>prompt_per_second</code> and " +
      "<code>predicted_per_second</code>. VRAM is the GPU's used-memory peak during the run. A " +
      '<span class="pending">pending</span> cell is a probe that has not been run at that server context yet — it is never estimated.</p>' + html;
    host.hidden = false;
  }

  function errorBars(eb) {
    var host = document.getElementById("errbars");
    if (!host) return;
    if (!eb) { host.hidden = true; return; }
    function pct(v, d) { return v === null || v === undefined ? "—" : Number(v).toFixed(d === undefined ? 2 : d) + "%"; }
    var rows = [
      ["A3B, 32K server window", eb.a3b_32k, false],
      ["A3B, 256K server window", eb.a3b_256k, false],
      ["Qwen3.8-27B, 131K server window", eb.qwen38_27b_32k, true]
    ];
    var body = rows.map(function (r) {
      var k = r[1];
      if (!k) return "";
      var dec = k.decode || {};
      var decTxt = dec.mean === null || dec.mean === undefined ? "—"
        : fmtNum(dec.mean, 2) + (dec.n > 1 ? ' <span class="spread">' + pct(dec.spread_pct) + " spread</span>"
          : ' <span class="spread">' + esc(dec.n === 1 ? "1 rep" : "n/a") + "</span>");
      return "<tr><td>" + esc(r[0]) + "</td>" +
        '<td class="num">' + fmtNum(k.prefill.mean, 1) + ' <span class="spread">' + pct(k.prefill.spread_pct) + "</span></td>" +
        '<td class="num">' + decTxt + "</td>" +
        '<td class="num">' + fmtNum(k.wall_s.mean, 2) + ' <span class="spread">' + pct(k.wall_s.spread_pct) + "</span></td>" +
        '<td class="num">' + (k.n || "") + "</td></tr>";
    }).join("");
    host.innerHTML = '<h2>Error bars — how far one identical run moves</h2>' +
      '<p class="probe-note">' + esc(eb.policy) + " Every measured spread in the campaign was under 5% " +
      "(largest " + pct(eb.max_spread_pct) + "), so the single-run numbers here are trustworthy at that level. " +
      "Prefill/decode are the server's own rates; spread is (max−min)/mean.</p>" +
      '<div class="table-wrap"><table class="probe"><thead><tr><th>Point</th>' +
      "<th>Prefill t/s (spread)</th><th>Decode t/s (spread)</th><th>Wall s (spread)</th><th>Reps</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      '<p class="probe-note sm">Qwen3.8-27B decode is one valid <code>/completion ignore_eos</code> run at ' +
      "28.61 t/s (400 generated tokens); its chat-probe figure (25.9 at 2 tokens) is an end-of-answer " +
      "stop, i.e. noise, and is not a decode measurement — so no decode spread is quoted for it.</p>";
    host.hidden = false;
  }

  /* ------------------------------------------------------------------- boot */

  function boot(doc) {
    state.rows = rowsOf(doc).filter(function (r) { return r && r.name; });
    if (doc && doc.generated) document.getElementById("gen").textContent = "data generated " + doc.generated;

    /* restore per-view column choice */
    Object.keys(VIEWS).forEach(function (v) {
      try { state.allCols[v] = localStorage.getItem(LS + v) === "1"; } catch (e) { state.allCols[v] = false; }
    });

    fillArchSelects(state.rows);
    probesTable(state.rows);
    errorBars(doc && doc.error_bars);
    bindHeaderSort();
    wire();

    var hash = String(location.hash || "").replace(/^#/, "");
    setView(VIEWS[hash] ? hash : "speed", false);
  }

  window.addEventListener("hashchange", function () {
    var h = String(location.hash || "").replace(/^#/, "");
    if (VIEWS[h] && h !== state.view) setView(h, false);
  });

  function fail(msg) {
    var box = document.getElementById("empty");
    box.hidden = false;
    box.textContent = "Could not load data/results.json (" + msg + ").";
  }

  if (window.LLMBENCH_DATA) { boot(window.LLMBENCH_DATA); return; }

  if (location.protocol === "file:") {
    var s = document.createElement("script");
    s.src = "data/results.js";
    s.onload = function () { if (window.LLMBENCH_DATA) boot(window.LLMBENCH_DATA); else fail("no data"); };
    s.onerror = function () { fail("file:// fallback missing; run a local server"); };
    document.head.appendChild(s);
    return;
  }

  fetch("data/results.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(boot)
    .catch(function (e) { fail(e.message); });
})();
