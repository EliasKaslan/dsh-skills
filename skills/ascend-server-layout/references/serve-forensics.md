# 从 npu-smi 进程名反查真实服务（2026-11-19 A5 实测）

## 命令序列

```bash
# 1. 全量命令行（comm 只有 15 字符，看不清）
ps -eo pid,ppid,etime,args | grep -E 'sglang|vllm' | grep -v grep | cut -c1-900

# 2. 宿主还是容器
cat /proc/<pid>/cgroup | grep -oE '[0-9a-f]{64}' | head -1     # 取前 12 位
docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' | grep <12位>

# 3. 服务是否真在提供服务
curl -s -m 5 -o /dev/null -w 'healthz %{http_code}\n' http://127.0.0.1:<port>/health
curl -s -m 5 http://127.0.0.1:<port>/get_model_info | head -c 400

# 4. 设备级占卡（权威口径）
for i in 0 1 2 3 4 5 6 7; do echo "--- npu $i"; npu-smi info -t proc-mem -i $i 2>&1 | tail -4; done

# 5. 漏网进程（只作补充）
find /proc -maxdepth 3 -lname '*davinci*' 2>/dev/null | awk -F/ '{print $3}' | sort -u \
  | while read p; do echo "$p $(ps -o args= -p $p 2>/dev/null | cut -c1-80)"; done
```

## 实测样例（A5 rack09os2，8×Ascend950DT，npu-smi 26.2.0.b020）

- `npu-smi info` 进程表 8 卡全为 `sglangschedul` 53599MB；`ps args` 才是 `python3 -m sglang.launch_server --model-path /mnt/weight/Qwen3.8-27B --host 0.0.0.0 --port 30000 --tp-size 8 --nnodes 1 --attention-backend ascend --device npu --mem-fraction-static 0.80 --max-total-tokens 750000 --enable-multimodal`。
- 父进程 `bash /tmp/launch_qwen.sh`；`etime` = 服务运行时长。
- cgroup ID → `6dce3ff5c624` → 容器 `sglang_qwen`（`lmsysorg/sglang:main-cann9.1.0-950`，Up 3 days）。`npu-smi` 的 `Process id in container` 仍显示 `NA`，不能据此判宿主进程。
- `/health` 200；`/get_model_info` 给出 `model_type=qwen3`、`reasoning_parser`、`has_image_understanding=true`。
- 8 卡 `NPU Util 0%`（此刻无请求），HBM 各 58.4/96GB。

## 判读要点

- **`Process name` 是内核 comm，截断 15 字符**：`sglangschedul` 对应 `sglang::scheduler_TP0..TP7`；`VLLM::DPCoordinator` 同理。要区分 scheduler/proxy/detokenizer 只能读 `/proc/<pid>/cmdline` 或 `ps args`。
- **单卡 HBM 高 ≠ 权重那么多**：`--mem-fraction-static 0.80` 是预留 KV 池，小模型在大卡上也会显示 50GB/卡量级。
- **判「谁占卡」以 `-t proc-mem` 为准**。`-lname '*davinci*'` 会命中持有 fd 但不占 HBM 的进程：`[vllm] <defunct>` 僵尸、以及跨机 `torchrun ... --node_rank=1 --master_addr=<其他节点>` 卡在等待的 bench 脚本（实测已挂 2 天）。这些按「吃 CPU 不占卡」单独报，别写进占卡结论。
- 8 卡单机 TP 服务：每卡一个 scheduler 进程是正常拓扑，不是重复启动；`ss -lntp` 会看到大量 `127.0.0.1:<高位端口>` 的进程间通信端口，暴露服务端口（如 `0.0.0.0:30000`）只有主进程一个。
