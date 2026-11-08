#!/usr/bin/env python
"""anime-art 自检 / 验收测试。

  python selftest.py             # 单元测试 + 集成测试（需要 torch 和权重）
  python selftest.py --unit-only # 只跑单元测试（不加载 torch，秒级）
  python selftest.py --json      # 机器可读报告

退出码：0 全部通过；1 有失败；2 环境缺失（集成测试无法进行）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

RESULTS: list[dict] = []


def case(name: str, group: str = "unit"):
    def deco(fn):
        fn._case = {"name": name, "group": group}
        return fn

    return deco


def run_case(fn) -> None:
    meta = getattr(fn, "_case", {"name": fn.__name__, "group": "unit"})
    try:
        detail = fn() or ""
        RESULTS.append({**meta, "ok": True, "detail": str(detail)})
        print(f"  PASS  {meta['name']}" + (f"  ({detail})" if detail else ""))
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc(limit=3)
        RESULTS.append({**meta, "ok": False, "detail": f"{type(exc).__name__}: {exc}", "trace": tb})
        print(f"  FAIL  {meta['name']}  -> {type(exc).__name__}: {exc}")


# ==========================================================================
# 单元测试
# ==========================================================================
@case("预设目录可加载且包含关键角色")
def t_catalog():
    from artlib import Catalog

    cat = Catalog()
    ids = set(cat.ids())
    for required in ("whale-chan", "whale-chan-chibi", "anime-girl", "anime"):
        assert required in ids, f"缺少预设 {required}"
    whale = cat.get("whale-chan", kind="character")
    assert "1girl" in whale.tags and "blue hair" in whale.tags
    assert whale.source.get("license"), "角色预设必须带授权说明"
    return f"{len(ids)} 个预设"


@case("非法预设 id / 类型错误会被拒绝")
def t_preset_errors():
    from artlib import Catalog, PresetError

    cat = Catalog()
    for bad in ("nope", ""):
        try:
            cat.get(bad, kind="character")
        except PresetError:
            continue
        raise AssertionError(f"应当拒绝 {bad!r}")
    try:
        cat.get("anime", kind="character")
    except PresetError:
        return "类型校验生效"
    raise AssertionError("kind 校验失效")


@case("中文场景转译：最长匹配 + 虚词忽略")
def t_cn_tags():
    from artlib.cn_tags import translate_cn

    tags, unmatched = translate_cn("雨天的电车站，撑着伞回头看")
    assert "train station" in tags, tags
    assert "holding umbrella" in tags, tags
    assert "looking back" in tags, tags
    assert not unmatched, f"不应有未收录：{unmatched}"

    tags2, _ = translate_cn("毛毛细雨")
    assert tags2 == ["drizzle"], f"最长匹配失败：{tags2}"

    tags3, unmatched3 = translate_cn("在夜晚的海边")
    assert "night" in tags3 and "beach" in tags3, tags3
    assert not unmatched3, unmatched3

    tags4, _ = translate_cn("silver hair, red eyes")
    assert tags4 == ["silver hair", "red eyes"], tags4
    return f"{len(translate_cn('雨天的电车站')[0])} 个 tag"


@case("提示词：质量词/评级/去重/token 预算")
def t_prompt():
    from artlib import build_prompt, count_tokens

    plan = build_prompt(
        core_tags=["1girl", "solo", "Blue_Hair", "blue hair", "blue hair"],
        detail_tags=["maid headdress"],
        scene_text="樱花树下微笑",
        style_tags=["anime style"],
        composition_tags=["upper body"],
        family="animagine",
    )
    assert plan.prompt.startswith("masterpiece"), plan.prompt
    assert "safe" in plan.positive_tags, plan.positive_tags
    assert plan.positive_tags.count("blue hair") == 1, plan.positive_tags
    assert plan.prompt.count("blue hair") == 1
    assert "cherry blossoms" in plan.prompt
    assert count_tokens(plan.prompt) <= 77
    assert not plan.dropped, plan.dropped

    long_plan = build_prompt(
        core_tags=["1girl"] * 1,
        detail_tags=[f"detail{i}" for i in range(60)],
        scene_text="",
        family="animagine",
        max_tokens=60,
    )
    assert long_plan.dropped, "超预算时必须裁掉标签"
    assert all(t.startswith("detail") for t in long_plan.dropped), long_plan.dropped
    assert len(long_plan.positive_tags) >= 5
    assert count_tokens(long_plan.prompt) <= 60
    return f"预算裁剪 {len(long_plan.dropped)} 项"


@case("提示词：权重语法会被剥离并提示")
def t_prompt_weight():
    from artlib import build_prompt

    plan = build_prompt(core_tags=["(smile:1.2)", "1girl"], family="animagine")
    assert "smile" in plan.positive_tags, plan.positive_tags
    assert "1.2" not in plan.prompt, plan.prompt
    assert any("权重" in w for w in plan.warnings), plan.warnings
    return "已剥离"


@case("风格 drop：单色风格剔除颜色 tag")
def t_style_drop():
    from artlib import Catalog, build_prompt

    cat = Catalog()
    sketch = cat.get("sketch", kind="style")
    assert "blue hair" in sketch.drop, sketch.drop

    plan = build_prompt(
        core_tags=["1girl", "dark blue hair", "blue eyes", "fin ears", "maid"],
        style_tags=sketch.tags,
        drop_tags=sketch.drop,
        family="animagine",
    )
    assert "blue hair" not in plan.positive_tags, plan.positive_tags
    assert "blue eyes" not in plan.positive_tags
    assert "fin ears" in plan.positive_tags and "maid" in plan.positive_tags
    assert "monochrome" in plan.positive_tags
    assert any("剔除" in w for w in plan.warnings), plan.warnings
    return "剔除生效"


@case("画幅解析与边界校验")
def t_aspect():
    from artlib import ASPECTS, RenderError, parse_aspect

    assert parse_aspect("portrait") == ASPECTS["portrait"]
    assert parse_aspect("1024x1024") == (1024, 1024)
    assert parse_aspect("833x1219") == (832, 1216), parse_aspect("833x1219")
    for bad in ("100x100", "abc", "3000x3000", "1x1"):
        try:
            parse_aspect(bad)
        except RenderError:
            continue
        raise AssertionError(f"应当拒绝 {bad!r}")
    return "6 个预设画幅"


@case("PNG 元数据写入 / 读回 / sidecar")
def t_meta():
    from PIL import Image

    from artlib import read_png_text, save_png, save_sidecar

    with tempfile.TemporaryDirectory() as tmp:
        img = Image.new("RGB", (64, 64), (30, 60, 120))
        path = Path(tmp) / "t.png"
        meta = {"prompt": "1girl, 测试", "seed": 12345, "nested": {"a": 1}}
        save_png(img, path, meta)
        text = read_png_text(path)
        assert text["prompt"] == "1girl, 测试", text
        assert text["seed"] == "12345"
        assert json.loads(text["nested"]) == {"a": 1}
        side = save_sidecar(path, meta)
        assert json.loads(side.read_text(encoding="utf-8"))["seed"] == 12345
    return "tEXt + json 通过"


@case("图像体检：纯色/正常图判定")
def t_stats():
    from PIL import Image, ImageDraw

    from artlib import image_stats, looks_blank

    for color in ((255, 255, 255), (0, 0, 0), (30, 60, 120)):
        blank = Image.new("RGB", (256, 256), color)
        assert looks_blank(image_stats(blank))[0], f"纯色 {color} 应判为无效"

    # 造一张有渐变和线条的「像图像」的图
    busy = Image.new("RGB", (256, 256))
    px = busy.load()
    for y in range(256):
        for x in range(256):
            px[x, y] = (20 + x // 3, 30 + y // 4, 60 + (x + y) // 6)
    draw = ImageDraw.Draw(busy)
    for i in range(0, 256, 8):
        draw.line([(i, 20), (255 - i, 235)], fill=(245, 205, 125), width=3)
    draw.ellipse([70, 60, 186, 176], fill=(240, 240, 250))
    ok, reason = looks_blank(image_stats(busy))
    assert not ok, f"有内容的图被误判：{reason}"
    return "判定逻辑正确"


@case("拼图输出尺寸与布局")
def t_sheet():
    from PIL import Image

    from artlib import contact_sheet

    with tempfile.TemporaryDirectory() as tmp:
        imgs = [(Image.new("RGB", (512, 768), (i * 40, 90, 160)), f"seed {i}") for i in range(3)]
        out = contact_sheet(imgs, Path(tmp) / "sheet.png", cols=2, tile_width=320)
        with Image.open(out) as sheet:
            assert sheet.width > 320 and sheet.height > 320
            assert sheet.width < 1200
        # 单图也应能出拼图
        contact_sheet(imgs[:1], Path(tmp) / "one.png", cols=2)
    return "OK"


@case("CLI --dry-run / --list-presets / 错误码")
def t_cli():
    py = sys.executable
    gen = str(SCRIPTS / "anime_gen.py")

    out = subprocess.run(
        [py, gen, "--scene", "樱花树下微笑", "--dry-run", "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, out.stderr[-800:]
    payload = json.loads(out.stdout)
    assert payload["width"] > 0 and payload["prompt"]

    out2 = subprocess.run([py, gen, "--list-presets"], capture_output=True, text=True, encoding="utf-8")
    assert out2.returncode == 0 and "whale-chan" in out2.stderr + out2.stdout

    out3 = subprocess.run(
        [py, gen, "--preset", "not-exist", "--dry-run"], capture_output=True, text=True, encoding="utf-8"
    )
    assert out3.returncode == 2, f"未知预设应返回 2，实际 {out3.returncode}"
    return "CLI 行为正确"


# ==========================================================================
# 集成测试（需要 torch + 权重）
# ==========================================================================
def _pick_model():
    from anime_gen import pick_model

    return pick_model(None)


@case("推理引擎可加载并出图", group="integration")
def t_engine():
    from PIL import Image

    from artlib import Engine, image_stats, looks_blank

    model = _pick_model()
    with Engine(model, verbose=False) as engine:
        res = engine.generate(
            prompt="masterpiece, 1girl, solo, blue hair, blue eyes, upper body, looking at viewer, safe",
            negative="lowres, worst quality, low quality",
            width=768,
            height=768,
            steps=6,
            cfg=5.0,
            sampler="euler_a",
            seed=1234,
        )[0]
        assert isinstance(res.image, Image.Image)
        stats = image_stats(res.image)
        blank, reason = looks_blank(stats)
        assert not blank, f"生成结果疑似无效：{reason}"
        assert (res.image.width, res.image.height) == (768, 768)
        return f"{res.seconds:.1f}s, 边缘密度 {stats['edge_mean']}"


@case("同 seed 可复现", group="integration")
def t_reproducible():
    from artlib import Engine

    model = _pick_model()
    kwargs = dict(
        prompt="1girl, blue hair, blue eyes, upper body, safe, masterpiece",
        negative="lowres, worst quality",
        width=640,
        height=640,
        steps=4,
        cfg=5.0,
        sampler="euler_a",
        seed=777,
    )
    with Engine(model, verbose=False) as engine:
        a = engine.generate(**kwargs)[0].image
        b = engine.generate(**kwargs)[0].image
    ha = hashlib.sha256(a.tobytes()).hexdigest()
    hb = hashlib.sha256(b.tobytes()).hexdigest()
    assert ha == hb, f"同 seed 结果不一致：{ha[:12]} vs {hb[:12]}"
    return f"hash {ha[:12]}"


@case("不同 seed 出图不同", group="integration")
def t_seed_varies():
    from artlib import Engine

    model = _pick_model()
    with Engine(model, verbose=False) as engine:
        a = engine.generate(
            prompt="1girl, blue hair, upper body, safe, masterpiece", width=512, height=512,
            steps=4, cfg=5.0, sampler="euler_a", seed=1,
        )[0].image
        b = engine.generate(
            prompt="1girl, blue hair, upper body, safe, masterpiece", width=512, height=512,
            steps=4, cfg=5.0, sampler="euler_a", seed=2,
        )[0].image
    assert hashlib.sha256(a.tobytes()).hexdigest() != hashlib.sha256(b.tobytes()).hexdigest()
    return "OK"


@case("hires-fix 放大且保持内容", group="integration")
def t_hires():
    from artlib import Engine

    model = _pick_model()
    with Engine(model, verbose=False) as engine:
        base = engine.generate(
            prompt="1girl, blue hair, upper body, safe, masterpiece", width=512, height=512,
            steps=4, cfg=5.0, sampler="euler_a", seed=42,
        )[0]
        up = engine.hires_fix(
            base.image, prompt="1girl, blue hair, upper body, safe, masterpiece",
            scale=1.5, denoise=0.35, steps=4, seed=42,
        )
    assert up.image.width == 768 and up.image.height == 768, (up.image.width, up.image.height)
    return f"{base.image.width}->{up.image.width}, {up.seconds:.1f}s"


@case("端到端 CLI 出图 + 元数据完整", group="integration")
def t_e2e():
    from artlib import read_png_text

    py = sys.executable
    gen = str(SCRIPTS / "anime_gen.py")
    with tempfile.TemporaryDirectory() as tmp:
        out = subprocess.run(
            [py, gen, "--preset", "whale-chan", "--scene", "樱花树下微笑", "--aspect", "square",
             "--steps", "4", "--seed", "2024", "--out", tmp, "--json"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert out.returncode == 0, out.stderr[-1200:]
        payload = json.loads(out.stdout)
        assert payload["ok"] and payload["count"] == 1
        png = Path(payload["outputs"][0]["file"])
        assert png.is_file()
        text = read_png_text(png)
        for key in ("prompt", "seed", "model", "preset"):
            assert key in text, f"PNG 缺少元数据 {key}"
        assert text["seed"] == "2024"
        sidecar = png.with_suffix(".json")
        assert sidecar.is_file()
        assert json.loads(sidecar.read_text(encoding="utf-8"))["seed"] == 2024
        return png.name


# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    print("== anime-art 自检 ==")
    print(f"skill : {SKILL_ROOT}")

    unit = [v for v in globals().values() if callable(v) and getattr(v, "_case", {}).get("group") == "unit"]
    integ = [v for v in globals().values() if callable(v) and getattr(v, "_case", {}).get("group") == "integration"]

    print("\n[单元测试]")
    for fn in unit:
        run_case(fn)

    env_ok = True
    if args.unit_only:
        print("\n[集成测试] 跳过（--unit-only）")
    else:
        print("\n[集成测试]")
        try:
            import torch  # noqa: F401

            device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
            print(f"  device: {device}")
        except Exception as exc:  # noqa: BLE001
            env_ok = False
            print(f"  跳过：torch 不可用（{type(exc).__name__}: {exc}）")
        if env_ok:
            try:
                model = _pick_model()
                print(f"  model : {model.name} ({model.stat().st_size / 1024**3:.2f} GB)")
            except Exception as exc:  # noqa: BLE001
                env_ok = False
                print(f"  跳过：找不到权重（{exc}）")
        if env_ok:
            for fn in integ:
                run_case(fn)

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["ok"])
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n结果：{passed}/{total} 通过" + (f"，{len(failed)} 失败" if failed else ""))
    for item in failed:
        print(f"  - {item['name']}: {item['detail']}")

    if args.json:
        print(json.dumps({"total": total, "passed": passed, "results": RESULTS}, ensure_ascii=False, indent=2))

    if failed:
        return 1
    return 0 if env_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
