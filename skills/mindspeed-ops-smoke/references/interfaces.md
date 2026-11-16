# 消费方接口与算子增量

分别盘Ops→外部依赖、消费仓→Ops的真实调用。AST需处理import别名、模块级Assign/AnnAssign、partial、re-export和条件分支；字符串命中、安装文档和同名局部变量不是调用证据。动态注册/反射无法闭合时不判缺失。带设备分支的同名函数逐分支绑定位置和关键字，不能“任一候选接受就通过”。

torch.ops命名空间可能惰性创建，hasattr(namespace)与dir都不能证明具体算子注册；解析具体op/overload和真实加载库。Triton shim可能将extension回挂tl，查构建映射和实际初始化顺序；找到赋值语句仍不证明该路径可运行。

从消费方恢复真实dtype/shape/stride、可选参数和fallback条件。测试返回结构、原地修改/alias、非连续输入和异常语义。签名仍在但分支无条件raise、参数被忽略、某形状编译预算超限，都可能让“名称级通过”变成运行失败。只有某条fallback失败时，报告标明实际可达条件。

版本对比使用干净独立前缀，不能--system-site-packages加--no-deps叠半套Triton；核对Python层、C扩展及backend的来源。固定其余条件做单变量/合取矩阵，确认probe与消费方契约一致；不因某个beta dtype的探针失败宣称整个尺寸必炸，也不直接把依赖错误算Ops缺陷。

requirements、pyproject、docker/CI配方、release notes和实际产物各自保留其作用域。不同分支pin不同可能是有意维护；不能仅凭发布时间或master时间更旧判“master落后需回补”，要看目标版本契约和合入历史。

算子增量以两个固定树的公共API/实现/绑定/测试/文档集合为线索，再按语义区分新算子、新阶段、新实现和搬迁。路径集合差也会把改名列为新路径，必须核对rename/同族实现；“四件套齐”是项目质量检查而非所有算子存在性的通用定义。首次log结果受浅克隆与路径迁移影响，归因需完整历史。
