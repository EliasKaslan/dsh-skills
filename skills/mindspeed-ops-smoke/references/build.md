# Wheel构建与独立验收

从目标SHA读取setup/pyproject/CMake和工具链要求。CANN安装、host driver、SOC归一化、Python解释器、torch C++ ABI、编译器和并行度明确记录。SOC_VERSION未设可能自动探测，也可能产纯Python包；不能只由环境变量有无判断。CATLASS/ACLNN/ATB的编译/JIT路线按目标代码分别追踪。

构建日志必须保留实际命令和失败退出码，pip|tee用pipefail或保存前段rc。缺regex/CMake选错Python时设置本版支持的解释器变量并查实际调用；不用隐藏python字面量绕过旧wrapper检测，除非当前版本确有该检测且已复现。GCC/clang选择需满足目标头文件和语言标准，单个版本守卫绕过不证明整扩展兼容。

ZIP/WHEEL/METADATA/RECORD与ELF成员核对：tag/架构、所需扩展、vendor包、CATLASS库、版本/依赖声明、RPATH/RUNPATH/NEEDED和符号版本。成员数随版本/构建模式变化，不固定48/7；同名同大小不证明二进制同一。缺Requires-Dist不代表无需torch，只说明包没有完整声明依赖。

在目标兼容、依赖已明确满足的独立环境中安装wheel，离开源码树，核对所有模块来源。CPU上的pip安装/zip检查不能证明NPU可用。按任务实际需要执行具体扩展注册/调用及ACLNN/Triton/CATLASS/ATB数值用例；未构建的分支不以skip冒充覆盖。版本变化要重验受影响产物，某两套CANN通过不能推出任意小版本兼容。

第三方下载核对TLS验证生效、不可变来源及每个制品的hash。CMake默认TLS随版本变化，显式TLS_VERIFY ON可避免依赖旧默认；hash要绑定实际选中的本地/远端制品，不能不同URL共用一个值。可选list参数是否引用按目标API参数语义验证，不把“空变量一律不加引号”泛化为CMake规则。

容器检查manifest/digest与实际architecture、工具版本和driver挂载，tag中的aarch64不证明内容是arm64。先验证新镜像可拉取及目标任务，再切换已授权目标分支workflow；构建成功不自动授权push或变更共享CI。
