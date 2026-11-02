/* llmbench — sortable, filterable table over data/results.json.
   No framework, no build step, no external requests.

   Sorting model (spec):
     click 1 header -> ascending on that column
     click 2 header -> descending on that column
     click 3 header -> sort cleared, rows return to their default (filename) order
   Numeric columns compare as numbers (never lexically); blanks always sort last,
   in both directions. The active header carries data-dir + a ▲/▼ arrow. */
(function () {
  "use strict";

  var COLUMNS = [
    { key: "name",           type: "text"   },
    { key: "params",         type: "params" },
    { key: "quant",          type: "text"   },
    { key: "arch",           type: "text"   },
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
    { key: "videos",         type: "num"    }
  ];
  var COL = {};
  COLUMNS.forEach(function (c) { COL[c.key] = c; });

  var LABELS = {
    gpqa: "GPQA", aime: "AIME", livebench: "LiveBench", ctx30k: "ctx30k",
    ctx110k: "ctx110k", tau2: "tau2", shell: "Shell", termbench: "TermBench",
    decode_tps: "Decode t/s", prefill_tps: "Prefill t/s",
    context_window: "Ctx (tokens)", vram_mib: "VRAM (GiB)", videos: "Videos",
    quant: "Quant", arch: "Arch", date: "Date"
  };

  var state = { sortKey: null, dir: 0, rows: [], view: [] };

  /* ------------------------------------------------------------------ data */

  function num(v) {                       // finite number or null
    return (typeof v === "number" && isFinite(v)) ? v : null;
  }

  var CELL_KEYS = { gpqa: 1, aime: 1, livebench: 1, ctx30k: 1, ctx110k: 1, tau2: 1,
                    shell: 1, termbench: 1 };

  function value(row, key) {
    if (CELL_KEYS[key]) return num((row.cells || {})[key]);
    if (key === "params") return paramsB(row.params_total);
    if (key === "videos") return Object.keys(row.videos || {}).length;
    if (key === "vram_mib") return num(row.vram_mib);
    if (key === "decode_tps" || key === "prefill_tps" || key === "context_window")
      return num(row[key]);
    if (key === "date") return row.date || null;
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

  function matches(row, q, arch, onlyVid) {
    if (onlyVid && !Object.keys(row.videos || {}).length) return false;
    if (arch && (row.arch || "") !== arch) return false;
    if (!q) return true;
    var hay = [row.name, row.slug, row.quant, row.arch, row.params_total,
               row.params_active].join(" ").toLowerCase();
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
    return v >= 1024 ? Math.round(v / 1024) + "k" : String(v);
  }

  function videosCell(row) {
    var vids = row.videos || {};
    var cells = Object.keys(vids);
    if (!cells.length) return '<span class="dash">—</span>';
    var links = cells.map(function (c) {
      return '<a href="' + esc(vids[c]) + '" target="_blank" rel="noopener noreferrer">' +
        esc(c) + "</a>";
    }).join("");
    if (cells.length === 1) {
      return '<a href="' + esc(vids[cells[0]]) + '" target="_blank" rel="noopener noreferrer">' +
        "watch</a>";
    }
    return '<details><summary>' + cells.length + "</summary>" +
      '<div class="vlist">' + links + "</div></details>";
  }

  function rowHTML(r, rank) {
    var c = r.cells || {};
    var cls = rank ? "rank rank-" + rank : "";
    var badge = rank ? '<span class="rank-badge">' + rank + "</span>" : "";
    var pAct = r.params_active && r.params_active !== r.params_total
      ? ' <span class="act">/ ' + esc(r.params_active) + "</span>" : "";
    var meta = [
      r.quant || "", r.params_total || "", r.decode_tps ? r.decode_tps + " t/s" : "",
      r.vram_mib ? Math.round(r.vram_mib / 1024) + " GiB" : "", r.date || ""
    ].filter(Boolean).join(" · ");
    return '<tr class="' + cls + '">' +
      '<td class="c-name">' + badge + esc(r.name) +
        '<span class="slug">' + esc(r.slug) + "</span>" +
        '<span class="meta">' + esc(meta) + "</span></td>" +
      '<td class="num c-params" data-label="Params">' + esc(r.params_total || "—") + pAct + "</td>" +
      '<td class="c-quant" data-label="Quant"><span class="pill">' + esc(r.quant || "—") + "</span></td>" +
      '<td class="c-arch" data-label="Arch">' + esc(r.arch || "—") + "</td>" +
      '<td class="num" data-label="GPQA">' + fmtPct(num(c.gpqa)) + "</td>" +
      '<td class="num" data-label="AIME">' + fmtPct(num(c.aime)) + "</td>" +
      '<td class="num" data-label="LiveBench">' + fmtPct(num(c.livebench)) + "</td>" +
      '<td class="num" data-label="ctx30k">' + fmtPct(num(c.ctx30k)) + "</td>" +
      '<td class="num" data-label="ctx110k">' + fmtPct(num(c.ctx110k)) + "</td>" +
      '<td class="num" data-label="tau2">' + fmtPct(num(c.tau2)) + "</td>" +
      '<td class="num" data-label="Shell">' + fmtPct(num(c.shell)) + "</td>" +
      '<td class="num" data-label="TermBench">' + fmtPct(num(c.termbench)) + "</td>" +
      '<td class="num" data-label="Decode t/s">' + fmtNum(num(r.decode_tps), 1) + "</td>" +
      '<td class="num" data-label="Prefill t/s">' + fmtNum(num(r.prefill_tps), 0) + "</td>" +
      '<td class="num" data-label="Ctx">' + fmtCtx(num(r.context_window)) + "</td>" +
      '<td class="num" data-label="VRAM">' +
        (num(r.vram_mib) !== null ? (r.vram_mib / 1024).toFixed(1) : '<span class="dash">—</span>') + "</td>" +
      '<td class="num c-date" data-label="Date">' + esc(r.date || "—") + "</td>" +
      '<td class="num c-videos" data-label="Videos">' + videosCell(r) + "</td>" +
    "</tr>";
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
    document.getElementById("reset").addEventListener("click", function () {
      document.getElementById("q").value = "";
      document.getElementById("arch").value = "";
      document.getElementById("vid").checked = false;
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

  function boot(doc) {
    state.rows = rowsOf(doc).filter(function (r) { return r && r.name; });
    if (doc && doc.generated) {
      document.getElementById("gen").textContent = "data generated " + doc.generated;
    }
    var sortable = document.getElementById("tbl");
    if (sortable) sortable.dataset.ready = "1";
    fillArchSelects(state.rows);
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
