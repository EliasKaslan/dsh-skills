"""提示词构建：Danbooru 标签流水线 + 中文场景转译 + token 预算控制。

SDXL 的文本编码器每段只有 77 token，超出部分会被截断，因此这里：
1. 按「质量 → 评级 → 主体 → 角色特征 → 服装 → 场景 → 风格」的优先级拼装；
2. 用 CLIP tokenizer 实测 token 数（无 tokenizer 时按字符估算）；
3. 超预算时从优先级最低的尾部标签开始裁剪，并回报被裁掉的标签。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cn_tags import translate_cn

# --------------------------------------------------------------------------
# 质量标签：不同模型族使用不同习惯写法
# --------------------------------------------------------------------------
QUALITY_TAGS: dict[str, list[str]] = {
    # Animagine XL 3.x / 4.0 官方推荐
    "animagine": ["masterpiece", "high score", "great score", "absurdres"],
    # Illustrious / NoobAI 系常用的打分前缀
    "illustrious": ["masterpiece", "best quality", "amazing quality", "very aesthetic", "absurdres"],
    "noobai": ["masterpiece", "best quality", "very aesthetic", "absurdres"],
    # 通用 SDXL / SD1.5 动漫模型
    "generic": ["masterpiece", "best quality", "highly detailed", "absurdres"],
    # 无质量前缀（写实或特殊风格）
    "none": [],
}

NEGATIVE_PRESETS: dict[str, list[str]] = {
    "animagine": [
        "lowres", "bad anatomy", "bad hands", "text", "error", "missing finger",
        "extra digits", "fewer digits", "cropped", "worst quality", "low quality",
        "low score", "bad score", "average score", "signature", "watermark",
        "username", "blurry",
    ],
    "illustrious": [
        "lowres", "bad anatomy", "bad hands", "text", "error", "missing finger",
        "extra digits", "fewer digits", "cropped", "worst quality", "low quality",
        "jpeg artifacts", "signature", "watermark", "username", "blurry",
    ],
    "generic": [
        "lowres", "bad anatomy", "bad hands", "worst quality", "low quality",
        "jpeg artifacts", "signature", "watermark", "username", "blurry", "text",
    ],
    "none": ["lowres", "worst quality", "watermark", "signature", "text"],
}

# 安全评级：Animagine v4 支持 general / sensitive / nsfw / explicit
SAFETY_NEGATIVE = ["nsfw", "explicit", "nude", "nipple", "cleavage"]

DEFAULT_MAX_TOKENS = 75


def detect_family(model_name: str) -> str:
    """从模型文件名猜模型族，用于选择质量标签与负面词。"""
    low = (model_name or "").lower()
    if "animagine" in low:
        return "animagine"
    if "illustrious" in low:
        return "illustrious"
    if "noob" in low:
        return "noobai"
    if any(k in low for k in ("anything", "meina", "counterfeit", "orange", "pastel")):
        return "generic"
    return "animagine" if "xl" in low or "sdxl" in low else "generic"


# --------------------------------------------------------------------------
# 标签清洗
# --------------------------------------------------------------------------
_WS_RE = re.compile(r"\s+")
_WEIGHT_RE = re.compile(r"^\((.*?):([0-9.]+)\)$")


def normalize_tag(tag: str) -> str:
    """统一写法：去下划线、压空白、小写化，并剥离 (tag:1.2) 权重语法。"""
    t = tag.strip().strip(",;")
    t = t.replace("_", " ")
    t = _WS_RE.sub(" ", t)
    if not t:
        return ""
    m = _WEIGHT_RE.match(t)
    if m:
        t = _WS_RE.sub(" ", m.group(1)).strip().lower()
    return t.lower()


def dedupe(tags: list[str]) -> list[str]:
    """保序去重，且认为 (x:1.2) 与 x 是同一标签。"""
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if not tag:
            continue
        m = _WEIGHT_RE.match(tag)
        key = m.group(1) if m else tag
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def join_tags(tags: list[str]) -> str:
    return ", ".join(t for t in tags if t)


# --------------------------------------------------------------------------
# 构建结果
# --------------------------------------------------------------------------
@dataclass
class PromptPlan:
    prompt: str
    negative: str
    positive_tags: list[str]
    negative_tags: list[str]
    dropped: list[str] = field(default_factory=list)
    tokens: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative,
            "positive_tags": self.positive_tags,
            "negative_tags": self.negative_tags,
            "dropped_tags": self.dropped,
            "positive_tokens": self.tokens,
            "warnings": self.warnings,
        }


def _token_counter():
    """惰性加载 CLIP tokenizer；失败则返回 None（退化为字符估算）。"""
    try:
        from transformers import CLIPTokenizer  # noqa: WPS433 (lazy)

        tok = CLIPTokenizer.from_pretrained("openai/clip-vit-large-patch14")
    except Exception:  # pragma: no cover - 无网络/无缓存时退化
        return None

    def count(text: str) -> int:
        return len(tok(text, truncation=False)["input_ids"])

    return count


_TOKENIZER_CACHE: list = []


def count_tokens(text: str) -> int:
    if not _TOKENIZER_CACHE:
        _TOKENIZER_CACHE.append(_token_counter())
    counter = _TOKENIZER_CACHE[0]
    if counter is None:
        # 粗略估算：CLIP BPE 平均每 4 个字符 1 token
        return max(1, round(len(text) / 4))
    return counter(text)


def build_prompt(
    *,
    core_tags: list[str],
    detail_tags: list[str] | None = None,
    scene_text: str = "",
    scene_tags: list[str] | None = None,
    style_tags: list[str] | None = None,
    composition_tags: list[str] | None = None,
    extra_tags: list[str] | None = None,
    drop_tags: list[str] | None = None,
    style_negative: list[str] | None = None,
    family: str = "animagine",
    quality_tags: list[str] | None = None,
    safety: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    negative_extra: list[str] | None = None,
) -> PromptPlan:
    """按优先级组装正向/负向提示词，并做 token 预算裁剪。

    优先级（高 → 低）：质量词 → 评级 → 角色核心特征 → 用户显式 tag →
    场景（含中文转译）→ 构图 → 画风 → 角色细节补充。
    超预算时从尾部整条裁剪，因此「用户显式 tag」与「角色核心」永远保得住。
    """
    warnings: list[str] = []

    # SDXL 文本编码器硬截断在 77 token；超过的部分一定会被丢掉，这里显式提示
    if max_tokens > 77:
        warnings.append(f"max_tokens={max_tokens} 超过 SDXL 的 77 token 上限，已按 77 处理")
        max_tokens = 77

    quality = quality_tags if quality_tags is not None else QUALITY_TAGS.get(family, QUALITY_TAGS["generic"])
    # Animagine 4.0 的评级词是 safe/sensitive/nsfw/explicit（3.x 同）
    rating: list[str] = []
    if family in ("animagine", "illustrious") and safety:
        rating = ["safe"]

    # diffusers 原生管线不会解析 (tag:1.2) 语法，权重会被当普通字符吃掉，这里剥离并提示
    weighted = [t for t in (list(core_tags) + list(detail_tags or []) + list(extra_tags or []))
                if _WEIGHT_RE.match(str(t).strip())]
    if weighted:
        warnings.append(
            "提示词里包含权重写法（如 (smile:1.2)），当前管线不解析权重，已自动去掉数字；"
            "需要强调某个 tag 就把它写靠前一点（越靠前权重越高）"
        )

    translated, unmatched = translate_cn(scene_text)
    if unmatched:
        warnings.append(
            "中文描述中有词条未收录，已忽略：" + "、".join(unmatched[:8])
            + "（可用 --tags 直接补 danbooru tag，或在 cn_tags.py 增补）"
        )

    # 优先级从高到低。
    # 画风紧跟在核心特征之后：用户显式指定了 --style，就不该被场景词挤掉
    #（线稿这类风格要靠一整组 tag 才压得住模型的默认上色习惯）。
    tiers: list[list[str]] = [
        list(quality),
        rating,
        dedupe([normalize_tag(t) for t in core_tags]),           # 1girl, solo, 角色核心特征
        dedupe([normalize_tag(t) for t in (style_tags or [])]),
        dedupe([normalize_tag(t) for t in (extra_tags or [])]),  # 用户显式追加
        [t for t in dedupe([normalize_tag(t) for t in translated])],
        dedupe([normalize_tag(t) for t in (scene_tags or [])]),
        dedupe([normalize_tag(t) for t in (composition_tags or [])]),
        dedupe([normalize_tag(t) for t in (detail_tags or [])]),  # 细节补充，最先被裁
    ]

    positives = dedupe([t for tier in tiers for t in tier])

    # 风格可以声明要剔除的 tag（例如线稿风格要把「蓝发/蓝瞳」这类颜色词拿掉，
    # 否则模型会一边被要求单色、一边被要求蓝发，最后出来的是褪色彩图）
    drop_set = {normalize_tag(t) for t in (drop_tags or []) if t}
    if drop_set:
        kept = [t for t in positives if (normalize_tag(t) not in drop_set)]
        if len(kept) != len(positives):
            warnings.append(
                f"当前画风剔除了 {len(positives) - len(kept)} 个颜色/冲突 tag（单色风格需要）"
            )
            positives = kept

    # token 预算：超限时从尾部整条裁剪（先砍用户追加，再砍风格/构图）
    dropped: list[str] = []
    text = join_tags(positives)
    tokens = count_tokens(text)
    if max_tokens and tokens > max_tokens:
        keep = list(positives)
        while keep and count_tokens(join_tags(keep)) > max_tokens:
            dropped.insert(0, keep.pop())
        positives = keep
        text = join_tags(positives)
        tokens = count_tokens(text)
        warnings.append(
            f"提示词超出 {max_tokens} token 预算，已裁剪 {len(dropped)} 个低优先级标签"
            "（可用 --max-tokens 放宽，或精简场景描述）"
        )

    negatives = list(NEGATIVE_PRESETS.get(family, NEGATIVE_PRESETS["generic"]))
    negatives += [normalize_tag(t) for t in (style_negative or [])]
    if safety:
        negatives += SAFETY_NEGATIVE
    negatives += [normalize_tag(t) for t in (negative_extra or [])]
    negatives = dedupe([t for t in negatives if t])

    return PromptPlan(
        prompt=text,
        negative=join_tags(negatives),
        positive_tags=positives,
        negative_tags=negatives,
        dropped=dropped,
        tokens=tokens,
        warnings=warnings,
    )
