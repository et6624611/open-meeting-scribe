#!/usr/bin/env python3
"""
run.py — 声纹服务生产入口

用法：
    python run.py                    # 默认 0.0.0.0:8100
    python run.py --port 8100        # 指定端口
    python run.py --workers 2        # 多 worker（每个 worker 加载一份模型，约占 600MB 内存）
"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="声纹嵌入提取服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8100, help="监听端口（默认 8100）")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数（默认 1，每 worker ~600MB）")
    args = parser.parse_args()

    print(f"启动声纹服务: http://{args.host}:{args.port}（workers={args.workers}）")

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
