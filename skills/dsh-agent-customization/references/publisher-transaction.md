# skills自动发布与批量更新的事务边界

2026-11-23只读核实：`profiles/desktop/node_modules/dsh-plugin-skill-publish`是指向`D:/workspace/agent/dsh-plugin-skill-publish`的junction，package 1.0.0（工具`skill_publish` / `skill_publish_status`）；安装包已是0.2.2-rc.5，下文用到的`pluginManager/listPlugins`、`pluginManager/setPluginEnabled`、`pluginInventory/list`、`pluginManager/inspect`在该版asar里仍存在。结论来自index.js、lib/publish-core.js和当前管理实现；以下不是已经暂停或已经发布的声明。

**先看 loader 行**：本profile的`cordis.patch.yml`末尾是`- id: skill-publish` + `disabled: true`，本会话工具清单里也确实没有`skill_publish`——此刻自动与手动发布都没装载。这是配置快照，动手前先读该行，别沿用“会自动发布”的假设。

## 触发和锁的真实语义

- session/event中turn/end调用armAutoPublish，默认120000ms、下限5000ms；已有armed时直接return，所以是首个事件计时，后续事件不会把定时器向后重置。另默认15分钟（下限1分钟）轮询；publishOnStartup默认false。
- 自动路径比较相对路径+size+mtime指纹，不是内容SHA；内容相同最终git diff可NO_CHANGE。fingerprint不是编辑事务，不保证读取同一个完整版本。
- 只有apply闭包内inFlight防同实例重入并返回BUSY；core无文件锁，也没有暂停文件。自造.lock、quiet文件、改目录名或一次性快速复制均不能保证不被读到中间态。多个宿主/实例不共享该锁。
- 插件config的enabled/autoPublish只挡自动路径，手动skill_publish仍能调用；**但loader行的`disabled: true`是整个row卸载**，连工具一起消失（2026-11-23本会话即如此），两层不要混为一谈。dispose清poll和armed，但不取消/等待已经开始的publish。skill_publish_status会实时ls-remote，不是纯本地无网络检查，也不公开inFlight。
- push=false仍会写工作副本和提交；只有经源码复核的dryRun才是计划路径，且会读取token文件/查看工作仓，不能当零敏感访问的探针。不要用手动publish制造BUSY当编辑锁。

## 最窄现成暂停途径（执行前确认当前实现）

rc.5的pluginManager/listPlugins返回entryId及可管理性；pluginInventory/list给enabled/fiberPhase。pluginManager/setPluginEnabled(id,enabled)写desired enablement并reload，参数id取listPlugins实际返回值，不能猜include:id。其inspect(spec,options,signal)查看候选安装包，并非实例config检查。当前manager未暴露通用config更新Remote。

因此优先通过当前已认证UI的插件管理开关，或相同已验证Remote，临时停用唯一publisher row，保存原enabled并确保无第二个publisher实例。若选择改autoPublish配置，需保留并恢复完整原config，先核实当前override是否整对象替换；禁止仅写一个字段意外重置其他配置。两种途径均不能取消旧inFlight，只有观察其确实终结后才开始写源；若无法证明静止，应报告该限制并取得可实施的暂停/隔离方案，不能宣称已有事务锁。

HTTP Remote是POST /api/pluginManager/setPluginEnabled，Content-Type application/json，envelope为client-request/rpcId/method/payload.args，其中method与路径一致，args为{id:<entryId>,enabled:false}。认证使用同authority浏览器cookie；GET /?token=<launch token>交换cookie后跳转./。不要输出token或把它混进命令日志，不以Bearer猜测替代当前认证实现。

在可验证的暂停窗口中，预先验证stage和备份、检查源未并发改变、一次应用完整集合、校验全部hash/路由/schema；恢复原启用状态前先决定最终版本是否允许自动外发。恢复自动发布可能立即或在后续tick外发，不能悄悄将“本地整理”扩成公开发布。当前任务是否已包含相应授权由用户明确指令决定；没有则继续保持可回退状态并说明具体边界。
