#!/bin/bash
# v5 (final direction): Illustrious + `refine` (soft gradient shading, fine lines) +
# close-up portrait framing. 6 characters x 2 seeds.
cd /home/vllm/ai-musume || exit 1
L=logs/v5_$(date +%H%M%S).log
exec >"$L" 2>&1
echo "log=$L"
export SDXL_MODEL_DIR=/home/vllm/ai-musume/models/illustrious-xl
SCENE="portrait, close-up, simple background"

g() {  # $1=char $2=seed $3=tags
  bash run_gen190.sh gen --char "$1" --tag v5 --seed "$2" --steps 36 --cfg 5.2 \
    --base 896x1344 --scheduler euler_a --no-ip --style refine \
    --scene "$SCENE" --tags "$3"
}

for sd in 3131 4242; do
  g claude   $sd "orange hair, long hair, orange eyes, flower hair ornament, black ribbon, white blouse, brooch, gentle smile"
  g deepseek $sd "dark blue hair, gradient hair, very long hair, blue eyes, ahoge, maid, maid headdress, blue hair ribbon, white apron, navy blue dress, blue gem brooch, smile"
  g gpt      $sd "white hair, very long hair, purple eyes, white horn, white dress, bare shoulders, expressionless"
  g grok     $sd "blonde hair, long hair, blue eyes, bat wings, black crown, red gem, black gothic dress, smirk"
  g gemini   $sd "purple hair, drill hair, twintails, heterochromia, pink eyes, yellow eyes, star hair ornament, purple dress, open mouth, smile"
  g qwen     $sd "black hair, bob cut, side part, brown eyes, black shirt, blush, gentle smile"
done

echo DONE
