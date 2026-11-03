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

  var state = { sortKey: null, dir: 0, rows: [], view: [], group: "all", spdOnly: true };

  /* ------------------------------------------------------------------ data */

  function num(v) {                       // finite number or null
    return (typeof v === "number" && isFinite(v)) ? v : null;
  }

  var CELL_KEYS = { gpqa: 1, aime: 1, livebench: 1, ctx30k: 1, ctx110k: 1, tau2: 1,
                    shell: 1, termbench: 1 };

  function hasSpeed(r) { return !!(r && r.speed); }

  /** ctx_label may be plain ("32K") or markup ("256K<span class=\"native\">n</span>"):
      give consumers the plain text; speedCells reads the span through ctxMarkup(). */
  function ctxText(r) {
    if (!r || !r.ctx_label) return "";
    return String(r.ctx_label).replace(/<[^>]*>/g, "");
  }
  function ctxMarkup(r) {
    if (r && r.ctx_label && /<[^>]+>/.test(String(r.ctx_label))) return r.ctx_label;
    return '<span class="th-sub">' + esc(ctxText(r)) + "</span>";
  }


  function speed(row) { return row.speed || null; }

  /* Rows without a `speed` block carry one probe at the row's own server context in the
     top-level prefill_tps / decode_tps fields. That is one cold request at whatever token
     count the server saw — NOT the standardised 30K probe — so it renders in the "native
     ctx" column pair marked with a superscript, and never inside the 30K cells. */
  function nativeProbe(row) {
    var p = num(row.prefill_tps), d = num(row.decode_tps);
    if (p === null && d === null) return null;
    return { prefill_tps: p, decode_tps: d };
  }

  var NATIVE_TIP = 'a single probe at this row&#39;s own server context (\u00b7n) \u2014 ' +
    'not the standardised 30K probe';
  var NATIVE_MARK = '<sup class="nat" title="' + NATIVE_TIP + '">&#8226;n</sup>';

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
    if (key === "deep_prefill") { var n = nativeProbe(row); return n ? n.prefill_tps : null; }
    if (key === "deep_decode")  { var n2 = nativeProbe(row); return n2 ? n2.decode_tps : null; }
    if (key === "ctx_label") return ctxText(row) || (row.context_window ? fmtCtx(num(row.context_window)) : null);
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

  /* a row "has speed" when it carries a speed block or a native ctx prefill/decode probe */
  function hasSpeedData(r) { return !!nativeProbe(r) || !!(r.speed && r.speed.standard); }

  function matches(row, q, arch, onlyVid) {
    if (state.spdOnly && !hasSpeedData(row)) return false;
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
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;")
      .replace(/\n/g, " ");
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

  /** same date, year dropped: "2026-10-30" -> "10-30" (keeps the evidence cell on one line) */
  function shortDate(v) {
    var m = String(v || "").match(/^\d{4}-(\d{2}-\d{2})/);
    return m ? m[1] : coarseDate(v);
  }

  function shortNum(v) {
    if (v === null || v === undefined) return "";
    return v >= 10000 ? Math.round(v / 1000).toLocaleString() + "K" : v.toLocaleString();
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

  /* ---- the speed block of a row: one line per server context ----
     Column pair A (c-std) is the standardised 30K probe. It is only measured on the
     dedicated per-context server rows (the A3B 32K / 256K rows), so every other row
     leaves it blank rather than filling it with a look-alike number.
     Column pair B (c-nat) is the row's own measurement: the deepest depth probe for
     server rows, and for llama-bench rows the single native-context probe, marked n —
     the value itself is printed once, in group C.                                   */
  function speedCells(r) {
    var s = speed(r);
    var ctx = ctxText(r) || fmtCtx(num(r.context_window));
    var ctxCell = '<td class="num c-ctx" data-label="Server ctx">' + (ctx ? ctxMarkup(r) : "—") + "</td>";
    if (!s) {
      var n = nativeProbe(r);
      var mark = n ? '<span class="natbox" title="' + NATIVE_TIP + '">' + NATIVE_MARK + "</span>"
        : '<span class="dash">—</span>';
      return ctxCell +
        '<td class="num c-std" data-label="Prefill t/s @ 30K"><span class="dash">—</span></td>' +
        '<td class="num c-std" data-label="Decode t/s @ 30K"><span class="dash">—</span></td>' +
        '<td class="num c-nat" data-label="Prefill · decode t/s @ native ctx">' + mark + "</td>";
    }
    var std = s.standard || {};
    var stdP = std.pending
      ? '<span class="pending" title="not probed yet at this server context">pending</span>'
      : fmtNum(num(std.prefill_tps), 1);
    var stdD = std.pending
      ? '<span class="pending" title="not probed yet at this server context">pending</span>'
      : fmtNum(num(std.decode_tps), 2);
    var d = deepest(r);
    var bCell;
    if (d) {
      var tok = shortNum(d.tokens);
      var dip = ' title="deepest probe: ' + esc(tok) + ' prompt tokens"';
      bCell = '<span class="pair"' + dip + ">" + fmtNum(num(d.prefill_tps), 1) + "/" +
        fmtNum(num(d.decode_tps), 2) + "</span>";
    } else {
      bCell = '<span class="dash">—</span>';
    }
    return ctxCell +
      '<td class="num c-std" data-label="Prefill t/s @ 30K">' + stdP + "</td>" +
      '<td class="num c-std" data-label="Decode t/s @ 30K">' + stdD + "</td>" +
      '<td class="num c-nat" data-label="Prefill · decode t/s @ depth">' + bCell + "</td>";
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
    var firstOfModel = !r._repeat;          // _repeat is set in paint() from the default order
    var ctxLabel = ctxText(r) || (r.slug && r.slug !== r.name ? r.slug : "");
    var nameCell = firstOfModel
      ? '<span class="name">' + esc(r.name) + "</span>" + featBadges(r)
      : '<span class="name dim">' + esc(r.name) + "</span> " +
        '<span class="again">' + (ctxLabel ? esc(ctxLabel) : "&mdash;") + "</span>";
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
      '<td class="num sc" data-label="GPQA">' + scoreCell(r, "gpqa", c.gpqa) + "</td>" +
      '<td class="num sc" data-label="AIME">' + scoreCell(r, "aime", c.aime) + "</td>" +
      '<td class="num sc" data-label="LiveBench">' + scoreCell(r, "livebench", c.livebench) + "</td>" +
      '<td class="num sc" data-label="ctx30k">' + scoreCell(r, "ctx30k", c.ctx30k) + "</td>" +
      '<td class="num sc" data-label="ctx110k">' + scoreCell(r, "ctx110k", c.ctx110k) + "</td>" +
      '<td class="num sc" data-label="tau2">' + scoreCell(r, "tau2", c.tau2) + "</td>" +
      '<td class="num sc" data-label="Shell">' + scoreCell(r, "shell", c.shell) + "</td>" +
      '<td class="num sc" data-label="TermBench">' + scoreCell(r, "termbench", c.termbench) + "</td>" +
      '<td class="num sv" data-label="Decode t/s (llama-bench)">' +
        (num(r.decode_tps) !== null ? fmtNum(num(r.decode_tps), 1) + NATIVE_MARK : '<span class="dash">—</span>') + "</td>" +
      '<td class="num sv" data-label="Prefill t/s (llama-bench)">' +
        (num(r.prefill_tps) !== null ? fmtNum(num(r.prefill_tps), 1) + NATIVE_MARK : '<span class="dash">—</span>') + "</td>" +
      '<td class="num sv" data-label="Ctx">' + fmtCtx(num(r.context_window)) + "</td>" +
      '<td class="num sv" data-label="VRAM">' +
        (num(r.vram_mib) !== null ? (r.vram_mib / 1024).toFixed(1) : '<span class="dash">—</span>') + "</td>" +
      '<td class="num c-date" data-label="Date">' + esc(r.date || "—") + "</td>" +
      evidenceCell(r) +
    "</tr>";
  }

  /* ---- last column: compact one-line provenance ----
     "b11517 · 10-30" plus, when the weights are gone, a small amber "·s" badge whose
     tooltip carries a generic restatement of measurement_status (the raw text can name the
     measurement host). Nothing here may wrap the row except on the mobile card. */
  function evidenceCell(r) {
    var build = r.engine_build ? esc(r.engine_build) : "";
    /* the row already has its own Date column: only repeat the date here when it differs
       (speed measured on a different day than the accuracy run) */
    var when = r.speed_measured_at && coarseDate(r.speed_measured_at) !== String(r.date || "")
      ? shortDate(r.speed_measured_at) : "";
    var whenFull = r.speed_measured_at ? coarseDate(r.speed_measured_at) : "";
    var buildShort = build ? esc(String(r.engine_build || "").split(/[-+]/)[0]) : build;
    var prov = '<span class="prov" title="build ' + esc(r.engine_build || "-") +
      (whenFull ? ", measured " + esc(whenFull) : "") + '">' +
      [buildShort, when].filter(Boolean).join(" · ") + "</span>";
    var badge = "";
    if (r.speed) {
      var st = r.speed.standard || {};
      var tag = '<span class="probe-tag" title="standardised 30K probe: cold request">30K' +
        (st.pending ? " · pending" : "") + "</span>";
      var flags = r.speed_flags ? '<code class="ev-flags" title="' + esc(r.speed_flags) + '">' +
        esc(r.speed_flags) + "</code>" : "";
      /* long build ids (b11517-8a1a9b512) leave no room for the 30K chip: drop it there and
         carry the same fact in the build tooltip instead */
      var tight = (r.engine_build || "").length > 12;
      var tip = tight ? ' title="standardised 30K probe, cold request; built ' + esc(r.engine_build) + '"' : "";
      return '<td class="ev c-evidence" data-label="Speed evidence"' + tip + ">" +
        (tight ? "" : tag) + badge + prov + flags + "</td>";
    }
    if (build || when || badge) {
      return '<td class="ev c-evidence" data-label="Speed evidence">' + badge + prov + "</td>";
    }
    return '<td class="ev c-evidence" data-label="Speed evidence"><span class="dash">—</span></td>';
  }

  /* ---- top-3 highlight: follows the active numeric sort, else Decode t/s ---- */
  var DEFAULT_RANK_KEY = "decode_tps";

  function rankKey() {
    var k = state.sortKey;
    if (k && COL[k] && (COL[k].type === "num" || COL[k].type === "params")) return k;
    return DEFAULT_RANK_KEY;
  }

  function topRanks(order) {
    var key = rankKey(), vals = [], _seen = {};
    order.forEach(function (r) {
      /* rank models, not probes: a second context row must not take a second podium slot */
      var _mk = String(r.slug || r.name || "").replace(/-ctx\d+k$/i, "");
      if (_seen[_mk]) return;
      _seen[_mk] = 1;
      var v = value(r, key);
      if (v !== null && isFinite(v)) vals.push({ r: r, v: v });
    });
    vals.sort(function (a, b) { return b.v - a.v; });
    return vals.slice(0, 3).map(function (o, i) { return [o.r, i + 1]; });
  }

  /* ---- keep the fixed-layout table inside its scroll box ------------------
     Column widths are set in CSS; a header or a cell that wants more can still
     widen its column, which pushed the table past the viewport. Once the real
     widths settle, write them back as explicit px (shrunk, never grown) so the
     table always totals <= the available width. The wrap keeps scrolling on
     narrow screens; nothing is clipped mid-word on desktop. */
  /* score columns (accuracy %) all carry the same shape of number, and the table shows
     two extra columns (llama-bench prefill/decode) that repeat values already in group C;
     those are hidden on the phone card view only. Widths are budgeted, not guessed. */
  var SCORE_KEYS = { gpqa: 1, aime: 1, livebench: 1, ctx30k: 1, ctx110k: 1, tau2: 1, shell: 1, termbench: 1 };
  var SCORE_W = 46;                        /* "100.0" + play glyph + padding */

  function fitColumns(dry) {
    var tbl = document.getElementById("tbl");
    if (!tbl) return;
    var ths = tbl.querySelectorAll("thead th");
    if (!ths.length) return;
    if (window.matchMedia && window.matchMedia("(max-width: 760px)").matches) {
      tbl.style.width = "";                 /* phone cards are not a table */
      return;
    }
    var wrap = tbl.parentElement;
    var avail = wrap.clientWidth;
    if (!avail) return;
    if (tbl.style.width !== avail + "px") tbl.style.width = avail + "px";

    /* budget: every score column gets its label width, the text-ish columns split the rest
       in proportion to the CSS hint, number columns keep at least their longest value */
    var HINT = {};
    ["name", "params", "quant", "arch", "ctx_label", "std_prefill", "std_decode",
     "deep_prefill", "decode_tps", "prefill_tps", "context_window", "vram_mib",
     "date", "speed_evidence"].forEach(function (k) { HINT[k] = 1; });
    var plan = {}, fixed = 0, hintSum = 0, i, keys = [];
    for (i = 0; i < ths.length; i++) {
      var key = ths[i].dataset.key;
      keys.push(key);
      if (SCORE_KEYS[key]) { plan[key] = SCORE_W; fixed += plan[key]; }
      else if (hiddenCol(key)) { plan[key] = 0; }
      else hintSum += (SIZE_HINT[key] || 1);
    }
    /* spare may go negative on a narrow desktop viewport: every column keeps its hint-proportional
       share and the table's own min-width makes the wrap scroll instead */
    var spare = avail - 1 - fixed;
    for (i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (plan[k] !== undefined) continue;
      plan[k] = spare * (SIZE_HINT[k] || 1) / hintSum;
    }
    if (!dry) {
      for (i = 0; i < ths.length; i++) ths[i].style.width = Math.max(plan[keys[i]], 0).toFixed(2) + "px";
    }
    return true;
  }

  /* relative room each non-score column gets, before it is scaled to fit the viewport */
  var SIZE_HINT = {
    name: 15, params: 6.4, quant: 5.6, arch: 10, ctx_label: 5,
    std_prefill: 9.2, std_decode: 9.2, deep_prefill: 9.2,
    decode_tps: 6.2, prefill_tps: 6.2, context_window: 4, vram_mib: 4,
    date: 8.4, speed_evidence: 10.4
  };
  function hiddenCol(key) { return key === "deep_decode"; }

  /* re-fit after layout settles (fonts, sticky headers) and on resize */
  var fitTimers = [];
  function scheduleFit() {
    fitTimers.forEach(clearTimeout);
    fitTimers = [];
    [0, 120, 400, 1200].forEach(function (ms) {
      fitTimers.push(setTimeout(function () { fitColumns(false); }, ms));
    });
  }

  function paint() {
    var q = document.getElementById("q").value.trim();
    var arch = document.getElementById("arch").value;
    var onlyVid = document.getElementById("vid").checked;
    var shown = state.rows.filter(function (r) { return matches(r, q, arch, onlyVid); });
    sortView();
    var order = state.view.filter(function (r) { return shown.indexOf(r) !== -1; });
    var ranks = topRanks(order);

    /* A model measured at several server contexts (…-ctx32k / …-ctx256k) is ONE model with
       several probes, not several models. Key on the model, not on the neighbouring row —
       otherwise sorting separates the variants and each renders as its own model. */
    function modelKey(r) { return String(r.slug || r.name || "").replace(/-ctx\d+k$/i, ""); }
    state.rows.forEach(function (r) { r._repeat = false; });
    var _seenKey = {};
    order.forEach(function (r) {
      var k = modelKey(r);
      if (_seenKey[k]) { r._repeat = true; } else { _seenKey[k] = true; }
    });
    /* cluster the variants directly under their model so the grouping is visible */
    var _groups = {}, _keyOrder = [];
    order.forEach(function (r) {
      var k = modelKey(r);
      if (!_groups[k]) { _groups[k] = []; _keyOrder.push(k); }
      _groups[k].push(r);
    });
    order = _keyOrder.reduce(function (acc, k) { return acc.concat(_groups[k]); }, []);
    document.getElementById("rows").innerHTML = order.map(function (r) {
      var rank = 0;
      for (var i = 0; i < ranks.length; i++) { if (ranks[i][0] === r) { rank = ranks[i][1]; break; } }
      return rowHTML(r, rank);
    }).join("");
    fitColumns(false);
    var rk = rankKey();
    var note = document.getElementById("ranknote");
    if (note) {
      note.textContent = "Top 3 by " + (LABELS[rk] || rk) +
        (state.sortKey && state.sortKey !== rk ? " (sorted column is not numeric)" : "");
    }
    document.getElementById("empty").hidden = order.length > 0;
    var lg = document.getElementById("speedkey");
    if (lg) lg.hidden = false;
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
    var spd = document.getElementById("spdonly");
    if (spd) spd.addEventListener("change", function () { state.spdOnly = spd.checked; paint(); });
    var grp = document.getElementById("grp");
    if (grp) grp.addEventListener("change", function () { state.group = grp.value; paint(); });
    document.getElementById("reset").addEventListener("click", function () {
      document.getElementById("q").value = "";
      document.getElementById("arch").value = "";
      document.getElementById("vid").checked = false;
      var spd = document.getElementById("spdonly");
      if (spd) { spd.checked = true; state.spdOnly = true; }
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
        body += '<tr><td class="num">' + esc(ctxText(r) || fmtCtx(num(r.context_window))) + "</td>" +
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

  window.addEventListener("resize", scheduleFit);

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
    scheduleFit();
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
