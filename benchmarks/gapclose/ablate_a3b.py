#!/usr/bin/env python3
"""ablate_a3b.py -- reuse ablate2.py's measurement plan for Qwen3.6-35B-A3B.

Loads ablate2.py's module-level definitions into a namespace, overrides the model paths,
flags and arm set for A3B, then calls its main(). Same method, different model.
"""
import os
import sys

_D = open(os.path.join(os.environ.get("BENCHWORK","/bench-work"),"ablate2.py")).read().split('if __name__ == "__main__":')[0]
ns = {'__name__': 'ablate2_a3b', '__builtins__': __builtins__}
exec(compile(_D, 'ablate2.py', 'exec'), ns)

# --- A3B overrides ---
ns['MODEL_FILE'] = 'qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf'
ns['MMPROJ_FILE'] = 'qwen36/mmproj-Qwen3.6-35B-A3B-F16.gguf'
ns['GLOBAL_FLAGS'] = ['--host', '0.0.0.0', '--port', '8080', '-c', '131072', '-ngl', '99', '--jinja',
                     '-b', '16384', '-ub', '2048', '--cache-type-k', 'q8_0', '--cache-type-v', 'q4_0',
                     '--cache-reuse', '256', '--metrics']
ns['PREFILL_JSON'] = os.path.join(os.environ.get("BENCHWORK","/bench-work"),"ablation_a3b","_prefill_30k.txt")
ns['ARMS'] = {
    '1-baseline':   {'fa': 'on',  'extra': []},
    '2-fa-off':     {'fa': 'off', 'extra': [], 'kv': ns['KVF16'],
                     'note': 'q8_0K/q4_0V requires FA; FA-off only runnable with f16 KV'},
    '3-mtp':        {'fa': 'on',  'extra': ns['MTP']},
    '4-dflash':     {'fa': 'on',  'extra': ns['DFLASH_FLAGS'] + ['--spec-draft-n-max', '7']},
    '5a-mtp-ngram': {'fa': 'on',  'extra': ns['MTP_NGRAM']},
    '5b-dflash':    {'fa': 'on',  'extra': ns['DFLASH_FLAGS']},
    '6-dflash-fa-off': {'fa': 'off', 'extra': ns['DFLASH_FLAGS'], 'kv': ns['KVF16']},
}

# DFlash2 drafter is a Qwen3.8 (qwen35) drafter; A3B is qwen3.6 MoE. The DFlash arms will
# fail server-side (arch mismatch / no MTP layers); ablate2.py records that as the arm's
# evidence. MTP arms depend on the A3B GGUF carrying nextn (MTP) tensors.

if __name__ == '__main__':
    ns['main'] = ns['main']
    sys.exit(ns['main']())
