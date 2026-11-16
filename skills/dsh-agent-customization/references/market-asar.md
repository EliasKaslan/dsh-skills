# 插件市场与 ASAR

先读取实际市场包的 schema、解析器和所用版本。历史市场索引 format=1，title 为含英文的本地化对象，language id 小写，时间用整数 Unix 秒；npm source 用精确 SemVer，git source 用完整 commit SHA。engines 可选，DSH engine 支持范围，预发行是否匹配由当版 includePrerelease 设置决定；不要把“只能写最低版本”当规则。索引自称已审计不是安全证据。

检查下载/安装入口、依赖生命周期脚本、网络目标、凭据读取与发布副作用；区分观察到的行为和推断。插件描述中的角色词或某域名字符串不单独证明恶意。包版本固定后再做隔离安装，记录来源与完整性；此轮仅静态检查，未安装第三方插件。

`scripts/inspect_asar.py <app.asar> [--packages]` 有界只读列出条目/包版本和归档 SHA。对标准 Electron ASAR，前16字节四个 little-endian uint32；本机 `[4,5669972,5669968,5669961]`。JSON 字节数来自第四项（offset12），数据区起点是 `8+第二项`。旧笔记误用第三项（offset8）会把填充读进 JSON。读取内部 packed file 前检查 offset、size、总文件边界；拒绝 link/unpacked，不执行包代码。工具不会解包至磁盘，也不能替代完整 ASAR 完整性/签名验证。

格式依据：[Electron ASAR 实现](https://github.com/electron/asar)。读取失败应先核实格式/安装位置，不用“全文件搜索第一个大括号”猜 header。
