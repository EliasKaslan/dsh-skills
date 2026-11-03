#!/bin/bash
# npu_mem_report.sh -- vllm / vllm-ascend 服务显存占用与分布速查
# 用法: bash npu_mem_report.sh [vllm日志路径]
#   例: bash npu_mem_report.sh /home/vllm/x00886548/serve_test/serve.log
# 说明: 不依赖 vllm 环境，纯 npu-smi / curl 解析；日志段可选。

LOG="${1:-}"
IDLE_MB="${IDLE_MB:-3600}"        # 本机驱动基线约 2.8-3.2GB，低于此判空闲
EXPORTER="${EXPORTER:-http://localhost:9200/metrics}"

echo "=================================================================="
echo " 1. 全卡 HBM 快照  (npu-smi 主表; used 含驱动基线)"
echo "=================================================================="
printf "%-4s %-10s %-16s %9s %9s %7s  %s\n" "die" "NPU.Chip" "Bus-Id" "used_MB" "total_MB" "use%" "note"
npu-smi info 2>/dev/null | awk -F'|' -v idle="$IDLE_MB" '
  NF >= 4 {
    # 主表数据行: 第1列=Chip序号(该NPU内), 第2列=Phy-ID(= 全局 die 号, 0..15)
    two=$2; gsub(/ +/," ",two); sub(/^ /,"",two); sub(/ $/,"",two);
    if (split(two,a," ") != 2) next;
    if (a[1] !~ /^[0-9]+$/ || a[2] !~ /^[0-9]+$/) next;
    bus=$3; gsub(/ /,"",bus);
    if (bus !~ /^[0-9a-fA-F:]+\./) next;
    # $4 里同时含 AICore / DDR(Memory-Usage) / HBM，取最后一组 "N / N" 即 HBM
    s=$4; last="";
    while (match(s, /[0-9]+ *\/ *[0-9]+/)) { last=substr(s,RSTART,RLENGTH); s=substr(s,RSTART+RLENGTH) }
    if (last=="") next;
    split(last,b,"/"); gsub(/ /,"",b[1]); gsub(/ /,"",b[2]);
    if (b[1] !~ /^[0-9]+$/ || b[2] !~ /^[0-9]+$/) next;
    phy=a[2]+0; npu=int(phy/2); chip=phy%2;
    note = (b[1]+0 <= idle) ? "IDLE" : "BUSY";
    printf "%-4d %-10s %-16s %9d %9d %6.1f%%  %s\n", phy, npu"."chip, bus, b[1], b[2], b[1]*100/b[2], note;
  }'

echo
echo "=================================================================="
echo " 2. 进程归因  (npu-smi -t proc-mem; die = NPU*2 + Chip)"
echo "=================================================================="
printf "%-4s %-8s %-20s %10s\n" "die" "pid" "process" "mem_MB"
for npu in $(seq 0 7); do
  npu-smi info -t proc-mem -i "$npu" 2>/dev/null | awk -v npu="$npu" '
    /Process id:/ {
      pid=$0; sub(/.*Process id:/,"",pid); sub(/ .*/,"",pid);
      nm=$0;  sub(/.*Process name:/,"",nm); sub(/ *Process memory.*/,"",nm);
      mem=$0; sub(/.*Process memory\(MB\):/,"",mem);
      buf[++n]=pid "|" nm "|" mem; next
    }
    /Chip ID/ {
      cid=$0; sub(/.*Chip ID *: */,"",cid);
      for (i=1;i<=n;i++) { split(buf[i],f,"|"); printf "%-4d %-8s %-20s %10s\n", npu*2+cid, f[1], f[2], f[3]; }
      n=0
    }
  '
done

echo
echo "=================================================================="
echo " 3. vllm 自己的显存账本  (启动日志)"
echo "=================================================================="
if [ -n "$LOG" ] && [ -f "$LOG" ]; then
  echo "--- 分布拆解行 ---"
  grep -hE 'Free memory on device' "$LOG" | tail -1
  echo "--- KV cache ---"
  grep -hE 'Available KV cache memory|KV cache size' "$LOG" | tail -2
  echo "--- 运行期 KV 使用率 (log_stats) ---"
  grep -hE 'NPU KV cache usage' "$LOG" | tail -1
else
  echo "(未给日志路径；跳过。用法: bash $0 <vllm日志>)"
fi

echo
echo "=================================================================="
echo " 4. npu_exporter 绝对值  (长期监控入口, Prometheus 可抓)"
echo "=================================================================="
if curl -s --max-time 3 "$EXPORTER" >/dev/null 2>&1; then
  curl -s --max-time 5 "$EXPORTER" | awk '
    /npu_chip_info_hbm_(used|total)_memory\{/ {
      is_used = ($0 ~ /npu_chip_info_hbm_used_memory/);
      match($0, /[,{]id="[0-9]+"/); s=substr($0,RSTART,RLENGTH); gsub(/[^0-9]/,"",s); id=s;
      match($0, /pcie_bus_info="[^"]*"/); bus=substr($0,RSTART+15,RLENGTH-16);
      match($0, /\} +[0-9]+/); v=substr($0,RSTART,RLENGTH); gsub(/[^0-9]/,"",v);
      if (is_used) { used[id]=v; buses[id]=bus } else total[id]=v;
    }
    END { for (i in used) printf "die %-3s bus %-16s used %6d / %6d MB\n", i, buses[i], used[i], total[i] }' | sort -k2 -n
  echo "(val 单位 MB; total 恒为 65536)"
else
  echo "($EXPORTER 不可达; 该机未跑 npu_exporter)"
fi

echo
echo "=================================================================="
echo " 判读要点"
echo "=================================================================="
echo "* 空闲基线不是 0: npu-smi 的 used 含 ~2.8-3.2GB 驱动基线"
echo "* torch.npu.mem_get_info 的 used 不含基线, 两者差约 2730MB"
echo "* vllm 的 KV cache 启动时一次性预分配, 运行期不涨"
echo "* 主表 Memory-Usage(MB) 恒 0/0 是 DDR, 不是 HBM"
echo "* proc-mem 的 Chip ID 是段尾标记 (进程列表在前, Chip ID 在后)"
