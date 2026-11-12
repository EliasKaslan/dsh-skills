#!/bin/bash
# One-shot runtime setup on 192.168.13.188 (venue + models). Idempotent.
# Usage: bash setup_runtime.sh
set -x
exec 2>&1
mkdir -p /home/vllm/ai-musume/{models,out,scripts,logs,cache,refs}

docker run --rm --privileged --ipc=host \
  -e ASCEND_RT_VISIBLE_DEVICES=8 \
  -e HF_ENDPOINT=https://hf-mirror.com \
  -e HF_HOME=/work/cache/hf \
  -e PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  -v /home/vllm/ai-musume:/work \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/Ascend/firmware:/usr/local/Ascend/firmware \
  -v /etc/ascend_install.info:/etc/ascend_install.info \
  quay.nju.edu.cn/ascend/vllm-ascend:nightly-main-a3 \
  bash -lc '
    set -e
    cd /work
    if [ ! -x venv/bin/python ]; then python -m venv --system-site-packages venv; fi
    ./venv/bin/pip install -q --upgrade pip
    ./venv/bin/pip install -q diffusers accelerate huggingface_hub safetensors
    ./venv/bin/python -c "import torch, torch_npu, diffusers; print(torch.__version__, torch_npu.__version__, torch.npu.is_available(), torch.npu.device_count()); print(diffusers.__version__)"
    ./venv/bin/python - <<PY
from huggingface_hub import snapshot_download
print("base model ...", flush=True)
snapshot_download("cagliostrolab/animagine-xl-4.0", local_dir="/work/models/animagine-xl-4.0", max_workers=4)
print("ip-adapter ...", flush=True)
snapshot_download("h94/IP-Adapter",
                  allow_patterns=["models/image_encoder/*",
                                  "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors"],
                  local_dir="/work/models/ip-adapter-sdxl", max_workers=4)
PY
    du -sh /work/models/*
  '
echo "SETUP_DONE rc=$?"
