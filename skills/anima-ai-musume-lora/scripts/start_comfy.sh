#!/bin/bash
: "${CANN_ENV_SCRIPT:?set the verified CANN environment script}"
: "${ANIMA_COMFY_DIR:?set the verified ComfyUI checkout}"
: "${ANIMA_PYTHON:?set the verified Python executable}"
: "${ANIMA_MODEL_DIR:?set the verified model directory}"
: "${ASCEND_RT_VISIBLE_DEVICES:?set the assigned device using the current host mapping}"
[ -f "$CANN_ENV_SCRIPT" ] && [ -d "$ANIMA_COMFY_DIR" ] &&
  [ -x "$ANIMA_PYTHON" ] && [ -d "$ANIMA_MODEL_DIR" ] || {
  printf '%s\n' 'Verify the configured environment paths.' >&2
  exit 2
}
. "$CANN_ENV_SCRIPT" || exit 1
export ASCEND_RT_VISIBLE_DEVICES
cd "$ANIMA_COMFY_DIR" || exit 1
mkdir -p models/diffusion_models models/text_encoders models/vae models/loras
ln -sfn "$ANIMA_MODEL_DIR"/diffusion_models/anima-aesthetic-v1.1.safetensors models/diffusion_models/
ln -sfn "$ANIMA_MODEL_DIR"/diffusion_models/anima-turbo-v1.1.safetensors models/diffusion_models/
ln -sfn "$ANIMA_MODEL_DIR"/text_encoders/qwen_3_06b_base.safetensors models/text_encoders/
ln -sfn "$ANIMA_MODEL_DIR"/vae/qwen_image_vae.safetensors models/vae/
if [ -d "$ANIMA_MODEL_DIR"/loras ]; then
  for f in "$ANIMA_MODEL_DIR"/loras/*.safetensors; do [ -e "$f" ] && ln -sfn "$f" models/loras/; done
fi
exec "$ANIMA_PYTHON" main.py --listen 0.0.0.0 --port 18188 --highvram --bf16-unet --bf16-text-enc --preview-method none $EXTRA_ARGS
