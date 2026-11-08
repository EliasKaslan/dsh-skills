# 验收记录（anime-art）

> 机器：Windows 11 / RTX 4070 Ti SUPER 16GB / 32GB RAM
> 运行时：Python 3.12.14 · torch 2.9.1+cu128 · diffusers 0.42.1 · transformers 5.22.2
> 权重：Animagine XL 4.0 Opt（6.46GB fp16，单文件 safetensors）
> 记录时间：2026-11-08

## 1. 自动化测试：16/16 通过

`python scripts/selftest.py`（单元 11 项 + 集成 5 项，退出码 0）

| # | 用例 | 断言要点 |
|---|---|---|
| U1 | 预设目录可加载 | 15 个预设；`whale-chan` 必须有 `1girl/blue hair` 且带授权字段 |
| U2 | 非法预设被拒绝 | 未知 id、类型不匹配都抛 `PresetError` |
| U3 | 中文场景转译 | 「雨天的电车站，撑着伞回头看」→ `train station/holding umbrella/looking back`；虚词不报未收录；「毛毛细雨」优先于「下雨」 |
| U4 | 提示词组装 | 质量词在前、`safe` 评级、`Blue_Hair` 与 `blue hair` 去重、token ≤ 77、超预算只裁尾部 |
| U5 | 权重语法 | `(smile:1.2)` 被剥离并告警 |
| U6 | 风格 drop | `sketch` 剔掉 `blue hair/blue eyes`，保留 `fin ears/maid` |
| U7 | 画幅解析 | 预设画幅、`WxH`、8 对齐、越界报错 |
| U8 | PNG 元数据 | tEXt 写入/读回、中文、嵌套 JSON、sidecar |
| U9 | 图像体检 | 纯白/纯黑/纯色判无效；有内容的图不误判 |
| U10 | 拼图 | 多图/单图都能出，尺寸合理 |
| U11 | CLI 行为 | `--dry-run` JSON、`--list-presets`、未知预设返回码 2 |
| I1 | 引擎可加载出图 | 768×768/6 步，非空白，边缘密度 11.46 |
| I2 | 同 seed 可复现 | 两次生成 sha256 完全一致（`64e80d805af1…`） |
| I3 | 不同 seed 不同 | 哈希不同 |
| I4 | hires-fix | 512→768，内容保持 |
| I5 | 端到端 | CLI 出图 + PNG 元数据 + sidecar 齐全 |

## 2. 性能（单次冷启动实测，同批同画幅）

| 场景 | 纯生成 | 进程总耗时 |
|---|---|---|
| 832×1216 / 30 步 | 7.3~8.2 s | ~20 s（含加载与存盘） |
| 1024×1024 / 30 步 | 8.1 s | ~26 s |
| 1216×832 / 30 步 | 8.0 s | ~23 s |
| 832×1216 → hires 1.258× (1048×1528, 60 步) | 12.6 s | — |
| `--offload` 1024×1024 / 12 步 | 11.4 s（同参数常规 4 s，约 2.8×） | — |

显存：常驻 6.58 GB，峰值约 7.4 GB（修好碎片治理后；修复前 reserved 曾涨到 18.4 GB / 16 GB 并触发 WDDM 换页，单张退化到 489 s）。

## 3. 视觉验收（gallery/ 8 张，均逐张人工检查）

| 图 | 结论 | 备注 |
|---|---|---|
| 01 樱花英雄图（hires） | 通过 | 深蓝渐变发 + 呆毛 + 鳍耳 + 女仆头饰 + 围裙，五官正常 |
| 02 雨天电车站 | 通过 | 逆光、伞、回头、发梢渐变都对；鲸尾鳍状发饰可见 |
| 03 Q 版表情包 | 通过 | 白底贴纸风、端饭碗、鼓脸；符合"爱吃白饭"人设 |
| 04 全身海边（hires） | 通过 | 全身比例正常、手藏在裙后（规避了手部难点） |
| 05 夜晚天台回头 | 通过 | 城市光斑、头发高光 |
| 06 通用少女（非 IP） | 通过 | 银发红瞳黑裙夜景，证明不绑定角色也能用 |
| 07 子午（男性版） | 通过 | 蓝发西装，与鲸鱼娘成对 |
| 08 线稿 | 通过 | 真·单色铅笔稿（drop 机制生效） |

已知瑕疵（不影响交付，如实记录）：
- 鳍耳颜色在个别 seed 会偏米黄（应在深蓝）；换 seed 或加 `fin ears` 靠前可复现蓝色。
- Q 版偶尔出现装饰性小贴纸/食物漂浮物（`sticker` 风格副作用）。
- 全身图脸部像素偏少，需 `--hires` 才够看。

## 4. 消融实验（evidence/）

| 实验 | 变量 | 结论 |
|---|---|---|
| `01-tag-ablation` | `fin ears` / `fish ears` / `animal ears+fin` / 有无 `whale tail` | `fin ears` 最像鲸鳍；`fish ears` 次之；`animal ears, fin` 出的是绒毛圆耳；`tail` 会把鳍耳染成米黄 → 保留 `fin ears`，`whale tail` 降级到 detail |
| `02-style-hair` | 线稿三版 + 三种发色写法 | `sketch+monochrome` 单用无效（出褪色彩图）；发色 `dark blue hair + blue hair + gradient hair` 最接近设定（深蓝根 + 青色梢） |
| `03-core-consistency` | 同一模板 4 个 seed | 4/4 稳定呈现深蓝渐变发、鳍耳、女仆装、蓝瞳 → 提示词模板可靠 |
| `04-sketch-attempts` | 线稿再校准 | 只加负面词仍会保留蓝瞳；必须用 `drop` 删掉颜色 tag 才是真单色 |

## 5. 健壮性矩阵

| 场景 | 行为 |
|---|---|
| 没有 torch 的解释器调用 | 退出码 2，提示改用专用运行时并给完整命令 |
| 模型缺失 | 明确报错 + 三种获取方式 |
| 未知预设 / 类型错配 | 退出码 2，列出可用预设 |
| 画幅越界 / 非 8 倍数 | 越界报错；非 8 倍数自动对齐 |
| 显存不足（hires） | 自动降 25% 重试一次，仍失败才抛错 |
| 中文路径 | 工作目录含中文（如 `...\261107_视觉摸索`）全程无异常 |
| 权限受限的执行策略 | `.ps1` 用 `powershell -ExecutionPolicy Bypass -File`，文档已注明 |
| 断网 | 首次加载需从 hf-mirror 拉 ~2MB 配置（已缓存后完全离线） |

## 6. 复现性

- 每张图 PNG 内嵌 `prompt/negative_prompt/seed/steps/cfg/sampler/model` 等 tEXt 字段，同名 `.json` 另存完整记录（含 `image_stats`、`hires_fix`、`engine`）。
- 同 seed 同参数 → 位图级一致（I2 已验证）；跨机器不保证一致（CUDA 版本与驱动差异）。

## 7. 未做 / 建议下一步

1. 角色一致性：用 IP-Adapter + 参考图（约 3GB）可让"鲸鱼娘"更贴原设；当前靠 tag 模板已达可用。
2. 表情包批量：`--count 8` 固定 seed 段 + 网格挑图，再脚本合成表情包九宫格。
3. LoRA 微调：若要在商用场景替换 IP，训练一个自有角色 LoRA 最划算。
4. 加速：SDXL-Lightning/DMD2（4~8 步）能把单张压到 2 秒级，代价是细节损失。
