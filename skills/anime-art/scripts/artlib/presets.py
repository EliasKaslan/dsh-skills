"""角色 / 风格 / 构图 / 画幅 预设的加载与校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
PRESET_DIR = SKILL_ROOT / "presets"

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class PresetError(ValueError):
    pass


@dataclass
class Preset:
    id: str
    name: str
    kind: str  # character | style | composition
    tags: list[str] = field(default_factory=list)          # 核心特征：高优先级，永远保留
    detail: list[str] = field(default_factory=list)        # 细节补充：低优先级，token 紧张时先裁
    drop: list[str] = field(default_factory=list)          # 风格专用：从最终提示词里剔除的 tag
    negative: list[str] = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)
    notes: str = ""

    def describe(self) -> str:
        bits = [f"{self.id} ({self.name})"]
        if self.source.get("license"):
            bits.append(f"license: {self.source['license']}")
        return " — ".join(bits)


class Catalog:
    """从 presets/*.json 载入全部预设。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or PRESET_DIR)
        self._items: dict[str, Preset] = {}
        self.load()

    def load(self) -> None:
        self._items.clear()
        if not self.root.is_dir():
            raise PresetError(f"预设目录不存在: {self.root}")
        for path in sorted(self.root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise PresetError(f"{path.name} 不是合法 JSON: {exc}") from exc
            for item in raw.get("presets", []):
                preset = self._parse(item, path.name)
                if preset.id in self._items:
                    raise PresetError(f"预设 id 重复: {preset.id} ({path.name})")
                self._items[preset.id] = preset

    @staticmethod
    def _parse(item: dict, filename: str) -> Preset:
        pid = str(item.get("id", "")).strip()
        if not _NAME_RE.match(pid):
            raise PresetError(f"{filename}: 预设 id 非法（小写字母/数字/连字符）: {pid!r}")

        def _str_list(key: str) -> list[str]:
            values = item.get(key) or []
            if not isinstance(values, list) or not all(isinstance(t, str) and t.strip() for t in values):
                raise PresetError(f"{filename}: 预设 {pid} 的 {key} 必须是非空字符串数组")
            return [t.strip() for t in values]

        return Preset(
            id=pid,
            name=str(item.get("name") or pid),
            kind=str(item.get("kind") or "character"),
            tags=_str_list("tags"),
            detail=_str_list("detail"),
            drop=_str_list("drop"),
            negative=[str(t).strip() for t in (item.get("negative") or [])],
            defaults=dict(item.get("defaults") or {}),
            source=dict(item.get("source") or {}),
            notes=str(item.get("notes") or ""),
        )

    # -- 查询 -------------------------------------------------------------
    def get(self, pid: str, kind: str | None = None) -> Preset:
        item = self._items.get(pid)
        if item is None:
            scope = {k: v for k, v in self._items.items() if kind is None or v.kind == kind}
            hint = "、".join(sorted(scope)) or "（空）"
            raise PresetError(f"未知预设 {pid!r}；可用: {hint}")
        if kind and item.kind != kind:
            raise PresetError(f"预设 {pid!r} 的类型是 {item.kind}，此处需要 {kind}")
        return item

    def by_kind(self, kind: str) -> list[Preset]:
        return [p for p in self._items.values() if p.kind == kind]

    def ids(self, kind: str | None = None) -> list[str]:
        return sorted(p.id for p in self._items.values() if kind is None or p.kind == kind)
