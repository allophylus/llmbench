/* llmbench — sortable, filterable table over data/results.json.
   No framework, no build step, no external requests.

   Sorting model (spec):
     click 1 header -> ascending on that column
     click 2 header -> descending on that column
     click 3 header -> sort cleared, rows return to their default (filename) order
   Numeric columns compare as numbers (never lexically); blanks always sort last,
   in both directions. The active header carries data-dir + a ▲/▼ arrow.

   v3: rows may carry `speed` (one row per model + server context: standard-30K probe
   and deep-context probes), `games` and `thinking` blocks. Rows without them (the
   folded llama-bench rows) render exactly as before. */
(function () {
  "use strict";

  var COLUMNS = [
    { key: "name",           type: "text"   },
    { key: "params",         type: "params" },
    { key: "quant",          type: "text"   },
    { key: "arch",           type: "text"   },
    { key: "ctx_label",      type: "text"   },
    { key: "std_prefill",    type: "num"    },
    { key: "std_decode",     type: "num"    },
    { key: "deep_prefill",   type: "num"    },
    { key: "deep_decode",    type: "num"    },
    { key: "gpqa",           type: "num"    },
    { key: "aime",           type: "num"    },
    { key: "livebench",      type: "num"    },
    { key: "ctx30k",         type: "num"    },
    { key: "ctx110k",        type: "num"    },
    { key: "tau2",           type: "num"    },
    { key: "shell",          type: "num"    },
    { key: "termbench",      type: "num"    },
    { key: "decode_tps",     type: "num"    },
    { key: "prefill_tps",    type: "num"    },
    { key: "context_window", type: "num"    },
    { key: "vram_mib",       type: "num"    },
    { key: "date",           type: "text"   },
    { key: "speed_evidence", type: "text"   },
  ];
  var COL = {};
  COLUMNS.forEach(function (c) { COL[c.key] = c; });

  var LABELS = {
    gpqa: "GPQA", aime: "AIME", livebench: "LiveBench", ctx30k: "ctx30k",
    ctx110k: "ctx110k", tau2: "tau2", shell: "Shell", termbench: "TermBench",
    decode_tps: "Decode t/s", prefill_tps: "Prefill t/s",
    context_window: "Ctx (tokens)", vram_mib: "VRAM (GiB)", videos: "Videos",
    quant: "Quant", arch: "Arch", date: "Date",
    std_prefill: "Prefill t/s at 30K", std_decode: "Decode t/s at 30K",
    deep_prefill: "Prefill t/s at depth", deep_decode: "Decode t/s at depth",
    ctx_label: "Server ctx", speed_evidence: "Speed evidence"
  };

  var state = { sortKey: null, dir: 0, rows: [], view: [], group: "all" };

  /* ------------------------------------------------------------------ data */

  function num(v) {                       // finite number or null
    return (typeof v === "number" && isFinite(v)) ? v : null;
  }

  var CELL_KEYS = { gpqa: 1, aime: 1, livebench: 1, ctx30k: 1, ctx110k: 1, tau2: 1,
                    shell: 1, termbench: 1 };

  function hasSpeed(r) { return !!(r && r.speed); }

  function speed(row) { return row.speed || null; }

  /** deepest deep-context probe: the one at the largest prompt size */
  function deepest(row) {
    var s = speed(row);
    if (!s || !s.deep || !s.deep.length) return null;
    var best = null;
    s.deep.forEach(function (d) {
      if (!best || (num(d.tokens) || 0) > (num(best.tokens) || 0)) best = d;
    });
    return best;
  }

  function value(row, key) {
    if (CELL_KEYS[key]) return num((row.cells || {})[key]);
    if (key === "params") return paramsB(row.params_total);
    if (key === "game_attempts") return (row.game && row.game.attempts != null) ? row.game.attempts : null;
    if (key === "game_tokens")   return (row.game && row.game.tokens) ? row.game.tokens : null;
    if (key === "game_build")    return (row.game && row.game.build_s) ? row.game.build_s : null;
    if (key === "vram_mib") return num(row.vram_mib);
    if (key === "decode_tps" || key === "prefill_tps" || key === "context_window")
      return num(row[key]);
    if (key === "std_prefill")  { var s = speed(row); return s && s.standard ? num(s.standard.prefill_tps) : null; }
    if (key === "std_decode")   { var s2 = speed(row); return s2 && s2.standard ? num(s2.standard.decode_tps) : null; }
    if (key === "deep_prefill") { var d = deepest(row); return d ? num(d.prefill_tps) : null; }
    if (key === "deep_decode")  { var d2 = deepest(row); return d2 ? num(d2.decode_tps) : null; }
    if (key === "ctx_label") return row.ctx_label || (row.context_window ? fmtCtx(num(row.context_window)) : null);
    if (key === "date") return row.date || null;
    if (key === "speed_evidence") {
      if (row.measurement_status) return row.measurement_status;
      if (row.speed) {
        var std0 = (row.speed.standard || {});
        var rungs = (row.speed.deep || []).length;
        return "live probe " + (std0.tokens || 0).toLocaleString() + " tok" +
          (rungs ? " + " + rungs + " deep rung(s)" : "") +
          (row.engine_build ? " · " + row.engine_build : "");
      }
      var bits = [];
      if (row.speed_flags) bits.push(row.speed_flags);
      if (row.engine_build) bits.push(row.engine_build);
      if (row.speed_measured_at) bits.push(coarseDate(row.speed_measured_at));
      return bits.join(" · ") || null;
    }
    if (key === "name") return (row.name || "") + " " + (row.slug || "");
    if (key === "quant") return row.quant || null;
    if (key === "arch") return row.arch || null;
    return num(row[key]);
  }

  function paramsB(s) {                   // "27B" / "2.4B" / "350M" / "1.7B" -> billions
    if (!s) return null;
    var m = String(s).match(/([\d.]+)\s*([BbMmKk]?)/);
    if (!m) return null;
    var n = parseFloat(m[1]);
    if (!isFinite(n)) return null;
    var u = (m[2] || "B").toUpperCase();
    return u === "M" ? n / 1000 : (u === "K" ? n / 1e6 : n);
  }

  /** Provider: the JSON rows may be a bare array (or {rows:[...]}). */
  function rowsOf(doc) {
    if (Array.isArray(doc)) return doc;
    if (doc && Array.isArray(doc.rows)) return doc.rows;
    return [];
  }

  /* -------------------------------------------------------------- sorting */

  function compare(a, b) {                // returns <0 / 0 / >0; blanks sort last
    var type = COL[state.sortKey].type;
    var va = value(a, state.sortKey), vb = value(b, state.sortKey);
    var ea = va === null || va === undefined || va === "";
    var eb = vb === null || vb === undefined || vb === "";
    if (ea && eb) return 0;
    if (ea) return 1;                     // blank after everything, both directions
    if (eb) return -1;
    if (type === "num" || type === "params") {
      var d = Number(va) - Number(vb);
      if (d !== 0) return d < 0 ? -1 : 1;
    } else {
      var s = String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: "base" });
      if (s !== 0) return s < 0 ? -1 : 1;
    }
    return 0;
  }

  function sortView() {
    var v = state.rows.slice();           // default order preserved (row order in JSON)
    if (state.sortKey && state.dir) {
      var dir = state.dir;
      v.sort(function (a, b) {
        var r = compare(a, b);
        return r === 0 ? 0 : (dir === 1 ? r : -r);
      });
    }
    state.view = v;
  }

  /* ------------------------------------------------------------- filtering */

  function inGroup(row, g) {
    if (!g || g === "all") return true;
    if (g === "multi") return hasSpeed(row);
    if (g === "thinking") return !!row.thinking;
    if (g === "games") return !!(row.games && row.games.length) || !!row.game;
    return true;
  }

  function matches(row, q, arch, onlyVid) {
    if (onlyVid && !Object.keys(row.videos || {}).length) return false;
    if (arch && (row.arch || "") !== arch) return false;
    if (!inGroup(row, state.group)) return false;
    if (!q) return true;
    var hay = [row.name, row.slug, row.quant, row.arch, row.params_total,
               row.params_active, row.ctx_label].join(" ").toLowerCase();
    return q.toLowerCase().split(/\s+/).filter(Boolean).every(function (t) {
      return hay.indexOf(t) !== -1;
    });
  }

  /* ------------------------------------------------------------ rendering */

  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtNum(v, digits) {
    if (v === null || v === undefined) return '<span class="dash">—</span>';
    var o = { minimumFractionDigits: 0, maximumFractionDigits: digits };
    return Number(v).toLocaleString(undefined, o);
  }

  function fmtPct(v) {
    if (v === null || v === undefined) return '<span class="dash">—</span>';
    return '<span class="' + (v >= 70 ? "score-hi" : "") + '">' +
      Number(v).toFixed(1) + "</span>";
  }

  function fmtCtx(v) {
    if (v === null || v === undefined) return '<span class="dash">—</span>';
    if (v >= 1024 * 1024) return Math.round(v / (1024 * 1024)) + "M";
    return v >= 1024 ? Math.round(v / 1024) + "k" : String(v);
  }

  /** "2026-11-02T20:44:16+0800" -> "2026-11-02" (source dates are ISO-ish, but not always Z) */
  function coarseDate(v) {
    var m = String(v || "").match(/^\d{4}-\d{2}-\d{2}/);
    return m ? m[0] : String(v || "");
  }

  function shortNum(v) {
    if (v === null || v === undefined) return "";
    return v >= 10000 ? Math.round(v / 1000) + "K" : v.toLocaleString();
  }

  /* ---- per-cell video links: the video belongs on the score it proves ---- */
  var CELL_VIDEO = {
    gpqa: [/pub-gpqa25/, /gpqa25/],
    aime: [/pub-aime10x3/, /aime/],
    livebench: [/pub-livebench25/, /livebench/],
    ctx30k: [/ctx-gpqa30k/, /ctx30k/],
    ctx110k: [/ctx-gpqa110k/, /ctx110k/],
    tau2: [/tau2/],
    shell: [/shell10/, /shell/],
    termbench: [/termbench/]
  };

  function videoFor(key, vids) {
    var pats = CELL_VIDEO[key];
    if (!pats || !vids) return null;
    for (var k in vids) {
      for (var i = 0; i < pats.length; i++) if (pats[i].test(k)) return vids[k];
    }
    return null;
  }

  function scoreCell(r, key, v) {
    var t = fmtPct(num(v));
    var u = videoFor(key, r.videos);
    if (!u || num(v) === null) return t;
    return '<a class="cellvid" href="' + esc(u) + '" target="_blank" rel="noopener" title="watch this cell">' +
      t + '<span class="play">&#9654;</span></a>';
  }

  function featBadges(r) {
    var f = r.features || {}, out = [];
    if (f.fa) out.push('<span class="tag tag-fa" title="flash attention">FA</span>');
    if (f.mtp) out.push('<span class="tag tag-mtp" title="multi-token prediction (speculative)">MTP</span>');
    if (f.dflash) out.push('<span class="tag tag-dflash" title="DFlash speculative decoding">DFlash</span>');
    if (f.dflash2) out.push('<span class="tag tag-dflash" title="DFlash2 speculative decoding">DFlash2</span>');
    if (f.mxfp4) out.push('<span class="tag tag-quant" title="MXFP4 quantised weights">MXFP4</span>');
    return out.length ? ' ' + out.join('') : '';
  }

  /* ---- the speed block of a row: one line per server context ---- */
  function speedCells(r) {
    var s = speed(r);
    if (!s) {
      return '<td class="num" data-label="Server ctx"><span class="dash">—</span></td>' +
        '<td class="num c-std" data-label="Prefill t/s at 30K"><span class="dash">—</span></td>' +
        '<td class="num c-std" data-label="Decode t/s at 30K"><span class="dash">—</span></td>' +
        '<td class="num" data-label="Prefill t/s at depth"><span class="dash">—</span></td>' +
        '<td class="num" data-label="Decode t/s at depth"><span class="dash">—</span></td>';
    }
    var std = s.standard || {};
    var d = deepest(r);
    var ctx = r.ctx_label || fmtCtx(num(r.context_window));
    var stdP = std.pending
      ? '<span class="pending" title="not probed yet at this server context">pending</span>'
      : fmtNum(num(std.prefill_tps), 0);
    var stdD = std.pending
      ? '<span class="pending" title="not probed yet at this server context">pending</span>'
      : fmtNum(num(std.decode_tps), 2);
    var deepP = d ? fmtNum(num(d.prefill_tps), 0) + '<span class="dep">@' + shortNum(d.tokens) + "</span>"
      : '<span class="dash">—</span>';
    var deepD = d ? fmtNum(num(d.decode_tps), 2) + '<span class="dep">@' + shortNum(d.tokens) + "</span>"
      : '<span class="dash">—</span>';
    return '<td class="num c-ctx" data-label="Server ctx">' + esc(ctx || "—") + "</td>" +
      '<td class="num c-std" data-label="Prefill t/s at 30K">' + stdP + "</td>" +
      '<td class="num c-std" data-label="Decode t/s at 30K">' + stdD + "</td>" +
      '<td class="num" data-label="Prefill t/s at depth">' + deepP + "</td>" +
      '<td class="num" data-label="Decode t/s at depth">' + deepD + "</td>";
  }

  function metaLine(r) {
    var bits = [];
    if (r.params_total) bits.push(r.params_total + (r.params_active && r.params_active !== r.params_total ? "/" + r.params_active + " active" : ""));
    if (r.quant) bits.push(r.quant);
    if (r.vram_mib) bits.push((r.vram_mib / 1024).toFixed(1) + " GiB VRAM");
    if (r.date) bits.push(r.date);
    return bits.join(" · ");
  }

  function rowHTML(r, rank) {
    var c = r.cells || {};
    var cls = rank ? "rank rank-" + rank : "";
    var badge = rank ? '<span class="rank-badge">' + rank + "</span>" : "";
    var pAct = r.params_active && r.params_active !== r.params_total
      ? ' <span class="act">/ ' + esc(r.params_active) + "</span>" : "";
    var sp = speed(r);
    var prev = r._prevRow;                  // set in paint(): the row above in default order
    var firstOfModel = !prev || prev.name !== r.name;
    var nameCell = firstOfModel
      ? esc(r.name) + featBadges(r)
      : '<span class="same-model">&#8635;</span>' + esc(r.name) + ' <span class="dim">(' + esc(r.ctx_label || "") + ')</span>';
    var deepNote = "";                    // the per-context probe table below carries the rungs
    if (r.status === "failed") cls = (cls ? cls + " " : "") + "row-failed";
    return '<tr class="' + cls + '">' +
      '<td class="c-name">' + (firstOfModel ? badge : "") + nameCell +
        (r.status === "failed" ? ' <span class="st st-failed" title="the run did not produce a measurement">failed</span>' : "") +
        '<span class="slug">' + esc(r.filename || r.slug) + "</span>" +
        '<span class="meta">' + esc(metaLine(r)) + "</span>" +
        (deepNote ? deepNote : "") + "</td>" +
      '<td class="num c-params" data-label="Params">' + esc(r.params_total || "—") + pAct + "</td>" +
      '<td class="c-quant" data-label="Quant"><span class="pill">' + esc(r.quant || "—") + "</span></td>" +
      '<td class="c-arch" data-label="Arch">' + esc(r.arch || "—") + "</td>" +
      speedCells(r) +
      '<td class="num" data-label="GPQA">' + scoreCell(r, "gpqa", c.gpqa) + "</td>" +
      '<td class="num" data-label="AIME">' + scoreCell(r, "aime", c.aime) + "</td>" +
      '<td class="num" data-label="LiveBench">' + scoreCell(r, "livebench", c.livebench) + "</td>" +
      '<td class="num" data-label="ctx30k">' + scoreCell(r, "ctx30k", c.ctx30k) + "</td>" +
      '<td class="num" data-label="ctx110k">' + scoreCell(r, "ctx110k", c.ctx110k) + "</td>" +
      '<td class="num" data-label="tau2">' + scoreCell(r, "tau2", c.tau2) + "</td>" +
      '<td class="num" data-label="Shell">' + scoreCell(r, "shell", c.shell) + "</td>" +
      '<td class="num" data-label="TermBench">' + scoreCell(r, "termbench", c.termbench) + "</td>" +
      '<td class="num" data-label="Decode t/s">' + fmtNum(num(r.decode_tps), 1) + "</td>" +
      '<td class="num" data-label="Prefill t/s">' + fmtNum(num(r.prefill_tps), 0) + "</td>" +
      '<td class="num" data-label="Ctx">' + fmtCtx(num(r.context_window)) + "</td>" +
      '<td class="num" data-label="VRAM">' +
        (num(r.vram_mib) !== null ? (r.vram_mib / 1024).toFixed(1) : '<span class="dash">—</span>') + "</td>" +
      '<td class="num c-date" data-label="Date">' + esc(r.date || "—") + "</td>" +
      evidenceCell(r) +
    "</tr>";
  }

  /* ---- last column: can this row be trusted, and can it be re-run here? ---- */
  function evidenceCell(r) {
    if (r.speed) {
      var st = (r.speed.standard || {});
      var meta = [];
      if (r.kv_cache) meta.push("KV " + esc(r.kv_cache));
      if (r.engine_build) meta.push(esc(r.engine_build));
      if (r.speed_measured_at) meta.push(coarseDate(r.speed_measured_at));
      return '<td class="ev c-evidence" data-label="Speed evidence">' +
        '<span class="probe-tag">live probe · ' + (st.tokens || 0).toLocaleString() + " tok" +
        (st.pending ? " · pending" : "") + "</span>" +
        (r.speed_flags ? '<code>' + esc(r.speed_flags) + "</code>" : "") +
        (meta.length ? '<span class="ev-meta">' + meta.join(" · ") + "</span>" : "") +
        "</td>";
    }
    if (r.measurement_status) {
      var failed = /^failed/.test(r.measurement_status);
      return '<td class="ev c-evidence" data-label="Speed evidence">' +
        '<span class="' + (failed ? "st st-failed" : "st st-hist") + '">' +
        esc(r.measurement_status) + "</span>" +
        (r.engine_build ? '<span class="ev-meta">' + esc(r.engine_build) + "</span>" : "") +
        "</td>";
    }
    var bits = [];
    if (r.speed_flags) bits.push('<code>' + esc(r.speed_flags) + "</code>");
    var meta = [];
    if (r.kv_cache) meta.push("KV " + esc(r.kv_cache));
    if (r.engine_build) meta.push(esc(r.engine_build));
    if (r.speed_measured_at) meta.push(coarseDate(r.speed_measured_at));
    return '<td class="ev c-evidence" data-label="Speed evidence">' +
      (bits.join(" ") || '<span class="dash">—</span>') +
      (meta.length ? '<span class="ev-meta">' + meta.join(" · ") + "</span>" : "") +
      "</td>";
  }

  /* ---- top-3 highlight: follows the active numeric sort, else Decode t/s ---- */
  var DEFAULT_RANK_KEY = "decode_tps";

  function rankKey() {
    var k = state.sortKey;
    if (k && COL[k] && (COL[k].type === "num" || COL[k].type === "params")) return k;
    return DEFAULT_RANK_KEY;
  }

  function topRanks(order) {
    var key = rankKey(), vals = [];
    order.forEach(function (r) {
      var v = value(r, key);
      if (v !== null && isFinite(v)) vals.push({ r: r, v: v });
    });
    vals.sort(function (a, b) { return b.v - a.v; });
    return vals.slice(0, 3).map(function (o, i) { return [o.r, i + 1]; });
  }

  function paint() {
    var q = document.getElementById("q").value.trim();
    var arch = document.getElementById("arch").value;
    var onlyVid = document.getElementById("vid").checked;
    var shown = state.rows.filter(function (r) { return matches(r, q, arch, onlyVid); });
    sortView();
    var order = state.view.filter(function (r) { return shown.indexOf(r) !== -1; });
    var ranks = topRanks(order);

    state.rows.forEach(function (r, i) { r._prevRow = i ? state.rows[i - 1] : null; });
    document.getElementById("rows").innerHTML = order.map(function (r) {
      var rank = 0;
      for (var i = 0; i < ranks.length; i++) { if (ranks[i][0] === r) { rank = ranks[i][1]; break; } }
      return rowHTML(r, rank);
    }).join("");
    var rk = rankKey();
    var note = document.getElementById("ranknote");
    if (note) {
      note.textContent = "Top 3 by " + (LABELS[rk] || rk) +
        (state.sortKey && state.sortKey !== rk ? " (sorted column is not numeric)" : "");
    }
    document.getElementById("empty").hidden = order.length > 0;
    document.getElementById("count").textContent =
      order.length + " / " + state.rows.length + " models";

    Array.prototype.forEach.call(document.querySelectorAll("thead th"), function (th) {
      if (th.dataset.key === state.sortKey && state.dir) {
        th.dataset.dir = state.dir === 1 ? "asc" : "desc";
        th.setAttribute("aria-sort", state.dir === 1 ? "ascending" : "descending");
      } else {
        delete th.dataset.dir;
        th.removeAttribute("aria-sort");
      }
    });
  }

  /* ---------------------------------------------------------------- events */

  function onHeaderClick(key) {
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

  function wire() {
    var ths = document.querySelectorAll("thead th");
    Array.prototype.forEach.call(ths, function (th, i) {
      th.tabIndex = 0;
      th.setAttribute("role", "columnheader");
      th.addEventListener("click", function () { onHeaderClick(th.dataset.key); });
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onHeaderClick(th.dataset.key);
        } else if (e.key === "ArrowRight" && ths[i + 1]) ths[i + 1].focus();
        else if (e.key === "ArrowLeft" && ths[i - 1]) ths[i - 1].focus();
      });
    });
    document.getElementById("q").addEventListener("input", paint);
    document.getElementById("arch").addEventListener("change", paint);
    document.getElementById("vid").addEventListener("change", paint);
    var grp = document.getElementById("grp");
    if (grp) grp.addEventListener("change", function () { state.group = grp.value; paint(); });
    document.getElementById("reset").addEventListener("click", function () {
      document.getElementById("q").value = "";
      document.getElementById("arch").value = "";
      document.getElementById("vid").checked = false;
      if (grp) grp.value = "all";
      state.group = "all";
      paint();
    });
  }

  function fillArchSelects(rows) {
    var sel = document.getElementById("arch");
    var seen = {};
    rows.forEach(function (r) { if (r.arch) seen[r.arch] = (seen[r.arch] || 0) + 1; });
    var keys = Object.keys(seen).sort(function (a, b) { return a.localeCompare(b); });
    keys.forEach(function (k) {
      var o = document.createElement("option");
      o.value = k;
      o.textContent = (k.length > 46 ? k.slice(0, 45) + "…" : k) + " (" + seen[k] + ")";
      sel.appendChild(o);
    });
  }

  /* ----------------------------------------------------------------- boot */

  /* ---- error bars: how much a single number can move between identical runs ---- */
  function pct(v, d) {
    return v === null || v === undefined ? "—" : Number(v).toFixed(d === undefined ? 2 : d) + "%";
  }

  function errorBars(eb) {
    var host = document.getElementById("errbars");
    if (!host) return;
    if (!eb) { host.hidden = true; return; }
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
        : fmtNum(dec.mean, 2) + (dec.n > 1
          ? ' <span class="spread">' + pct(dec.spread_pct) + " spread</span>"
          : ' <span class="spread">' + esc(dec.n === 1 ? "1 rep" : "n/a") + "</span>");
      return "<tr><td>" + esc(r[0]) + "</td>" +
        '<td class="num">' + fmtNum(k.prefill.mean, 1) + ' <span class="spread">' + pct(k.prefill.spread_pct) + "</span></td>" +
        '<td class="num">' + decTxt + "</td>" +
        '<td class="num">' + fmtNum(k.wall_s.mean, 2) + ' <span class="spread">' + pct(k.wall_s.spread_pct) + "</span></td>" +
        '<td class="num">' + (k.n || "") + "</td></tr>";
    }).join("");
    host.innerHTML = '<h2>Error bars — how far one identical run moves</h2>' +
      '<p class="probe-note">' + esc(eb.policy) + " Every measured spread in the campaign was under 5% " +
      "(largest " + pct(eb.max_spread_pct) + "), so the single-run numbers elsewhere on this page are " +
      "trustworthy at that level. Prefill/decode are the server's own rates; spread is (max−min)/mean.</p>" +
      '<div class="table-wrap"><table class="probe"><thead><tr><th>Point</th>' +
      "<th>Prefill t/s (spread)</th><th>Decode t/s (spread)</th><th>Wall s (spread)</th><th>Reps</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      '<p class="probe-note sm">Qwen3.8-27B decode is one valid <code>/completion ignore_eos</code> run at ' +
      "28.61 t/s (400 generated tokens); its chat-probe figure (25.9 at 2 tokens) is an end-of-answer " +
      "stop, i.e. noise, and is not a decode measurement — so no decode spread is quoted for it.</p>" +
      '<p class="probe-note sm">Accuracy cells stop at ctx110k; speed reaches 262k (the A3B rows). ' +
      "A missing accuracy cell above 110k means not measured, not not-run.</p>";
    host.hidden = false;
  }

  /* ---- "how each number was measured": one compact table per model that has them ---- */
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
      var rs = groups[n];
      var body = "";
      rs.forEach(function (r) {
        var std = r.speed.standard || {};
        var rungs = r.speed.deep && r.speed.deep.length ? r.speed.deep : [];
        var depth = rungs.length ? rungs.map(function (d) {
          return '<span class="rung">' + Math.round(d.tokens).toLocaleString() + ' tok: ' +
            fmtNum(num(d.prefill_tps), 1) + " prefill / " + fmtNum(num(d.decode_tps), 2) + " decode</span>";
        }).join("") : '<span class="dash">none — 30K standard prompt only</span>';
        body += '<tr><td class="num">' + esc(r.ctx_label || fmtCtx(num(r.context_window))) + "</td>" +
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
      'the prompt cache off; prefill and decode are the server\'s own <code>prompt_per_second</code> and ' +
      '<code>predicted_per_second</code>. No speculative decoding. VRAM is the GPU\'s used-memory peak ' +
      'during the run. A <span class="pending">pending</span> cell is a probe that has not been run at ' +
      'that server context yet — it is never estimated.</p>' + html;
    host.hidden = false;
  }

  function boot(doc) {
    state.rows = rowsOf(doc).filter(function (r) { return r && r.name; });
    if (doc && doc.generated) {
      document.getElementById("gen").textContent = "data generated " + doc.generated;
    }
    var sortable = document.getElementById("tbl");
    if (sortable) sortable.dataset.ready = "1";
    fillArchSelects(state.rows);
    probesTable(state.rows);
    errorBars(doc && doc.error_bars);
    wire();
    paint();
  }

  function fail(msg) {
    var box = document.getElementById("empty");
    box.hidden = false;
    box.textContent = "Could not load data/results.json (" + msg + ").";
  }

  if (window.LLMBENCH_DATA) { boot(window.LLMBENCH_DATA); return; }

  // file:// blocks fetch in Chrome; fall back to a plain <script> load of data/results.js
  if (location.protocol === "file:") {
    var s = document.createElement("script");
    s.src = "data/results.js";
    s.onload = function () {
      if (window.LLMBENCH_DATA) boot(window.LLMBENCH_DATA); else fail("no data");
    };
    s.onerror = function () { fail("file:// fallback missing; run a local server"); };
    document.head.appendChild(s);
    return;
  }

  fetch("data/results.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(boot)
    .catch(function (e) { fail(e.message); });
})();
