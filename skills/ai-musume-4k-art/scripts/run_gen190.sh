#!/bin/bash
# Run gen.py (SDXL family) on the MindSpeed 26.2.0 / CANN 9.2.0 stack.
#
# 2026-11-10 切换：原来用 sglang 镜像（CANN 9.1.0）。换到商发配套 26.2.0
# （openEuler 24.03 + torch 2.10 + torch_npu 2.10.0.post7 + CANN 9.2.0）。
#
# 这个镜像**不含 diffusers / transformers**（它是 ops 镜像），所以用 venv-qwen：
# 它建在同一镜像的解释器上（py3.12.15），--system-site-packages 继承 torch，
# 里面装了 diffusers 0.42.0.dev0 + transformers 5.22 + accelerate。
#
# ⚠️ venv 必须与镜像解释器一致：换镜像就要重建，否则报
#    `bash: venv/bin/python: No such file or directory`（.188 就是这么坏的）。
#
# Usage:
#   bash run_gen190.sh gen --char deepseek --style keyvisual --base 1216x1024
#   SDXL_MODEL_DIR=.../models/noobai-xl-1.1 bash run_gen190.sh sweep --char deepseek \
#     --tag bf --seeds 4242,7777 --styles keyvisual --supersample 1.25
#
# Env knobs: DEV (die id, default 8), SDXL_MODEL_DIR, VAE_DIR, IP_ADAPTER_DIR, OUT_DIR
set -u
IMG=swr.cn-north-4.myhuaweicloud.com/mindspeed/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-a3-openeuler24.03-py3.12
W=/home/vllm/ai-musume
PY=$W/venv-qwen/bin/python
DEV=${DEV:-8}
MODEL=${SDXL_MODEL_DIR:-$W/models/illustrious-xl-2.0}
IPD=${IP_ADAPTER_DIR:-$W/models/ip-adapter}
OUTD=${OUT_DIR:-$W/out}
VD=${VAE_DIR:-}

docker run --rm --privileged --net=host --ipc=host \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
  -v /home:/home \
  -v /mnt:/mnt:ro \
  -e ASCEND_RT_VISIBLE_DEVICES="$DEV" \
  -e TASK_QUEUE_ENABLE=2 \
  -e SDXL_MODEL_DIR="$MODEL" \
  -e IP_ADAPTER_DIR="$IPD" \
  -e OUT_DIR="$OUTD" \
  -e REF_DIR="$W/refs" \
  -e SDXL_VAE_DIR="$VD" \
  -e VAE_FP32=1 \
  -e HF_HUB_OFFLINE=1 \
  -e OMP_NUM_THREADS=8 \
  "$IMG" bash -lc "cd $W && exec $PY scripts/gen.py \"\$@\"" bash "$@"
