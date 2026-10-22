# ascend-env 维护记录（原 §7 原样拆出）

> 从 `ascend-env/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

## 7. 维护记录

- **2026-10-22（服务器清单全面复核：三台机器 + `.188` 现状重采）**：
  1. **§1 机器表改为三行并带状态列**：`a3=.188`（可用）、`a3b=.190`（**整机不可达**）、`a5=177.8.21.1`（当时判为不可达，**同日已更正：需先连 A5 VPN**）。同时**证伪旧断言「`.188` load ~20，稳定」**——2026-10-22 实测 `load average: 281.25`（256 核），2026-10-08 也是 ~277；同一份文件 §3.1 早写着 ~277，两处自相矛盾，现统一为「重载机」。
  2. **新增 §1.1「接一台没见过的机器」**：三层（ICMP / TCP / 认证）分开测、`Test-NetConnection` 对不通地址会挂几分钟（改用短超时 `TcpClient`）、别扫全端口、**「连不上」≠「不存在」**（规格只能标 `未采`）。
  3. **`.190` 结论更新**：本机与 `.188` **双向** `ping` 100% 丢包 + TCP 22 超时（各 3 次重试），不是 9-22 那种"重试即可"的假死；保留 10-08 可达记录。
  4. **`.188` 复核通过项**：免密仍有效（`hostname` → `node-zj-110-132`）、密码 `AUTH_OK`（paramiko）、`/dev/davinci*` = 17、`npu-smi` 8 NPU × 2 die 全 `Health OK`、`source env_batch_inv.sh` 后 `torch.npu.is_available()=True` / `device_count()=16`、`/usr/local/Ascend/ascend-toolkit` 是**空目录**（bashrc 第 36 行断链的真因）。
  5. 采集通道再次验证：`scp` + `md5sum` 逐字相符后执行，5 个只读脚本全部一次通过（含中文注释），**没有走 base64**；其中 1 次 `scp` 报 `Connection closed`，原样重试即成功（已写进 §5）。
- **2026-10-08（第四批：§4 补 2 条判据 + §5 补 3 条硬规则 + 1 处再修正，全部实测）**：
  1. **新增 §4「完成标记不是证据」**：lane 脚本的 `LANE_Px_DONE` / `S4_DONE` **失败也照打**（实测两起：P4 clone 失败仍打 DONE、S3 被打断后仍打标记）；判完成只看产物（文件存在/大小/条数、`rc=` 行、真跑过的验收命令）。并补「shell 退出码也不可靠」——该机器每次 ssh 都因 `/root/.bashrc` 那行失效 `set_env.sh` 以 exit 1 结束。
  2. **§5 第一条补全机制**：单引号内的双引号会被本机 PS 5.1 重新转义成 `\"`，远端 bash 收到**字面引号** ⇒ `grep`/`pgrep`/`awk` 模式**静默零匹配**；逐字症状 `bash: -c: line 0: syntax error near unexpected token '('`；本轮复发 **6 次**、两次据此误判"进程已死"。规则收紧为：内联 ssh 只做无引号简单命令，模式匹配一律 base64 推 `.sh`。
  3. **新增 §5「核对最终目的地的 md5」**：只核 `/tmp/x.sh` 的 md5 会让你误以为推送成功——本轮 `source $ROOT/env_sv0230.sh` **静默失败**，整条 S3 在 CANN 变量未设置下运行；写完必须 `md5sum <最终路径>`。
  4. **新增 §5「ssh 里永远不要 `2>$null`」**：丢弃 stderr 会丢掉唯一能解释"进程为何立刻退出"的 traceback（本轮正是它把 `libhccl.so` 真因藏起来）；改为落盘再 grep。
  5. **新增 §5「重启长任务前先确认旧实例死了」**：`pgrep -af <name>` 期望 `(none)`；本轮两个同名实例同写一个日志，新实例截断了旧文件 → 据此误判（脚本里那段 kill 落在输出被截断处、**实际未生效**）。
  6. **再修正上文第 3 条那处 `VLLM_VERSION` 结论**：它只对仍读取该变量的 vllm 版本成立；vllm `v0.23.0` 上该变量已不被读取，`vllm_version_is("0.23.0")` 不设任何变量本就为 `True`（版本线判定）。

- **2026-10-08（执行方式大改：并行编排 + 下发通道勘误，用户要求"大刀阔斧"）**：把 §3 从「一条条按顺序跑」改成**先并行后串行**的编排——新增 §3.1 依赖图与 P1~P4 四条并行 lane（CANN 三包并发下载 / conda 建环境 / torch 栈 whl 预下载到 wheelhouse / 两仓 clone+切 commit）、§3.2 barrier 与"为什么 S1~S3 必须串行"、§3.3 子代理边界（只下不下、写盘白名单、禁止事项）、§3.4 与子 skill 的衔接；§3.4 末补**版本不纠结**纪律（只参考 vllm-ascend 的 requirements，vllm 的不参考，冲突不管）。
  - **本次 `.188` 实测取证**（2026-10-08，全部只读或落在 `/home/vllm`）：`pip download -d <wh>` → `pip install --no-index --find-links <wh>` 离线往返**通过**（`OFFLINE_INSTALL_OK six 1.17.0`），且 wheelhouse 里没有的包在 `--no-index` 下**必然失败**（证明真断网）；三条 `curl` 后台 `&` + `wait` 并发**全部 200**；`raw.githubusercontent.com/.../vllm-main-verified.commit` 免 clone 取到 `ced6857af…`（所以两个 clone 能真并行）；`curl --parallel` / `-Z` **不支持**（本机 curl 7.64），`aria2c` / `axel` **不存在**（并行只能 `&`+`wait`）。
  - **§5 勘误（原规则被证伪）**：旧文写「PowerShell 管道给 ssh 会自己注入 UTF-8 BOM，所以 `tail -c +4` 基本是必需的」——实测本机 `$OutputEncoding` 是**无 BOM UTF-8**（`GetPreamble().Length`=0），管道**不注入 BOM**，`tail -c +4` 会吃掉脚本前 3 字符（把 `#!/bin/bash` 削成 `bin/bash`）；且**多行含中文脚本直推会静默损坏**（丢行 + `确认` → `U+E1BF U+E17B`）。§5 已改为 **base64 通道**并给"先探有无 BOM 再决定剥不剥"的判据。
  - **第二轮（独立子代理对抗性复核后修的 4 处，全部有实证）**：
    1. **P3 由 3 组改为 1+1 组**（`ascend-torch-npu` 步骤 3）：原写法把 `torch-npu==2.12.0` 单独发一组且不带 `--no-deps`，而 torch_npu 依赖 `torch==2.12.0` → pip 会从 PyPI 拉**无 `+cpu` 的 CUDA 版 torch（GB 级）**，与坑 1 的 `+cpu` 纪律相反。改为「torch 三件套 + torch_npu **合为一条命令** + `-c constraints.txt`（`torch==2.12.0+cpu`）」。**约束语义已实测**（`packaging`：`==2.12.0+cpu` 不匹配 `2.12.0`、匹配 `2.12.0+cpu`；`==2.12.0` 匹配 `2.12.0+cpu`）；**两个索引已实测**（whl/cpu 只有 `+cpu` 形态、aliyun 只有无 local label 形态）。
    2. **P2 白名单物理上不成立**（`ascend-conda-env` 步骤 4）：`conda create -p` 只改环境落点、**不改包缓存落点**，共享 `.condarc` 的 `pkgs_dirs=/mnt/share/vllm/conda_pkgs` 在系统盘上 → lane 脚本补 `export CONDA_PKGS_DIRS=$L/conda_pkgs`，并把 `CPKGS` 写进 §3.1 白名单。
    3. **§3.1 标题把未验证写成结论**：删掉"实测各条命令可用"，改为显式「证据边界」块——实测的是**原语**（并发 curl 200、离线往返只验过 `six`、raw 免 clone 可读），**端到端整链没跑过**；§3.2 的 `--no-index` 也从"一律"降为"推荐 + 缺包按在线回退"。
    4. 顺手修掉真缺陷：`vllm` 那条 lane 的重定向原先只罩住最后一条命令（`init/fetch` 日志会丢）→ 改为罩整个子 shell；`<你的目录>` 这类占位符在 bash 里是重定向符（照抄即语法错）→ 全部换成可直接粘贴的 `envbuild` 路径。
    - 另：写进 skill 的 **6 段 lane/串行脚本已逐段 `bash -n` 校验通过**（在 `.188` 上跑，不下载不建环境）。注意 `bash -n` **抓不到占位符类错误**（`<lane>.sh` 语法合法、运行必错），所以占位符要单独清。
  - **第三轮（第二轮复核的回修）**：
    5. **`constraints.txt` 改为单一写者**：§3.1 落点块统一 `echo` 创建，两个下载组（torch 栈 / triton）都改成**只读校验**（`[ -s … ] || exit 1`）。原先两组各自 `echo >` 会构成同一文件双写、且把车道 B 的 pin 硬编码进 triton 组（车道 A 会写出错版本约束）；极端时序下 pip 还可能读到被截断的空文件 → 约束静默失效。
    6. **占位符全族清理**：`<lane>.sh`/`<lane>.log`（§3.3）、`<WORK>`（`ascend-torch-npu` 坑 3）、`<x>`/`<本 skill 目录>`（`vllm-ascend-source-install` §0/§3）、`<name>`/`<user>`（`ascend-conda-env` 步骤 4）全部换成可粘贴的实例值 + 就地警告。并补 §5 的「脚本 >20KB 别内联 base64，改 scp / 分块」。
    7. **`ascend-torch-npu` 步骤 2 与步骤 4 的 `ENVP` 对齐**：步骤 2 原先建 `torch_test/envs/torch_latest`、步骤 4 却用 `envbuild/envs/vllm312`（线性照抄会装进不存在的 env）→ 统一到 `$ROOT/envs/vllm312`，并补 `CONDA_PKGS_DIRS`。
    8. 复核确认：①②③ 三项均已真修好；`conda create -p` 只剩 `~/.conda/environments.txt`（几十字节）在白名单外，已就地标注（机制推断、未实测）。
- **建立（2026-09-23）**：把原 `ascend-vllm-env` 单体 skill **删除并拆为「本总纲 + 7 个子 skill」**——`ascend-server-layout` / `ascend-cann-env` / `ascend-conda-env` / `ascend-torch-npu` / `ascend-triton-ascend` / `ascend-vllm-serve` 六个新建，`vllm-ascend-source-install` 为既有（已同步交叉引用）。旧文件内容按职责重分配，无丢失。
- 本次新增的实装验证：CANN 全新路径安装（合一包 + 独立 toolkit 包两分支）、torch / torch_npu / triton-ascend 商发版本安装。逐条证据见各子 skill 的「坑与修法」。
- **2026-10-08 凭据与免密复核**：两台 root 密码换成新值（旧密码已作废，不要再试），新值只写在 `credentials.txt`、**不写进本正文**，并已用 paramiko 实测 AUTH-OK。免密复核：`.188` 直接通过；`.190` **免密失效**（`Permission denied (publickey,password)`，机器本身可达）→ 用新密码把本机公钥追加进 `/root/.ssh/authorized_keys`（5 → 6 行）后 `ssh -n -o BatchMode=yes root@192.168.13.190` 返回 `zj-131` 恢复。同次勘误：**本机并无 `a3` / `a3b` ssh 别名**，已把 §1 的示例改成直连 IP。
- **2026-10-08（M92 lane：vllm/vllm-ascend 双 v0.23.0 tag + CANN 9.2.0-beta.2 实装，4 处勘误）**：
  1. **§5 的 base64 示例自己就是坏的**（原样照抄会静默损坏脚本）：`(Get-Content -Raw $f)` 在 PS 5.1 按 **GBK** 解码，含中文的 `.py` 推过去后**字节数都变了**（`strip_torch_pins.py` 7343 → 7819），远端 `python` 报 `SyntaxError: invalid non-printable character U+E15E`（`閲屽舰濡` 类乱码）。已改为 `[IO.File]::ReadAllBytes($f)`，并把「**`md5sum` 与本地 md5 一致才算推送成功**」写成硬判据——这一条能同时兜住 GBK 改坏 / CRLF / 截断三种坏法。
  2. `ascend-cann-env` 坑 11 的「公开源最高 = 9.1.0，9.2.0-beta.1/2 全 403」**被证伪**：真因是**桶内目录名不是版本号**（9.2.0-beta.2 在 `CANN 9.2.T3/`，按 `CANN 9.2.0-beta.2/` 探才 403）；Referer 头**非必需**。同时**确认「9.2.0 商发公网不存在」这条结论成立**（同目录下 `…_9.2.0_linux-x86_64.run` 403，对照 beta.2 = 200）。
  3. `ascend-vllm-serve` 坑 4 原写「同理别设 `VLLM_VERSION`」**是错的**：它正是 vllm 版本串非纯 `x.y.z`（脏树 / `VLLM_TARGET_DEVICE=empty` 的 `.empty`）时 `vllm_version_is()` 全线误判的逃生口；不设就崩在 `AttributeError: module 'vllm.v1.engine.utils' has no attribute 'get_physical_gpu_ids_for_local_dp_rank'`。完整机理归 `vllm-ascend-source-install` §5 / §6 坑 10。
      > **2026-10-08 再修正（本条只对「仍读取该变量」的 vllm 版本成立）**：在 vllm `v0.23.0` 上 `VLLM_VERSION` **已不被 `setup.py` 读取**——`grep -n VLLM_VERSION setup.py` 逐字只剩 `VLLM_VERSION_OVERRIDE` 两行（见 `vllm-ascend-source-install` §5.1）；且**不导任何变量时** `vllm_version_is("0.23.0")` 本来就为 `True`（它是**版本线**判定，不是等值判定）。⇒ 别再把它当"必须 export 的逃生口"；该版本的修法是 `VLLM_VERSION_OVERRIDE` 或核对配对版本。
  4. `ascend-conda-env` 补 pip 源限速判据：阿里云**只对 HTTP/1.1** 限到 185 KB/s，同 URL `curl`(HTTP/2) 14.2 MB/s、`curl --http1.1` 181 KB/s、`mirrors.huaweicloud.com`(HTTP/1.1) 7.9 MB/s → 「同 URL 三连对照」是定性方法，不是"网慢"。

