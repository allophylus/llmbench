#!/usr/bin/env python3
"""diff_gguf.py — tensor-level integrity diff between the stock and WSP Q4_K_M GGUFs.

Two questions:
  1. structural: same tensor count / names / shapes / quant types?
  2. substantive: where do the values actually differ, and is the difference
     concentrated in model.language_model.layers.29.mlp.down_proj (the tensor the
     upstream card says was edited)?

Because both files are Q4_K_M but may come from different quantizer runs, raw-byte
inequality everywhere is expected noise. The discriminating statistic is the
per-column RMS difference in dequantized weight space: an edit of the form
W[:,S] -= alpha*u*q^T leaves a large, structured signal in the selected columns,
far above quantisation noise.
"""
import json, sys
import numpy as np
import gguf
from gguf.quants import dequantize

STOCK = '/home/ubuntu/models/Qwen3.8-27B-Q4_K_M.gguf'
WSP = '/home/ubuntu/models/qwen38fn/wsp-bench/Qwen3.8-27B-WSP-Q4_K_M.gguf'

r_s = gguf.GGUFReader(STOCK, 'r')
r_w = gguf.GGUFReader(WSP, 'r')

def info(reader):
    out = {}
    for t in reader.tensors:
        out[t.name] = dict(shape=[int(x) for x in t.shape], type=str(t.tensor_type.name),
                           n_bytes=int(t.n_bytes))
    return out

a, b = info(r_s), info(r_w)
rep = {'stock': STOCK, 'wsp': WSP,
       'stock_n_tensors': len(a), 'wsp_n_tensors': len(b),
       'names_equal': sorted(a) == sorted(b),
       'shape_or_type_mismatch': []}
for n in sorted(set(a) & set(b)):
    if a[n]['shape'] != b[n]['shape'] or a[n]['type'] != b[n]['type']:
        rep['shape_or_type_mismatch'].append({'tensor': n, 'stock': a[n], 'wsp': b[n]})
rep['only_stock'] = sorted(set(a) - set(b))
rep['only_wsp'] = sorted(set(b) - set(a))

_CACHE = {}
def tens(reader, name):
    key = id(reader)
    if key not in _CACHE:
        _CACHE[key] = {t.name: t for t in reader.tensors}
    return _CACHE[key][name]

# --- raw byte comparison by tensor (cheap: n_bytes equality) ---
byte_diff = {}
for n in sorted(set(a) & set(b)):
    ts, tw = tens(r_s, n), tens(r_w, n)
    if ts.data.nbytes != tw.data.nbytes:
        byte_diff[n] = {'bytes_stock': int(ts.data.nbytes), 'bytes_wsp': int(tw.data.nbytes)}
        continue
    d = ts.data.view(np.uint8) != tw.data.view(np.uint8)
    byte_diff[n] = {'n_bytes': int(ts.data.nbytes), 'diff_bytes': int(d.sum()),
                    'diff_frac': round(float(d.mean()), 8)}
rep['byte_diff_by_tensor'] = byte_diff

# --- dequantized per-tensor + per-column RMS on the target tensor ---
def deq(reader, name):
    t = tens(reader, name)
    arr = dequantize(t.data, t.tensor_type)
    return np.asarray(arr).reshape(tuple(reversed(t.shape))).astype(np.float32)

TARGET = 'blk.29.ffn_down.weight'
col_report = {}
if TARGET in a and TARGET in b:
    ws, ww = deq(r_s, TARGET), deq(r_w, TARGET)
    d = ww - ws
    rms_s = float(np.sqrt((ws.astype(np.float64) ** 2).mean()))
    col_rms = np.sqrt((d.astype(np.float64) ** 2).mean(axis=0))   # per input column
    # noise floor from the quietest 50% of columns
    q = np.quantile(col_rms, 0.5)
    thr = max(q * 4, 1e-6)
    sel = np.where(col_rms > thr)[0]
    col_report = {
        'tensor': TARGET, 'np_shape': list(ws.shape), 'quant': b[TARGET]['type'],
        'weight_rms': rms_s,
        'total_rel_rms': float(np.sqrt((d.astype(np.float64) ** 2).mean()) / rms_s),
        'per_col_rms_median': float(np.median(col_rms)),
        'per_col_rms_max': float(col_rms.max()),
        'cols_above_threshold': int(len(sel)),
        'threshold': float(thr),
        'selected_col_range': [int(sel.min()), int(sel.max())] if len(sel) else None,
        'n_cols': int(col_rms.size),
        'frac_values_changed_gt_1e-3': float((np.abs(d) > 1e-3).mean()),
        'cols_first10': [float(x) for x in col_rms[:10]],
    }
    np.save('/home/ubuntu/wsp-bench/col_rms_l29_down.npy', col_rms)
rep['target_tensor'] = col_report

# --- control: relative RMS for a spread of untouched tensors ---
controls = {}
names = [n for n in sorted(a) if n in b and n != TARGET]
step = max(1, len(names) // 12)
for n in names[::step][:12]:
    try:
        ws, ww = deq(r_s, n), deq(r_w, n)
        if ws.shape != ww.shape:
            continue
        rms = float(np.sqrt((ws.astype(np.float64) ** 2).mean())) or 1.0
        controls[n] = {'shape': list(ws.shape), 'type': b[n]['type'],
                       'rel_rms': float(np.sqrt(((ww - ws).astype(np.float64) ** 2).mean()) / rms),
                       'frac_neq': float((ws != ww).mean())}
    except Exception as e:
        controls[n] = {'error': repr(e)}
rep['controls'] = controls

json.dump(rep, open('/home/ubuntu/wsp-bench/diff_report.json', 'w'), indent=1, default=str)

# --- human-readable report ---
with open('/home/ubuntu/wsp-bench/diff_report.txt', 'w') as f:
    f.write('GGUF integrity diff: stock Q4_K_M vs WSP Q4_K_M\n')
    f.write('=' * 72 + '\n')
    f.write(f"tensors: stock={rep['stock_n_tensors']} wsp={rep['wsp_n_tensors']} "
            f"names_equal={rep['names_equal']}\n")
    f.write(f"shape/type mismatches: {len(rep['shape_or_type_mismatch'])}\n")
    f.write(f"only in stock: {rep['only_stock']}\nonly in wsp: {rep['only_wsp']}\n\n")
    nd = [n for n, v in byte_diff.items() if v.get('diff_bytes')]
    f.write(f'tensors with >=1 differing byte: {len(nd)} / {len(byte_diff)}\n')
    tot_b = sum(v.get('n_bytes', 0) for v in byte_diff.values())
    tot_d = sum(v.get('diff_bytes', 0) for v in byte_diff.values())
    if tot_b:
        f.write(f'total bytes differ: {tot_d}/{tot_b} = {100*tot_d/tot_b:.6f}%\n')
    f.write('\nTop 10 tensors by differing-byte fraction:\n')
    for n, v in sorted(byte_diff.items(), key=lambda kv: -kv[1].get('diff_frac', 0))[:10]:
        f.write(f"  {n:44s} {v.get('diff_frac', 0)*100:9.5f}%  type={b[n]['type']}\n")
    f.write('\nTarget tensor (edited per upstream card):\n')
    for k, v in col_report.items():
        f.write(f'  {k}: {v}\n')
    f.write('\nControl tensors (should be pure quantisation noise):\n')
    for n, v in controls.items():
        if 'rel_rms' in v:
            f.write(f"  {n:44s} rel_rms={v['rel_rms']:.6f} frac_neq={v['frac_neq']*100:.4f}% type={v['type']}\n")
print(open('/home/ubuntu/wsp-bench/diff_report.txt').read())
