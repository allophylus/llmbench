#!/usr/bin/env python3
"""bench_wsp.py — resumable A/B harness for the WSP vs stock Qwen3.8-27B comparison.

usage: bench_wsp.py --base http://127.0.0.1:8080 --tasks ccp,math20,math500,gpqa \
                    --outdir /home/ubuntu/wsp-bench/out --label wsp

One request at a time. Appends to <outdir>/<label>.<task>.jsonl and skips ids already
present, so a crash or a card hand-back loses at most one item.
Thinking is forced off via chat_template_kwargs (same as prod's enable_thinking:false).
"""
import json, os, re, sys, time, urllib.request

args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
BASE = args.get('--base', 'http://127.0.0.1:8080').rstrip('/')
OUTDIR = args.get('--outdir', '/home/ubuntu/wsp-bench/out')
LABEL = args.get('--label', 'run')
TASKS = args.get('--tasks', 'ccp,math20,math500,gpqa').split(',')
LIMIT = {k: int(v) for k, v in (kv.split('=') for kv in args.get('--limit', '').split(',') if kv)}
os.makedirs(OUTDIR, exist_ok=True)

PACKS = {
    'ccp':     ('/home/ubuntu/wsp-bench/packs/ccp30.jsonl',     'question', 0.2, 1024),
    'math20':  ('/home/ubuntu/wsp-bench/packs/math20.jsonl',    'prompt',   0.0, 1024),
    'math500': ('/home/ubuntu/wsp-bench/packs/math500_20.jsonl', 'problem',  0.0, 1536),
    'gpqa':    ('/home/ubuntu/llmbench/suite/packs/gpqa25.jsonl', None,       0.0, 2048),
}
BOX = re.compile(r'\\boxed\s*\{((?:[^{}]|\{[^{}]*\})*)\}')


def post(path, payload, timeout=7200):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), time.time() - t0


def prompt_for(task, it):
    if task == 'gpqa':
        ch = it['choices']
        letters = 'ABCD'
        return (it['question'] + '\n\n' + '\n'.join(f'({letters[i]}) {c}' for i, c in enumerate(ch))
                + '\n\nAnswer with the single letter of the correct choice on the last line, '
                  'formatted exactly as "Answer: X".')
    return it[PACKS[task][1]]


def postproc(task, it, content):
    if task == 'gpqa':
        m = re.findall(r'Answer:\s*\(?([ABCD])\b', content or '')
        return {'pred': m[-1] if m else None,
                'correct': (m[-1] == 'ABCD'[it['answer_index']]) if m else False}
    if task == 'math20':
        nums = re.findall(r'-?\d[\d,]*\.?\d*', (content or '').replace('$', ''))
        pred = nums[-1].replace(',', '') if nums else None
        try:
            ok = pred is not None and abs(float(pred) - float(it['answer'])) < 1e-6
        except Exception:
            ok = False
        return {'pred': pred, 'correct': ok}
    if task == 'math500':
        b = BOX.findall(content or '')
        pred = b[-1].strip() if b else None
        if pred is None:
            m = re.findall(r'(?:final answer|answer is)\s*[:=]?\s*(.+)', (content or ''), re.I)
            pred = m[-1].strip() if m else None
        return {'pred': pred, 'gold': it['answer'], 'correct': None}
    return {'pred': content, 'correct': None}


summaries = {}
for task in TASKS:
    pack, _, temp, maxt = PACKS[task]
    items = [json.loads(l) for l in open(pack) if l.strip()]
    if task in LIMIT:
        items = items[:LIMIT[task]]
    out_path = os.path.join(OUTDIR, f'{LABEL}.{task}.jsonl')
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path):
            try:
                done.add(json.loads(l)['id'])
            except Exception:
                pass
    print(f'== {task}: {len(items)} items, {len(done)} already done', flush=True)
    with open(out_path, 'a') as f:
        for k, it in enumerate(items):
            if it['id'] in done:
                continue
            payload = {
                'messages': [{'role': 'user', 'content': prompt_for(task, it)}],
                'temperature': temp, 'top_p': 1.0, 'max_tokens': maxt, 'seed': 42,
                'chat_template_kwargs': {'enable_thinking': False},
                'cache_prompt': False,
            }
            t0 = time.time()
            try:
                body, wall = post('/v1/chat/completions', payload)
            except Exception as e:
                rec = {'id': it['id'], 'error': repr(e), 'wall_s': round(time.time() - t0, 2)}
                f.write(json.dumps(rec) + '\n'); f.flush()
                print(' ERR', it['id'], repr(e)[:120], flush=True)
                continue
            ch = body['choices'][0]
            msg = ch.get('message', {})
            content = msg.get('content') or ''
            reason = msg.get('reasoning_content') or ''
            usage = body.get('usage', {})
            tm = body.get('timings', {}) or {}
            rec = {
                'id': it['id'], 'task': task, 'wall_s': round(wall, 2),
                'prompt_tokens': usage.get('prompt_tokens'),
                'completion_tokens': usage.get('completion_tokens'),
                'reasoning_chars': len(reason), 'content_chars': len(content),
                'predicted_per_second': tm.get('predicted_per_second'),
                'prompt_per_second': tm.get('prompt_per_second'),
                'finish': ch.get('finish_reason'),
                'content': content, 'reasoning': reason[:2000],
            }
            rec.update(postproc(task, it, content))
            f.write(json.dumps(rec) + '\n'); f.flush()
            print(f" [{k+1}/{len(items)}] {it['id']} tok={rec['completion_tokens']} "
                  f"wall={rec['wall_s']}s tps={rec['predicted_per_second']} "
                  f"corr={rec.get('correct')}", flush=True)
    recs = [json.loads(l) for l in open(out_path)]
    ok = [r for r in recs if r.get('correct') is not None]
    summaries[task] = {
        'n': len(recs), 'scored': len(ok),
        'score': (sum(1 for r in ok if r['correct']) / len(ok)) if ok else None,
        'tokens': sum(r.get('completion_tokens') or 0 for r in recs),
        'wall_s': round(sum(r.get('wall_s') or 0 for r in recs), 1),
        'errors': sum(1 for r in recs if r.get('error')),
    }

print(json.dumps({'label': LABEL, 'tasks': summaries}, indent=1))
json.dump({'label': LABEL, 'tasks': summaries},
          open(os.path.join(OUTDIR, f'{LABEL}.summary.json'), 'w'), indent=1)
