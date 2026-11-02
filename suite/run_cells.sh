#!/usr/bin/env bash
# Generic cell runner. Works against ANY OpenAI-compatible endpoint.
#
#   LLMBENCH_BASE=http://host:8080 ./run_cells.sh <slug> [cells]
#
# cells (default 1,2,3,c1,c2):
#   1  = GPQA diamond (25)            4/pub-gpqa25
#   2  = AIME (15 x 3, temp 0.6)      pub-aime10x3
#   3  = LiveBench (25)               pub-livebench25
#   c1 = GPQA @30k context            ctx-gpqa30k
#   c2 = GPQA @110k context           ctx-gpqa110k
#   b  = shell tasks (10, 6 turns)    agent-shell10
#   a  = tau2 telecom (20 tasks)      agent-tau2-telecom20   (needs tau2 installed)
#   8  = terminal-bench (8 tasks)     agent-termbench8       (needs terminal-bench)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/config.sh" ] && . "$HERE/config.sh"
export LLMBENCH_BASE="${LLMBENCH_BASE:-http://127.0.0.1:8080}"
export R97_BASE="$LLMBENCH_BASE"
export LLMBENCH_RESULTS="${LLMBENCH_RESULTS:-$HERE/results}"
export R97_RESULTS="$LLMBENCH_RESULTS"
mkdir -p "$LLMBENCH_RESULTS"

SLUG="${1:?usage: run_cells.sh <slug> [1,2,3,c1,c2,a,b,8]}"
CELLS="${2:-1,2,3,c1,c2}"
cd "$HERE/bin"

IFS=, read -ra LIST <<< "$CELLS"
for c in "${LIST[@]}"; do
  case "$c" in
    1) echo "== $SLUG cell 1: GPQA";        python3 score_pack.py gpqa ;;
    2) echo "== $SLUG cell 2: AIME x3";     python3 score_pack.py aime --n 15 --samples 3 --temp 0.6 ;;
    3) echo "== $SLUG cell 3: LiveBench";   python3 score_pack.py livebench ;;
    c1) echo "== $SLUG c1: GPQA @30k";      python3 ctx_embed.py --cell c1 ;;
    c2) echo "== $SLUG c2: GPQA @110k";     python3 ctx_embed.py --cell c2 ;;
    b) echo "== $SLUG b: shell10";          python3 score_pack.py shell --n 10 --turns 6 ;;
    a) echo "== $SLUG a: tau2 telecom";     python3 tau2_cell.py --slug "$SLUG" --dry 0 ;;
    8) echo "== $SLUG 8: terminal-bench";   python3 termbench_cell.py --n 8 ;;
    0) echo "== cell 0 (llama-bench sweep) is hardware-specific; run it directly" ;;
    *) echo "unknown cell: $c" >&2 ;;
  esac
done
echo "results in $LLMBENCH_RESULTS"
