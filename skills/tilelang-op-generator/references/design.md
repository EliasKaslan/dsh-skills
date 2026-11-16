# 内存、派发与同步

先从最接近且同backend的现有实现建立骨架，明确Vector/Cube分工、tiling、workspace、buffer生命周期和同步所有权。GM/UB/L1/L0传输边和专用直通取目标backend及SoC实际限制，不能把某一路线的内存图推广所有平台。

自动sync/memory planning/CV combine等pass的名称、默认值和相互约束先核对目标源码；手动Scope/barrier/flag与自动pass不可想当然混用。查看生成IR和实际schedule，确认生产者/消费者、跨核可见性与buffer复用，不因开启自动sync就认为所有同步都正确。

多Vector核分块时load/compute/store使用同一基址，尾块extent夹到合法非负范围，分别测试M/N/K边缘、块数大于核数、prime尺寸、小于子块的尾段。ceildiv只给网格数量；自动lowering是否裁剪在目标版本实证，不能按旧N尾块PASS推所有轴。

GEMM分形、block尺寸、dtype对齐和Pipelined动态边界按后端限制证明；某些非法配置可能编译过仍错算。检查布局/stride、转置、读写重叠、store覆盖和未初始化workspace。host侧必要cast/pad/contiguous可能是用户契约的一部分，但必须计入成本并披露，不能靠它悄悄简化内核条件或冒充优化收益。

cache开关局限在本任务main/进程，避免import模块时清全局cache。调试instrumentation与交付实现分开，改实现后回到原触发场景重验。
