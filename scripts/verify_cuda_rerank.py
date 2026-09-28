"""Verify that the local reranker runs through ONNX Runtime's CUDA provider."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import onnxruntime as ort

from app.reranker import Reranker


def main():
    available = ort.get_available_providers()
    if 'CUDAExecutionProvider' not in available:
        raise SystemExit(f'ONNX Runtime 未提供 CUDAExecutionProvider：{available}')

    data_dir = Path(os.environ.get('RAG_DATA_DIR', ROOT / 'data'))
    reranker = Reranker(data_dir / 'models')
    result = reranker.rank(
        '推免资格需要什么条件？',
        [
            {'chunk_id': 'probe:1', 'text': '必修课程平均学分绩点至少为3.2。'},
            {'chunk_id': 'probe:2', 'text': '学院设立推免工作小组。'},
        ],
        {'reranker_enabled': True, 'reranker_device': 'cuda'},
    )
    if result.fallback or result.device != 'cuda':
        raise SystemExit(f'重排未使用 CUDA：{result.error or result.device}')
    active = reranker._model.model.get_providers()
    if 'CUDAExecutionProvider' not in active:
        raise SystemExit(f'重排 session 未使用 CUDA：{active}')
    print(f'CUDA 重排验证通过：ONNX Runtime {ort.__version__}；实际提供器 {active}')


if __name__ == '__main__':
    main()
