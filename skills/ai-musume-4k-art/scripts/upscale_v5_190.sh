#!/bin/bash
# 4K for the v5 picks, with a stronger progressive denoise (0.32) so the upscale ADDS detail
# instead of just smoothing (the user's complaint was "精细度").
cd /home/vllm/ai-musume || exit 1
L=logs/v5k_$(date +%H%M%S).log
exec >"$L" 2>&1
echo "log=$L"
export SDXL_MODEL_DIR=/home/vllm/ai-musume/models/illustrious-xl
SCENE="portrait, close-up, simple background"

up() {  # $1=char $2=seed $3=tags
  bash run_gen190.sh gen --char "$1" --seed "$2" --tag v5k \
    --init "/home/vllm/ai-musume/out/$1_v5_$2.png" \
    --target 2560x3840 --upscale progressive --tile-denoise 0.32 --tile-steps 30 \
    --hires 1.0 --no-ip --style refine --steps 36 --cfg 5.2 --scheduler euler_a \
    --scene "$SCENE" --tags "$3"
}

up claude   4242 "orange hair, long hair, orange eyes, flower hair ornament, black ribbon, white blouse, brooch, gentle smile"
up deepseek 3131 "dark blue hair, gradient hair, very long hair, blue eyes, ahoge, maid, maid headdress, blue hair ribbon, white apron, navy blue dress, blue gem brooch, smile"
up gpt      4242 "white hair, very long hair, purple eyes, white horn, white dress, bare shoulders, expressionless"
up grok     4242 "blonde hair, long hair, blue eyes, bat wings, black crown, red gem, black gothic dress, smirk"
up gemini   3131 "purple hair, drill hair, twintails, heterochromia, pink eyes, yellow eyes, star hair ornament, purple dress, open mouth, smile"
up qwen     3131 "black hair, bob cut, side part, brown eyes, black shirt, blush, gentle smile"

echo DONE
