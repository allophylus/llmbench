#!/usr/bin/env python3
"""llmbench H3 video baseline payload — identical prompt/settings for every machine."""
import json, sys, hashlib

PROMPT = "/tmp/h3_bench_prompt.txt"
txt = open(PROMPT).read()

LENGTH   = 240      # 10.0 s @ 24 fps
SEED     = 2223112508
STEPS    = 20
MP       = 0.5
FPS      = 24
AUDIO    = "roadster_b1_ryan_l1.flac"   # cloned ryan voice ref (2.80 s spoken line, in ComfyUI input/)
PREFIX   = sys.argv[1] if len(sys.argv) > 1 else "video/h3__rtx3090__10s"

g = {
 "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
 "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
 "3": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
 "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
 "5": {"class_type": "ResolutionSelector", "inputs": {"aspect_ratio": "16:9 (Widescreen)", "megapixels": MP, "multiple": 32}},
 "6": {"class_type": "PrimitiveInt", "inputs": {"value": LENGTH}},
 "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
 "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
 "9": {"class_type": "BasicScheduler", "inputs": {"model": ["1", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1}},
 "11": {"class_type": "LoadImage", "inputs": {"image": "ryan_reference.jpg"}},
 "13": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": txt}},
 "A1": {"class_type": "LoadAudio", "inputs": {"audio": AUDIO}},
}
g["10"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
    "clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0], "prompt": ["13", 0],
    "width": ["5", 0], "height": ["5", 1], "length": ["6", 0], "ref_image_size": "max",
    "ref_images.ref_image_0": ["11", 0], "ref_audios.ref_audio_0": ["A1", 0]}}
g["24"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": ["10", 0], "latent": ["10", 1], "vae": ["3", 0], "image": ["11", 0], "frame_idx": 0, "audio_vae": ["4", 0]}}
g["16"] = {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["24", 0]}}
g["17"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["7", 0], "guider": ["16", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["10", 1]}}
g["18"] = {"class_type": "VAEDecode", "inputs": {"samples": ["17", 0], "vae": ["3", 0]}}
g["19"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["17", 0], "vae": ["4", 0]}}
g["20"] = {"class_type": "CreateVideo", "inputs": {"images": ["18", 0], "audio": ["19", 0], "fps": FPS, "bit_depth": 8}}
g["21"] = {"class_type": "SaveVideo", "inputs": {"video": ["20", 0], "filename_prefix": PREFIX, "format": "mp4", "codec": "auto"}}

out = "/tmp/h3_bench_payload.json"
json.dump({"prompt": g, "client_id": "llmbench-h3-baseline"}, open(out, "w"))
print(f"wrote {out} length={LENGTH} seed={SEED} steps={STEPS} mp={MP} fps={FPS}")
print("prompt_sha256:", hashlib.sha256(txt.encode()).hexdigest())
