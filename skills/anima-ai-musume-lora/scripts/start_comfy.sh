#!/bin/bash
. /home/cann/921/ascend-toolkit/set_env.sh
export LD_LIBRARY_PATH=/home/vllm/x00886548/env/compat_lib:$LD_LIBRARY_PATH
export ASCEND_RT_VISIBLE_DEVICES=4
export TMPDIR=/home/vllm/x00886548/env/pkgs/tmp
cd /home/vllm/x00886548/work/anima-comfy || exit 1
P=/home/vllm/x00886548/env/conda_envs/anima/bin/python
mkdir -p models/diffusion_models models/text_encoders models/vae models/loras
ln -sfn /home/vllm/ai-musume/anima/diffusion_models/anima-aesthetic-v1.1.safetensors models/diffusion_models/
ln -sfn /home/vllm/ai-musume/anima/diffusion_models/anima-turbo-v1.1.safetensors models/diffusion_models/
ln -sfn /home/vllm/ai-musume/anima/text_encoders/qwen_3_06b_base.safetensors models/text_encoders/
ln -sfn /home/vllm/ai-musume/anima/vae/qwen_image_vae.safetensors models/vae/
if [ -d /home/vllm/ai-musume/anima/loras ]; then
  for f in /home/vllm/ai-musume/anima/loras/*.safetensors; do [ -e "$f" ] && ln -sfn "$f" models/loras/; done
fi
exec $P main.py --listen 0.0.0.0 --port 18188 --highvram --bf16-unet --bf16-text-enc --preview-method none $EXTRA_ARGS
