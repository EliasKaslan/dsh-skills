# 旧脚本调用边界

旧文件保留以便历史追溯，存在文件不等于可直接执行。下面两个补丁/下载工具已退役成失败桩：运行只打印退役原因并以退出码 2 结束，不读凭据、不改文件、不联网（本轮实测确认）。

- [patch_ops.py](../../anima-ai-musume-lora/scripts/patch_ops.py)：原版在模块顶层写死 ComfyUI 源码路径且无 main guard，导入即读写硬编码文件；隔离替身上连续两次执行会重复插入 guard 并覆盖原备份，**不是幂等**。现在触发不到该副作用；真要修复就从当前精确版本定位，局部 patch 并验证幂等、备份与回退。
- [wheel_par.py](../../anima-ai-musume-lora/scripts/wheel_par.py)：原版按固定 cp312/x86 偏好选 wheel，Range 下载未核对 206/Content-Range 与分片长度；隔离 fixture 证明服务端返回 200 整文件时会写入错误分片。改用当前可靠包管理与下载工具，校验兼容 tag、长度和哈希。

[patch_qwen_rotary.py](../../minimax-ai-musume-4k-art/scripts/patch_qwen_rotary.py)、旧部署/下载/训练/自愈脚本还含固定路径或外部副作用，未做真实后端执行验收。不要把静态解析通过当部署成功。H3 与 SDXL/Anima 模型及接口边界各自独立，不以旧一套脚本替代所有后端。
