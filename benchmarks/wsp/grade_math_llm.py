#!/usr/bin/env python3
"""grade_math_llm.py — blind final-answer grading for MATH-500 spot checks.

For each stored completion: give an independent model the reference answer only
(never which arm produced it) and ask whether the response's *final stated answer*
is mathematically equivalent. Returns YES/NO + the answer the response commits to,
so mismatches can be audited.
"""
import json, os, sys, time, urllib.request

SRC = sys.argv[1]
KEY = os.environ['DEEPSEEK_API_KEY']
SYS = ("You are a strict mathematics grader. You are given a REFERENCE ANSWER and a "
       "model's full solution text. Decide only whether the solution's final committed "
       "answer is mathematically equivalent to the reference answer. Ignore reasoning "
       "style, length and intermediate slips. Equivalent forms count (0.5 = 1/2, "
       "pi/2 = \\frac{\\pi}{2}, degrees written with or without ^\\circ). If the solution "
       "never commits to a final answer, answer NO.")
TPL = ('REFERENCE ANSWER:\n{gold}\n\n---\nSOLUTION TEXT:\n{sol}\n---\n\n'
       'Reply with exactly two lines:\nFINAL: <the answer the solution commits to, or NONE>\n'
       'VERDICT: YES or NO')


def ask(gold, sol):
    body = {'model': 'deepseek-chat',
            'messages': [{'role': 'system', 'content': SYS},
                         {'role': 'user', 'content': TPL.format(gold=gold, sol=sol[-7000:])}],
            'temperature': 0, 'max_tokens': 200}
    for a in range(4):
        try:
            req = urllib.request.Request('https://api.deepseek.com/v1/chat/completions',
                                         data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json',
                                                  'Authorization': f'Bearer {KEY}'})
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = json.load(r)['choices'][0]['message']['content']
            fin = re_final(txt)
            ver = 'YES' in (re_verdict(txt) or '').upper()
            return ver, fin, txt
        except Exception as e:
            print('  retry', a + 1, repr(e)[:100], flush=True)
            time.sleep(2 + 2 * a)
    return None, None, ''


def re_final(t):
    for l in t.splitlines():
        if l.upper().startswith('FINAL:'):
            return l.split(':', 1)[1].strip()
    return None


def re_verdict(t):
    for l in t.splitlines():
        if l.upper().startswith('VERDICT:'):
            return l.split(':', 1)[1].strip()
    return t.strip().splitlines()[-1] if t.strip() else ''


rows = []
for line in open(SRC):
    r = json.loads(line)
    v, fin, raw = ask(r['gold'], r.get('content', ''))
    rows.append({'id': r['id'], 'gold': r['gold'], 'judge_final': fin, 'correct': bool(v),
                 'tokens': r.get('completion_tokens'), 'finish': r.get('finish')})
    print(f"{r['id']:14s} {'OK ' if v else 'ERR'} final={str(fin)[:34]:36s} gold={str(r['gold'])[:26]}", flush=True)
    json.dump(rows, open(SRC.replace('.jsonl', '.llmjudged.json'), 'w'), indent=1)
n = len(rows); c = sum(1 for x in rows if x['correct'])
print(f"\n{SRC}: {c}/{n} = {c/max(n,1):.3f}")
