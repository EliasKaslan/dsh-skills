"""Bake-off wrapper: register实验用画风/角色，不改 gen.py 本体。

为什么需要它：每次 `docker run` 要付约 2.5 分钟（容器启动 + 装载 6.5G 权重），
所以一轮对照必须塞进**一个**容器、一次 `sweep` 跑完。而 `--style-tags` 会把
所有 seed 的画风全改成同一个字符串，没法同容器对比多档画风。这个 wrapper 的
做法是：把 gen.py 当模块加载（此时 `__name__ != "__main__"`，main() 不会跑），
先把候选档注册进 `STYLE_PRESETS` / `STYLE_NEG` / `CHARS`，再自己调 main()——
argparse 的 `choices=sorted(STYLE_PRESETS)` 是在 main() 里构造的，所以新档名
在命令行上是合法的。

用法（容器内）：

    # 1) 写一份 patch（候选画风 + 可选角色改动）
    cat > /work/patch.json <<'JSON'
    {
      "styles": {
        "kvA": {"pos": "official art, soft shading, detailed eyes, delicate lineart, warm lighting"},
        "kvB": {"pos": "official art, soft shading, detailed eyes, delicate lineart, rich colors",
                "neg": "flat color, bold lineart, posterize, neon colors"}
      },
      "chars": {
        "deepseek": {"core": ["blue hair", "very long hair", "blue eyes", "ahoge", "maid headdress"],
                     "detail": ["navy blue dress", "white ruffled blouse", "gem brooch", "smile"]}
      }
    }
    JSON

    # 2) 一次跑完
    EXP_PATCH=/work/patch.json python scripts/exp_wrap.py sweep \
      --char deepseek --tag t1 --seeds 4242,7777 --styles kvA,kvB \
      --base 1216x1024 --scheduler euler_a \
      --scene "upper body, looking at viewer, indoors, wooden wall"

    # 3) 选中的档再手写进 gen.py 的 STYLE_PRESETS，别让它只活在这份 patch 里

没有 `EXP_PATCH` 时等价于直接跑 gen.py。
"""
import importlib.util
import json
import os
import sys

GEN_PATH = os.environ.get("GEN_PY", "/home/vllm/ai-musume/scripts/gen.py")

# 新档默认用的负面词：只压"海报感/霓虹感"，不要压光泽（眼睛得有高光）
DEFAULT_NEG = ("flat color, bold lineart, thick outline, sketchy, posterized, "
               "oversaturated, neon colors, vivid colors, low detail")


def load_gen():
    spec = importlib.util.spec_from_file_location("genmod", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)      # __name__ 是 "genmod"，所以 main() 不会执行
    return mod


def main():
    g = load_gen()
    patch_path = os.environ.get("EXP_PATCH", "")
    if patch_path:
        with open(patch_path, "r", encoding="utf-8") as fh:
            patch = json.load(fh)
        for name, spec in (patch.get("styles") or {}).items():
            g.STYLE_PRESETS[name] = spec["pos"]
            g.STYLE_NEG[name] = spec.get("neg") or DEFAULT_NEG
        for char, spec in (patch.get("chars") or {}).items():
            g.CHARS.setdefault(char, {})
            g.CHARS[char].update(spec)
        print("exp_wrap: patched styles=%s chars=%s"
              % (sorted(patch.get("styles") or {}), sorted(patch.get("chars") or {})),
              flush=True)

    sys.argv[0] = "gen.py"
    g.main()


if __name__ == "__main__":
    main()
