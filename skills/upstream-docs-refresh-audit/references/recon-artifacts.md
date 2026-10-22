# 三件前置产物（Recon A / Recon B / 词存在性普查）

用途：在 fan-out 派子代理**之前**，主 Agent 先落盘三份种子文件，作为 12 个子代理 prompt 的共用输入——否则子代理会凭猜名检索、各自重复 grep。
实测来源：2026-09-28 第三轮，输入 `D:\workspace\260928_vllm资料确认\转测文档_2026Q3\*.txt`（12 份 / 165KB / 最大 50891B / 1231 行），主线 vllm-ascend `233adfea55c565260345311845811237d726c2f2`。

| 产物 | 落盘范本 | 行数 | 产出 |
|---|---|---|---|
| Recon A 关键词抽取 | `keywords.md` | 162 | 236 个去重关键词 = 类别关键词 90 + 环境变量 50 + 启动参数 96 |
| Recon B 代号映射表 | `codename_map.md` | 171 | 24 词中 23 有映射、1 `unclear`（`M级长序列`） |
| 词存在性普查 | `existence_audit.md` | 496 | 236 词：存在 193 / 不存在 43（三表各 50/96/90 行） |

## Recon A：转测文档关键词抽取

```powershell
Get-ChildItem "D:\workspace\260928_vllm资料确认\转测文档_2026Q3\*.txt" |
  Select-Object Name, Length, @{n='Lines';e={(Get-Content $_ -Encoding UTF8).Count}}
```

- 抽取原则：**逐字保真**（照抄 `export`/`=`/`--flag`、不改写连字符/下划线、不改大小写）；未写的字段写 `缺`。
- **硬规则 ①：wiki 导出的 `.txt` 必然丢代码块。** 本轮 REQ-05（moonlight）/ REQ-07 的「环境变量」「业务启动」小节标题下**正文全空**，一条 env/flag 都抽不到。缺失一律写「缺」+ 标 `待业务确认`，**不得臆断补全**。
- **硬规则 ②：`(?:^|\bexport\s+)(\w+)\s*=` 抓不到 `env["VLLM_ALLOW_RUNTIME_LORA_UPDATING"] = "1"` 这类写法**，必须补扫 `os.getenv|environ|env\[`。
- 每个环境变量/启动参数都要进存在性普查（见下），不能只抽不用。

## Recon B：内部代号 → 仓库符号 / 文档用词映射表

- 范本行：`A5 | is_950()/A5_SUPPORT_MEGA_MOOSE_QUANT_TYPES | 950DT Products（用户指南）/ 保留 A5（开发者指南）`
  证据：`vllm_ascend/attention/dsa_v1.py:1644`、`docs/source/getting_started/installation.md:173`、`supported_models.md:18`。
- 工作区 0 命中时**改搜提交信息**（不要直接判 unclear）：

  ```powershell
  git -C <repo> log --all -i --grep="<内部代号>" --oneline
  git -C <repo> log -1 --format="%H%n%ad%n%s%n%b" <sha>    # 看正文，必要时 -p 看 diff
  ```
  实测 `moonlight`：工作区 0 命中 → 唯一提交 `d86021f7b` 正文的 modelscope 链接破解为 `moonshotai/Moonlight-16B-A3B-Instruct`；但 **docs 内 0 落点**（无页 / 无行 / 无 nav / 无 po）⇒ 该条判 `yes`，方案给「新建页 + 矩阵行 + nav + `nav_titles.py` 登记」三步。
- `git log -S/-G` **无匹配时 exit code 仍是 0** → 必须数输出行数判有无命中。
- 每个代号都要同时记「代码侧符号」与「文档侧用词」，两者常不同（`A5` → `950DT Products`；`dspark` → `DSpark`）。

## 词存在性普查

判据命令（**必须搜全仓**，只搜 `vllm_ascend` 会误判）：

```powershell
git -C <repo> grep -F -q -- <词>      # exit 0 = 存在 / exit 1 = 不存在
```

- 反例：`max-model-len` 在 `vllm_ascend` exit=1，但全仓代码属性 `max_model_len` 有 51 文件命中。
- 本轮 236 词：**存在 193 / 不存在 43**。不存在的 43 个分组：env 8（`CUDA_VISIBLE_DEVICES, FLASHINFER_DISABLE_VERSION_CHECK, IP_SOCKET_IFNAME, MASTER_IP_ADDRESS, VLLM_ASCEND_DSV4_KV_BF16, VLLM_ENABLE_V1_MULTIPROCESSING, VLLM_SSM_CONV_STATE_LAYOUT, VLLM_USE_SIMPLE_KV_OFFLOAD`）+ flag 6（`--kv-offloading-size, --random-mm-bucket-config, --master_addr, --master_port, --node_rank, --nproc_per_node`）+ 类别关键词 29。
- 关键裁决：`--master_addr/--master_port/--node_rank` 主线**只有连字符写法**（`--master-addr` 8 / `--master-port` 8 / `--node-rank` 10 文件），`--nproc_per_node` **两种写法都没有**；`CUDA_VISIBLE_DEVICES` → 主线是 `ASCEND_RT_VISIBLE_DEVICES`（165 文件）；`--additional_config` 11 文件 vs `--additional-config` 298 文件（**都存在但悬殊**，不能只判「存在」了事）。

### 误命中三件套（错误原文 → 修法）

- `git grep -i A5` 回 190 行，含 `Binary file ... matches` 24 行与 CSS `color: #ffa500;` 2 行 → 改 `git grep -I -l -E "\bA5\b"` 回 8 文件。
- `git grep -i 35B` 回 69 文件，42 个是 `235B` / `DequantSwigluQuantV35BaseTilingData` → 改 `\b35B\b` 回 27 文件。
- `git grep -F -c` 是**子串**匹配（`GLM-5.2-w4a8` 会因 `w4a8c8` 得 11）→ 精确场合用 `\b` 或 `-w`。
- `-l` 回的是**文件数不是命中次数**；`-c` 也只在单文件下才是「次数」。
