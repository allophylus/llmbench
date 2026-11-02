# suite — generic cell runner

Runs the accuracy / long-context / agentic cells against **any** OpenAI-compatible
chat-completions endpoint (llama.cpp, vLLM, Ollama, SGLang, a hosted API).

## Quick start

```bash
cp config.example.sh config.sh      # edit LLMBENCH_BASE if needed
./run_cells.sh my-model 1,2,3,c1,c2
```

That writes SCHEMA-1 JSON into `results/` (`pub-gpqa25.pub.json`, `pub-aime10x3.pub.json`, …).

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `LLMBENCH_BASE` | `http://127.0.0.1:8080` | URL of your OpenAI-compatible endpoint — point this at your own server (`/v1` is appended where needed) |
| `LLMBENCH_RESULTS` | `./results` | where cell JSON is written |
| `LLMBENCH_HOME` | parent of `bin/` | suite root (packs, tau2, terminal-bench data) |
| `LLMBENCH_API_KEY` | unset | optional bearer token |
| `CHROME_BIN` | auto-detect | browser used by the game-cell validator |
| `TBENCH` / `TBDATASET` / `TB_MODEL` | — | terminal-bench cell |
| `R97_BASE` / `R97_RESULTS` | — | legacy aliases, still honoured |

No absolute paths are baked in: the suite root is derived from the script location, so a
clone can live anywhere.

## Cells

| Short | Cell id | Command |
|---|---|---|
| `1` | `pub-gpqa25` | `score_pack.py gpqa` |
| `2` | `pub-aime10x3` | `score_pack.py aime --n 15 --samples 3 --temp 0.6` |
| `3` | `pub-livebench25` | `score_pack.py livebench` |
| `c1` | `ctx-gpqa30k` | `ctx_embed.py --cell c1` |
| `c2` | `ctx-gpqa110k` | `ctx_embed.py --cell c2` |
| `b` | `agent-shell10` | `score_pack.py shell --n 10 --turns 6` |
| `a` | `agent-tau2-telecom20` | `tau2_cell.py --slug <slug> --dry 0` (needs tau2-bench) |
| `8` | `agent-termbench8` | `termbench_cell.py --n 8` (needs terminal-bench) |
| `0` | `bench-ctx-sweep` | llama-bench, hardware-specific — run directly |

## Requirements

- Python 3.10+ (stdlib only for the scoring cells)
- A server that speaks `/v1/chat/completions` with the model's own chat template
- Optional: `tau2-bench`, `terminal-bench`, `llama-bench` for the `a`/`8`/`0` cells

## Notes that save time

- The endpoint must have **thinking disabled** for deterministic runs, or the scoring cells
  burn the completion budget on reasoning and return empty `content`.
- A truncated prompt (server window smaller than the requested context) is recorded as a
  harness failure, not a model failure.
- Results are per-cell files; merge them into a per-model record before publishing.
