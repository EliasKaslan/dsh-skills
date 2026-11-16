# 旧脚本调用边界

旧文件保留以便历史追溯，存在文件不等于可直接执行。本轮确认的两个问题：

- 原skill目录下 `anima-ai-musume-lora/scripts/patch_ops.py`：模块顶层写死ComfyUI源码路径，无main guard；在隔离替身上连续两次执行会重复插入guard并覆盖原备份。禁止导入或直接执行到共享环境。需要修复时从当前精确版本定位，局部patch并验证幂等、备份与回退。
- 原skill目录下 `anima-ai-musume-lora/scripts/wheel_par.py`：按固定cp312/x86偏好选择wheel，Range下载未核对206/Content-Range/分片长度；隔离fixture证明服务端返回200整文件时写入错误分片。使用当前可靠包管理与下载工具，校验兼容tag、长度和哈希。

`patch_qwen_rotary.py`、旧部署/下载/训练/自愈脚本还含固定路径或外部副作用，未做真实后端执行验收。不要把静态解析通过当部署成功。H3与SDXL/Anima模型及接口边界各自独立，不以旧一套脚本替代所有后端。
