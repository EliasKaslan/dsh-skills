#!/usr/bin/env python3
"""把本地算子文件部署到远程昇腾机并执行测试。

设计要点：

1. 远程命令先写入一个本地 .sh 文件、scp 上传、再 ssh 执行，
   彻底避开 Windows OpenSSH 对引号/管道的转义问题。
2. 生成的远端 wrapper 开头是 `set -eo pipefail`：`--cmd` 里若写成 `a | b`，
   管道任一段失败都会让整体退出码非 0，不会把失败伪装成「退出码 0 = 通过」。
3. 运行环境（CANN / TileLang-Ascend / Python venv）不写死在脚本里，
   而由命令行参数或环境变量提供；本脚本把它们拼成远程脚本的激活前置，
   因此 `--cmd` 里只写真正要执行的命令。

远端工作目录由三个参数拼出，语义固定：

    远端工作目录 = {remote-base}/{workdir-name}

| 参数 | 作用 |
|------|------|
| `--remote-base` | 远端父目录；上传落在它下面、`--cmd` 也在它下面执行（不存在会自动创建） |
| `--workdir-name` | `--remote-base` 下真正落地、并作为 `--cmd` 工作目录的目录名；默认 `basename(--deploy)` |
| `--deploy` | 本地要上传的文件或目录 |

- 目录：`--deploy custom/softmax`（不带 `--workdir-name`）→ 远端 `{remote-base}/softmax/`，
  随后 `cd {remote-base}/softmax` 再跑 `--cmd`。
- 同一目录加 `--workdir-name cmp` → 远端 `{remote-base}/cmp/`，`cd {remote-base}/cmp`。
  即 **scp 的落地目录名与 `cd` 的目录永远是同一个**，不会再出现「传到了 A、却 cd 到 B」。
  每次部署会先清掉该目录再放新的一份，重复部署不会嵌套成 `work/op/op`。
- 单文件：`--deploy foo.py` → 远端 `{remote-base}/{workdir-name}/foo.py`，
  在该目录下跑 `--cmd`（`--workdir-name` 对单文件同样生效，不会被静默忽略）。

默认值一览（本脚本内置；共享机上地址与路径各不相同，**务必逐项显式指定，不要照抄别人的路径**）：

| 参数 | 环境变量 | 内置默认值 | 说明 |
|------|----------|------------|------|
| `--host` | `TILELANG_NPU_HOST` | 无（必填） | 远程昇腾机地址 |
| `--port` | `TILELANG_NPU_PORT` | `22` | SSH 端口 |
| `--user` | `TILELANG_NPU_USER` | `root` | SSH 用户 |
| `--remote-base` | `TILELANG_NPU_WORKDIR` | `~/tilelang-work` | 远端父目录 |
| `--cann-path` | `CANN_INSTALL_PATH` | 空（不激活） | `source {cann_path}/set_env.sh`（缺失时回退 `bin/setenv.bash`） |
| `--tilelang-path` | `TILELANG_ASCEND_PATH` | 空（不激活） | 用于 `source {tilelang_path}/set_env.sh` |
| `--env-dir` | `TILELANG_ENV_DIR` | 空（不前置 PATH） | 把 `{env_dir}/bin` 前置到 PATH；给出即必须存在 |
| `--workdir-name` | 无 | `basename(--deploy)` | 远端落地目录名（= `--cmd` 的工作目录） |
| `--deploy` | 无 | 无（必填） | 本地源路径 |
| `--cmd` | 无 | 无（必填） | 远端要执行的命令 |

除 `--host` 外这些默认值只是「少打字」的便利值，**不代表目标机的真实环境**；
`--help` 里列出的就是本脚本的全部内置默认值。

示例：

    export TILELANG_NPU_HOST=10.0.0.1
    export CANN_INSTALL_PATH=/usr/local/Ascend/ascend-toolkit/latest
    export TILELANG_ASCEND_PATH=/opt/tilelang-ascend
    export TILELANG_ENV_DIR=/opt/tilelang-env

    python remote_run.py --deploy custom/softmax \\
        --cmd 'ASCEND_RT_VISIBLE_DEVICES=0 python test_softmax.py --level l0'
"""

import argparse
import os
import secrets
import subprocess
import sys
import tempfile


def run(cmd, check=True, capture=False):
    """执行本地命令；capture=True 时顺带把子进程输出收回来给调用方解析。"""
    print(f"+ {cmd}", flush=True)
    kwargs = (dict(capture_output=True, text=True, encoding="utf-8", errors="replace")
              if capture else {})
    proc = subprocess.run(cmd, shell=True, **kwargs)
    if check and proc.returncode != 0:
        if capture:
            sys.stderr.write(proc.stdout or "")
            sys.stderr.write(proc.stderr or "")
        sys.exit(proc.returncode)
    return proc


def sh_quote(value):
    """包成远端 shell 的单引号字面量（含单引号时按 POSIX 规则转义）。"""
    return "'" + value.replace("'", "'\\''") + "'"


def sh_quote_path(value):
    """路径引用：开头的 `~` 与紧随的斜杠都必须裸露在引号外，否则 bash 不做 tilde 展开。

    两种错法实测都会落到字面目录 `/root/~/tilelang-work`：
    `sh_quote("~/tilelang-work")` → `'~/tilelang-work'`；
    `"~" + sh_quote("/tilelang-work")` → `~'/tilelang-work'`（斜杠被引号吃掉，
    bash 会把整个 `~/tilelang-work` 当成一个登录名去查，查不到就原样保留）。
    正确写法是 `~` + 未加引号的 `/` + 引号包住其余部分：`~/'tilelang-work'`。
    """
    if value == "~":
        return "~"
    if value.startswith("~/"):
        return "~/" + sh_quote(value[2:])
    return sh_quote(value)


def env_port():
    """TILELANG_NPU_PORT 必须是整数：坏值给可读错误 + exit 2，不要抛 ValueError traceback。"""
    raw = os.environ.get("TILELANG_NPU_PORT")
    if raw in (None, ""):
        return 22
    try:
        return int(raw)
    except ValueError:
        print(f"error: 环境变量 TILELANG_NPU_PORT 不是整数：{raw!r}", file=sys.stderr)
        raise SystemExit(2)


def check_quotable(value, flag):
    """值要穿过两层引号（本地 cmd.exe 的双引号 + 远端 shell 的单引号）。

    双引号与换行会破坏其中一层，直接报错，而不是拼出一条悄悄跑错的命令。
    """
    bad = [c for c in value if c == '"' or ord(c) < 32]
    if bad:
        raise SystemExit(f"{flag} 不能含双引号或控制字符（会破坏本地/远端引号）：{value!r}")


def check_name(name, flag):
    """--workdir-name 必须是单级目录名：它会被拼进远端路径与脚本名。"""
    if name in ("", ".", ".."):
        raise SystemExit(f"{flag} 不能为 {name!r}")
    for ch in ("/", "\\", ":"):
        if ch in name:
            raise SystemExit(f"{flag} 只能是单级目录名，不能含 {ch!r}：{name!r}")
    check_quotable(name, flag)


def build_preamble(cann_path, tilelang_path, env_dir):
    """远程脚本的环境激活前置（含 ssh 非登录 shell 的 PATH 补全）。

    首行 PATH 补全是必需的：ssh 非登录 shell 可能缺 /usr/local/sbin（npu-smi）
    与 /usr/bin（git，tilelang 的 version.py 会调）。
    """
    lines = ["export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"]
    if cann_path:
        # 标准安装的入口是 <toolkit>/set_env.sh；bin/setenv.bash 只存在于版本子目录
        # （如 .../cann-9.1.0/x86_64-linux/bin/setenv.bash）。两者都认，且在都缺时响亮失败。
        p = sh_quote_path(cann_path)
        lines.append(
            f"if [ -f {p}/set_env.sh ]; then source {p}/set_env.sh; "
            f"elif [ -f {p}/bin/setenv.bash ]; then source {p}/bin/setenv.bash; "
            f"else echo {sh_quote('[FAIL] --cann-path 下既无 set_env.sh 也无 bin/setenv.bash: ')}"
            f"{p} >&2; exit 2; fi")
    if tilelang_path:
        lines.append(f"source {sh_quote_path(tilelang_path + '/set_env.sh')}")
    if env_dir:
        lines.append(f"export PATH={sh_quote_path(env_dir + '/bin')}:$PATH")
    return lines


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("TILELANG_NPU_HOST"),
                    help="远程昇腾机地址（必填；默认取环境变量 TILELANG_NPU_HOST）")
    ap.add_argument("--port", type=int, default=env_port(),
                    help="SSH 端口（默认 22，可被环境变量 TILELANG_NPU_PORT 覆盖）")
    ap.add_argument("--user", default=os.environ.get("TILELANG_NPU_USER", "root"),
                    help="SSH 用户（默认 root，可被环境变量 TILELANG_NPU_USER 覆盖）")
    ap.add_argument("--remote-base",
                    default=os.environ.get("TILELANG_NPU_WORKDIR", "~/tilelang-work"),
                    help="远端父目录（默认 ~/tilelang-work 或环境变量 TILELANG_NPU_WORKDIR）；"
                         "远端工作目录 = {remote-base}/{workdir-name}")
    ap.add_argument("--cann-path", default=os.environ.get("CANN_INSTALL_PATH", ""),
                    help="CANN 安装路径（默认取 CANN_INSTALL_PATH）；用于 source {path}/set_env.sh"
                         "（缺失时回退 {path}/bin/setenv.bash）")
    ap.add_argument("--tilelang-path", default=os.environ.get("TILELANG_ASCEND_PATH", ""),
                    help="TileLang-Ascend 仓库路径（默认取 TILELANG_ASCEND_PATH）；用于 source {path}/set_env.sh")
    ap.add_argument("--env-dir", default=os.environ.get("TILELANG_ENV_DIR", ""),
                    help="远程 Python venv 目录（默认取 TILELANG_ENV_DIR）；会把 {dir}/bin 前置到 PATH，"
                         "显式给出时必须存在")
    ap.add_argument("--deploy", required=True,
                    help="本地文件或目录（整个目录递归上传）")
    ap.add_argument("--cmd", required=True,
                    help="在 {remote-base}/{workdir-name} 下执行的命令（激活前置由本脚本注入）")
    ap.add_argument("--workdir-name", default=None,
                    help="remote-base 下的落地目录名，同时也是 --cmd 的工作目录"
                         "（默认取 --deploy 的最后一级名；单文件部署同样生效）")
    return ap, ap.parse_args(argv)


def main(argv=None):
    ap, args = parse_args(argv)
    if not args.host:
        ap.error("缺少目标机地址：传 --host 或设置环境变量 TILELANG_NPU_HOST")

    deploy = os.path.abspath(args.deploy)
    if not os.path.exists(deploy):
        ap.error(f"--deploy 路径不存在：{deploy}")
    is_dir = os.path.isdir(deploy)
    check_quotable(deploy, "--deploy")

    # 落地目录名：--workdir-name 优先，否则取 --deploy 的最后一级；两者都不再各说各话。
    name = args.workdir_name or os.path.basename(deploy.rstrip("\\/"))
    check_name(name, "--workdir-name" if args.workdir_name else "--deploy 的最后一级名")

    remote_base = args.remote_base.replace("\\", "/").rstrip("/")
    if not remote_base or remote_base == "/":
        ap.error(f"--remote-base 不能为空或 /（当前：{args.remote_base!r}）")
    check_quotable(remote_base, "--remote-base")
    for flag, value in (("--cann-path", args.cann_path), ("--tilelang-path", args.tilelang_path),
                        ("--env-dir", args.env_dir)):
        if value:
            check_quotable(value, flag)

    target = f"{args.user}@{args.host}"
    ssh_opt = f"-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -p {args.port}"
    scp_opt = f"-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -P {args.port}"

    # 1) 建好父目录，并解析成绝对路径：其后的 rm -rf / cd / scp 目标全部用绝对路径，
    #    避免 `~` 或相对路径在「远端 shell 展开」与「scp 字面传输」两边语义不同。
    probe = run(f'ssh {ssh_opt} {target} '
                f'"mkdir -p {sh_quote_path(remote_base)} && cd {sh_quote_path(remote_base)} && pwd"',
                capture=True)
    lines = [ln.strip() for ln in (probe.stdout or "").splitlines() if ln.strip()]
    remote_base = lines[-1] if lines else ""
    if not remote_base.startswith("/"):
        raise SystemExit(f"无法把 --remote-base 解析成远端绝对路径："
                         f"{args.remote_base!r} -> {(probe.stdout or '').strip()!r}")
    remote_dir = f"{remote_base}/{name}"

    # --env-dir 显式给出却不存在时必须直接失败，不能带着错解释器继续跑。
    if args.env_dir:
        chk = run(f'ssh {ssh_opt} {target} '
                  f'"test -d {sh_quote_path(args.env_dir)} && echo __exists__ || echo __missing__"',
                  capture=True)
        if "__exists__" not in (chk.stdout or ""):
            raise SystemExit(f"--env-dir 已给出但远端不存在该目录：{args.env_dir}"
                             f"（远端实际返回 {(chk.stdout or '').strip()!r}）")

    # 唯一后缀：远端临时文件名按 invocation 隔离，并发跑不同参数不会互相覆盖。
    token = f"{os.getpid()}_{secrets.token_hex(4)}"

    # 2) 上传
    if is_dir:
        # scp 的目标目录若已存在，会把源目录「嵌套」进去（work/op/op）；
        # 所以先传到唯一暂存名（目标不存在时 scp 会按该名字建目录），再整体替换 remote_dir。
        stage = f"{remote_base}/.{name}.staging.{token}"
        run(f'ssh {ssh_opt} {target} "rm -rf {sh_quote(stage)}"')
        run(f'scp -r {scp_opt} "{deploy}" "{target}:{stage}"')
        run(f'ssh {ssh_opt} {target} '
            f'"rm -rf {sh_quote(remote_dir)} && mv {sh_quote(stage)} {sh_quote(remote_dir)}"')
    else:
        run(f'ssh {ssh_opt} {target} '
            f'"rm -rf {sh_quote(remote_dir)} && mkdir -p {sh_quote(remote_dir)}"')
        run(f'scp {scp_opt} "{deploy}" "{target}:{remote_dir}/"')

    # 3) 环境激活 + 命令写成脚本，避免引号转义问题
    lines = ["#!/bin/bash", "set -eo pipefail"]
    lines += build_preamble(args.cann_path, args.tilelang_path, args.env_dir)
    lines += [f"cd {sh_quote(remote_dir)}", args.cmd]
    script = "\n".join(lines) + "\n"
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, newline="\n", encoding="utf-8") as f:
        f.write(script)
        local_sh = f.name

    remote_sh = f"{remote_base}/.run_{name}.{token}.sh"
    try:
        run(f'scp {scp_opt} "{local_sh}" "{target}:{remote_sh}"')
        run(f'ssh {ssh_opt} {target} "bash {sh_quote(remote_sh)}"')
    finally:
        os.unlink(local_sh)
        # 清理不能覆盖主命令的退出码，所以 check=False。
        run(f'ssh {ssh_opt} {target} "rm -f {sh_quote(remote_sh)}"', check=False)


if __name__ == "__main__":
    main()
