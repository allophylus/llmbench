#!/usr/bin/env python3
"""Stratified deterministic 30-question subset of CCPBench-A (375 China / 125 non-China)."""
import json, random

rows = [json.loads(l) for l in open('ccpbench-a.jsonl')]
for r in rows:
    if isinstance(r['metadata'], str):
        r['metadata'] = json.loads(r['metadata'])

rng = random.Random(5)
china = [r for r in rows if r['metadata'].get('is_china_related') == 'True']
noncn = [r for r in rows if r['metadata'].get('is_china_related') != 'True']
print('pool', len(china), len(noncn))

def strat(pool, k):
    """Take k across top_level_topic as evenly as possible."""
    by = {}
    for r in pool:
        by.setdefault(r['metadata'].get('top_level_topic', '?'), []).append(r)
    for v in by.values():
        rng.shuffle(v)
    topics = sorted(by)
    out, i = [], 0
    while len(out) < k and any(by.values()):
        t = topics[i % len(topics)]
        if by[t]:
            out.append(by[t].pop())
        i += 1
    return out

sel = strat(china, 22) + strat(noncn, 8)
out = []
for r in sel:
    out.append({
        'id': r['id'],
        'subject': r['metadata'].get('title', ''),
        'question': r['input'],
        'china': r['metadata'].get('is_china_related') == 'True',
        'topic': r['metadata'].get('top_level_topic', ''),
        'ref_score_gpt_oss_120b': r['metadata'].get('gpt_oss_120b_score'),
    })
with open('ccp30.jsonl', 'w') as f:
    for o in out:
        f.write(json.dumps(o) + '\n')
print('wrote', len(out), 'china', sum(o['china'] for o in out))
print('reviewer-reference mean (gpt-oss-120b):', round(sum(float(o['ref_score_gpt_oss_120b']) for o in out if o['ref_score_gpt_oss_120b']), 2))
