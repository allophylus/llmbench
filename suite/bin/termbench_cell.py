#!/usr/bin/env python3
"""termbench_cell.py — optional terminal-bench agentic cell (used only when
TERMBENCH_ENABLED=1).

  termbench_cell.py --slug S --n 8 --out <logfile>

Runs `tbench run --task-id <id> ...` for N frozen task ids with an OpenAI-compatible
endpoint pointed at :8081 (TB_MODEL / OPENAI_API_BASE), one task per invocation so a
single broken image cannot kill the whole cell, and writes a SCHEMA-1 test cell
(results/agent-termbench8.pub.json) with acc = passed/total.

If the harness or Docker misbehaves the cell is emitted as n/a with the exact blocker —
the run_suite.sh caller then falls back to agent-shell10 instead.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.environ.get("LLMBENCH_HOME") or os.path.dirname(HERE)
RESULTS = (os.environ.get("LLMBENCH_RESULTS") or os.environ.get("R97_RESULTS")
           or os.path.join(SUITE, "results"))
TBENCH = os.environ.get("TBENCH", os.path.join(SUITE, "tbench-venv", "bin", "tb"))
TBDATASET = os.environ.get("TBDATASET", "terminal-bench-core==0.1.1")
BASE = (os.environ.get("LLMBENCH_BASE") or os.environ.get("R97_BASE")
        or "http://127.0.0.1:8080").rstrip("/")

# 8 frozen easy/medium task ids (terminal-bench-core), fixed order = frozen subset
# frozen subset (8 of the 241 tasks in terminal-bench original-tasks, chosen easy/medium)
TASKS = ["hello-world", "fix-permissions", "csv-to-parquet", "count-dataset-tokens",
         "create-bucket", "fibonacci-server", "heterogeneous-dates", "grid-pattern-transform"]


def main():
    a = dict(zip(sys.argv[1::2], sys.argv[2::2]))
    n = int(a.get("--n", 8))
    out = a.get("--out", os.path.join(SUITE, "logs", "termbench.log"))
    model = os.environ.get("TB_MODEL", "")  # gguf path or provider-prefixed model id
    # the harness talks to the model through litellm, which needs an api_base argument
    # (it does NOT read OPENAI_API_BASE): without it every trial died with
    # InternalServerError and the cell published a false 0/8 on all 5 models.
    api_base = BASE + "/v1"
    tasks = TASKS[:n]
    t0 = time.time()
    passed = 0
    ran = 0
    scored = 0
    errs = []
    with open(out, "a") as logf:
        for tid in tasks:
            # litellm needs an explicit provider prefix for a local OpenAI-compatible server
            tmodel = model if "/" in model.split("/", 1)[0] else "openai/" + os.path.basename(model)
            # terminus_1 takes its endpoint as a constructor kwarg (agent_factory passes
            # --agent-kwarg through to the agent's __init__)
            cmd = [TBENCH, "run", "-d", TBDATASET, "--agent", "terminus", "--model", tmodel,
                   "--agent-kwarg", "api_base=" + api_base,
                   "--task-id", tid, "--n-concurrent", "1"]
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                                   env={**os.environ, "OPENAI_API_BASE": BASE + "/v1",
                                        "OPENAI_API_KEY": "sk-noop"})
                logf.write(f"\n$ {' '.join(cmd)}\n{p.stdout[-4000:]}\n{p.stderr[-2000:]}\n")
                ran += 1
                # ONLY a real agent trial counts: "Running tasks (1/1, Accuracy: 100.00%)"
                # (a build error prints 0.00% and the oracle agent would not be run at all)
                m = re.search(r"Running tasks \(1/1, Accuracy: ([0-9.]+)%\)", p.stdout)
                if not m:
                    m = re.search(r"\| Accuracy\s*\|\s*([0-9.]+)%\s*\|", p.stdout)
                logf.write(f"\nPARSED accuracy: {m.group(1) if m else 'none'}\n")
                # a failed trial with zero LLM exchanges is a HARNESS fault (the agent
                # could not reach a model), never a model score: count it as n/a.
                if m and "Error in LLM interaction" in p.stdout:
                    errs.append(f"{tid}: harness LLM interaction failed")
                    continue
                scored += 1
                if m and float(m.group(1)) > 0:
                    passed += 1
            except Exception as e:
                errs.append(f"{tid}: {e}")
                logf.write(f"\n$ {' '.join(cmd)}\nEXC {e}\n")
    dur = time.time() - t0
    cell = {"id": "agent-termbench8", "task": "terminal-bench", "acc": None, "metric": "pass",
            "samples": len(tasks), "duration_s": int(dur), "n_a": True, "reason": ""}
    if scored:
        cell.update(acc=round(passed / scored, 4), n_a=False,
                    metrics={"pass": passed, "total": scored, "attempted": len(tasks)})
        if errs:
            cell["reason"] = "; ".join(errs)[:300]
    elif ran:
        # tasks ran but every trial was a transport/agent-construction failure
        cell["reason"] = ("all trials failed in the harness (no scored trial) | "
                          + "; ".join(errs)[:250])
    else:
        cell["reason"] = ("terminal-bench harness produced no runnable tasks | "
                          + "; ".join(errs)[:250])
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "agent-termbench8.pub.json"), "w") as f:
        json.dump(cell, f, indent=1)
    print(json.dumps(cell))


if __name__ == "__main__":
    main()
