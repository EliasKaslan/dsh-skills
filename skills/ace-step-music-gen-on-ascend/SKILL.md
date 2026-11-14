---
name: ace-step-music-gen-on-ascend
description: 用 ACE-Step 1.5 turbo 在 192.168.13.190 上 CPU 出整首歌：权重补齐、批量生成、母带。
disable-model-invocation: true
warm-triggers: ACE-Step / AI 生成歌曲 / 出音乐 / 司凤版改编 / CPU 跑音乐模型
warm-reason: 低频：只在"用 AI 生成歌曲/编曲"时用；本机无 GPU，CPU 路线已固化，留档备查即可。
---

# ACE-Step 1.5 在昇腾机上用 CPU 出歌

## 何时调用

- 要"用 AI 生成一首歌/编曲/人声"且只有本机能连的昇腾机（无 NVIDIA GPU）时。
- 目标机：`root@192.168.13.190`（Atlas 800I A3，**64 核 / 1.38 TB RAM**，无可用 torch_npu 环境）。
- 不适用：要高质量商用中文人声 → 走云端 Suno 类平台；要 LoRA 微调 → 本机 `torch 2.10.0+cpu` 不具备训练可行性。

## 已固化的路径

远端根：`/home/x00886548/music/`，env：`env/acestep/bin/python`（3.11.18 + torch 2.10.0+cpu）。

| 文件 | 作用 |
|---|---|
| `gen.py` | 单次生成 CLI（`--caption --lyrics-file --duration --bpm --keyscale --steps 8`） |
| `run_batch.py` | 加载一次模型连跑多版，按 `specs*.json` 读 caption/BPM/调性/时长 |
| `master.py` | 母带：削头静音 + 20ms 淡入 + 1.5s 淡出 + K 加权 LUFS 归一 + 峰值封顶 |

关键：`gen.py` 靠自身位置推 `MUSIC_ROOT`，**必须放在 `/home/x00886548/music/`**，否则报
`can't open file '/home/x00886548/music/gen.py': [Errno 2] No such file or directory`。

Windows 侧三个助手（都验证过）：`music/_shared/rsh.ps1`（本地 .sh → base64 → 远端 bash）、
`upsh.ps1`（本地文件 → 远端，回显 md5 对账）、`downsh.ps1`（scp 拉回）。

## 实测性能（CPU，56 线程，8 步）

- 模型加载：60–90 s（一次）
- 10 s 音频：14.2 s
- 168 s 成曲：扩散 120–142 s（≈6 s/步）+ tiled VAE 解码，端到端 136 s；最慢一版 326 s

## 坑（全部有原文）

1. **下权重时 `--exclude 'acestep-5Hz-lm-1.7B/*'` 会导致每次运行都重下 3.4 GB**
   `MAIN_MODEL_COMPONENTS` 含 LM-1.7B，缺它 `check_main_model_exists()` 恒 False → 每次 `initialize_service` 打
   `[initialize_service] Main model not found, starting auto-download...` 并再下一遍。
   → 不要 exclude，或先下全再跑。`DEFAULT_LM_MODEL = "acestep-5Hz-lm-1.7B"`。
2. **判存抢跑**：`model.safetensors` 还在 `.cache/huggingface/**/*.incomplete` 时检查就跑了，日志说"缺失"其实几分钟后已就位。
   → 用 `find models/checkpoints/.cache -name '*.incomplete'` 判进度，比看日志准。
3. **`check_vae_exists` 的参数是 `"official"` 不是 `"default"`**（`DEFAULT_VAE_VARIANT = "official"`），传错会误报 VAE 缺失。
4. **没有 ffmpeg/lame**：只能出 WAV（48 kHz/16-bit/立体声，Peak 自动归一到 0.891≈-1 dBFS），要 MP3 得另想办法。
5. 机器上**没有任何 env 能 `import torch`**，`/usr/local/Ascend/ascend-toolkit` 也不存在 → 别浪费时间试 NPU，CPU 够快。

## 歌词红线

官方词（如 HOYO-MiX 的《耀斑》）不可抄录。项目内 `music/_shared/validate_packages.py` 的 `FORBIDDEN`
就是这道闸；生成用本项目自创词（`music/_shared/lyrics_fixed.txt`），要换词由用户自己提供文本落到远端
`/home/x00886548/music/lyrics_fixed.txt` 后重跑 `run_batch.py`。

## 客观验收口径（没有耳朵时）

`compare.py` 一行一版：时长/峰值/RMS/crest/1s-RMS 动态范围/**onset 自相关估 BPM**/低中高频占比。
BPM 自相关会出现半速读数（78.1≈156、84≈168），属正常歧义不是失败。
`analyze.py` 出对数频谱 PNG，可肉眼确认段落塌陷与段落切换是否真的存在。
削波看 `|x|>=0.999` 的采样点计数，必须为 0。
