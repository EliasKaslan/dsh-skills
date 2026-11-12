#!/usr/bin/env python3
"""Minimal ComfyUI API client for Anima text2img on 190."""
import argparse, json, os, sys, time
import requests


def build(prompt, negative, seed, steps, cfg, sampler, scheduler, w, h,
          unet, clip, vae, prefix, batch=1, lora=None, lora_strength=1.0):
    wf = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": clip, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "6": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": w, "height": h, "batch_size": batch}},
        "7": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": sampler, "scheduler": scheduler,
                         "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["6", 0], "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }
    if lora:
        wf["10"] = {"class_type": "LoraLoaderModelOnly",
                    "inputs": {"lora_name": lora, "strength_model": lora_strength, "model": ["1", 0]}}
        wf["7"]["inputs"]["model"] = ["10", 0]
    return wf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:18188")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default="photorealistic, 3d render, realistic photo, text, watermark, signature, blurry, low quality, multiple girls, extra limbs")
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--scheduler", default="simple")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=1536)
    ap.add_argument("--unet", default="anima-aesthetic-v1.1.safetensors")
    ap.add_argument("--clip", default="qwen_3_06b_base.safetensors")
    ap.add_argument("--vae", default="qwen_image_vae.safetensors")
    ap.add_argument("--prefix", default="anima/test")
    ap.add_argument("--lora", default=None)
    ap.add_argument("--lora-strength", type=float, default=1.0)
    ap.add_argument("--outdir", default="/home/vllm/ai-musume/anima/out")
    ap.add_argument("--timeout", type=float, default=900)
    args = ap.parse_args()

    wf = build(args.prompt, args.negative, args.seed, args.steps, args.cfg,
               args.sampler, args.scheduler, args.width, args.height,
               args.unet, args.clip, args.vae, args.prefix,
               lora=args.lora, lora_strength=args.lora_strength)
    t0 = time.time()
    r = requests.post(args.host + "/prompt", json={"prompt": wf}, timeout=60)
    if r.status_code != 200:
        print("POST /prompt failed", r.status_code, r.text[:800])
        sys.exit(2)
    pid = r.json()["prompt_id"]
    print("queued", pid, flush=True)
    while time.time() - t0 < args.timeout:
        time.sleep(1.5)
        h = requests.get(args.host + "/history/" + pid, timeout=30).json()
        if pid in h:
            entry = h[pid]
            if entry.get("status", {}).get("status_str") == "error":
                print("ERROR", json.dumps(entry.get("status"))[:800])
                sys.exit(3)
            outs = entry.get("outputs", {}).get("9", {}).get("images", [])
            if not outs:
                print("no images", json.dumps(entry)[:500])
                sys.exit(4)
            os.makedirs(args.outdir, exist_ok=True)
            saved = []
            for im in outs:
                q = {"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                     "type": im.get("type", "output")}
                data = requests.get(args.host + "/view", params=q, timeout=120).content
                dst = os.path.join(args.outdir, im["filename"])
                with open(dst, "wb") as f:
                    f.write(data)
                saved.append(dst)
            dt = time.time() - t0
            print("OK %.2fs %s" % (dt, " ".join(saved)))
            print(json.dumps({"elapsed_s": round(dt, 2), "seed": args.seed,
                              "steps": args.steps, "cfg": args.cfg,
                              "size": [args.width, args.height],
                              "files": saved}, ensure_ascii=False))
            return
        st = requests.get(args.host + "/queue", timeout=30).json()
        run = st.get("queue_running", [])
        if not run and not st.get("queue_pending"):
            pass
    print("TIMEOUT after", args.timeout)
    sys.exit(5)


if __name__ == "__main__":
    main()
