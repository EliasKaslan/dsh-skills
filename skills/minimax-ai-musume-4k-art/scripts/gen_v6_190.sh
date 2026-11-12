#!/bin/bash
# v6: refined re-render anchored on the official single-character crops.
# init = refs_cover/<char>.png, denoise 0.65 (keeps the official rendering quality but
# the prompt/seed drive a new render). Qwen has no 2D official art -> text-to-image.
cd /home/vllm/ai-musume || exit 1
L=logs/v6_$(date +%H%M%S).log
exec >"$L" 2>&1
echo "log=$L"
export SDXL_MODEL_DIR=/home/vllm/ai-musume/models/illustrious-xl
SCENE="upper body, simple background"

g() {  # $1=char $2=seed $3=tags $4=init(optional)
  local extra=""
  if [ -n "${4:-}" ]; then extra="--init /home/vllm/ai-musume/refs_cover/$4 --init-denoise 0.65"; fi
  bash run_gen190.sh gen --char "$1" --tag v6 --seed "$2" --steps 36 --cfg 5.2 \
    --base 896x1344 --scheduler euler_a --no-ip --style refine \
    --scene "$SCENE" --tags "$3" $extra
}

for sd in 3131 4242; do
  g claude   $sd "orange hair, long hair, orange eyes, flower hair ornament, black ribbon, white blouse, brooch, gentle smile" claude.png
  g deepseek $sd "dark blue hair, gradient hair, very long hair, blue eyes, ahoge, maid, maid headdress, blue hair ribbon, white apron, navy blue dress, blue gem brooch, smile" deepseek.png
  g gpt      $sd "white hair, very long hair, purple eyes, white horn, white dress, bare shoulders, expressionless" gpt.png
  g grok     $sd "blonde hair, long hair, blue eyes, bat wings, black crown, red gem, black gothic dress, smirk" grok.png
  g gemini   $sd "purple hair, drill hair, twintails, heterochromia, pink eyes, yellow eyes, star hair ornament, purple dress, open mouth, smile" gemini.png
  g qwen     $sd "black hair, bob cut, side part, brown eyes, black shirt, blush, gentle smile" ""
done

echo DONE
