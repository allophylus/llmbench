# llmbench — environment configuration
# Copy to config.sh and edit, or export these before running anything.

# OpenAI-compatible endpoint serving the model under test.
export LLMBENCH_BASE="http://127.0.0.1:8080"

# Where per-cell results are written (SCHEMA-1 JSON).
export LLMBENCH_RESULTS="$PWD/results"

# Root of this suite (defaults to the parent of bin/). Only set if you move things.
# export LLMBENCH_HOME="/path/to/llmbench"

# Optional bearer token for the endpoint.
# export LLMBENCH_API_KEY=""

# --- terminal-bench cell (optional) ---
# export TBENCH="$PWD/.venv/bin/tb"
# export TBDATASET="terminal-bench-core==0.1.1"
# export TB_MODEL="<model id or gguf path>"

# --- tau2 cell (optional) ---
# tau2-bench must be installed and pointed at your endpoint; see suite/README.md

# --- browser game cells (optional) ---
# export CHROME_BIN="/usr/bin/google-chrome"
