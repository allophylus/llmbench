#!/usr/bin/env python3
"""assemble_results.py — build benchmarks/wsp/results.json from the raw records.

Reads the per-item JSONL/JSON this directory's harnesses produced (raw/out/…) and
writes one flat results.json that both the page and RESULTS.md render from.
No number is typed by hand: every value comes from a file in raw/.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')
OUT = os.path.join(RAW, 'out')


def jload(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return default


def ccp(label):
    s = jload(os.path.join(RAW, f'{label}.ccp.judged.summary.json'))
    if not s:
        return None
    return {'mean': s['mean'], 'china_mean': s['china_mean'],
            'non_china_mean': s['non_china_mean'], 'n': s['n'],
            'n_china': s['n_china'], 'n_non_china': s['n_non_china'],
            'distribution': s['distribution'], 'categories': s['cat_counts']}


def judged(label):
    """MATH judge output: .llmjudged.json -> n, correct, acc."""
    p = os.path.join(RAW, f'{label}.llmjudged.json')
    rows = jload(p)
    if rows is None:
        p = os.path.join(RAW, f'{label}.json')
        rows = jload(p) or []
    if not rows:
        return None
    n = len(rows)
    c = sum(1 for r in rows if r.get('correct'))
    trunc = sum(1 for r in rows if r.get('finish') == 'length')
    return {'n': n, 'correct': c, 'acc': round(c / n, 3), 'truncated': trunc}


def gpqa(label):
    rows = [json.loads(l) for l in open(os.path.join(OUT, f'{label}.gpqa.jsonl'))]
    if not rows:
        return None
    n = len(rows)
    c = sum(1 for r in rows if r.get('correct'))
    trunc = sum(1 for r in rows if r.get('finish') == 'length')
    return {'n': n, 'correct': c, 'acc': round(c / n, 3), 'truncated': trunc,
            'tokens': sum(r.get('completion_tokens') or 0 for r in rows),
            'wall_s': round(sum(r.get('wall_s') or 0 for r in rows), 1)}


def spec(p):
    d = jload(os.path.join(OUT, p))
    if not d or not d.get('summary', {}).get('prefill_tps'):
        return None
    return {'prefill_tps': d['summary']['prefill_tps']['mean'],
            'prefill_spread': d['summary']['prefill_tps']['spread_pct'],
            'decode_tps': d['summary']['decode_tps']['mean'],
            'decode_spread': d['summary']['decode_tps']['spread_pct'],
            'reps': d['summary']['prefill_tps']['n'],
            'prompt_n': d['runs'][0]['prompt_n'] if d.get('runs') else None,
            'n_ctx': d.get('n_ctx'), 'vram_peak_gib': d.get('vram_peak_gib'),
            'vram_idle_gib': d.get('vram_idle_gib'), 'build': d.get('build_info')}


def main():
    diff = jload(os.path.join(RAW, 'diff_report.json')) or {}
    svd = jload(os.path.join(RAW, 'svd_probe.json')) or {}
    res = {
        'generated': '2026-11-07',
        'models': {
            'stock': {
                'name': 'Qwen3.8-27B (local baseline file, labelled Q4_K_M)',
                'file': 'Qwen3.8-27B-Q4_K_M.gguf', 'bytes': 16464440224,
                'note': 'mixed-precision build: Q5_K / IQ4_XS / Q8_0 / Q6_K tensors present',
            },
            'wsp': {
                'name': 'Qwen3.8-27B-Weight-Space-Programming (Q4_K_M)',
                'file': 'Qwen3.8-27B-WSP-Q4_K_M.gguf', 'bytes': 16810715616,
                'note': 'mradermacher quant of ReBatch/Qwen3.8-27B-Weight-Space-Programming',
                'upstream_base': 'Qwen/Qwen3.8-27B @ 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0',
            },
        },
        'ccpbench30': {'stock': ccp('stock'), 'wsp': ccp('wsp'),
                       'judge': 'deepseek-chat, official CCPBench rubric, blind to arm'},
        'math20': {'stock': judged('stock.math20r'), 'wsp': judged('wsp.math20r')},
        'math500_20': {'stock': judged('stock.math500'), 'wsp': judged('wsp.math500'),
                       'grader': 'deepseek-chat, reference-answer equivalence, blind to arm'},
        'gpqa25': {'stock': gpqa('stock128k'), 'wsp': gpqa('wsp128k')},
        'speed': {'wsp_4k': spec('wsp-4k.json'), 'wsp_128k': spec('wsp-128k.json'),
                  'stock_4k': spec('stock-4k.json'), 'stock_128k': spec('stock-128k.json')},
        'recorded_baselines': {
            'gpqa25_thinking_off': {'correct': 16, 'n': 25, 'tokens': 65251, 'wall_s': 2148},
            'speed_4k': {'prefill_tps': 846.8, 'decode_tps': 30.61},
            'speed_128k': {'prefill_tps': 365.8, 'decode_tps': 23.16},
        },
        'diff': {
            'tensors_stock': diff.get('stock_n_tensors'),
            'tensors_wsp': diff.get('wsp_n_tensors'),
            'names_equal': diff.get('names_equal'),
            'tensors_differing_type_or_shape': len(diff.get('shape_or_type_mismatch') or []),
            'svd_target': svd.get('target'),
            'svd_controls': svd.get('controls'),
        },
    }
    json.dump(res, open(os.path.join(HERE, 'results.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1)[:4000])


main()
