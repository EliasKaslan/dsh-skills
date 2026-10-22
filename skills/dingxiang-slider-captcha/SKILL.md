---
name: dingxiang-slider-captcha
description: 顶象（dx）拼图缺口滑块验证码在 Android 模拟器上的实测结构与破解结论——含 DOM/几何参数、块与手指位移 1:1、块是半透明混合渲染（NCC 定位失效根因）；结论：成功率极低（实测 0/6）。适用于"过一下顶象滑块验证码 / 提示请拖动滑块至正确缺口 / 用 adb 拖验证码 / 拿 dx_captcha_basic 的 DOM 和坐标 / LDPlayer 上模拟器里滑块拖不过"。不适用：不是 PR / 不是读 AIDD 报告 → 用 `aidd-report-reader`。
whenToUse: 要用 adb / LDPlayer 在 Android 模拟器上自动化通过顶象滑块验证码，或快速拿到它的 DOM 结构与几何参数时使用（已知成功率极低）。模型看不到本节。
---

# 顶象拼图缺口滑块 —— 实测结论

> **结论先行：此路成功率极低。实测 6 次拖动 0 次通过，短信验证码未发出。**
> 下面所有数字都是在 Windows 11 + LDPlayer 14（Android 14 / SDK 34，1080x1920，density 440）
> 上**实际测量**出来的，不是推测。想要"能用"的方案，请直接看 §7「卡在哪一步」。

## 何时调用

**加载本 skill 当：**
- 遇到顶象（`dx_captcha_basic_*`）或同类滑块验证码，要判断能不能自动化拖动、值不值得做。
- 口令是「请拖动滑块至正确缺口」，或验证码层出现时 `has_dx: True`、`tv_get_code` 读不到。
- 要用 adb / LDPlayer 在 Android 模拟器上操作滑块，或要拿该验证码的 DOM resource-id 与几何参数。

**不要用本 skill（转交）：**
- 要提 / 修 PR → 用 `github-pr-flow`（GitHub）或 `gitcode-pr-flow`（GitCode）。
- 要登录网站读或导出扫描报告 → 用 `aidd-report-reader`。

**前置**：LDPlayer 已启动、`adb -s 127.0.0.1:5555` 可连；Python + PIL + numpy。 ／ **后继**：无（结论是此路成功率极低，见 §7）。

---

## 1. 环境与硬约束

| 项 | 值 |
|---|---|
| 宿主 | Windows 11，**只有 PowerShell 5.1（无 pwsh）** |
| 模拟器 | LDPlayer 14，Android 14 / SDK 34，1080x1920，density 440 |
| adb | LDPlayer 自带 `platform-tools\adb.exe`，serial `127.0.0.1:5555` |
| Python | 3.12.10；PIL 12.3.0；numpy 2.5.3（**无 scipy**） |
| 目标 App | `com.longfor.supera`（龙湖），`LoginActivity` |

**必须遵守**（违反会毁掉环境或被风控）：

1. **绝不 root**：不 `ldconsole modify --root 1`、不 `adb root`、不 `adb remount`。
   顶象 DXRisk 会检查 `/data/local/su`、`persist.sys.root_access` 等。
2. **不卸载 / 不清数据 / 不换手机号**。
3. **截图必须字节安全**：用
   `subprocess.run([ADB,"-s",S,"exec-out","screencap","-p"], capture_output=True).stdout` → `write_bytes`。
   **PowerShell 的 `>` 会损坏 PNG**（不要 `adb exec-out screencap -p > x.png`）。
4. **验证码层弹出时不要反复试**：每次失败都会换新图，且频繁失败有风控升级风险（换更难的验证 / 限制短信下发）。
   建议硬性上限 **≤3 次**。

### adb 输入手段实测

- `input motionevent <DOWN|UP|MOVE|CANCEL> x y` **可用**，**~30 ms/次**（10 次 = 0.303 s）。
  → 想做拟人轨迹就用它逐点 MOVE，不要用 `input swipe`（~236 ms/次，且是匀速直线，很机器）。
- `input swipe` 慢且匀速，仅适合粗测。
- 触摸设备 `/dev/input/event4`（name `input`，`ABS_MT_POSITION_X` max 1919 / `Y` max 1079，横屏原始轴）。
  本次未用到 `sendevent`。
- **无 WebView devtools**：`/proc/net/unix` 中**没有** `webview_devtools_remote` socket
  → CDP 路线关闭，**拿不到 JS 里的缺口坐标**。
- `uiautomator dump` **只返回最顶层窗口**：验证码层在时，`tv_get_code` 等登录页节点**读不到**。
  解析时从 `<?xml` 处截断取文本。
- 本机**无视觉能力**：所有感知只能靠 uiautomator XML / 数值像素分析 / OCR。

---

## 2. 验证码 DOM 结构（resource-id 稳定，可直接用）

整层在 WebView 覆盖层里：

| resource-id | bounds | 说明 |
|---|---|---|
| `dx-sdk-vcode` / `dx_captcha_basic_wrapper_1` / `main-box_1` / `box_1` | `[127,718][952,1268]` | 外容器 |
| `dx_captcha_basic_content_1` | `[127,718][952,1158]` | |
| `dx_captcha_basic_pic_1` / `dx_captcha_basic_bg_1` | `[127,718][952,1133]` | **背景图 825x415** |
| `dx_captcha_basic_sub-slider_1` | x 恒 `[151,292]`；**y 每次实例都变** | **拼图块**，宽 141 |
| `dx_captcha_basic_slider_1` | `[127,1155][292,1268]` | **把手**，中心 **(209,1211)**，165x113，**稳定** |
| `dx_captcha_basic_bar_1` | `[127,1158][952,1268]` | 轨道，宽 825 |
| `dx_captcha_basic_btn-refresh_1` | `[864,1037][938,1111]` | 刷新，中心 (901,1074) |
| `dx_captcha_basic_init-inform_1` | `[182,1037][611,1103]` | 文案「拖动下方的滑块」 |
| （无 resource-id） | `[349,1188][740,1237]` | 文案「**请拖动滑块至正确缺口**」 |
| `dx_captcha_basic_slider-img-normal_1` | `[127,1155][292,1268]` | text 是**被 uiautomator 截断的 base64 PNG data URI** |
| `dx-sdk-backup` | `[127,718][952,718]` | 零高度，备用验证码 |

块 `sub-slider` 的 y 实测出现过 abs 795 / 855 / 863 / 866 / 885 / 908 / 916，高度 140/141/143。
**不要假设 y 固定。**

### 几何（关键）

- 块矩形左边缘与背景图左边缘同源（块 rel x = 24，背景 x = 127）
  → **拖动距离 Δ 直接等于缺口相对背景左边缘的 x 偏移，无需任何补偿**。
- **Δ_max = 825 − 141 − 24 = 660**。
- 块的**不透明轮廓**比矩形小：实测 rel x 40..152（宽 **86~112**，跨实例会变）、带内 y 112..219。

---

## 3. 实测行为（这几条决定方案可行性）

1. **背景完全静止**：5 帧间隔 0.35 s 逐帧差分 = 0；`|S1−S2|` 全图均值 **0.90**，非零处只有块的两个位置。
   → **没有任何动画可利用，唯一变化的是块。**
2. **块位移与手指位移严格 1:1**：命令 250 → 实测 250；命令 250 → 实测 247；
   S1→S2 对齐量实测 150（命令 150）。
   → **不需要任何比例换算**。
3. **松手（UP 或 CANCEL）会刷新验证码**：+250 拖动后 CANCEL，`|A−D| = 53.59`（整图换新），而 `|A−C| = 5.68`。
   → **测量与求解必须在同一次 DOWN…UP 手势内完成**，不能"先量后拖"分两次手势。
4. 每次失败都换新图 → 每次尝试都是新实例，块的 y 与轮廓都变。

---

## 4. 核心发现：拼图块是**半透明混合**渲染的

这是本任务最有价值的发现。直接拿"块静止帧"里的块当模板去匹配背景，
NCC 峰值永远是"**0.71 / 次峰 0.63**"这种被淹没的状态。原因是：

```
A[rest] = α·P + (1−α)·bg[rest]      P = 真实块图，α = 不透明度
S1[m1]  = α·P + (1−α)·bg[m1]
```

拟合 `S1[m1] − S2[m2] = (1−α)·(bg[m1] − bg[m2])` 得
**1−α ≈ 0.55~0.57 → α ≈ 0.43~0.45**（R² = 0.39 / 0.57；对照：错误位移的 R² ≤ 0.25）。

**修正办法**（块移走后 `S1[rest]` 就是纯背景）：

```
P = (A[rest] − (1−α)·S1[rest]) / α
```

再拿 P 去匹配背景。实测**对 α 完全不敏感**（α 取 0.35/0.40/0.44/0.50/0.60 结果全同）。

| 方法 | 峰值 | 次峰 | Δ |
|---|---|---|---|
| 直接用 A 里的块 | 0.743 | 0.442 | 501 |
| **半透明还原后的 P** | **0.732** | **0.197** | **501** |

修正后**次峰从 0.44 掉到 0.20，峰值真正孤立**，且两个独立方法给出同一个 Δ=501。

---

## 5. 试过且**无效**的方法（别重复踩）

| 方法 | 实测结果 |
|---|---|
| `\|A−C\|>t` 掩码 + 1D NCC | 某实例出现干净等腰三角形（NCC **0.8729**，Δ=353），换实例退化成不规则楔形+内容巧合空洞 → 不可用 |
| 自一致掩码 `\|S1(x)−S2(x+DM)\|<ε` | 掩码 26~32%，峰 0.42~0.71 且次峰很近 → 失败 |
| 块矩形 2D 全图 NCC | 最大 0.72（71x71 模板），无孤立峰 → **块不是背景图的直接裁切** |
| 多尺度(0.5~1.5) 彩色+掩码 NCC | 最大 **z=3.84**，竞争者同样高 → **无统计显著匹配** |
| "缺口 = 背景整体压暗" 模型 | **R² = −0.006 → 证伪** |
| 形状匹配（暗度 / 局部对比度 / 饱和度 / 轮廓边缘线） | 全部 **z ≤ 2.4 → 噪声** |
| 拟人化轨迹（ease-in-out + 抖动 + 减速 ~1.1 s） | 该实例块轮廓提取退化（宽只有 86）→ NCC 全平（0.187/0.187），定位本身失败 |

### 一个曾经害死全流程的 bug

```python
delta = (M1 + DM) + (bx - ox0)          # 错！量纲不一致
```
`bx` 是背景图坐标，`ox0` 是块矩形内的偏移。算出来必然 > 684，
被 `min(delta, 825-141)` 夹住 → **每次都拖到最右端，永远不可能命中**。
（症状：`results.jsonl` 里 `delta` 恒为 684 而 `gap_x` 在变。）

**正确公式：`delta = best_x − rest0`**
（`rest0` = 块不透明轮廓左边缘；因为块位移 = 手指位移，所以轮廓左边缘 = `rest0 + 手指位移`。）

---

## 6. 成功/失败判据（实测）

- **成功**：`dx_captcha_basic_*` 整层消失 **且** `tv_get_code` 从「获取验证码」变成倒计时（如 `59s` / `重新获取(59)`），
  或有 toast「验证码已发送」。
- **失败**：`inform` 仍是「拖动下方的滑块」、无 id 节点仍是「请拖动滑块至正确缺口」、`has_dx: True`。
  实测**从未出现过**「验证失败」这类文案。
- ⚠️ **验证码层在时 `tv_get_code` 读不到**（uiautomator 只给顶层窗口），
  所以不能只靠 `tv_get_code` 判断；要同时看 `has_dx`。

---

## 7. 卡在哪一步 / 下次从哪接着做

**卡点：缺口定位在多数实例上不可靠。**
6 次拖动里只有 1 次得到真正孤立的 NCC 峰（0.732 / 次峰 0.197）。

根因链：
**块半透明混合 → 直接取模板被背景稀释 → 掩码（靠 `|A−S1|` 提块轮廓）跨实例不稳定
（轮廓宽在 86~112 之间跳、掩码占比 26~32%）→ 掩码一歪 NCC 峰就塌。**

而且**即使定位正确也没通过**：v3 第 2 次 Δ=501 被两个独立方法互相印证，拖到位仍然失败。
此时剩下的嫌疑是：

- **手势被判成机器**——v3 在一次手势中间插了两次 450 ms 完全静止来截图，非常机器化；
- 或**所需精度比该方法跨实例的稳定性更严**。

**下次的优先级：**

1. **先把块轮廓掩码做稳**（整条链最弱一环）。建议：
   - 用 **3 帧以上**（S1/S2/S3）对半透明模型做**联合最小二乘**，同时解出 α 与 P，比单帧硬编码 α 稳；
   - 或对 `|A−S1|` 掩码改用**连通域 + 形状先验**（块轮廓应是单一近凸区域），
     而不是当前的行填充/列填充形态学。
2. **单独设计实验判断"轨迹是否被判机器"**：在同一个实例上按最自然的轨迹（不截图、不停顿）盲拖一次，
   看是否出现「验证失败」文案。注意每次拖动都会换新图，实验要单独设计。
3. 想直接拿 SDK 内部缺口坐标，唯一方向是让 WebView 开 devtools——**需要改 App 或 root，本任务明确禁止**。

---

## 8. 可复用的代码骨架

```python
import subprocess, numpy as np
from PIL import Image
ADB = r"...\platform-tools\adb.exe"; S = "127.0.0.1:5555"
BGX, BGY, BW, BH = 127, 718, 825, 415

def shot(dest):                      # 字节安全截图
    b = subprocess.run([ADB,"-s",S,"exec-out","screencap","-p"],
                       capture_output=True).stdout
    assert b[:4] == b"\x89PNG"
    open(dest,"wb").write(b)

def me(kind,x,y):                    # ~30ms/次，做拟人轨迹用
    subprocess.run([ADB,"-s",S,"shell","input","motionevent",
                    kind,str(int(x)),str(int(y))], capture_output=True)

def bg(p):                           # 裁出 825x415 背景图
    return np.asarray(Image.open(p).convert("RGB")
                      .crop((BGX,BGY,BGX+BW,BGY+BH))).astype(np.float32)

# 关键流程（必须在一次 DOWN…UP 内）：
#   A  = 截图(块静止)
#   me("DOWN", 209, 1211)
#   human_drag 到 +250 -> 短暂停顿 -> S1 = 截图
#   M  = |A-S1| > 18 的连通域，取"静止位置"那个 -> 得到块轮廓 rest0 / w
#   P  = (A[rest] - (1-0.44)*S1[rest]) / 0.44        # 半透明还原
#   在 S1 上做掩码 NCC（排除块已移到的位置）-> best_x
#   delta = best_x - rest0        # 不是 (M1+DM)+(bx-ox0)！
#   human_drag 到 209+delta -> 微停 -> me("UP", 209+delta, 1211)
```

判据：`has_dx` 变 False 且 `tv_get_code` 出现倒计时才算成功。
**到倒计时就停手——不要填验证码、不要点登录。**
