<#
.SYNOPSIS
    为 anime-art 技能搭建本地推理运行时（venv + torch CUDA + 动漫向 SDXL 权重）。

.DESCRIPTION
    一次性 / 可重复执行：已完成的步骤会自动跳过。
      1. 用 DSH 自带 Python 建独立 venv（不污染 DSH 运行时）
      2. 从国内镜像装 torch(cu128) + diffusers/transformers 等
      3. 从 ModelScope 下载 Animagine XL 4.0 权重（断点续传）
      4. 自检：CUDA 可用性 + 权重完整性 + 采样一次

.PARAMETER InstallDir
    运行时根目录，默认 %DSH_HOME%\venvs\anime-art

.PARAMETER ModelDir
    权重目录，默认 %DSH_HOME%\models\anime-art

.PARAMETER SkipModel
    跳过权重下载（已手动放好 checkpoint 时使用）

.EXAMPLE
    # 默认执行策略禁止跑脚本时，用这一行：
    powershell -ExecutionPolicy Bypass -File setup_runtime.ps1
    powershell -ExecutionPolicy Bypass -File setup_runtime.ps1 -SkipModel
#>
[CmdletBinding()]
param(
    [string]$InstallDir = $(if ($env:DSH_HOME) { Join-Path $env:DSH_HOME 'venvs\anime-art' } else { Join-Path $HOME '.dsh\venvs\anime-art' }),
    [string]$ModelDir = $(if ($env:DSH_HOME) { Join-Path $env:DSH_HOME 'models\anime-art' } else { Join-Path $HOME '.dsh\models\anime-art' }),
    [switch]$SkipModel
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$TorchWheel = 'torch-2.9.1+cu128-cp312-cp312-win_amd64.whl'
$TorchIndex = 'https://mirrors.aliyun.com/pytorch-wheels/cu128/'
$PipIndex   = 'https://mirrors.cloud.tencent.com/pypi/simple'
$PipExtra   = 'https://mirrors.aliyun.com/pypi/simple'
$ModelRepo  = 'https://www.modelscope.cn/models/cagliostrolab/animagine-xl-4.0/resolve/master/animagine-xl-4.0-opt.safetensors'
$ModelFile  = 'animagine-xl-4.0-opt.safetensors'

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [ok] $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  [warn] $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. venv
Write-Step "1/4 Python venv -> $InstallDir"
$pyExe = Join-Path $InstallDir 'Scripts\python.exe'
if (Test-Path $pyExe) {
    Write-Ok "已存在，跳过创建"
} else {
    $base = Join-Path $env:DSH_HOME 'dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
    if (-not (Test-Path $base)) {
        $base = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
    if (-not $base) { throw "找不到可用的 Python 解释器（先安装 Python 3.12，或设置 DSH_HOME）" }
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir -Parent) | Out-Null
    & $base -m venv $InstallDir
    if (-not (Test-Path $pyExe)) { throw "venv 创建失败: $InstallDir" }
    Write-Ok "已创建 ($(& $pyExe -V))"
}

# ---------------------------------------------------------------- 2. torch
Write-Step "2/4 PyTorch CUDA + diffusers 依赖"
$hasTorch = $false
try {
    $null = & $pyExe -c "import torch, diffusers" 2>&1
    $hasTorch = ($LASTEXITCODE -eq 0)
} catch { $hasTorch = $false }

if ($hasTorch) {
    Write-Ok "torch/diffusers 已安装，跳过"
} else {
    Write-Host "  安装 torch（约 2.7GB，来自阿里云 PyTorch 镜像）..."
    & $pyExe -m pip install --upgrade pip -i $PipIndex --quiet
    & $pyExe -m pip install --find-links $TorchIndex --index-url $PipIndex --extra-index-url $PipExtra "$TorchWheel" --quiet
    if ($LASTEXITCODE -ne 0) { throw "torch 安装失败；可换用 --index-url https://download.pytorch.org/whl/cu128 重试" }
    & $pyExe -m pip install --index-url $PipIndex --extra-index-url $PipExtra diffusers transformers accelerate safetensors pillow numpy --quiet
    if ($LASTEXITCODE -ne 0) { throw "diffusers 依赖安装失败" }
    Write-Ok "安装完成"
}

# ---------------------------------------------------------------- 3. model
Write-Step "3/4 权重 -> $ModelDir"
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
$modelPath = Join-Path $ModelDir $ModelFile
if ($SkipModel) {
    Write-Warn2 "跳过下载（-SkipModel）"
} elseif ((Test-Path $modelPath) -and ((Get-Item $modelPath).Length -gt 6GB)) {
    Write-Ok "已存在 $([math]::Round((Get-Item $modelPath).Length/1GB,2)) GB，跳过"
} else {
    Write-Host "  从 ModelScope 下载 Animagine XL 4.0 Opt（约 6.5GB，支持断点续传）..."
    & curl.exe -L --fail --retry 5 --retry-delay 3 -C - -o $modelPath $ModelRepo
    if ($LASTEXITCODE -ne 0) { throw "权重下载失败；可手动下载后放入 $ModelDir" }
    Write-Ok "$([math]::Round((Get-Item $modelPath).Length/1GB,2)) GB"
}

# ---------------------------------------------------------------- 4. 自检
Write-Step "4/4 自检"
$probe = @'
import json, sys
out = {}
try:
    import torch
    out["torch"] = torch.__version__
    out["cuda_available"] = bool(torch.cuda.is_available())
    if torch.cuda.is_available():
        out["gpu"] = torch.cuda.get_device_name(0)
        out["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
except Exception as exc:
    out["torch_error"] = f"{type(exc).__name__}: {exc}"
try:
    import diffusers
    out["diffusers"] = diffusers.__version__
except Exception as exc:
    out["diffusers_error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(out, ensure_ascii=False))
'@
$probeFile = Join-Path $env:TEMP 'anime_art_probe.py'
Set-Content -Path $probeFile -Value $probe -Encoding UTF8
$probeOut = & $pyExe $probeFile
Write-Host "  $probeOut"
$probeJson = $probeOut | ConvertFrom-Json
if (-not $probeJson.cuda_available) {
    Write-Warn2 "CUDA 不可用：生成会退回 CPU（极慢）。检查 NVIDIA 驱动，或确认装的是 cu128 版本 torch。"
} else {
    Write-Ok "CUDA 就绪：$($probeJson.gpu) / $($probeJson.vram_gb) GB"
}

if (Test-Path $modelPath) {
    & $pyExe -c "from safetensors import safe_open; f=safe_open(r'$modelPath','pt'); ks=list(f.keys()); print('tensors:', len(ks)); print('first:', ks[0])"
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "权重读取失败，文件可能不完整" }
}

Write-Host "`n运行时路径：" -ForegroundColor Cyan
Write-Host "  python : $pyExe"
Write-Host "  model  : $modelPath"
Write-Host "`n试跑：" -ForegroundColor Cyan
Write-Host "  & '$pyExe' '<skill>\scripts\anime_gen.py' --preset whale-chan --scene '樱花树下微笑' --grid"
