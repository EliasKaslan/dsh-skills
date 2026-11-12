#!/bin/bash
# Run gen_qwen.py (Qwen-Image-2.1 / 2.1-Turbo) on the MindSpeed 26.2.0 / CANN 9.2.0 stack.
#
# 这条路径需要：
#   1) venv-qwen（diffusers 0.42.0.dev0 + transformers + accelerate）
#      —— 一次性用 `bash setup_qwen_runtime.sh` 建好；
#   2) 打过过 CANN 旋转编码补丁（setup 脚本里会调用），否则推理必崩：
#      `AclNN_Parameter_Error(EZ1001): Tensor self not implemented for DT_COMPLEX64`
#
# 实测（1216x1024，单 die）：
#   Turbo  8 步  4.9 秒   （默认，质量与基模肉眼几乎无差）
#   基模  40 步 37.2 秒
#
# Usage:
#   bash run_qwen.sh --preset deepseek --size 1216x1024 --seed 7777 --tag q1
#   QWEN_MODEL_DIR=/home/vllm/ai-musume/models/qwen-image-2.1 bash run_qwen.sh --tag base
#
# Env knobs: DEV (die id, default 8), QWEN_MODEL_DIR
set -u
IMG=swr.cn-north-4.myhuaweicloud.com/mindspeed/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-a3-openeuler24.03-py3.12
W=/home/vllm/ai-musume
PY=$W/venv-qwen/bin/python
DEV=${DEV:-8}
MODEL=${QWEN_MODEL_DIR:-$W/models/qwen-image-2.1-turbo}

docker run --rm --privileged --net=host --ipc=host \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
  -v /home:/home \
  -v /mnt:/mnt:ro \
  -e ASCEND_RT_VISIBLE_DEVICES="$DEV" \
  -e TASK_QUEUE_ENABLE=2 \
  -e OMP_NUM_THREADS=8 \
  -e HF_HUB_OFFLINE=1 \
  -e QWEN_MODEL_DIR="$MODEL" \
  "$IMG" bash -lc "cd $W && exec $PY scripts/gen_qwen.py --model \"\$QWEN_MODEL_DIR\" \"\$@\"" bash "$@"
