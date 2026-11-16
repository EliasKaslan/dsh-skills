# 昇腾运行时、训练集成与更新同步

环境、内存、状态和版本问题经常表现成数值差异。只读已保存工件可离线完成，不应为了查文档或比 SHA 启动设备任务。

## 实际执行环境比版本标签更重要

记录芯片/可见设备映射、driver/firmware、实际 CANN 与 OPP/vendor 路径、Python/Torch/后端、训练/推理包的实际 import 来源、源码/dirty 状态和 SO 指纹。容器 ENV 可能被宿主 bind mount 覆盖；editable 安装、PYTHONPATH、源码 overlay 和默认 device 都可能使实际路径不同。

对 BI/custom op 分别检查包可导入、SO 可加载、Torch/后端注册、真实 schema、代表性调用。安装完成不等于调用成功，白名单命中不等于本模型数学正确；名单必须匹配实际芯片、版本、shape/dtype，并以目标路径实测为依据。

对 torch_npu 分支，在每个承担 NPU 工作的进程、实际工作前显式设置：

~~~python
import torch_npu
torch_npu.npu.set_deterministic_level(3)
~~~

再使用当前版本确实提供的查询方式记录等级及 Torch deterministic 状态。不要猜 getter 名、仅主进程设置、只写日志常量，或把某一份 worker 配置推广到所有 rank。启动新 worker、reload/重建后检查是否仍成立。

其他框架记录自身真实支持的确定性机制和局限；不能因为应用里另有 torch_npu 就声称它控制了所有后端。缺少用户要求的能力时报告不兼容，不静默切后端或降级标准。

## Profiling、异步错误与受限重试

按实际调用栈定位关键路径；区分模型计算、scorer、调试 dump 与统计辅助支路。必要时用 msprof、msprobe 或框架 profiler 取同一执行范围的 shape/dtype、workspace、调用数量和调度证据；工具名称不构成必选依赖。

先保存首个异常及 per-rank 日志，使用局部 synchronize 缩小异步报错范围。设备 fault、内存越界或上下文污染后终止该实验，重新建立干净任务进程再取数值证据；不要从后续碰巧跑完的结果宣称修复。

重试应有新证据或可区分的假设；保持原失败配置、每次只改必要因素，受授权窗口/设备健康/剩余预算约束。重复同一失败且没有新证据时整理阻塞和可继续的 CPU 工作，不用固定次数的空转重启或自行扩展资源。

## 训练框架集成的检查点

保留原生参数容器、optimizer、并行和训练入口。在框架 glue 中显式分开：

- checkpoint 存储 dtype、master dtype、forward 计算 dtype、导出 dtype。
- buffer/复数位置表、冻结但影响前向的 bias/sink/adapter、量化 scale。
- FSDP/TP/EP 参数 ownership、DTensor placement、共享/别名权重和 hook/recompute 生命周期。
- old-logprob 路径与实际 grad-enabled 分支的不同上下文。

整体 `model.to(bfloat16)` 或 blanket autocast 可能覆盖模型显式要求的 FP32 参数。分片库对同组 dtype、owner 顺序和直接读参数的支持需看当前版本；“子先父后”是某类 owner 问题的候选修复，不是所有框架统一改法。

自定义模块直接读 `weight` 可能绕过 Linear.forward hook；recompute 可能看不到原先跨层状态。通过调用证据和实际 local/global tensor 形态验证，不靠模块名字判断。

## 在线更新的内容链

将同步拆成可观测的链条：

~~~text
训练 master / optimizer step
    → 逻辑参数及 buffer 的完整导出
    → dtype/分片/融合/量化/packing 转换
    → 接收端 loader 实际装载
    → shadow/packed/NZ/scale 等派生状态刷新
    → cache、Graph、sleep/wake 状态进入新策略
    → 新策略固定历史评分
~~~

每段都有内容证据。策略版本号不是成功同步的充分条件；文件 SHA 正确也不证明 shadow/Graph 实际使用该内容。FP32 shadow 不应从已丢位的 BF16 物理参数恢复；冻结参数和非训练 buffer 只要影响 forward，也必须有明确导出/保留策略。

接收端参数名、专家全局/本地编号、TP 切片、转置/融合规则必须与导出端对应。使用官方 loader/reload API 时确认所有特殊参数走相同生命周期，不能对 sink 等直接 copy 绕过其装配/计数包装。

RPC/广播要核对每个 DP/TP/EP worker 的身份、版本、包数和 SHA；API 名叫 collective 不代表覆盖所有 DP。用户要求驻留同步时，记录原 worker 身份，不能通过重启并从磁盘读新权重代替。

cache/Graph 如何失效或重建依具体后端说明；可能持有旧权重地址、旧 scale 或旧 KV。不能只看 parameter.data 的值，需检查实际计算副本和更新后输出。异步装载未完成前不能发布新版本。

## 真实更新的典型探针

任务包含在线训练闭环时，可采用两次真实更新及最后一次同步后的探针：

~~~text
θ0 同版本 rollout / native old / native grad 比较
→ backward、optimizer step、同步 θ1
→ θ1 同版本比较
→ 第二次真实更新、同步 θ2
→ θ2 同版本最终比较（无需第三次 optimizer step）
~~~

这是短闭环的典型方法，是否执行及步数服从本轮范围；只做固定权重或单侧 BI 的任务不自动扩展训练。真实 RL 用约定 loss/reward/advantage；诊断 response NLL 可以证明训练和同步通路，不能替代正式 RL 算法/质量验收。

更新证据包括目标梯度覆盖、有限/非零、optimizer counter、master 前后变化；连续两步时核对前一步 after 等于下一步 before。梯度正确性另用独立参考。量化部署值未跨 bin 时不要求每个部署字节都改变，但应验证导出内容与实际部署内容一致；受控同步扰动可隔离问题，不能替代真实更新。

更新后的训练策略与旧 rollout 不必相同。比较时必须明确策略版本，不能为了 0 diff 跳过 optimizer、复用旧分数或修改算法。

## 内存、传输与资源窗口

评估同时驻留的训推模型、optimizer/master、通信 buffer、cache、kernel workspace、weight gather 和临时文件。权重静态大小不是峰值上界；单个 metadata/stride 配置可触发很大 workspace。

可考虑 CPU offload、训练/推理 sleep/wake 交替、逐 tensor/专家流式导出和有界分包。仅在 placement/ownership 可证明时实现分片转换；不要把某案例 TP1/DP4/linear EP 的过滤规则用于其他布局。

mmap 文件 ACK 后删除不一定回收空间：loader/buffer 若持有映射，文件仍被引用。必要时 clone 接收端真正需要的 tensor，再释放映射；其额外内存要计入预算。包阈值与不可分大 tensor 的处理应明确，不能把阈值误报为硬上界。

时间受限任务使用当前窗口与时区的门禁、任务自有标签、独立清理守护及结束后核对。不硬编码历史日期，不杀其他任务，不靠对话在线保证退出。窗口结束后继续 CPU 归档与复核；下一次 NPU 运行需要新的有效授权。
