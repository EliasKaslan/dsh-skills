# 故障排查

## A. 运行时

### `$env:DSH_HOME\venvs\anime-art\Scripts\python.exe` 不存在
运行时还没搭。跑（注意本机默认禁止执行 .ps1，需要 Bypass）：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:DSH_HOME\skills\anime-art\scripts\setup_runtime.ps1"
```

它做四件事：建 venv → 装 torch(cu128)/diffusers → 下权重（断点续传）→ 自检。重复执行会跳过已完成步骤。

### `import torch` 报 DLL 错误 / `torch.cuda.is_available()` 为 False
1. 先看 `--doctor` 输出。
2. 确认装的是 **cu128** 版而不是 CPU 版：
   ```powershell
   & $py -c "import torch; print(torch.__version__, torch.version.cuda)"
   ```
   期望形如 `2.9.1+cu128 12.8`。
3. 驱动太旧会导致 CUDA 初始化失败：NVIDIA 驱动需支持 CUDA 12.8（2024 年末以后的驱动基本都行）。
4. 实在不行就用 `--device cpu` 兜底（1024×1024 一张约 3~8 分钟，仅应急）。

### pip 装不动 / 超时
脚本默认走国内镜像（腾讯 PyPI + 阿里云 pytorch-wheels）。手动装：

```powershell
& $py -m pip install --find-links https://mirrors.aliyun.com/pytorch-wheels/cu128/ `
    --index-url https://mirrors.cloud.tencent.com/pypi/simple `
    "torch-2.9.1+cu128-cp312-cp312-win_amd64.whl"
```

### `transformers` 版本过新导致 diffusers 报错
```powershell
& $py -m pip install "transformers<5" --index-url https://mirrors.cloud.tencent.com/pypi/simple
```

## B. 模型

### `找不到模型` / `模型文件不存在`
优先级顺序：`--model` > `ANIME_ART_MODEL_DIR` > `%DSH_HOME%\models\anime-art` > 技能内 `models/`。

手动下载（ModelScope，支持断点续传）：
```powershell
curl.exe -L -C - -o "$env:DSH_HOME\models\anime-art\animagine-xl-4.0-opt.safetensors" `
  "https://www.modelscope.cn/models/cagliostrolab/animagine-xl-4.0/resolve/master/animagine-xl-4.0-opt.safetensors"
```
文件应约 6.5GB；不完整时 `safetensors` 读取会报 header 错误，删掉重下即可。

### 换成别的 checkpoint
任何单文件 SDXL 动漫模型都能用：`--model "D:\models\my-anime-xl.safetensors"`。
文件名里带 `illustrious`/`noob` 时会自动切到对应的质量词与负面词表（见 `artlib/prompts.py` 的 `QUALITY_TAGS`）。

## C. 生成质量

| 现象 | 原因 | 处理 |
|---|---|---|
| 纯黑/纯白 | VAE 溢出或采样崩 | 换 seed；`--offload`；降 `--cfg` 到 5 |
| 手部畸形 | SDXL 通病 | 多抽几张；`--negative-extra "extra arms, fused fingers"`；不要全身+手部特写 |
| 画面糊、颜色灰 | 步数太低 / cfg 太高 | `--steps 30`（**低于 20 步质量断崖式下降**，实测 12 步会出拼贴怪图） |
| 角色不像 | 关键 tag 被裁 | `--dry-run` 检查；场景写短一点 |
| 少了女仆头饰/鲸尾/发带 | detail 层最先被裁（`--dry-run` 的 `dropped_tags` 里能看到） | 把它们写进 `--tags`（优先级高于场景/构图/细节层），或删掉一两个场景词 |
| 说"打游戏"但桌面是空的 | 模型不会自己布景 | 场景词点名道具：`显示器`／`键盘`／`手柄`／`台灯`，或用 `--style gaming-night` |
| 出现文字/水印 | 模型学到的封面习惯 | 负面词已含 `text, watermark`；仍出现就换 seed |
| 构图不对（说回头却是正面） | 场景词被裁 + 构图冲突 | 用 `--composition back` 显式指定 |
| 出图慢得离谱 | 在跑 CPU 或 offload | `--doctor` 确认；关 `--offload` |
| **越跑越慢（第二张开始慢 10~20 倍）** | Windows WDDM 在显存超额时把显存换到内存，不报 OOM 只降速 | 引擎已内置 `set_per_process_memory_fraction(0.92)` + 碎片回收；若自己写脚本，务必在每次生成后 `gc.collect(); torch.cuda.empty_cache()`，并检查 `torch.cuda.memory_reserved()` 是否超过显存（实测曾飙到 18.4GB / 16GB，单张从 12s 变 489s） |

## D. 文件与元数据
- 图片在哪：`--out` 指定，默认 `./anime-out`（相对当前工作目录）。
- 元数据怎么看：同名 `.json`；或直接读 PNG tEXt：
  ```powershell
  & $py -c "from PIL import Image; print(Image.open('x.png').text)"
  ```
- 路径含中文/空格没问题（已在含中文的工作目录下实测）。

### 精修尺寸上不去（想要 1248×1824 却只给 1048×1528）
hires 默认把放大后的像素压到 1.6MP，所以 `--hires 1.5` 实际落到 1048×1528。要更大就调上限：

```powershell
& $py $gen ... --hires 1.5 --hires-denoise 0.38 --hires-max-mp 2.3   # 1248×1824
```

16GB 卡单张 2.3MP 实测不 OOM（1248×1824 精修约 15 秒）；真爆了引擎会自动按 0.75 降档重试，
元数据里 `hires_fix.retried_after_oom=true` 就是触发过降档。再往上（>2.5MP）收益很小、风险很大。

### PowerShell 里命令"报错"但图其实出好了
把 python 的 stderr 接进管道时（`... 2>&1 | Select-Object`），PowerShell 会把进度/警告行当成
ErrorRecord，进程退出码变 1 且整条命令看起来失败。判据是**文件在不在、尺寸对不对**，不是退出码：

```powershell
& $py $gen ... *> run.log    # 想留日志就这样写，避免 stderr 混进管道
Write-Output "exit=$LASTEXITCODE"   # 单独跑一次才准
```

## E. 自检

```powershell
& $py "$env:DSH_HOME\skills\anime-art\scripts\selftest.py"            # 单元 + 集成
& $py "$env:DSH_HOME\skills\anime-art\scripts\selftest.py" --unit-only # 只跑单元（秒级）
```

单元测试 FAIL 说明代码/预设被改坏了；集成测试跳说明 torch 或权重没就位。
