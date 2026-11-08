#!/usr/bin/env python
"""anime-art 生成器 CLI。

示例：
  # 最常用：鲸鱼娘、雨中电车站、竖版、2 张
  python anime_gen.py --preset whale-chan --scene "雨天的电车站，撑着伞回头看" --count 2

  # 只出提示词，不跑模型（秒回，用于核对 tag）
  python anime_gen.py --scene "海边夕阳" --dry-run

  # Q 版表情包
  python anime_gen.py --preset whale-chan-chibi --scene "得意地吃白饭" --aspect square --style sticker

输出：PNG（内嵌提示词元数据）+ 同名 .json sidecar + 可选拼图。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from artlib import (  # noqa: E402
    ASPECTS,
    SAMPLERS,
    Catalog,
    PresetError,
    RenderError,
    build_meta,
    build_prompt,
    contact_sheet,
    detect_family,
    device_report,
    image_stats,
    looks_blank,
    parse_aspect,
    save_png,
    save_sidecar,
    slugify,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]
FALLBACK_MODEL_DIRS = [
    Path(os.environ.get("ANIME_ART_MODEL_DIR", "")) if os.environ.get("ANIME_ART_MODEL_DIR") else None,
    Path(os.environ.get("DSH_HOME", Path.home() / ".dsh")) / "models" / "anime-art",
    SKILL_ROOT / "models",
]


def eprint(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def pick_model(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        for root in FALLBACK_MODEL_DIRS:
            if root and (root / explicit).is_file():
                return root / explicit
            if root and (root / f"{explicit}.safetensors").is_file():
                return root / f"{explicit}.safetensors"
        raise RenderError(f"找不到模型: {explicit}（也未在模型目录中匹配到同名文件）")

    for root in FALLBACK_MODEL_DIRS:
        if not root or not root.is_dir():
            continue
        files = sorted(root.glob("*.safetensors")) + sorted(root.glob("*.ckpt"))
        if not files:
            continue
        # 优先级：opt（官方优化版）最好 -> animagine -> illustrious/noob -> 其它 SDXL
        for kw in ("animagine-xl-4.0-opt", "animagine", "illustrious", "noob", "xl"):
            for f in files:
                if kw in f.name.lower():
                    return f
        return files[0]
    raise RenderError(
        "没有找到任何 checkpoint。\n"
        "  1) 运行 scripts/setup_runtime.ps1 自动下载 Animagine XL 4.0；或\n"
        "  2) 手动把 .safetensors 放进 "
        + str(FALLBACK_MODEL_DIRS[1])
        + "；或\n"
        "  3) 用 --model 指定文件路径。"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anime_gen.py",
        description="本地二次元图像生成器（SDXL / Animagine 系）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    g = p.add_argument_group("内容")
    g.add_argument("--preset", default=None, help="角色预设 id（默认 whale-chan）")
    g.add_argument("--scene", default="", help="中文/英文画面描述，如“雨天的电车站，撑着伞回头看”")
    g.add_argument("--scene-tags", default="", help="直接给场景 danbooru tag（逗号分隔，优先级高于 --scene）")
    g.add_argument("--tags", default="", help="额外 danbooru tag，逗号分隔，如 'looking at viewer, wind'")
    g.add_argument("--style", default=None, help="风格预设 id（anime/soft/cinematic/sketch/sticker）")
    g.add_argument("--composition", default=None, help="构图预设 id（bust/half/full/back/sit/headshot）")
    g.add_argument("--negative-extra", default="", help="追加负面词，逗号分隔")

    g = p.add_argument_group("质量与参数")
    g.add_argument("--aspect", default=None, help=f"画幅: {'/'.join(sorted(ASPECTS))} 或 WxH")
    g.add_argument("--size", default=None, help="自定义尺寸 WxH（等价于 --aspect WxH）")
    g.add_argument("--steps", type=int, default=None, help="采样步数（默认取预设，通常 28~32）")
    g.add_argument("--cfg", type=float, default=None, help="CFG（默认 6.0；动漫模型 5~7）")
    g.add_argument("--sampler", default=None, choices=sorted(SAMPLERS), help="采样器")
    g.add_argument("--seed", type=int, default=-1, help="随机种子；-1 表示随机（会写进元数据）")
    g.add_argument("--count", type=int, default=1, help="生成张数（种子依次递增）")
    g.add_argument("--hires", type=float, default=0.0, help="hires-fix 放大倍数，如 1.5；0 表示关闭")
    g.add_argument("--hires-denoise", type=float, default=0.45, help="hires-fix 重绘强度（0.3~0.6）")
    g.add_argument(
        "--hires-max-mp",
        type=float,
        default=1.6,
        help="hires-fix 的像素上限（百万像素，默认 1.6）。16GB 卡单张可放到 2.3，"
        "再大注意力开销平方增长；真爆显存会自动降档重试",
    )
    g.add_argument("--max-tokens", type=int, default=75, help="正向提示词 token 预算（SDXL 上限 77）")
    g.add_argument("--no-safety", action="store_true", help="移除 NSFW 负面词（默认开启安全过滤）")

    g = p.add_argument_group("运行环境")
    g.add_argument("--model", default=None, help="checkpoint 路径或模型目录内的文件名")
    g.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    g.add_argument("--offload", action="store_true", help="显存不足时启用 CPU offload（更慢）")

    g = p.add_argument_group("输出")
    g.add_argument("--out", default="anime-out", help="输出目录（默认 ./anime-out）")
    g.add_argument("--name", default="", help="文件名前缀（默认用预设 id）")
    g.add_argument("--grid", action="store_true", help="额外生成一张拼图")
    g.add_argument("--no-sidecar", action="store_true", help="不写 .json sidecar")
    g.add_argument("--json", action="store_true", help="以 JSON 输出结果（供程序解析）")
    g.add_argument("--dry-run", action="store_true", help="只打印提示词，不加载模型")
    g.add_argument("--list-presets", action="store_true", help="列出全部预设")
    g.add_argument("--doctor", action="store_true", help="检查运行环境（torch/CUDA/模型）")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    args = build_parser().parse_args(argv)
    catalog = Catalog()

    # ---------------- 信息类子功能 ----------------
    if args.list_presets:
        for kind in ("character", "style", "composition"):
            eprint(f"\n[{kind}]")
            for preset in catalog.by_kind(kind):
                eprint(f"  {preset.id:<20} {preset.name}")
        eprint(f"\n画幅: {', '.join(sorted(ASPECTS))}")
        eprint(f"采样器: {', '.join(sorted(SAMPLERS))}")
        return 0

    if args.doctor:
        report = device_report()
        try:
            report["model"] = str(pick_model(args.model))
            report["model_size_gb"] = round(Path(report["model"]).stat().st_size / 1024**3, 2)
        except RenderError as exc:
            report["model_error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("cuda_available") and report.get("model") else 1

    # ---------------- 解析预设 ----------------
    char_id = args.preset
    if char_id is None:
        chars = catalog.by_kind("character")
        if not chars:
            raise PresetError("没有任何角色预设")
        char_id = "whale-chan" if "whale-chan" in catalog.ids() else chars[0].id
    character = catalog.get(char_id, kind="character")
    defaults = character.defaults

    style_id = args.style or defaults.get("style", "anime")
    style = catalog.get(style_id, kind="style")
    composition_id = args.composition or defaults.get("composition", "bust")
    composition = catalog.get(composition_id, kind="composition")

    width, height = parse_aspect(args.size or args.aspect or defaults.get("aspect", "portrait"))
    steps = args.steps if args.steps is not None else int(defaults.get("steps", 30))
    cfg = args.cfg if args.cfg is not None else float(defaults.get("cfg", 6.0))
    sampler = args.sampler or defaults.get("sampler", "euler_a")
    if steps < 1 or steps > 150:
        raise RenderError("--steps 需在 1~150")
    if not 0 < cfg <= 30:
        raise RenderError("--cfg 需在 (0, 30]")
    if args.count < 1 or args.count > 16:
        raise RenderError("--count 需在 1~16")

    model_path = Path(args.model) if args.model and Path(args.model).is_file() else None
    family = detect_family(model_path.name if model_path else (args.model or "animagine-xl-4.0"))

    extra_tags = [t for t in (args.tags or "").split(",") if t.strip()]
    neg_extra = [t for t in (args.negative_extra or "").split(",") if t.strip()]

    plan = build_prompt(
        core_tags=character.tags,
        detail_tags=character.detail,
        scene_text=args.scene,
        scene_tags=[t for t in (args.scene_tags or "").split(",") if t.strip()],
        style_tags=style.tags,
        composition_tags=composition.tags,
        extra_tags=extra_tags,
        drop_tags=list(style.drop),
        style_negative=list(style.negative) + list(character.negative),
        family=family,
        safety=not args.no_safety,
        max_tokens=args.max_tokens,
        negative_extra=neg_extra,
    )
    for warning in plan.warnings:
        eprint(f"[warn] {warning}")

    if args.dry_run:
        payload = {
            "preset": character.id,
            "style": style.id,
            "composition": composition.id,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "sampler": sampler,
            **plan.as_dict(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    # ---------------- 生成 ----------------
    try:
        import torch  # noqa: F401  先探一下依赖是否齐全
        from artlib import Engine  # 延迟导入：--dry-run 不需要 torch
    except ImportError as exc:
        raise RenderError(
            f"缺少推理依赖（{exc}）。当前解释器没有装 torch/diffusers，请用技能专用运行时：\n"
            '  $py = "$env:DSH_HOME\\venvs\\anime-art\\Scripts\\python.exe"\n'
            f'  & $py "{Path(__file__).resolve()}" <同样的参数>\n'
            "运行时不存在时先执行 scripts/setup_runtime.ps1 搭建。"
        ) from exc

    resolved_model = pick_model(args.model)
    eprint(f"[anime-art] 模型: {resolved_model.name}")
    eprint(f"[anime-art] 预设: {character.name} / 风格: {style.name} / 构图: {composition.name}")
    eprint(f"[anime-art] 尺寸: {width}x{height}  steps={steps} cfg={cfg} sampler={sampler}")
    eprint(f"[anime-art] 提示词: {plan.prompt}")

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(args.name or character.id)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    started_all = time.perf_counter()
    with Engine(resolved_model, device=args.device, offload=args.offload) as engine:
        results = engine.generate(
            prompt=plan.prompt,
            negative=plan.negative,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            sampler=sampler,
            seed=args.seed,
            count=args.count,
        )

        outputs: list[dict] = []
        tiles: list[tuple] = []
        for idx, res in enumerate(results):
            image = res.image
            hires_meta = None
            if args.hires and args.hires > 1.0:
                refined = engine.hires_fix(
                    image,
                    prompt=plan.prompt,
                    negative=plan.negative,
                    scale=args.hires,
                    denoise=args.hires_denoise,
                    steps=steps,
                    cfg=cfg,
                    sampler=sampler,
                    seed=res.seed,
                    max_pixels=max(400_000, int(args.hires_max_mp * 1_000_000)),
                )
                image = refined.image
                hires_meta = dict(refined.extra.get("hires", {}))
                hires_meta["seconds"] = round(refined.seconds, 2)
                if hires_meta.get("clamped"):
                    eprint(
                        f"[warn] 放大倍率被压到 {hires_meta['applied_scale']}×（{image.width}x{image.height}）："
                        f"超过 --hires-max-mp={args.hires_max_mp} 的像素上限被截断。"
                        "想要更大尺寸就调高这个上限（16GB 卡单张约 2.3），或换更小的基础尺寸。"
                    )

            stats = image_stats(image)
            blank, reason = looks_blank(stats)
            meta = build_meta(
                preset_id=character.id,
                preset_name=character.name,
                style_id=style.id,
                composition=composition.id,
                plan=plan.as_dict(),
                seed=res.seed,
                width=image.width,
                height=image.height,
                steps=steps,
                cfg=cfg,
                sampler=sampler,
                model_path=str(resolved_model),
                extras={
                    "hires_fix": hires_meta,
                    "seconds": round(res.seconds, 2),
                    "engine": {"device": engine.device, "dtype": str(engine.dtype).replace("torch.", "")},
                    "image_stats": stats,
                    "blank_suspect": blank,
                    "blank_reason": reason,
                },
            )

            fname = f"{stem}-{stamp}-{res.seed}{'-hires' if hires_meta else ''}.png"
            path = out_dir / fname
            save_png(image, path, meta)
            if not args.no_sidecar:
                save_sidecar(path, meta)
            if blank:
                eprint(f"[warn] {fname} 疑似无效图：{reason}；可尝试 --offload 或换 seed")
            eprint(
                f"[anime-art] {path.name}  {image.width}x{image.height}  "
                f"{res.seconds:.1f}s" + (f" (+hires {hires_meta['seconds']}s)" if hires_meta else "")
            )
            outputs.append(
                {
                    "file": str(path),
                    "sidecar": None if args.no_sidecar else str(path.with_suffix(".json")),
                    "seed": res.seed,
                    "width": image.width,
                    "height": image.height,
                    "seconds": round(res.seconds, 2),
                    "blank_suspect": blank,
                    "stats": stats,
                }
            )
            tiles.append((image, f"{character.id} · seed {res.seed}"))

        grid_path = None
        if args.grid and len(tiles) > 1:
            grid_path = contact_sheet(tiles, out_dir / f"{stem}-{stamp}-grid.png", cols=min(4, len(tiles)))
            eprint(f"[anime-art] 拼图: {grid_path.name}")

    summary = {
        "ok": True,
        "preset": character.id,
        "style": style.id,
        "composition": composition.id,
        "model": str(resolved_model),
        "prompt": plan.prompt,
        "negative_prompt": plan.negative,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "sampler": sampler,
        "count": len(outputs),
        "total_seconds": round(time.perf_counter() - started_all, 1),
        "outputs": outputs,
        "grid": str(grid_path) if grid_path else None,
        "warnings": plan.warnings,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"完成：{len(outputs)} 张 -> {out_dir}")
        for item in outputs:
            print(f"  {Path(item['file']).name}  seed={item['seed']}  {item['seconds']}s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PresetError, RenderError) as exc:
        eprint(f"[error] {exc}")
        raise SystemExit(2)
    except KeyboardInterrupt:
        eprint("[error] 已中断")
        raise SystemExit(130)
