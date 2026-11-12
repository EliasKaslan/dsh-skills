#!/usr/bin/env bash
# init-home-layout.sh — 建立 /home/x00886548 统一工作目录（幂等，可反复跑）
#
# 用法（在服务器上以 root 执行）：
#   bash init-home-layout.sh \
#       --root /home/x00886548 \
#       [--link-target /home/vllm/x00886548] \
#       [--models /home/vllm/weights] [--datasets /mnt/dataset]
#   bash init-home-layout.sh --check          # 只检查，不写
#
# --link-target：root 不存在时建成指向该目录的软链（用于 /home 落在系统小盘的机器）
#               不传则建真实目录。
# --models/--datasets：公共空间入口；不存在或未传则跳过，不覆盖已有同名目录。
#
# 设计原则：幂等、不删任何东西、已有同名文件不覆盖。

set -euo pipefail

ROOT=/home/x00886548
LINK_TARGET=
MODELS=
DATASETS=
CHECK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root)        ROOT=$2; shift 2 ;;
    --link-target) LINK_TARGET=$2; shift 2 ;;
    --models)      MODELS=$2; shift 2 ;;
    --datasets)    DATASETS=$2; shift 2 ;;
    --check)       CHECK=1; shift ;;
    -h|--help)     sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '  ok    %s\n' "$*"; }
warn() { printf '  warn  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; CHECK_FAIL=1; }

CHECK_FAIL=0
DIRS="env/conda_envs env/venvs env/cann env/pkgs work agent/scripts agent/bin agent/lib agent/logs data tmp logs"

# ---------- 0) 根目录 ----------
say "== root: $ROOT"
if [ -L "$ROOT" ]; then
  REAL=$(readlink -f "$ROOT")
  ok "symlink -> $REAL"
elif [ -d "$ROOT" ]; then
  REAL=$(readlink -f "$ROOT")
  ok "directory ($REAL)"
else
  if [ "$CHECK" = 1 ]; then
    fail "root 不存在"
  elif [ -n "$LINK_TARGET" ]; then
    mkdir -p "$(dirname "$ROOT")"
    ln -s "$LINK_TARGET" "$ROOT"
    REAL=$(readlink -f "$ROOT")
    ok "created symlink -> $LINK_TARGET"
  else
    mkdir -p "$ROOT"
    REAL=$(readlink -f "$ROOT")
    ok "created directory"
  fi
fi

# ---------- 1) 目录骨架 ----------
say "== dirs"
for d in $DIRS; do
  if [ -d "$ROOT/$d" ]; then
    ok "$d"
  elif [ "$CHECK" = 1 ]; then
    fail "缺目录 $d"
  else
    mkdir -p "$ROOT/$d"
    ok "created $d"
  fi
done

# ---------- 2) 公共空间入口 ----------
link_pub() {
  name=$1; target=$2
  [ -z "$target" ] && return 0
  say "== $name -> $target"
  if [ ! -e "$target" ]; then
    warn "目标不存在，跳过"
    return 0
  fi
  if [ -L "$ROOT/$name" ]; then
    cur=$(readlink "$ROOT/$name")
    if [ "$cur" = "$target" ]; then ok "已指向"; else warn "现指向 $cur（期望 $target），未改动"; fi
    return 0
  fi
  if [ -e "$ROOT/$name" ]; then
    warn "已存在且不是软链，未覆盖"
    return 0
  fi
  if [ "$CHECK" = 1 ]; then fail "缺软链 $name"; else ln -s "$target" "$ROOT/$name"; ok "created symlink"; fi
}
link_pub models "$MODELS"
link_pub datasets "$DATASETS"

# ---------- 3) env/env.sh ----------
write_env_sh() {
  cat > "$ROOT/env/env.sh" <<'EOS'
# /home/x00886548/env/env.sh — 个人环境统一入口（bash: source 本文件）
# 用法: source /home/x00886548/env/env.sh
#       xh_use <env-name>     # conda activate $XH_ENV/conda_envs/<env-name>
#       xh_cann [目录名]      # source CANN 的 set_env.sh（缺省取 env/cann 下最新）
export XH=/home/x00886548
export XH_ENV=$XH/env
export XH_WORK=$XH/work
export XH_AGENT=$XH/agent
export XH_MODELS=$XH/models
export XH_DATASETS=$XH/datasets

# 缓存与临时目录都落在个人根，别写 / 或 /tmp
export PIP_CACHE_DIR=$XH_ENV/pkgs/pip
export CONDA_PKGS_DIRS=$XH_ENV/pkgs/conda
export HF_HOME=${HF_HOME:-$XH/data/hf}
export TMPDIR=${TMPDIR:-$XH/tmp}

case ":$PATH:" in
  *":$XH_AGENT/bin:"*) ;;
  *) export PATH=$XH_AGENT/bin:$PATH ;;
esac

# conda：优先个人根里的 conda3，其次本机共享 miniconda
_conda_sh=
for c in "$XH_ENV/conda3/etc/profile.d/conda.sh" \
         /mnt/share/miniconda3/etc/profile.d/conda.sh; do
  if [ -f "$c" ]; then _conda_sh=$c; break; fi
done
if [ -n "$_conda_sh" ]; then . "$_conda_sh"; fi
unset _conda_sh

xh_use() {
  local p=$XH_ENV/conda_envs/$1
  if [ ! -d "$p" ]; then echo "no env: $p" >&2; return 1; fi
  conda activate "$p"
}

xh_cann() {
  local d=${1:-}
  if [ -z "$d" ]; then
    d=$(ls -1d "$XH_ENV"/cann/cann_* 2>/dev/null | tail -1)
  fi
  for f in "$d/cann/set_env.sh" "$d"/cann-*/set_env.sh; do
    if [ -f "$f" ]; then . "$f"; return 0; fi
  done
  echo "no CANN set_env.sh under: ${d:-$XH_ENV/cann}" >&2
  return 1
}
EOS
}
say "== env/env.sh"
if [ -f "$ROOT/env/env.sh" ]; then
  ok "已存在（不覆盖）"
elif [ "$CHECK" = 1 ]; then
  fail "缺 env/env.sh"
else
  write_env_sh; ok "written"
fi

# ---------- 4) README.md ----------
REAL=${REAL:-$ROOT}
say "== README.md"
if [ -f "$ROOT/README.md" ]; then
  ok "已存在（不覆盖）"
elif [ "$CHECK" = 1 ]; then
  fail "缺 README.md"
else
  {
    echo "# /home/x00886548 — 个人工作根"
    echo
    echo "> 唯一入口：项目、脚本、agent 中间件、环境都在这里。"
    echo "> 模型权重 / 数据集不放这里，用本目录下 models/、datasets/ 软链指向本机公共空间。"
    echo
    echo "## 目录"
    echo
    echo "| 路径 | 用途 |"
    echo "|---|---|"
    echo "| \`env/\` | **环境专放**：\`conda3/\`(base) \`conda_envs/<name>\` \`venvs/<name>\` \`cann/\` \`pkgs/\` \`env.sh\` |"
    echo "| \`work/\` | 项目工作区，一个项目一个子目录 |"
    echo "| \`agent/\` | agent 生成的脚本/中间件：\`scripts/\` \`bin/\` \`lib/\` \`logs/\` |"
    echo "| \`data/\` | 个人数据与产物（非公共数据集） |"
    echo "| \`tmp/\` \`logs/\` | 临时文件与日志 |"
    echo "| \`models\` \`datasets\` | 软链到本机公共空间（只读用，别往里写个人产物） |"
    echo
    echo "## 本机落位（生成于 $(date '+%Y-%m-%d %H:%M')）"
    echo
    echo "- root 物理位置：\`$REAL\`"
    echo "- models -> \`${MODELS:-（未配置）}\`"
    echo "- datasets -> \`${DATASETS:-（未配置）}\`"
    echo "- 磁盘："
    df -h "$ROOT" 2>/dev/null | sed 's/^/  /'
    echo
    echo "## 规矩"
    echo
    echo "1. 新项目一律 \`work/<项目名>/\`；不要在根下或 \`/mnt/share\`、\`/tmp\` 新建项目目录。"
    echo "2. 环境一律放 \`env/\`：conda 用 \`conda create -p \$XH_ENV/conda_envs/<name>\`。"
    echo "3. agent 生成的脚本、中间件、日志分别落 \`agent/{scripts,bin,lib,logs}\`。"
    echo "4. 写大文件前先 \`df -h <目标路径>\`；根盘满时只能写 \`work/\` 或公共数据盘。"
    echo "5. 本文件与 \`env/env.sh\` 由 skill \`ascend-server-layout\` 生成，改结构请先改 skill。"
  } > "$ROOT/README.md"
  ok "written"
fi

# ---------- 5) 汇总 ----------
say
say "== summary"
if [ -d "$ROOT" ]; then
  du -sh "$ROOT/" 2>/dev/null || true
  df -h "$ROOT" 2>/dev/null || true
  for n in models datasets; do
    [ -L "$ROOT/$n" ] && printf '  %-8s -> %s\n' "$n" "$(readlink "$ROOT/$n")"
  done
fi
if [ "$CHECK" = 1 ]; then
  if [ "$CHECK_FAIL" = 1 ]; then echo "RESULT: FAIL"; exit 1; fi
  echo "RESULT: PASS"
fi
