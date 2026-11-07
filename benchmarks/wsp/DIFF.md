# Weight-space diff: does the edit survive Q4_K_M?

Two public files were compared on the same card:

| file | bytes | provenance |
|---|---:|---|
| `Qwen3.8-27B-Q4_K_M.gguf` (the serving baseline) | 16,464,440,224 | existing local file, 9 Oct 2026 |
| `Qwen3.8-27B-WSP-Q4_K_M.gguf` | 16,810,715,616 | `mradermacher/Qwen3.8-27B-Weight-Space-Programming-GGUF`, downloaded 7 Nov 2026 |

Both carry the `GGUF` magic; both have **866 tensors with identical names, shapes and
order**, so the two files are the same architecture and vocabulary.

## Finding 1 — the "Q4_K_M" baseline is not a uniform Q4_K_M file

417 of 866 tensors differ in *quantisation type* between the two files:

| tensor types in the baseline → WSP | tensors |
|---|---:|
| Q5_K → Q4_K | 111 |
| IQ4_XS → Q4_K | 102 |
| Q8_0 → Q4_K | 101 |
| Q6_K → Q4_K | 26 |
| Q5_K → Q6_K | 20 |
| Q4_K → Q6_K | 19 |
| IQ4_XS → Q6_K | 15 |
| Q3_K → Q4_K | 6 |
| Q8_0 → Q6_K | 5 |
| IQ3_S → Q4_K | 4 |

The local baseline is a mixed/dynamic-precision build (Q5_K, IQ4_XS and Q8_0 tensors
side by side) that its filename labels Q4_K_M. The WSP file is a standard uniform
mradermacher Q4_K_M. **Any behavioural difference between the two therefore mixes the
weight edit with a precision difference**, and no byte-level test can attribute the
difference to the edit alone. This is a real limitation of comparing published
releases rather than re-quantising one checkpoint twice.

Only 103/866 tensors differ in their raw bytes at all (25.96% of total tensor bytes);
the F32 tensors (norms, conv) are **bit-identical**, which confirms both files were
built from the same base weights.

## Finding 2 — the documented edit is present, and at the documented magnitude

The upstream card (`MODIFICATIONS.md`) states the edit is exactly one tensor:

> Modified tensor: `model.language_model.layers.29.mlp.down_proj.weight`
> 19,680,881 stored BF16 values within 4,096 selected input columns of layer 29
> final stored perturbation L2 norm, measured in float64: **7.4606041947214665**

`blk.29.ffn_down.weight` is 5120×17408 in both files. Dequantising both and taking
`D = W_wsp − W_stock`, the leading singular value of D is:

| tensor | ‖D‖_F | σ₁ | σ₂ | σ₁/σ₂ |
|---|---:|---:|---:|---:|
| **blk.29.ffn_down** | 13.69 | **7.438** | 0.505 | **14.7** |
| blk.27.ffn_down (control) | 8.69 | 0.424 | 0.195 | 2.2 |
| blk.29.ffn_gate (control) | 11.25 | 0.288 | 0.261 | 1.1 |

σ₁ = 7.438 against the documented perturbation norm of 7.4606 is a **0.3% difference** —
the size of the residual you expect when the edited float32 weights are re-quantised to
4-bit. Untouched tensors in the same layer show no such component (σ₁ ≈ 0.29–0.42, i.e.
15–25× smaller), and their spectra are flat (σ₁/σ₂ ≈ 1–2) as pure quantisation noise
should be. The top rank-1 component carries 29.5% of D's energy in the edited tensor
versus 0.07–0.24% in the controls.

**Conclusion: the weight edit survives Q4_K_M quantisation and is present in the
published GGUF at the claimed magnitude.** What cannot be shown from the files alone is
how much of the *behavioural* change comes from the edit and how much from the
precision difference described above — that is what the A/B measures.

## Reproduce

```bash
python3 diff_gguf.py    # tensor census, type transitions, byte diffs -> diff_report.txt
python3 svd_probe.py    # power-iteration σ₁/σ₂ on the edited tensor + controls -> svd_probe.json
```

Both need `pip install gguf numpy`. The originals are the two files named at the top;
edit the two paths in each script.
