"""diffusers 推理后端：模型加载、采样器选择、批量生成、hires-fix 精修。

设计要点：
- 单一 safetensors 直接从磁盘加载（from_single_file），无需先转 diffusers 目录；
- CUDA fp16 优先，CPU fp32 兜底；
- 同 seed 同参数可复现（关闭 cudnn benchmark / 开启 deterministic）；
- 显存不足时按需 CPU offload。
"""

from __future__ import annotations

import gc
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 先设置环境变量再 import torch / diffusers：
# - from_single_file 需要从 Hub 拉取少量 config JSON；直连 huggingface.co 在部分网络下不可用，
#   默认指向 hf-mirror 镜像（可用 HF_ENDPOINT 覆盖）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

SAMPLERS = {
    "euler_a": "EulerAncestralDiscreteScheduler",
    "euler": "EulerDiscreteScheduler",
    "dpmpp_2m": "DPMSolverMultistepScheduler",
    "dpmpp_2m_karras": "DPMSolverMultistepScheduler",
    "dpmpp_2m_sde": "DPMSolverMultistepScheduler",
    "dpmpp_sde": "DPMSolverSinglestepScheduler",
    "unipc": "UniPCMultistepScheduler",
    "ddim": "DDIMScheduler",
    "lms": "LMSDiscreteScheduler",
    "kdpm2_a": "KDPM2AncestralDiscreteScheduler",
}

# 画幅 -> (width, height)，均按 64 对齐
ASPECTS = {
    "portrait": (832, 1216),
    "portrait_tall": (768, 1344),
    "square": (1024, 1024),
    "landscape": (1216, 832),
    "wide": (1344, 768),
    "card": (896, 1152),
    "banner": (1536, 640),
}


class RenderError(RuntimeError):
    pass


def _torch():
    import torch  # noqa: WPS433 (lazy import: 让 --help/--dry-run 不必加载 torch)

    return torch


@dataclass
class GenResult:
    image: Any
    seed: int
    width: int
    height: int
    seconds: float
    extra: dict = field(default_factory=dict)


def parse_aspect(aspect: str) -> tuple[int, int]:
    """接受 'portrait' / '832x1216' / '832*1216' 三种写法。"""
    key = (aspect or "").strip().lower()
    if key in ASPECTS:
        return ASPECTS[key]
    for sep in ("x", "*", "X"):
        if sep in key:
            left, _, right = key.partition(sep)
            try:
                w, h = int(left), int(right)
            except ValueError as exc:
                raise RenderError(f"画幅写法无法解析: {aspect!r}") from exc
            w, h = (w // 8) * 8, (h // 8) * 8
            if not (256 <= w <= 2048 and 256 <= h <= 2048):
                raise RenderError(f"画幅超出范围（256~2048，且需 8 的倍数）: {aspect!r}")
            return w, h
    raise RenderError(
        f"未知画幅 {aspect!r}；可用: {', '.join(sorted(ASPECTS))} 或 WxH（如 832x1216）"
    )


def _make_scheduler(name: str, pipe):
    from diffusers import (  # noqa: WPS433
        DDIMScheduler,
        DPMSolverMultistepScheduler,
        DPMSolverSinglestepScheduler,
        EulerAncestralDiscreteScheduler,
        EulerDiscreteScheduler,
        KDPM2AncestralDiscreteScheduler,
        LMSDiscreteScheduler,
        UniPCMultistepScheduler,
    )

    if name not in SAMPLERS:
        raise RenderError(f"未知采样器 {name!r}；可用: {', '.join(sorted(SAMPLERS))}")

    cfg = dict(pipe.scheduler.config)
    cfg.pop("_class_name", None)
    cfg.pop("_diffusers_version", None)

    if name == "euler_a":
        return EulerAncestralDiscreteScheduler.from_config(cfg)
    if name == "euler":
        return EulerDiscreteScheduler.from_config(cfg)
    if name == "dpmpp_2m":
        return DPMSolverMultistepScheduler.from_config(cfg, algorithm_type="dpmsolver++")
    if name == "dpmpp_2m_karras":
        return DPMSolverMultistepScheduler.from_config(
            cfg, algorithm_type="dpmsolver++", use_karras_sigmas=True
        )
    if name == "dpmpp_2m_sde":
        return DPMSolverMultistepScheduler.from_config(
            cfg, algorithm_type="sde-dpmsolver++", use_karras_sigmas=True
        )
    if name == "dpmpp_sde":
        return DPMSolverSinglestepScheduler.from_config(cfg, use_karras_sigmas=True)
    if name == "unipc":
        return UniPCMultistepScheduler.from_config(cfg)
    if name == "ddim":
        return DDIMScheduler.from_config(cfg)
    if name == "lms":
        return LMSDiscreteScheduler.from_config(cfg)
    if name == "kdpm2_a":
        return KDPM2AncestralDiscreteScheduler.from_config(cfg)
    raise RenderError(f"采样器 {name!r} 未实现")


class Engine:
    """单个 checkpoint 的推理引擎，可重复调用 generate()。"""

    def __init__(
        self,
        model_path: Path | str,
        *,
        device: str = "auto",
        dtype: str = "auto",
        offload: bool = False,
        verbose: bool = True,
    ) -> None:
        torch = _torch()
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise RenderError(
                f"模型文件不存在: {self.model_path}\n"
                "先运行 scripts/setup_runtime.ps1 下载模型，或传 --model 指定其它 checkpoint。"
            )

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RenderError("请求了 CUDA，但 torch.cuda.is_available() 为 False；改用 --device cpu")
        if dtype == "auto":
            dtype = "float16" if device == "cuda" else "float32"
        self.device = device
        self.dtype = getattr(torch, dtype)
        self.offload = offload and device == "cuda"
        self.verbose = verbose

        if device == "cuda":
            # 复现性：关掉 cudnn 自动调优，固定确定性算法
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
            torch.backends.cuda.matmul.allow_tf32 = True
            # 关键：限制单进程显存占比。Windows 的 WDDM 在显存超额时会静默把显存换到内存，
            # 结果不是报 OOM 而是慢十倍（实测 20s 变 489s）。卡住上限宁可直接报错。
            try:
                torch.cuda.set_per_process_memory_fraction(0.92, 0)
            except Exception:  # noqa: BLE001
                pass

        from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline  # noqa: WPS433
        from diffusers.utils import logging as dlog  # noqa: WPS433

        # 安静模式：默认把 diffusers 的加载进度条/警告压掉，只保留真正的错误，
        # 免得命令行输出里混进一堆 fp16 提示。
        if not verbose:
            dlog.set_verbosity_error()

        load_kwargs: dict[str, Any] = {"torch_dtype": self.dtype, "use_safetensors": True}
        name = self.model_path.name.lower()
        # SD1.5 规模模型体积 < 4GB，用 SD1.5 管线加载
        size_gb = self.model_path.stat().st_size / (1024**3)
        self.family_pipeline = "sdxl"
        if size_gb < 4.0 and not any(k in name for k in ("xl", "sdxl", "illustrious", "noob")):
            self.family_pipeline = "sd15"
            pipe = StableDiffusionPipeline.from_single_file(str(self.model_path), **load_kwargs)
        else:
            pipe = StableDiffusionXLPipeline.from_single_file(str(self.model_path), **load_kwargs)

        pipe.set_progress_bar_config(disable=not verbose)
        pipe.safety_checker = None

        if self.offload:
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(self.device)

        # SDXL 内置 VAE 在 fp16 下偶发溢出，交给 diffusers 的 force_upcast 处理
        if hasattr(pipe, "vae") and getattr(pipe.vae, "config", None) is not None:
            pipe.vae.config.force_upcast = True

        self.pipe = pipe
        self._img2img = None

    # -- 生命周期 ---------------------------------------------------------
    def _defrag(self) -> None:
        """显存碎片治理：把缓存块还给驱动，避免 reserved 一路涨到超过物理显存。

        只在「预留远大于在用」时清，避免每张图都付一次重新分配的代价。
        """
        if self.device != "cuda":
            return
        torch = _torch()
        allocated = torch.cuda.memory_allocated()
        reserved = torch.cuda.memory_reserved()
        total = torch.cuda.get_device_properties(0).total_memory
        if reserved > allocated * 2.0 or reserved > total * 0.85:
            gc.collect()
            torch.cuda.empty_cache()

    def _from_pipe(self, cls):
        """from_pipe 的兼容包装：始终把 dtype 传下去，避免 fp32 重建导致显存翻倍。"""
        try:
            return cls.from_pipe(self.pipe, dtype=self.dtype)
        except TypeError:
            return cls.from_pipe(self.pipe, torch_dtype=self.dtype)

    def close(self) -> None:
        self.pipe = None
        self._img2img = None
        gc.collect()
        if self.device == "cuda":
            _torch().cuda.empty_cache()

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- 生成 -------------------------------------------------------------
    def _generator(self, seed: int):
        torch = _torch()
        gen = torch.Generator(device=self.device if self.device == "cuda" else "cpu")
        gen.manual_seed(int(seed) & 0xFFFFFFFF)
        return gen

    def generate(
        self,
        *,
        prompt: str,
        negative: str = "",
        width: int = 832,
        height: int = 1216,
        steps: int = 30,
        cfg: float = 6.0,
        sampler: str = "euler_a",
        seed: int = -1,
        count: int = 1,
    ) -> list[GenResult]:
        if count < 1:
            raise RenderError("count 必须 >= 1")
        self.pipe.scheduler = _make_scheduler(sampler, self.pipe)
        results: list[GenResult] = []
        for i in range(count):
            real_seed = (
                int.from_bytes(os.urandom(4), "little") & 0x7FFFFFFF if seed is None or seed < 0 else int(seed) + i
            )
            started = time.perf_counter()
            out = self.pipe(
                prompt=prompt,
                negative_prompt=negative or None,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=cfg,
                generator=self._generator(real_seed),
            )
            elapsed = time.perf_counter() - started
            results.append(
                GenResult(
                    image=out.images[0],
                    seed=real_seed,
                    width=width,
                    height=height,
                    seconds=elapsed,
                )
            )
            self._defrag()
        return results

    def hires_fix(
        self,
        image,
        *,
        prompt: str,
        negative: str = "",
        scale: float = 1.5,
        denoise: float = 0.45,
        steps: int = 30,
        cfg: float = 6.0,
        sampler: str = "euler_a",
        seed: int = -1,
        max_pixels: int = 1_600_000,
    ) -> GenResult:
        """把图放大后做低强度重绘，补细节（尤其脸/发丝）。

        显存保护：放大后的像素数会被压到 `max_pixels` 以内（16GB 显卡的实测甜点区，
        超过这个尺寸 SDXL 的注意力开销是平方级增长，会直接把 16GB 显存打满并拖慢十倍）。
        """
        from PIL import Image  # noqa: WPS433

        if not (1.0 < scale <= 2.5):
            raise RenderError("hires 倍数需在 (1.0, 2.5] 之间")
        if self._img2img is None:
            from diffusers import StableDiffusionXLImg2ImgPipeline  # noqa: WPS433

            # 关键：必须把 dtype 传下去。from_pipe 默认按 float32 重建管线，
            # 而组件是共享对象 —— 不传 dtype 会把已经加载好的 fp16 权重原地转成 fp32，
            # 显存直接翻倍（6.5GB -> 13GB），16GB 卡上会慢十倍甚至卡死。
            if self.family_pipeline == "sdxl":
                self._img2img = self._from_pipe(StableDiffusionXLImg2ImgPipeline)
            else:
                from diffusers import StableDiffusionImg2ImgPipeline

                self._img2img = self._from_pipe(StableDiffusionImg2ImgPipeline)
            self._img2img.set_progress_bar_config(disable=not self.verbose)
        # 每次调用都按当前采样器重建调度器，避免沿用上一次的配置
        self.pipe.scheduler = _make_scheduler(sampler, self.pipe)
        self._img2img.scheduler = self.pipe.scheduler

        requested = (image.width * scale, image.height * scale)
        effective_scale = scale
        if requested[0] * requested[1] > max_pixels:
            effective_scale = round((max_pixels / (image.width * image.height)) ** 0.5, 3)
        # 大图解码时开 VAE 分块，避免解码峰值爆显存（vae 在 pipe 与 img2img 间共享）
        tiling = (image.width * image.height * effective_scale**2) > 1_200_000
        if tiling:
            try:
                self.pipe.vae.enable_tiling()
            except AttributeError:  # 老版本 diffusers 没有该方法，忽略即可
                pass

        # img2img 的有效步数 = steps * denoise，这里换算回等效总步数（并限制上限避免过慢）
        effective_steps = max(4, min(60, int(round(steps / max(0.05, denoise)))))
        real_seed = int.from_bytes(os.urandom(4), "little") & 0x7FFFFFFF if seed < 0 else int(seed)

        torch = _torch()
        attempt_scale = effective_scale
        last_error: Exception | None = None
        for attempt in range(2):
            tw = max(64, int(round(image.width * attempt_scale / 8)) * 8)
            th = max(64, int(round(image.height * attempt_scale / 8)) * 8)
            upscaled = image.convert("RGB").resize((tw, th), Image.LANCZOS)
            started = time.perf_counter()
            try:
                out = self._img2img(
                    prompt=prompt,
                    negative_prompt=negative or None,
                    image=upscaled,
                    strength=denoise,
                    num_inference_steps=effective_steps,
                    guidance_scale=cfg,
                    generator=self._generator(real_seed),
                )
            except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:  # 显存不足时降档重试一次
                if "out of memory" not in str(exc).lower() or attempt == 1:
                    raise
                last_error = exc
                gc.collect()
                torch.cuda.empty_cache()
                attempt_scale = round(attempt_scale * 0.75, 3)
                continue
            elapsed = time.perf_counter() - started
            self._defrag()
            return GenResult(
                image=out.images[0],
                seed=real_seed,
                width=tw,
                height=th,
                seconds=elapsed,
                extra={
                    "hires": {
                        "requested_scale": scale,
                        "applied_scale": round(attempt_scale, 3),
                        "clamped": attempt_scale < scale,
                        "retried_after_oom": attempt > 0,
                        "denoise": denoise,
                        "steps": effective_steps,
                        "vae_tiling": tiling,
                    }
                },
            )
        raise RenderError(f"hires-fix 失败：{last_error}")


def device_report() -> dict:
    """给 selftest / --doctor 用的环境报告。"""
    info: dict[str, Any] = {}
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_available"] = bool(torch.cuda.is_available())
        info["torch_cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            info["vram_gb"] = round(props.total_memory / (1024**3), 1)
    except Exception as exc:  # pragma: no cover
        info["torch_error"] = f"{type(exc).__name__}: {exc}"
    try:
        import diffusers

        info["diffusers"] = diffusers.__version__
    except Exception as exc:  # pragma: no cover
        info["diffusers_error"] = f"{type(exc).__name__}: {exc}"
    return info
