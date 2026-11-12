#!/bin/bash
# Train a character LoRA for Qwen-Image-2.1(-Turbo) on the NPU.
#
#   STEPS=400 DATA=/home/vllm/ai-musume/lora_data/train_mix bash train_lora.sh
#   STEPS=20  ...                                     # smoke: does it start?
#
# DATA is a flat folder of images. `train_mix` = 8 real frames from the show +
# 16 generated images — the real ones are what teach the actual design, the
# generated ones add pose/scene variety.
#
# Measured on .190: 1.39 s/step, so 400 steps ≈ 9.5 min, output ≈ 33 MB.
set -u
cd /home/vllm/ai-musume || exit 1
V=/home/vllm/ai-musume/venv-qwen
S=/home/vllm/ai-musume/cache/diffusers-main/examples/dreambooth/train_dreambooth_lora_qwenimage21.py
D=${DATA:-/home/vllm/ai-musume/lora_data/train_mix}
OUT=${OUT:-/home/vllm/ai-musume/lora_data/whale_lora_mix}
STEPS=${STEPS:-400}
RES=${RES:-1024}
RANK=${RANK:-16}
LR=${LR:-1e-4}

[ -d "$D" ] || { echo "no data dir: $D"; exit 1; }
echo "data=$D  images=$(ls -1 "$D" | wc -l)  steps=$STEPS  rank=$RANK  lr=$LR"
rm -rf "$OUT"; mkdir -p "$OUT"

export ASCEND_RT_VISIBLE_DEVICES=${DEV:-8}
export OMP_NUM_THREADS=8
export HF_HUB_OFFLINE=1

"$V/bin/python" "$S" \
  --pretrained_model_name_or_path /home/vllm/ai-musume/models/qwen-image-2.1-turbo \
  --instance_data_dir "$D" \
  --instance_prompt "whale_chan, a girl with long blue hair fading to lighter tips, white lace maid headdress, navy blue dress, white ruffled blouse front, blue ribbon bow at collar, blue eyes, ahoge" \
  --output_dir "$OUT" \
  --rank "$RANK" --resolution "$RES" --center_crop \
  --train_batch_size 1 --max_train_steps "$STEPS" --learning_rate "$LR" \
  --gradient_checkpointing --mixed_precision bf16 \
  --checkpointing_steps 100000 --lr_scheduler constant \
  2>&1 | tail -12

echo "=== output ==="
ls -l "$OUT" 2>&1 | tail -3
