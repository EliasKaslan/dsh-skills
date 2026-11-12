#!/bin/bash
# One-time setup for the Qwen-Image-2.1 path on .190 (CANN 9.2.0 stack).
#
# Builds a side venv because:
#   - the MindSpeed ops image ships torch/torch_npu but NO diffusers/transformers;
#   - QwenImage21Pipeline needs diffusers >= 0.42.0.dev0, which is not on PyPI
#     (PyPI tops out at 0.36; the image's own copy is 0.37).
#
# The venv must be built with THIS image's interpreter. A venv built against
# another image keeps a dangling python symlink and fails with
#   bash: venv/bin/python: No such file or directory
# Re-run this script after changing the base image.
#
# Run inside the container:
#   bash setup_qwen_runtime.sh
set -u
W=/home/vllm/ai-musume
V=$W/venv-qwen
SRC=$W/cache/diffusers-main
TAR=$W/cache/diffusers-main.tar.gz

echo "=== interpreter ==="
python3 -V
python3 -c "import torch,torch_npu;print('torch',torch.__version__,'torch_npu',torch_npu.__version__)"

echo "=== venv ($V) ==="
rm -rf "$V"
python3 -m venv --system-site-packages "$V" || exit 1

echo "=== diffusers from source (>=0.42.0.dev0 needed for QwenImage21Pipeline) ==="
if [ ! -d "$SRC/diffusers" ]; then
  mkdir -p "$W/cache"
  if [ ! -f "$TAR" ]; then
    curl -sL --max-time 300 -o "$TAR" \
      https://github.com/huggingface/diffusers/archive/refs/heads/main.tar.gz || exit 1
  fi
  rm -rf "$SRC"; mkdir -p "$SRC"
  tar xzf "$TAR" -C "$SRC" --strip-components=1 || exit 1
fi
"$V/bin/pip" install -q --no-deps --no-build-isolation "$SRC" 2>&1 | tail -2

echo "=== transformers / accelerate (image has neither) ==="
"$V/bin/pip" install -q -U transformers accelerate 2>&1 | tail -2

echo "=== apply the CANN rotary patch ==="
"$V/bin/python" "$W/scripts/patch_qwen_rotary.py"

echo "=== verify ==="
"$V/bin/python" - <<'PY'
import torch, torch_npu, diffusers, transformers
print("diffusers", diffusers.__version__, "| transformers", transformers.__version__)
print("QwenImage21Pipeline:", hasattr(diffusers, "QwenImage21Pipeline"))
f, t = torch.npu.mem_get_info()
print("device free/total: %.1f/%.1f GB" % (f / 1e9, t / 1e9))
PY
