$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw '请先运行 .\scripts\setup.ps1 创建 Python 环境。'
}
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    throw '请先停止正在运行的知屿服务，再替换 ONNX Runtime。'
}

Push-Location $projectRoot
try {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip uninstall --python $python onnxruntime
        if ($LASTEXITCODE -ne 0) { throw '卸载 CPU 版 ONNX Runtime 失败。' }
        & uv pip install --python $python 'onnxruntime-gpu[cuda,cudnn]==1.23.2'
        if ($LASTEXITCODE -ne 0) { throw '安装 GPU 版 ONNX Runtime 或 CUDA/cuDNN 运行库失败。' }
    } else {
        & $python -m pip uninstall -y onnxruntime
        if ($LASTEXITCODE -ne 0) { throw '卸载 CPU 版 ONNX Runtime 失败。' }
        & $python -m pip install 'onnxruntime-gpu[cuda,cudnn]==1.23.2'
        if ($LASTEXITCODE -ne 0) { throw '安装 GPU 版 ONNX Runtime 或 CUDA/cuDNN 运行库失败。' }
    }
    & $python scripts\verify_cuda_rerank.py
    if ($LASTEXITCODE -ne 0) { throw 'GPU 包已安装，但实际 CUDA 重排验证失败。' }
    Write-Host 'CUDA 重排已可用。现在可以重新启动知屿服务。'
} finally {
    Pop-Location
}
