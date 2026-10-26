#!/usr/bin/env python3
"""检查远程昇腾机的 TileLang-Ascend 环境是否可用。

检查逻辑写入临时脚本、scp 上传、ssh 执行，避免 Windows 引号转义问题。
CANN 与 venv 路径由参数或环境变量提供（`CANN_INSTALL_PATH` / `TILELANG_ASCEND_PATH`
/ `TILELANG_ENV_DIR`）；未提供时**不再静默回落**到猜测的路径或解释器，
而是判定环境不合格并提示显式指定。

退出码契约（可直接当 skill 的通过判据）：

- `0`：全部必检项通过——CANN 可激活、TileLang-Ascend 可激活且有编译产物、
  `npu-smi` 能看到 Ascend 设备、python 能 import torch/torch_npu/tilelang 且 NPU 设备数 > 0；
- 非 `0`：任一必检项失败。每项都有 `[ OK ]` / `[FAIL]` 标记，失败项把子命令的
  **原始输出整段**打出来（不再用 `| tail -1` 只看最后一行、把真实原因吞掉）。

幂等性：远端临时脚本名带 pid+随机后缀（`/tmp/tilelang_env_check_{pid}_{rand}.sh`，
跑完自删），不同并发调用互不覆盖；同一环境重复运行，输出结构与结论一致
（`npu-smi` 的显存/进程数字本身随机器状态变化，不参与结论）。

默认值一览（本脚本内置；共享机上地址与路径各不相同，**务必逐项显式指定，不要照抄别人的路径**）：

| 参数 | 环境变量 | 内置默认值 | 说明 |
|------|----------|------------|------|
| `--host` | `TILELANG_NPU_HOST` | 无（必填） | 远程昇腾机地址 |
| `--port` | `TILELANG_NPU_PORT` | `22` | SSH 端口 |
| `--user` | `TILELANG_NPU_USER` | `root` | SSH 用户 |
| `--cann-path` | `CANN_INSTALL_PATH` | 空（必检项判失败） | CANN 路径，需含 `set_env.sh` 或 `bin/setenv.bash` |
| `--tilelang-path` | `TILELANG_ASCEND_PATH` | 空（必检项判失败） | TileLang-Ascend 路径，需含 `set_env.sh` |
| `--env-dir` | `TILELANG_ENV_DIR` | 空（自动发现 `python3`） | 远程 Python venv 目录，需含 `bin/python` |

`--env-dir` 一旦显式给出就**必须**存在（缺 `bin/python` 即失败），不会静默换用别的解释器。

示例：

    export TILELANG_NPU_HOST=10.0.0.1
    export CANN_INSTALL_PATH=/usr/local/Ascend/ascend-toolkit/latest
    export TILELANG_ASCEND_PATH=/opt/tilelang-ascend
    export TILELANG_ENV_DIR=/opt/tilelang-env

    python env_check.py
"""

import argparse
import os
import secrets
import subprocess
import sys
import tempfile

CHECK_SCRIPT = r"""#!/bin/bash
# 远端环境自检。刻意不用 `set -e`：本脚本要「跑完全部检查项再汇总」，
# 中途退出会让同一环境下不同次运行的输出结构随失败点漂移（正是本脚本要修的病）。
# `set -o pipefail` 必须留：否则 `a | b` 里前半段的失败会被后半段掩盖。
set -o pipefail
trap 'rm -f "$0"' EXIT

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
CANN=__CANN_PATH__
TILELANG=__TILELANG_PATH__
ENVDIR=__ENV_DIR__

FAILED=0
ok()  { echo "[ OK ] $1"; }
bad() { echo "[FAIL] $1"; FAILED=1; }
raw() { echo "  --- 原始输出 ---"; sed 's/^/  | /' "$1"; }
LOG=$(mktemp 2>/dev/null); [ -n "$LOG" ] || LOG=/tmp/tl_env_check_$$.log

echo "=== host ==="
hostname 2>&1
uname -m 2>&1

echo
echo "=== CANN ==="
# 标准安装把入口放在 <toolkit>/set_env.sh；只有版本子目录里才有 bin/setenv.bash
# （如 .../cann-9.1.0/x86_64-linux/bin/setenv.bash）。两者都认，避免"路径没错却判失败"。
CANN_ENV=""
if [ -n "$CANN" ] && [ -d "$CANN" ]; then
    if [ -f "$CANN/set_env.sh" ]; then
        CANN_ENV="$CANN/set_env.sh"
    elif [ -f "$CANN/bin/setenv.bash" ]; then
        CANN_ENV="$CANN/bin/setenv.bash"
    fi
fi
if [ -n "$CANN_ENV" ]; then
    echo "CANN: $CANN"
    source "$CANN_ENV" >"$LOG" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then ok "source $CANN_ENV"; else bad "source $CANN_ENV（退出码 $rc）"; raw "$LOG"; fi
    echo "ASCEND_HOME_PATH: ${ASCEND_HOME_PATH:-未设置}"
    if [ -f /etc/Ascend/ascend_cann_install.info ]; then
        echo "--- CANN 安装记录 /etc/Ascend/ascend_cann_install.info ---"
        sed -n '1,12p' /etc/Ascend/ascend_cann_install.info | sed 's/^/  | /'
    else
        echo "[INFO] 未找到 /etc/Ascend/ascend_cann_install.info"
    fi
    if [ -x "$CANN/query_pkg_version.sh" ]; then
        echo "--- CANN 版本（$CANN/query_pkg_version.sh）---"
        (cd "$CANN" && bash ./query_pkg_version.sh 2>&1 | head -6) | sed 's/^/  | /'
    else
        echo "[INFO] 未找到 $CANN/query_pkg_version.sh，CANN 版本见上方 npu-smi 的 Version 行"
    fi
else
    bad "CANN_INSTALL_PATH 未指定或路径无效：${CANN:-未指定}（需指向含 set_env.sh 或 bin/setenv.bash 的目录）"
    echo "--- 候选位置 ---"
    ls -d /usr/local/Ascend/ascend-toolkit/latest /usr/local/Ascend/cann* /mnt/share/*/cann/*/cann-* 2>&1 | sed 's/^/  | /'
fi

echo
echo "=== TileLang-Ascend ==="
if [ -n "$TILELANG" ] && [ -f "$TILELANG/set_env.sh" ]; then
    echo "TileLang-Ascend: $TILELANG"
    source "$TILELANG/set_env.sh" >"$LOG" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then ok "source $TILELANG/set_env.sh"; else bad "source $TILELANG/set_env.sh（退出码 $rc）"; raw "$LOG"; fi
    shopt -s nullglob
    sos=("$TILELANG"/build/*.so)
    if [ "${#sos[@]}" -gt 0 ]; then ok "已编译产物 ${#sos[@]} 个（例：$(basename "${sos[0]}")）"; else bad "未找到 $TILELANG/build/*.so（TileLang-Ascend 未编译？）"; fi
else
    bad "TILELANG_ASCEND_PATH 未指定或缺少 set_env.sh：${TILELANG:-未指定}"
    if [ -n "$TILELANG" ]; then
        echo "--- 该路径实际内容（ls -la）---"
        ls -la "$TILELANG" 2>&1 | head -10 | sed 's/^/  | /'
    fi
fi

echo
echo "=== NPU ==="
if command -v npu-smi >/dev/null 2>&1; then
    npu-smi info >"$LOG" 2>&1
    rc=$?
    sed 's/^/  | /' "$LOG"
    if [ "$rc" -eq 0 ]; then ok "npu-smi info"; else bad "npu-smi info（退出码 $rc）"; fi
    n=$(grep -oE '^\| [0-9]+ +Ascend' "$LOG" | awk '{print $2}' | sort -u | wc -l)
    if [ "${n:-0}" -gt 0 ]; then ok "npu-smi 报告 $n 个 NPU（按 NPU 编号去重）"; else bad "npu-smi 未报告任何 Ascend 设备"; fi
else
    bad "找不到 npu-smi 命令（PATH 或驱动问题）"
fi

echo
echo "=== python env ==="
if [ -n "$ENVDIR" ]; then
    PY="$ENVDIR/bin/python"
    if [ -x "$PY" ]; then ok "使用 --env-dir 指定的解释器：$PY"; else bad "--env-dir 已给出但 $PY 不存在或不可执行（不回落其它解释器）"; fi
else
    PY=$(command -v python3 2>/dev/null)
    if [ -n "$PY" ]; then echo "[INFO] 未指定 --env-dir / TILELANG_ENV_DIR，自动发现解释器：$PY"; else bad "未指定 --env-dir 且 PATH 中找不到 python3"; fi
fi
echo "python: ${PY:-无可用解释器}"

py_check() {
    local desc="$1" code="$2" out rc
    out=$("$PY" -c "$code" 2>&1)
    rc=$?
    echo "$out" | sed 's/^/  | /'
    if [ "$rc" -eq 0 ]; then ok "$desc"; else bad "$desc（退出码 $rc）"; fi
}

if [ -n "$PY" ] && [ -x "$PY" ]; then
    py_check "import torch / torch_npu" \
        "import torch, torch_npu; print('torch', torch.__version__, '| torch_npu', torch_npu.__version__)"
    py_check "import tilelang" \
        "import tilelang; print('tilelang', getattr(tilelang, '__version__', '未知版本'), '|', tilelang.__file__)"
    py_check "torch.npu 可用且 NPU 设备数 > 0" \
        "import torch, sys
if not hasattr(torch, 'npu'):
    print('ERROR: 当前解释器没有 torch.npu（缺少 torch_npu），需用带 torch_npu 的 venv（--env-dir / TILELANG_ENV_DIR）')
    sys.exit(3)
import torch_npu
n = torch.npu.device_count()
print('npu devices:', n)
sys.exit(0 if n > 0 else 4)"
else
    bad "跳过 python 检查：没有可用解释器"
fi

rm -f "$LOG"

echo
if [ "$FAILED" -eq 0 ]; then
    echo "=== RESULT: ALL CHECKS PASSED ==="
    exit 0
fi
echo "=== RESULT: ENV CHECK FAILED（见上文 [FAIL] 项）==="
exit 1
"""


def run(cmd, check=True):
    print(f"+ {cmd}", flush=True)
    proc = subprocess.run(cmd, shell=True)
    if check and proc.returncode != 0:
        sys.exit(proc.returncode)
    return proc


def sh_quote(value):
    """包成远端 shell 的单引号字面量（含单引号时按 POSIX 规则转义）。

    这样路径里的空格、`$`、反引号都按字面传入，不会在远端被二次展开。
    """
    return "'" + value.replace("'", "'\\''") + "'"


def sh_quote_path(value):
    """路径引用：开头的 `~` 与紧随的斜杠都裸露在引号外，否则 bash 不做 tilde 展开。

    `'~/x'` 与 `~'/x'` 都会落到字面目录 `$HOME/~/x`；正确写法是 `~/'x'`。
    """
    if value == "~":
        return "~"
    if value.startswith("~/"):
        return "~/" + sh_quote(value[2:])
    return sh_quote(value)


def env_port():
    """TILELANG_NPU_PORT 必须是整数：坏值给可读错误 + exit 2（不能退回"必检项失败"）。"""
    raw = os.environ.get("TILELANG_NPU_PORT")
    if raw in (None, ""):
        return 22
    try:
        return int(raw)
    except ValueError:
        print(f"error: 环境变量 TILELANG_NPU_PORT 不是整数：{raw!r}", file=sys.stderr)
        raise SystemExit(2)


def render_check_script(cann_path, tilelang_path, env_dir):
    return (CHECK_SCRIPT
            .replace("__CANN_PATH__", sh_quote_path(cann_path))
            .replace("__TILELANG_PATH__", sh_quote_path(tilelang_path))
            .replace("__ENV_DIR__", sh_quote_path(env_dir)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("TILELANG_NPU_HOST"),
                    help="远程昇腾机地址（必填；默认取环境变量 TILELANG_NPU_HOST）")
    ap.add_argument("--port", type=int, default=env_port(),
                    help="SSH 端口（默认 22，可被环境变量 TILELANG_NPU_PORT 覆盖）")
    ap.add_argument("--user", default=os.environ.get("TILELANG_NPU_USER", "root"),
                    help="SSH 用户（默认 root，可被环境变量 TILELANG_NPU_USER 覆盖）")
    ap.add_argument("--cann-path", default=os.environ.get("CANN_INSTALL_PATH", ""),
                    help="CANN 安装路径（默认取 CANN_INSTALL_PATH）；需含 set_env.sh 或 bin/setenv.bash，"
                         "未给出即判该项失败")
    ap.add_argument("--tilelang-path", default=os.environ.get("TILELANG_ASCEND_PATH", ""),
                    help="TileLang-Ascend 仓库路径（默认取 TILELANG_ASCEND_PATH）；需含 set_env.sh，"
                         "未给出即判该项失败")
    ap.add_argument("--env-dir", default=os.environ.get("TILELANG_ENV_DIR", ""),
                    help="远程 Python venv 目录（默认取 TILELANG_ENV_DIR）；需含 bin/python，"
                         "显式给出时必须存在")
    args = ap.parse_args()

    if not args.host:
        ap.error("缺少目标机地址：传 --host 或设置环境变量 TILELANG_NPU_HOST")

    target = f"{args.user}@{args.host}"
    ssh_opt = f"-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -p {args.port}"
    scp_opt = f"-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -P {args.port}"

    script = render_check_script(args.cann_path, args.tilelang_path, args.env_dir)
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, newline="\n", encoding="utf-8") as f:
        f.write(script)
        local_sh = f.name
    # 远端脚本名按 invocation 唯一化：并发（不同参数）不会互相覆盖，
    # 也不会出现「读到别人写了一半的文件」导致的 syntax error。
    remote_sh = f"/tmp/tilelang_env_check_{os.getpid()}_{secrets.token_hex(4)}.sh"
    try:
        run(f'scp {scp_opt} "{local_sh}" {target}:{remote_sh}')
        run(f'ssh {ssh_opt} {target} "bash {remote_sh}"')
    finally:
        os.unlink(local_sh)
        # 远端脚本自己也有 trap 清理；这里兜底（不改主命令退出码）。
        run(f'ssh {ssh_opt} {target} "rm -f {remote_sh}"', check=False)


if __name__ == "__main__":
    main()
