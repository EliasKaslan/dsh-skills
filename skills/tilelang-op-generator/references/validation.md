# Golden、覆盖与性能

独立高精度/明确舍入语义reference与实际kernel分开，固定输入后保存shape/dtype/stride/seed和期望输出。测试普通输入、零、极端幅度、不对称分布、NaN/±Inf/subnormal、尾块、非连续/alias、非法参数；按目标契约选择项，不强制每个算子接受相同形状或全NaN必须失败。

比较前确认shape/dtype、有效元素数和nonfinite语义；按数值预算比较时明确有限位置与最大误差，不用99%匹配自动忽略1%错误。bitwise目标比较原始dtype位模式；整数不能先cast掩盖越界/符号。未知dtype/未约定容差标无法判定，不能回落fp16表。空输入的返回语义与非空验收证据分开，不能拿空用例证明精度。

manifest里的覆盖维度与正整数计数只是作者声明。旧check_coverage.py做AST静态记账，不能证明那些case真的执行；核对case参数、收集和执行事件、FAIL/skip/cancelled，故意注入已知错误验证比较器会拒绝。模板占位必须替换且有效case非空；生成后先语法/导入，再目标NPU编译执行与同步。

同卡baseline使用同公式、同输入、同输出语义和同计时边界。warmup与测量次数取决于编译/缓存/噪声，记录median/分位/重复分布；不能固定3+20均值当正式性能结论。host准备、copy/cast与kernel时间分别说明，需要时用设备profiler。对比运行交错并留设备占用/频率/栈证据；资源污染的数值与性能结果标无效。

交付源码与环境指纹、正确性覆盖、原失败复测、实际执行后端、性能与未覆盖；无NPU时明确未验证，不能给PRECISION_PASS或性能达标声明。
