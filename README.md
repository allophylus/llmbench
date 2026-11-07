# llmbench — sortable benchmark table

A static, dependency-free page that renders the benchmark results of local LLMs served by
**llama.cpp (Vulkan)** on an **AMD Radeon AI PRO R9700 32 GiB** box, with client-side
sorting and filtering.

- Live: <https://allophylus.github.io/llmbench/>

## Why this exists: Markdown tables cannot sort

A Markdown table (as used in the original notes) is a block of text. Once it is written to a
file or rendered by a Markdown viewer it has no state, no event handlers and no way to
reorder rows — the only way to see "best GPQA score first" is to rewrite the whole table by
hand, and every rewrite risks transcribing a number wrong.

This page solves that with ~300 lines of plain JavaScript:

| Need | How this repo does it |
| --- | --- |
| Sort by any column | Click a column header: **asc → desc → off** (third click restores the default order). |
| Numeric sort | Numeric columns compare as numbers; `8` sorts below `10`. One exception is deliberate: `Params` compares billions parsed from `"27B"`/`"2.4B"`, so it sorts numerically too. |
| Missing data | Blank cells sort **last in both directions** and render as a dim `—`. Values are never filled in or guessed. |
| Filter | Free-text box (name / slug / quant / arch), an architecture dropdown, and an "only rows with video" toggle. |
| Phone | Speed stays a horizontally scrollable comparison table with a pinned model column; other views become cards at ≤ 760 px. There is no horizontal page scroll. |

The Speed view shows each model's 4K, 32K, 64K, 128K and 256K context sweep
directly in its row. Each sweep
cell labels prefill/decode (tokens/s), peak VRAM (GiB), and actual prompt tokens;
Logic off/on columns are not displayed in Speed. The older standalone speed,
VRAM and server-context columns are not displayed, including under "Show all
columns"; their raw measurements remain in the dataset. Sweep columns are visible
without expanding details or selecting "Show all columns". Context headers sort
by decode rate. At every screen width, Speed keeps
models in compact table rows with aligned columns, a pinned model name, and sticky
column headers. Scroll inside the table to compare all contexts and models.
Use the Speed-only "Sweep metrics" checkboxes to show any combination of Prefill,
Decode, VRAM and Prompt across all five contexts. All four start selected; selecting
none shows "No metrics selected". Choices are retained while switching views
but reset on reload. Context headers still sort by decode rate.

Models with measurement-status notes stay in the normal sortable table without an
Archive grouping; missing measurements remain blank. The accelerator-ablation
table identifies the tested model and each configuration's draft model or MTP
head directly from the arm records. These tests cover Qwen3.8-27B-Q4_K_M only,
not every model in the Speed table.

No framework, no build step, no CDN, no analytics. Just `index.html`, `style.css`, `app.js`
and the generated data.

```
index.html          markup + column headers (data-key / data-type per column)
style.css           dark theme, sticky header, zebra rows, mobile card layout
app.js              load -> filter -> sort -> render; three-click sort cycle
data/results.json   the dataset (one object per model+quant)
data/results.js     same dataset as window.LLMBENCH_DATA (file:// fallback only)
raw/*.json          copies of the raw SCHEMA-1 run records each row is folded from
scripts/update_data.py   regenerates data/ from the benchmark results dir
```

## Where the numbers come from

The benchmark suite writes **one SCHEMA-1 JSON record per run phase**
(`results/<slug>.json` — plain bench, `rebench_*`, `tune_*`, `c7_*` power sweeps,
`tetris_*`). A single model therefore has several records, and blindly rendering one row per
file shows the same model up to four times.

`scripts/update_data.py` folds them the same way the suite's own `merge_rows.py` does:

1. **Group** records by `.gguf` file basename with the quant suffix stripped — same file
   means same model even when display names drift; a different quant stays a separate row.
2. **Identity** (name, params, quant, arch, context) comes from the richest `model` block
   in the group; throughput from the best-ranked source (`rebench` > `bench` > `tune` >
   `power-sweep`), prefill = `pp512`, decode = `tg128` tokens/s.
3. **Cells** are taken per test id, never averaged and never max-ed across sources:
   `pub-gpqa25`, `pub-aime10x3`, `pub-livebench25`, `ctx-gpqa30k`, `ctx-gpqa110k`,
   `agent-tau2-telecom20`, `agent-shell10`, `agent-termbench8`. Scores are stored as
   percent (0–100); `acc` falls back to `correct/total` when a record stores raw counts.
4. **Nothing is invented.** A test the model never ran is `null` in the JSON and a `—` on
   the page. Records with no tests at all (stub files) never create a row.

Videos are **not** hosted in this repo. A link is emitted only when the rendered file
exists in the local videos directory, and it points at the CloudFront copy:

```
https://d1zqwbb1zduc6n.cloudfront.net/llmbench/videos/<slug>__<cell>.mp4
```

## Updating the data

Prerequisites: Python 3.8+ (standard library only) and a checkout of the benchmark suite
workspace and its rendered videos.

```sh
# 1. regenerate the dataset + the raw-record copies, then commit
python3 scripts/update_data.py --raw-out raw
git add data raw && git commit -m "data: refresh benchmark results" && git push

# 2. (optional) local preview — any static server works
python3 -m http.server 8765     # then open the printed local URL
```

Paths may be overridden for a different machine or a copied run:

```sh
python3 scripts/update_data.py \
    --results-dir  /path/to/llmbench/results \
    --videos-dir   /path/to/llmbench/site/videos \
    --raw-out      raw \
    --out          data/results.json
```

Only the benchmark suite writes into `results/`; this repository only reads it. If a new
test id starts being written, add it to the `CELLS` table (and to the `<th>` list in
`index.html` + `COLUMNS` in `app.js`) so the column appears.

## Deployment

GitHub Pages serves the repository root of `main` directly (`Settings → Pages → Deploy from
a branch`). There is no workflow and no artifact step: pushing to `main` *is* the deploy.
Caching is short; a hard refresh picks up new data immediately.

## Limitations / notes

- Scores are percent correct over small, frozen prompt sets — treat differences of a few
  points as noise.
- One `—` means "this model was not run on that test", not "scored zero".
- Throughput figures come from different llama-bench variants over time (`llama-bench` vs
  `llama-bench-ppextended`); the raw record for every row is linked under `raw/` so any
  number can be traced to its source file.
- The `Arch` dropdown lists the free-text arch strings exactly as recorded; they are
  descriptive, not a controlled vocabulary.

## Licence

Code is MIT licensed (see `LICENSE`). Model outputs, generated games and benchmark data are published for reference; the models themselves keep their own licences.
