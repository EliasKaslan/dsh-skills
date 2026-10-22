#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注释掉 vllm-ascend 仓里 torch 家族的版本 pin —— vllm-ascend 版的 use_existing_torch.py。

为什么需要：`pip install -e . --no-build-isolation` 期间不要动环境里已经装好的
torch / torch-npu / triton(-ascend) 栈，直接复用它们（torch 与 torch_npu 版本强绑定，
被 pip 换掉就会 import 崩）。

处理范围：
  requirements.txt   -> 整行注释掉（setuptools 的 _reqs.parse_strings 会丢弃 # 行，
                        所以注释行不会进 install_requires）
  pyproject.toml     -> 注释掉 [build-system].requires 数组里同名的整行元素
                        （--no-build-isolation 下 pip 会校验数组里每一项已安装，
                         留着 pin 就会因版本不一致报 build dependencies 不满足）

必须处理的包：torch / torch-npu / triton / triton-ascend
一并处理（同族，pin 留着会把 torch 反拉回来）：torchvision / torchaudio

可选 --arctic：额外注释 arctic-inference==0.1.1。
  仅在 gcc < 9 的机器上需要（如 Debian 10 的 gcc 8.3）：它的 C++ 扩展要 C++20 <span>，
  编不过。该包只被 vllm 的可选 suffix-decoding 路径使用，vllm-ascend 源码不引用它。
  注意与「预装」策略相反：gcc>=9 的机器应带隔离预装它，而不是注释掉。

特性：幂等（重复运行不会叠加注释）；首次运行备份为 <file>.pinbak；
pyproject.toml 改完用 tomllib 自校验，不合法则自动回滚。
用法：python3 strip_torch_pins.py [--arctic] [repo_dir]   # repo_dir 默认当前目录
"""

import os
import re
import shutil
import sys

TORCH_TARGETS = ("torch", "torch-npu", "torchvision", "torchaudio", "triton", "triton-ascend")
ARCTIC = "arctic-inference"

# 当前生效的目标集合；main() 里可被 --arctic 扩展。
TARGETS = TORCH_TARGETS

MARK = "pin removed -> reuse the torch stack installed in this env"
MARK_ARCTIC = "pin removed -> needs C++20 <span>, not buildable with this gcc"

REQ_FILES = ("requirements.txt", "pyproject.toml")
BAK_SUFFIX = ".pinbak"

NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(.*)$")
TOML_ENTRY_RE = re.compile(r'^"([A-Za-z0-9][A-Za-z0-9._-]*)(.*?)"\s*,?\s*$')
SEP = "[<>=!~; \t#"


def norm(name):
    return name.lower().replace("_", "-")


def mark_for(name):
    return MARK_ARCTIC if name == ARCTIC else MARK


def req_target(line):
    """requirements.txt 的某一行命中目标包则返回包名，否则 None。"""
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("-"):
        return None
    m = NAME_RE.match(s)
    if not m:
        return None
    name, rest = m.group(1), m.group(2)
    if norm(name) not in TARGETS:
        return None
    if rest and rest[0] not in SEP:  # 防 torchx / torchvisionx 这类前缀误判
        return None
    return norm(name)


def toml_target(line):
    """pyproject.toml 里形如 `"torch==2.10.0",` 的整行元素命中则返回包名，否则 None。"""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    m = TOML_ENTRY_RE.match(s)
    if not m:
        return None
    name, rest = m.group(1), m.group(2)
    if norm(name) not in TARGETS:
        return None
    if rest and rest[0] not in SEP:
        return None
    return norm(name)


def comment_out(path, matcher):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    hits, pins, out = [], [], []
    for line in lines:
        name = matcher(line)
        if name is None:
            out.append(line)
            continue
        nl = "\n" if line.endswith("\n") else ""
        body = line[:-1] if nl else line
        indent = body[: len(body) - len(body.lstrip())]
        out.append("%s# %s  # %s%s" % (indent, body.strip(), mark_for(name), nl))
        hits.append(name)
        pins.append(body.strip().rstrip(",").strip())
    if not hits:
        print("[=] %s: no target pin found (already stripped?)" % os.path.basename(path))
        return out, hits, pins
    bak = path + BAK_SUFFIX
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print("[+] backup: %s" % os.path.basename(bak))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(out)
    print("[+] %s: commented %d line(s) -> %s" % (os.path.basename(path), len(hits), ", ".join(hits)))
    return out, hits, pins


def check_requirements(text):
    left = [ln.strip() for ln in text.splitlines() if req_target(ln) is not None]
    return left


def check_toml(path):
    try:
        import tomllib
    except ImportError:
        return None
    with open(path, "rb") as f:
        data = tomllib.load(f)
    requires = data.get("build-system", {}).get("requires", [])
    bad = [r for r in requires if norm(re.split(r"[<>=!~;\[]", r, maxsplit=1)[0]) in TARGETS]
    return requires, bad


def main(argv):
    global TARGETS
    args = [a for a in argv[1:] if not a.startswith("-")]
    flags = [a for a in argv[1:] if a.startswith("-")]
    unknown = [f for f in flags if f not in ("--arctic", "-h", "--help")]
    if unknown or "-h" in flags or "--help" in flags:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr if unknown else sys.stdout)
        if unknown:
            print("[x] unknown option(s): %s" % ", ".join(unknown), file=sys.stderr)
            return 2
        return 0

    if "--arctic" in flags:
        TARGETS = TORCH_TARGETS + (ARCTIC,)
        print("[i] --arctic: also stripping %s (needed on gcc < 9)" % ARCTIC)

    repo = args[0] if args else "."
    if not os.path.isdir(repo):
        print("[x] not a directory: %s" % repo, file=sys.stderr)
        return 2
    missing = [f for f in REQ_FILES if not os.path.isfile(os.path.join(repo, f))]
    if missing:
        print("[x] %s not found in %s -- is this a vllm-ascend source checkout?"
              % (", ".join(missing), os.path.abspath(repo)), file=sys.stderr)
        return 2

    req_path = os.path.join(repo, "requirements.txt")
    toml_path = os.path.join(repo, "pyproject.toml")

    req_text, hits1, pins1 = comment_out(req_path, req_target)
    toml_text, hits2, pins2 = comment_out(toml_path, toml_target)

    left = check_requirements("".join(req_text))
    if left:
        print("[x] still active in requirements.txt: %s" % left, file=sys.stderr)
        return 1
    checked = check_toml(toml_path)
    if checked is not None:
        requires, bad = checked
        if bad or not requires:
            print("[x] pyproject.toml [build-system].requires invalid after edit (bad=%s) -- restoring" % bad,
                  file=sys.stderr)
            shutil.copy2(toml_path + BAK_SUFFIX, toml_path)
            return 1
        print("[=] pyproject.toml parses; build-system.requires has %d entries left" % len(requires))

    pins = pins1 + pins2
    if pins:
        print("[i] original pins (install these first if the env lacks a torch stack):")
        for p in pins:
            print("      %s" % p)
    print("[ok] done. review with: cd %s && git diff -- requirements.txt pyproject.toml" % os.path.abspath(repo))
    print("[i] do NOT commit these edits; restore with: mv requirements.txt%s ... (or git checkout)" % BAK_SUFFIX)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
