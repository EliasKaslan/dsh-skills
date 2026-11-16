# UT / ATK与CI取证

从目标分支依赖、发布配方与实际镜像核对组合。docker/与ci/可能不同，--no-deps的CI不会按requirements自动换栈。包产品版本、pip版本、CANN和镜像列开，不推算版本对应关系。旧镜像可复用时仍核对源码/二进制/工具来源。

运行前确认实际目标Python、source入口、设备映射、当前无人占用物理卡和磁盘余量。环境激活失败立即停止，不让后续pip落入共享base；不用全局卸包或覆盖配置“恢复”。多worker会重复持有NPU上下文/缓存，按任务资源逐文件分片、独立cache，不能默认8片或压同一卡。

收集阶段也可能import并初始化设备；pytest --collect-only不一概无显存副作用。保存collected/executed/passed/failed/error/skipped/cancelled与每个case原因，平台未实现可单列，但仍影响用户要求的整体覆盖，不能从失败分母中消失而宣称全绿。

ATK执行状态、精度结果、性能结果分别读取并校验总case覆盖。参考后端应符合目标数学契约并足够独立，不把CPU永远正确或NPU参考永远错误写成规则。读当前工具help/版本和report schema，旧固定8881/9090端口及kombu降级只作失败线索。端口冲突时只停止本任务已记录PID，不宽泛pkill。

NaN/Inf、OOM、SIGKILL是症状，不自动归环境。检查资源/设备上下文与完整日志，隔离重现后比较相同输入和代码；同head重跑通过说明需定位不稳定性，不能一概证明产品无缺陷。保留原失败条件以及wrapper里的归一化、cast、layout和mask，最小复现不得丢触发步骤。

ATK精度报告可能与“execution failed=0”矛盾；读取逐case数值与nonfinite，别只看总退出码或最后一条Pass。graph与eager、不同SoC派发、真实wheel与源码模式均分别覆盖。

CI镜像迁移先验证配方/架构、目标设备准入、实际版本、构建与所需用例，再在授权范围更新workflow。trigger、label和required gate读取目标分支当前配置，旧PR号、固定4处image、固定等候时间、历史“已验证镜像”不作为现在事实。
