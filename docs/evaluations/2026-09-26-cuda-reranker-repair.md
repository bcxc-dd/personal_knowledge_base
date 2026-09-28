# 本机 CUDA 重排故障定位与修复

日期：2026-09-26。仅处理重排 CUDA 运行问题；推免细则四题的证据判定仍为独立未修缺陷。

## 原因

1. NVIDIA RTX 4060 与驱动 566.24 可用，`nvidia-smi` 报告驱动支持 CUDA 12.7。但项目基础依赖固定为 CPU 版 `onnxruntime==1.23.2`，虚拟环境起初只有 Azure/CPU 提供器。设置指定 CUDA，FastEmbed 直接报 `CUDAExecutionProvider is not available`，`Reranker.rank` 因而回退 RRF。
2. 在隔离目录安装同版本 `onnxruntime-gpu[cuda,cudnn]` 后，提供器列表已有 CUDA，但不预加载包内 DLL 时实际 session 仍回退 CPU，错误指出缺少 `cublasLt64_12.dll`。调用 `onnxruntime.preload_dlls(directory='')` 后，实际 session 为 `['CUDAExecutionProvider', 'CPUExecutionProvider']`，真实重排推理完成。系统 CUDA Toolkit 11.7 不是本次 Python CUDA 12 运行库的来源。
3. 原 `Reranker._load` 在首次模型加载后把后续调用的设备固定报告为 CPU；且未核对 session 的实际提供器。只看配置或 `get_available_providers()` 都不足以证明模型在 GPU 上运行。

## 本次改动

- `backend/app/reranker.py`：请求 CUDA 且 GPU 包提供 CUDA EP 时预加载随包安装的 DLL；核对真实 session 提供器，CUDA 初始化失败则保持原有 RRF 回退；缓存并复用真实设备标签。
- `backend/app/models.py`：本地向量模型显式保持 CPU，避免安装 GPU 版运行时后从原有 CPU 行为变成自动尝试 CUDA 并产生 DLL 警告。
- `scripts/enable-cuda.ps1` 与 `scripts/verify_cuda_rerank.py`：在停止服务后把 CPU 包替换为 GPU 包及 CUDA/cuDNN 运行库，并以真实模型推理和 session 提供器验收；`scripts/setup.ps1 -Cuda` 提供新机器安装入口。README 增加操作说明。基础 `backend/requirements.txt` 仍采用 CPU 版，保证没有 NVIDIA 显卡也能安装。
- 本机已执行安装脚本并重启 8765 服务；当前虚拟环境含 `onnxruntime-gpu 1.23.2`、CUDA 12/cuDNN 9 包，服务配置仍为 `reranker_enabled=true`、`reranker_device=cuda`。

## 验证与边界

- 两个针对预加载、缓存设备标签及真实提供器的测试先失败，修改后通过。
- 原 PDF 的隔离索引快照中，问题“我的绩点是3.1，可以保研吗？”返回 `provider=local-reranker`、`device=cuda`、`fallback=false`；重排 session 含 `CUDAExecutionProvider`，第 2 页成绩门槛片段进入前六。没有调用回答服务，也没有写入用户会话。
- 同一检索核对到本地向量模型的实际 session 只有 `CPUExecutionProvider`，重排模型的实际 session 为 `['CUDAExecutionProvider', 'CPUExecutionProvider']`；这是本次限定的设备分工。运行时没有再出现缺少 `cublasLt64_12.dll` 或 CUDA 提供器创建失败。
- 全量后端测试最终复跑 `80 passed, 4 xfailed`；四个 xfail 是此前登记的推免问答缺陷。首次全量运行又遇到历史上出现过的 Windows Chroma 临时快照文件占用，单项与第二次全量复跑通过；未将其归因于 CUDA 变更。
- `uv pip check` 会报告 FastEmbed/Chroma 的 `onnxruntime` 发行包名依赖未满足：它们的元数据只认 CPU 包名，不把 `onnxruntime-gpu` 视作替代。这是安装元数据告警；真实导入、CUDA session 和上述测试均通过。再次运行默认 `setup.ps1` 后须重新运行 `enable-cuda.ps1`，或直接使用 `setup.ps1 -Cuda`。
- 无需重建 PDF 索引或前端构建；后端已重启。CUDA 重排恢复不等于四题能回答，词法候选与证据判定仍须单独修复并回归。
- 隔离验证目录 `test-results/cuda-probe/` 约 2.85 GiB，仍留在 Git 忽略目录；清理该目录的递归删除被执行策略拒绝，未尝试绕过。它不参与当前服务运行。

参考：[ONNX Runtime CUDA 提供器与 DLL 预加载](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)、[ONNX Runtime 安装](https://onnxruntime.ai/docs/install/)。
