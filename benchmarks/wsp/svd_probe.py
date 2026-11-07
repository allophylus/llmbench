#!/usr/bin/env python3
"""svd_probe.py (v2) — rank-1 edit detection by power iteration.

D = W_wsp - W_stock on the documented-edited tensor. If WSP really contains
W[:, S] -= alpha*u*q^T (norm 7.46), D has a rank-1 component whose singular value
sits above the quantisation-noise spectrum. Power iteration gives sigma_1 and v_1
cheaply; deflating it gives sigma_2 for the "is it really one direction?" test.
"""
import json
import numpy as np
import gguf
from gguf.quants import dequantize

STOCK = '/home/ubuntu/models/Qwen3.8-27B-Q4_K_M.gguf'
WSP = '/home/ubuntu/models/qwen38fn/wsp-bench/Qwen3.8-27B-WSP-Q4_K_M.gguf'
T_S = {t.name: t for t in gguf.GGUFReader(STOCK, 'r').tensors}
T_W = {t.name: t for t in gguf.GGUFReader(WSP, 'r').tensors}


def deq(t):
    return np.asarray(dequantize(t.data, t.tensor_type)).reshape(
        tuple(reversed(t.shape))).astype(np.float32)


def top_sv(D, iters=40, seed=0):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(D.shape[1])
    v /= np.linalg.norm(v)
    s = 0.0
    for _ in range(iters):
        u = D @ v
        nu = np.linalg.norm(u)
        if nu == 0:
            return 0.0, 0.0, v
        u /= nu
        v = D.T @ u
        s = np.linalg.norm(v)
        v /= s
    return float(s), float(nu), v          # sigma1, 2-norm of u, v1


def probe(name):
    if name not in T_S or name not in T_W:
        return {'tensor': name, 'error': 'missing'}
    ws, ww = deq(T_S[name]), deq(T_W[name])
    if ws.shape != ww.shape:
        return {'tensor': name, 'error': f'shape {ws.shape} vs {ww.shape}'}
    D = (ww - ws).astype(np.float32)
    m, n = D.shape
    s1, _, v1 = top_sv(D)
    s2, _, _ = top_sv(D - s1 * np.outer(D @ v1 / max(s1, 1e-30), v1), seed=1)
    fro = float(np.linalg.norm(D))
    # how many columns carry 90% of v1's energy, and is the support blocky?
    a = np.abs(v1)
    idx = np.argsort(-a)
    cum = np.cumsum(v1[idx] ** 2) / max((v1 ** 2).sum(), 1e-30)
    n90 = int(np.searchsorted(cum, 0.90) + 1)
    top_cols = np.sort(idx[:4096])
    blockiness = float(np.mean(np.diff(top_cols) == 1)) if len(top_cols) > 1 else 0.0
    cm = np.abs(D.mean(axis=0))
    return {'tensor': name, 'shape': [int(m), int(n)],
            'fro_norm': round(fro, 4), 'sv1': round(s1, 4), 'sv2': round(s2, 4),
            'sv1_over_sv2': round(s1 / max(s2, 1e-30), 3),
            'top1_energy_frac': round(s1 ** 2 / max(fro ** 2, 1e-30), 5),
            'cols_for_90pct_v1_energy': n90,
            'v1_top4096_col_blockiness': round(blockiness, 4),
            'v1_abs_max_over_mean': round(float(a.max() / max(a.mean(), 1e-30)), 3),
            'colmean_abs_median': round(float(np.median(cm)), 6),
            'colmean_abs_p99': round(float(np.percentile(cm, 99)), 6)}


out = {'target': probe('blk.29.ffn_down.weight'),
       'controls': [probe(n) for n in ['blk.27.ffn_down.weight', 'blk.29.ffn_gate.weight']]}
json.dump(out, open('/home/ubuntu/wsp-bench/svd_probe.json', 'w'), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
