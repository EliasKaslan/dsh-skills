# CANN 与动态库

## 取证与安装

先核对 driver/firmware 配套矩阵、架构、卡型、安装器 `--help` 和现有组件。Toolkit、对应芯片 ops、nnal/ATB 的安装与需要性依版本/任务确定；旧“合一包”可能含 driver，不因路径隔离就保证不触及系统。安装前保留现有安装信息与回退路径，不删 `/etc/Ascend/*`，不递归 chmod 777。

安装器放独立 pkgs 目录，按精确 `.run` 文件名执行；重跑 `*toolkit*` 会同时命中安装目录。先安装并 source 同版本 toolkit，再按本版流程装依赖它的组件。脚本需要严格模式时，若 vendor source 实际触发 nounset 错误，可仅在 source 边界临时关闭并恢复；不用历史错误强制所有脚本关闭检查。

用 `readlink -f`、`test -f` 定位真实 `set_env.sh`；source 在当前 shell 执行，不能 `source X | head`（管道子 shell 不保留变量）。记录 `ASCEND_HOME_PATH`、`ASCEND_OPP_PATH`、`ATB_HOME_PATH` 的真实目录。多个版本共存时在干净 shell 中只激活目标组合，避免 PATH/LD_LIBRARY_PATH 混合。

搬移安装树可能因 version_dirpath 等绝对路径失效，应读当前脚本和安装器再选重装/修复。不要按“第 63 行”盲改。`atc --help` 与组件 version.info 可提供证据，不能假定各版都支持 `--version`。`libacl_dvpp.so` 缺失可源自 ops 组件或库搜索路径，先定位文件与 `ldd`，不直接判安装成功/失败。

## 下载的证据边界

2026-11-16 本轮同命名 toolkit x86_64 URL 的 HEAD：9.1.0/9.2.0/9.2.1 返回 200，9.3.0 返回 403。它只证明这些 URL 当时的响应；403 无法独自区分权限、对象隐藏、命名错误、网络策略，不代表版本不存在。用已知对象作网络对照仍不能证明 403 的根因。

下载使用厂商可信来源与可获得的校验和，不继承 `curl -k`。ETag 在分片上传/加密等情形下不是文件 MD5，不能直接当官方校验和。包名与架构、芯片 ops、版本分别确认。

## ABI 排查

`GLIBCXX_* not found` 或 CANN tiling “参数错误”应沿实际失败 `.so` 查依赖、符号和加载来源。编译器版本与运行时 libstdc++ 是两个维度。若证实仅缺 libstdc++，可将兼容库放本任务 compat_lib，仅对该进程前置，并验证 `ldd`/实际加载与原失败用例；不要以整个 conda lib 目录污染所有系统工具，也不写成“这样一定让 git 崩”。

保留 CANN 已有 PYTHONPATH，增加目录用 `export PYTHONPATH=/needed/path:${PYTHONPATH:-}`；覆盖它可能使 acl 不可见。宿主驱动可见不证明容器内 CANN/用户态库兼容。

一手入口：[CANN 安装选择器](https://www.hiascend.com/developer/download/community/result?module=cann)、[Ascend PyTorch](https://gitcode.com/Ascend/pytorch)。具体配套以目标发布版本文件为准。
