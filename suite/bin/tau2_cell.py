#!/usr/bin/env python3
"""tau2_cell.py — turn a tau2-bench run directory into a SCHEMA-1 test cell.

  tau2_cell.py --slug S --out DIR_OR_STDOUT_FILE --dry 0|1 [--expect-tasks 20]

tau2 writes data/simulations/<save_to>/results.json (also writes it for a crashed
partial run when at least one simulation finished). We read:
  simulation_results[*].reward_info.reward      (per-task average reward, 0..1)
  simulation_results[*].termination_reason
  info.num_tasks / num_trials (if present)
and emit <out-dir>/results/<id>.pub.json with:
  acc      = mean reward
  metrics  = {reward: mean, success_rate: share with reward>=1.0, num_tasks, num_trials,
              pass_hat_1: mean reward at k=1}
"""
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.environ.get("LLMBENCH_HOME") or os.path.dirname(HERE)
RESULTS = (os.environ.get("LLMBENCH_RESULTS") or os.environ.get("R97_RESULTS")
           or os.path.join(SUITE, "results"))
CID = "agent-tau2-telecom20"


def find_results(slug, dry):
    pats = [
        f"{SUITE}/tau2-repo/data/simulations/{slug}{'-dryrun' if dry else ''}/results.json",
        f"{SUITE}/tau2-repo/data/simulations/{slug}{'-dry' if dry else ''}/results.json",
        f"{SUITE}/tau2-repo/data/simulations/{slug}-dry/results.json",
        f"{SUITE}/data/simulations/{slug}{'-dryrun' if dry else ''}/results.json",
    ]
    for p in pats:
        if os.path.exists(p):
            return p
    # newest results.json that mentions the slug
    cands = sorted(glob.glob(SUITE + "/**/data/simulations/**/results.json", recursive=True)
                   + glob.glob(SUITE + "/tau2-repo/data/simulations/*/results.json"),
                   key=os.path.getmtime, reverse=True)
    for c in cands:
        if slug in c:
            return c
    return None


def tail_reason(path, n=600):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf8", "replace").replace("\n", " ")[-n:]
    except Exception:
        return ""


def main():
    a = dict(zip(sys.argv[1::2], sys.argv[2::2]))
    slug = a["--slug"]; out = a.get("--out", ""); dry = a.get("--dry", "0") == "1"
    p = find_results(slug, dry)
    cell = {"id": CID, "task": "tau2-bench telecom", "acc": None, "metric": "pass_hat_1",
            "samples": None, "duration_s": 0, "n_a": True, "reason": ""}
    if not p:
        cell["reason"] = "no tau2 results.json produced | " + tail_reason(out)[-300:]
        _write(cell)
        print(json.dumps(cell))
        return 0
    d = json.load(open(p))
    sims = d.get("simulations") or d.get("simulation_results") or []
    rewards = []
    peaks = []
    for s in sims:
        ri = s.get("reward_info") or {}
        r = ri.get("reward")
        if r is None:
            r = (s.get("reward") if isinstance(s.get("reward"), (int, float)) else None)
        if isinstance(r, (int, float)):
            rewards.append(float(r))
        # multi-turn context growth: peak prompt tokens seen by either party (when recorded)
        for who in ("agent_usage", "user_usage"):
            u = s.get(who) or {}
            if isinstance(u, dict):
                v = u.get("prompt_tokens") or u.get("max_prompt_tokens")
                if isinstance(v, (int, float)):
                    peaks.append(int(v))
    info = d.get("info") or {}
    if rewards:
        n = len(rewards)
        mean = sum(rewards) / n
        succ = sum(1 for r in rewards if r >= 1.0) / n
        # headline number = pass^1 (share of tasks fully resolved, reward == 1.0);
        # tau2's own leaderboard reports average reward, kept in metrics
        cell.update(acc=round(succ, 4), samples=n, n_a=False,
                    metrics={"reward": round(mean, 4), "success_rate": round(succ, 4),
                             "pass_hat_1": round(succ, 4),
                             "ctx_peak_used": (max(peaks) if peaks else None),
                             "num_tasks": info.get("num_tasks") or n,
                             "num_trials": info.get("num_trials") or 1,
                             "task_set": info.get("task_set_name") or info.get("domain") or "telecom_small"},
                    reason="")
        # duration from first/last simulation timestamps if present
        try:
            ts = [time.mktime(time.strptime(s["start_time"][:19], "%Y-%m-%dT%H:%M:%S")) for s in sims if s.get("start_time")]
            te = [time.mktime(time.strptime(s["end_time"][:19], "%Y-%m-%dT%H:%M:%S")) for s in sims if s.get("end_time")]
            if ts and te:
                cell["duration_s"] = int(max(te) - min(ts))
        except Exception:
            pass
    else:
        cell["reason"] = "results.json had no scored simulations | " + tail_reason(out)[-300:]
    _write(cell)
    print(json.dumps(cell))
    return 0


def _write(cell):
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, cell["id"] + ".pub.json"), "w") as f:
        json.dump(cell, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
