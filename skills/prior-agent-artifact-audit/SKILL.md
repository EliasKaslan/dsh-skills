---
name: prior-agent-artifact-audit
description: 前代 agent 产物目录（「上一轮交付」）的真实完成度取证——证据分四层标注【自测/落盘/文档/复核】，部署/工作区现实分开判（线上入口与本地候选逐字节比对、判装没装看运行时清单与包目录而非源码），档案行号自证矛盾即降为线索，产品化完成度按清单逐项要证据。适用于"上一轮 agent 的产物，看看做到什么程度 / 这个目录真做完了还是只写在文档里 / 文档说验收全绿能信吗 / 线上跑的到底是哪一版 / 这个报告里的行号对不对 / 上个 agent 说已完成，帮我验一遍"。不适用：拆解派活与校验子代理 → 用 `orchestrating-subagents`；论文/开源复现核查 → 用 `arxiv-paper-deep-read-and-claim-verification`；第三方漏洞扫描报告结论核实 → 用 `vuln-scan-report-verification`；改 SKILL.md frontmatter → 用 `dsh-skill-authoring`；本机 pwsh 编码与计数坑 → 用 `pwsh-on-windows`。
whenToUse: 拿到前代 agent 留下的产物目录或分析报告，要判它真做到了什么、哪一版在跑时用。模型看不到本节，只有 description 决定触发。
disable-model-invocation: true
warm-triggers: 上一轮 agent 产物做到什么程度 / 文档说全绿能信吗
warm-reason: 低频审计方法论
---

# 前代 agent 产物的可信度审计

审的不是「有没有代码」，而是**哪一版真的在跑、哪些「完成」只存在于文档里**。

## 何时调用

**加载本 skill 当：**
- 用户丢来一个目录并说「这是上一轮 agent 的产物 / 你看看做到什么程度 / 能不能交付」。
- 目录里有 README、分析档案、验收表（S1…Sn）、`RESULT: PASS` 之类自证材料，要判哪些是真的。
- 要回答「线上跑的是哪一版」「新版到底装没装」「手里这份报告还能不能当基线」。

**不要用本 skill（转交）：**
- 拆解、派发、校验子代理的通用规则 → 用 `orchestrating-subagents`。
- 对象是第三方漏洞 / 安全扫描报告，要判每条漏洞结论真假、定级是否偏高、有没有漏报 → 用 `vuln-scan-report-verification`。
- 对象是论文 / 开源仓库的声称与复现 → 用 `arxiv-paper-deep-read-and-claim-verification`。
- 要写 / 改 SKILL.md 的 frontmatter、description → 用 `dsh-skill-authoring`。
- 本机 PowerShell 的编码 / 行数 / 计数 / BOM 坑 → 用 `pwsh-on-windows`。
- 子代理报「没有 web_fetch / 工具受限」 → 用 `subagent-toolset-precheck`。

**前置**：被审目录的读权限 + 能跑本地命令；能发 HTTP 时 §2 的线上比对才做得了。全程只读，不需要写被审目录。 ／ **后继**：审计结论要沉淀 → `sedimenting-skills`。

## 0. 一条总口径：证据分四层，每句断言带层标

| 层标 | 含义 | 取证形态 |
|---|---|---|
| 【自测】 | 我自己跑命令 / 发 HTTP 得到的 | 命令 + 退出码 + 输出片段 |
| 【落盘】 | 磁盘上有原始文件（日志、状态文件、构建产物、代码原文），可再 grep | 路径与行号 |
| 【文档】 | 只出现在 md / README / 报告里，没有任何原始输出 | 只能当线索 |
| 【复核】 | 子代理断言、且我抽查到行号 | 抽查过的那几行 |

- 判别力 **自测 > 落盘 > 文档**。「文档说了」不是证据，是**声明**。
- **文档层不许进「已完成」结论**：每条完成声明必须配一个【自测】或【落盘】。
- 最省事的一条量化判据：**全仓数一遍成功标记的出现次数**（如 `RESULT: PASS`），与验收表声称的条数对比——差值就是「只在文档里完成的量」。

```powershell
# 别用 Select-String 数次数（本机 Matches.Count 恒 0，见 pwsh-on-windows）
python -c "import io,sys;t=io.open(sys.argv[1],'rb').read().decode('utf-8');print('hits=%d' % (t.count('RESULT: PASS')))" <文件>
```

## 1. 先分层再谈完成度：这往往不是一个项目，是 N 代产物叠加

盘点成四列：**目录 → 身份 → 体量（文件数 + 字节）→ 状态（在用 / 停用 / 备份）**。先排除 `node_modules` / `.git`，否则体量被依赖淹没、真结构看不见。

```powershell
# 体量与文件数：交给 Python（PowerShell 管道统计会给假值）
python -c "import os,sys
root=sys.argv[1]
for d in sorted(os.listdir(root)):
    p=os.path.join(root,d)
    if not os.path.isdir(p) or d in ('node_modules','.git'): continue
    n=b=0
    for dp,dn,fn in os.walk(p):
        dn[:]=[x for x in dn if x not in ('node_modules','.git')]
        for f in fn: n+=1; b+=os.path.getsize(os.path.join(dp,f))
    print(str(d)+'\t'+str(n)+'\t'+str(b))" <被审目录>
```

**「多代叠加」的判据**（命中 ≥2 条就别再当单项目看，先分层）：
- 同名文件在相邻两代目录里**字节数不同** → 是两个快照，不是副本（用 §2 的 `cmpbytes.py` 逐字节比）。
- 同一层里 `docs/`（构建产物）与 `web/`（源码）并存，或 `dist/` 与 `src/` 都自称最新。
- 存在 `backup-*` / `*_bak` / 日期后缀目录。
- 源码 `package.json` 的版本与 `node_modules/<pkg>/package.json` 的版本对不上（**未验证：本次未取这条证据**）。

**结论必须先写「这是 N 层产物、每层是什么、哪一层在跑」，再谈完成度。** 不分层就谈完成度，必然把新版源码当旧版线上。

## 2. 部署现实 vs 工作区现实（各 1 条命令，胜过读 10 份文档）

文档描述的是「应该」，线上与运行时才是「实际」。两边各取一次，判定才有力量。

**(a) 线上跑的是哪一代**——抓下来落盘，与本地候选**逐字节**比：

```powershell
$w = Invoke-WebRequest -Uri <线上URL> -UseBasicParsing
[IO.File]::WriteAllBytes("<本地落盘>.bin", $w.RawContentStream.ToArray())   # 别直接读字符串，响应头缺 charset 会乱码
python cmpbytes.py "<线上落盘>.bin" "<本地候选文件>"
```

```python
# cmpbytes.py：长度相同也要比 same；first_diff 用来定位是哪一代的差异
import hashlib,sys
a=open(sys.argv[1],'rb').read(); b=open(sys.argv[2],'rb').read()
i=next((k for k in range(min(len(a),len(b))) if a[k]!=b[k]), min(len(a),len(b)))
print('lenA=%d lenB=%d same=%s first_diff=%d' % (len(a),len(b),hashlib.sha256(a).digest()==hashlib.sha256(b).digest(),i))
```

判读：`same=True` → 线上就是这份；`lenA != lenB` 或 `first_diff` 靠前 → 不是同一代，别用「源码里已经改了」安慰自己。

**(b) 新版到底装没装**——看运行时侧，不看源码侧；两件同时成立才算装：

```powershell
Select-String -Path <运行时清单，如 profile\cordis.patch.yml 或 package.json> -Pattern '<包名 / 插件名>'   # 有没有被引用
Test-Path <运行时包目录，如 ~\.dsh\<pkg>>                                                                 # 包里实际有没有
```

- 目标目录不存在 → **没装**，源码里躺着一份完整实现也不算。
- 清单里没有该包 → 没被引用，装上也跑不到。
- 只查一边就下结论，是这类审计最常见的错判。

## 3. 每份档案开工前先做三查（各 1 条命令，代价极小）

1. **行号自证矛盾**：报告声称某文件 N 行，实测 M 行；且报告内部引用同一文件时出现了 >N 的行号 → 该档案**自己就矛盾**，整份降级为**线索**。

   ```powershell
   python -c "import io,sys;t=io.open(sys.argv[1],'rb').read().decode('utf-8');print('lines=%d' % (t.count(chr(10))))" <文件>
   ```

   → 数行数只用 Python 二进制读；PowerShell 管道 / `Measure-Object -Line` / 不带 `-Encoding utf8` 都会给假值且不报错（见 `pwsh-on-windows`）。
2. **引用文件存在性**：报告里出现的每个路径逐个 `Test-Path`；声明 N 个、实际存在 M 个 → 不能用它的结论当基线。
3. **验收表的原始输出留存**：验收表里每条「通过 / PASS / 已完成」，去找对应原始日志或命令输出；找不到的只算【文档】层。**验收表本身不是验收。**

处理纪律：**自证矛盾的档案不许当基线，只能当线索；以最新一次可复现的实测报告为基线**，并逐条写明「哪条被降级、为什么」。

## 4. 产品化完成度清单（判能不能交付，不是有没有代码）

逐项给 **是/否 + 证据层标 + 缺口**：

| 项 | 判据（可复现） | 失败长什么样 |
|---|---|---|
| 版本控制 | `git -C <目录> rev-parse --is-inside-work-tree`；再 `git -C <目录> log -1 --oneline` | `false` / 无提交 → 无历史、无回滚 |
| CI 真跑过 | 看**最后一次 run 的结果**，不是看配置文件在不在 | 有 CI 目录却零 run，或 run 全红 |
| 测试入口指向真实文件 | 把清单里的 test 脚本路径逐个 `Test-Path` | `test/xxx` 是**空目录**却写进了 scripts |
| 构建产物与源码同步 | 跑 `<build> --check` 这类检查，**看退出码**，不看输出里有没有 error 字样 | 退出码非 0，或 check 根本没实现 |
| 迁移文档 | 数据目录 / 接口 / 配置键**改过名**时，是否有迁移脚本或兼容读 | 改名不迁移 → 存量用户直接坏 |
| 回滚资产 | 旧版本快照 / 备份目录 / 开关是否真的在 | 只有一句「可回滚」 |

判据要点：**「配置存在」≠「跑过」**；**「脚本里有 test 名字」≠「有测试」**；**「README 声明了文件」≠「文件在」**——三者各有一条命令可验，别靠读。

## 5. 子代理证据回写

- 子代理给的每个「文件:行号」，自己 `read` 抽查 **≥3 处**（行号失准是常态，比例别省）。
- **行号错 ≠ 结论错**：先只记「行号失准」，再看它定位到的内容是否支撑结论。
- 抽过的升【复核】；**没抽过的保持原层标，不顺手升格**。
- 同一性声明（「逐字节相同」「md5 三处一致」）与对抗验证的做法见 `orchestrating-subagents` §4——规则只写在那里，本节不复述。

## 6. 坑与修法

- **只读 md 就下完成度结论** → 文档是声明不是证据。修法：每句「已完成」配一个【自测】或【落盘】。
- **用 PowerShell 数行数 / 计数 / 体量** → 静默给假值（本机实测行数会少算、`Matches.Count` 恒 0）。修法：一律 Python 二进制读并自己解码，见 `pwsh-on-windows`。
- **「目录里有这个文件」当「装上了」** → 要同时满足清单引用 + 包目录存在，见 §2(b)。
- **空测试目录 + npm scripts** → 门面。修法：脚本里每个路径逐个 `Test-Path`。
- **照抄报告里的行号** → 版本一变就失效，且失效后引用看起来仍然「很确定」。修法：按文件名 + 符号 / 小节标题定位；非要写行号就先量一次。
- **把「上一轮报告说已修复」当这一轮的基线** → 修法：只认这一轮能复现的实测，旧报告只作线索。

## 7. 验收标准

1. 报告的每条结论都带层标，**没有无层标的完成声明**。
2. 【自测】层各有一条「线上是哪一版」与「装没装」的结论（§2 的 a/b 都做了）。
3. 每份被引用的档案都有 §3 三查的结论，被降级的写明理由。
4. §4 六项逐项有 是/否 + 层标 + 缺口。
5. 开头有「这是 N 层产物、哪一层在跑」的分层结论，且每层体量数字可复算。
