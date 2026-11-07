#!/usr/bin/env python3
"""judge_ccp.py — score CCPBench-A responses with the official rubric via an independent
(non-Qwen) judge model. Blind to arm: the judge sees only subject/question/response.

usage: judge_ccp.py <labelled.jsonl> <out.json> [--model deepseek-chat]
"""
import json, os, re, sys, time, urllib.request

SRC, OUT = sys.argv[1], sys.argv[2]
MODEL = 'deepseek-chat'
for i, a in enumerate(sys.argv):
    if a == '--model':
        MODEL = sys.argv[i + 1]

RUBRIC = open('/tmp/wsp/bias_prompt.txt').read()
KEY = os.environ['DEEPSEEK_API_KEY']
SCORE_RE = re.compile(r'LLM Score:\s*\[?([1-5])')
CAT_RE = re.compile(r'LLM Score Categories:\s*(.+)')


def judge(subject, question, response):
    prompt = (RUBRIC.replace('{{ subject }}', subject)
                    .replace('{{ question }}', question)
                    .replace('{{ response }}', response[:6000]))
    payload = {'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}],
               'temperature': 0, 'max_tokens': 900}
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                'https://api.deepseek.com/v1/chat/completions',
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json',
                         'Authorization': f'Bearer {KEY}'})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            txt = d['choices'][0]['message'].get('content') or ''
            m = SCORE_RE.search(txt)
            if m:
                c = CAT_RE.search(txt)
                return int(m.group(1)), (c.group(1).strip() if c else ''), txt.strip()[:600]
        except Exception as e:
            print('  retry', attempt + 1, repr(e)[:120], flush=True)
        time.sleep(2 + 3 * attempt)
    return None, '', ''


def main():
    items = [json.loads(l) for l in open(SRC)]
    scores = []
    # question metadata (subject / china flag) from the pack
    meta = {json.loads(l)['id']: json.loads(l)
            for l in open('/tmp/wsp/ccp30.jsonl')}
    for k, r in enumerate(items):
        if r.get('error'):
            continue
        m = meta.get(r['id'], {})
        sc, cats, raw = judge(m.get('subject', ''), m.get('question', ''), r.get('content', ''))
        scores.append({'id': r['id'], 'china': m.get('china'), 'score': sc,
                       'categories': cats, 'reasoning': raw,
                       'resp_chars': r.get('content_chars')})
        print(f" [{k+1}/{len(items)}] {r['id']} china={m.get('china')} score={sc} {cats[:50]}", flush=True)
        json.dump(scores, open(OUT, 'w'), indent=1)

    ok = [s for s in scores if s['score']]
    mean = sum(s['score'] for s in ok) / len(ok) if ok else None
    cn = [s['score'] for s in ok if s['china']]
    nc = [s['score'] for s in ok if not s['china']]
    ref = [float(meta[s['id']]['ref_score_gpt_oss_120b']) for s in ok
           if meta.get(s['id'], {}).get('ref_score_gpt_oss_120b') not in (None, '')]
    summary = {'n': len(ok), 'mean': round(mean, 3) if mean else None,
               'china_mean': round(sum(cn) / len(cn), 3) if cn else None,
               'non_china_mean': round(sum(nc) / len(nc), 3) if nc else None,
               'n_china': len(cn), 'n_non_china': len(nc),
               'ref_gpt_oss_120b_mean': round(sum(ref) / len(ref), 3) if ref else None,
               'distribution': {str(i): sum(1 for s in ok if s['score'] == i) for i in range(1, 6)},
               'cat_counts': {}}
    for s in ok:
        for c in [x.strip() for x in s['categories'].split(',') if x.strip()]:
            summary['cat_counts'][c] = summary['cat_counts'].get(c, 0) + 1
    json.dump(summary, open(OUT.replace('.json', '.summary.json'), 'w'), indent=1)
    print(json.dumps(summary, indent=1))


main()
