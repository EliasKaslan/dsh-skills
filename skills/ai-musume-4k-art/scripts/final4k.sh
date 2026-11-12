#!/bin/bash
cd /home/vllm/ai-musume
for c in claude deepseek gpt grok gemini qwen; do
  bash run_gen.sh gen --char $c --seed 4242 --hires 1.0 \
    --init /work/out/init/${c}_base.png \
    --target 2560x3840 --upscale progressive --tile-denoise 0.22 --tile-steps 26 \
    --no-ip --tag 4k
done
