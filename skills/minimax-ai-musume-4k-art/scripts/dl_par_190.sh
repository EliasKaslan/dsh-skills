#!/bin/bash
# Parallel ranged downloader for hf-mirror (single connection is throttled ~1.6MB/s).
set -u
W=/home/vllm/ai-musume
B=https://hf-mirror.com

par_dl() {  # url dest want n
  local url=$1 dest=$2 want=$3 n=${4:-8}
  local d="$dest.parts" i s e chunk have need t
  mkdir -p "$d"; rm -f "$d"/*.p
  chunk=$(( (want + n - 1) / n ))
  for i in $(seq 0 $((n-1))); do
    s=$((i*chunk)); e=$((s+chunk-1)); [ "$e" -ge "$want" ] && e=$((want-1))
    (
      for t in $(seq 1 500); do
        have=$(stat -c%s "$d/$i.p" 2>/dev/null || echo 0)
        need=$((e-s+1))
        [ "$have" -ge "$need" ] && break
        curl -sSL --retry 2 --connect-timeout 15 -m 600 \
             -r "$((s+have))-$e" "$url" >> "$d/$i.p" 2>/dev/null
        sleep 0.3
      done
    ) &
  done
  wait
  cat "$d"/{0,1,2,3,4,5,6,7}.p > "$dest" 2>/dev/null || cat "$d"/*.p > "$dest"
  local got; got=$(stat -c%s "$dest" 2>/dev/null || echo 0)
  if [ "$got" -eq "$want" ]; then
    echo "[par_dl] OK $(basename "$dest") $got"; rm -rf "$d"
  else
    echo "[par_dl] BAD $(basename "$dest") $got / $want"
  fi
}

echo "start $(date +%H:%M:%S)"
par_dl "$B/OnomaAIResearch/Illustrious-XL-v1.1/resolve/main/Illustrious-XL-v1.1.safetensors" \
       "$W/models/illustrious-xl/model.safetensors" 6938040728 8
echo "illustrious done $(date +%H:%M:%S)"
par_dl "$B/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors" \
       "$W/models/ip-adapter/models/image_encoder/model.safetensors" 2528373448 6
echo "encoder done $(date +%H:%M:%S)"
find "$W/models" -name '*.safetensors' -printf '%10s %p\n'
date > "$W/logs/dl3.done"
echo DONE
