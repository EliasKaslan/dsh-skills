# skill 根卫生：被正文引用的凭据文件就地保留（原 §2.15 原样拆出）

> 从 `dsh-agent-customization/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

### 2.15 skill 根卫生：清理 `~/.dsh/skills` 时，**被正文引用的凭据文件就地保留**（实测反例）

> 编号说明：接 2.14 顺延为 **2.15**。

`~/.dsh/skills` 是**多会话共享**目录（一次清理立刻对所有会话生效），而 skill 正文是用**相对路径**点名自己目录里的文件的 ⇒ **移走被引用者 = 制造假指针**：会话照着正文去找一个不存在的文件，**而且没有任何报错**。更重的一层：它可能**推翻用户的既有决策**。

**实测反例（本轮）**：`ascend-env\credentials.txt`（2,011 B）全库被 **6 处**引用——

| 引用方 | 行 | 性质 |
|---|---|---|
| `ascend-env` | `:38` / `:244` | 凭据本体所在 skill（"新值只写在 `credentials.txt`"） |
| `vllm-ascend-source-install` | `:11` | 密码 fallback 指过去 |
| `github-pr-flow` | `:32` / `:154` | **2026-10-08 用户决策的单一出处**（凭据允许放 skill 目录内、就地保留） |
| `dsh-skill-self-audit` | `:132` | **点名要求校验该文件真实存在，找不到按 FAIL 报** |

⇒ 移走一个 2 KB 文件 = **1 个 FAIL + 3 条假指针 + 推翻一条用户决策**。

**对照**：两枚 15,395 B 的编辑器残留（`.bak`）全库 **0 命中**引用 ⇒ 才属可移；本轮取证时它们**已被并行清理者移走**（该目录只剩 `SKILL.md` 21,580 B）——这也正说明**清单与行号都会漂，判据只能是"动手前 grep 一次"**。

**纪律（清理前逐条执行）**

1. **只移明确的编辑器残留**：`.bak` / `.orig` / `.tmp` 这类；即便如此也要**先看引用命中**再移，不要凭扩展名好看就动。
2. **任何 `*credentials*` / `*.key` / `*.pem` / `*.token` 一律先 grep 全库引用**；**被任何 skill 正文引用的就地保留**——被引用者移走等于制造假指针，还可能推翻用户的既有决策。
3. **移动一律是"移入 `artifacts\backups\skill-hygiene-<日期>\`、保留原相对路径、记 sha256"**，**不删除**（"移走"必须可逆）。

**取证（只读，可抄）**

```powershell
# 1) 全库谁被点名（列引用方 + 行号；数次数别用 Select-String -AllMatches，它恒为 0）
Get-ChildItem 'C:\Users\admin\.dsh\skills' -Recurse -File -Filter *.md |
  Select-String -Pattern 'credentials\.txt' -Encoding utf8 |
  ForEach-Object { "{0}:{1}" -f $_.Path, $_.LineNumber }
# 2) 残留候选（显式计数，不要从目录外观下结论）
Get-ChildItem 'C:\Users\admin\.dsh\skills' -Recurse -File |
  Where-Object { $_.Name -match 'credentials|\.bak$|\.orig$|\.tmp$' } |
  ForEach-Object { "{0}  {1} B  sha={2}" -f $_.FullName, $_.Length, (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower().Substring(0,8) }
```

> 凭据的**登记与存在性校验规则**单一归属在 `dsh-skill-self-audit`，凭据**存放策略**的单一出处是 `github-pr-flow` §0；本节只写"清理时怎么不制造假指针"。

