#!/bin/bash
# Run gen.py inside the Ascend container. Usage: bash run_gen.sh gen --char claude ...
docker run --rm --privileged --ipc=host \
  -e ASCEND_RT_VISIBLE_DEVICES=8 \
  -e TASK_QUEUE_ENABLE=2 \
  -v /home/vllm/ai-musume:/work \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/Ascend/firmware:/usr/local/Ascend/firmware \
  -v /etc/ascend_install.info:/etc/ascend_install.info \
  quay.nju.edu.cn/ascend/vllm-ascend:nightly-main-a3 \
  bash -lc 'cd /work && exec ./venv/bin/python scripts/gen.py "$@"' bash "$@"
