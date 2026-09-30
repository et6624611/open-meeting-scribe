"""selftest_autostop_pipeline.py — 验证 auto_stop_recording 的纪要管线派发不再抛 TypeError。

背景：core/silence_detection.py 原实现把同步的 run_pipeline_task 返回值传给
asyncio.ensure_future，事件循环回调抛 TypeError（2026-09-30 server.log）。
本自测桩掉 stop_recording_with_stream 与 run_pipeline_task，验证：
  1. auto_stop_recording 全程无异常；
  2. run_pipeline_task 以正确参数在线程池被执行；
  3. 不再出现 "An asyncio.Future, a coroutine or an awaitable is required"。
"""

import asyncio
import sys
from pathlib import Path

import core.silence_detection as sd

FAIL = 0


def check(name, cond):
    global FAIL
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAIL += 1
    print(f"[{status}] {name}")


async def main():
    task_id = "selftest-autostop-0001"
    calls = {}

    # 桩：任务与停止录音
    sd.tasks[task_id] = {"audio_name": "自测录音", "status": "recording"}
    audio_path = Path("/tmp/selftest_rec.wav")

    def fake_stop():
        return {"output_path": audio_path, "duration": 42.5}

    def fake_pipeline(tid, path, name, mapping, count):
        calls["pipeline"] = {"task_id": tid, "audio_path": path, "audio_name": name,
                             "mapping": mapping, "count": count}

    orig_stop, orig_pipeline, orig_save, orig_push, orig_cleanup = (
        sd.stop_recording_with_stream, sd.run_pipeline_task,
        sd.save_task_to_disk, sd.push_realtime_msg, sd.cleanup_silence_detection,
    )
    sd.stop_recording_with_stream = fake_stop
    sd.run_pipeline_task = fake_pipeline
    sd.save_task_to_disk = lambda tid: None
    sd.push_realtime_msg = lambda tid, msg: None
    sd.cleanup_silence_detection = lambda tid: None
    try:
        loop = asyncio.get_running_loop()

        def on_unhandled(_loop, context):
            calls.setdefault("loop_errors", []).append(context.get("message", ""))

        loop.set_exception_handler(on_unhandled)

        await sd.auto_stop_recording(task_id, reason="selftest")

        # 等待线程池中的管线任务执行完毕
        for _ in range(50):
            if "pipeline" in calls:
                break
            await asyncio.sleep(0.05)

        check("纪要管线被派发执行（线程池）", "pipeline" in calls)
        if "pipeline" in calls:
            c = calls["pipeline"]
            check("task_id 正确传递", c["task_id"] == task_id)
            check("audio_path 正确传递", c["audio_path"] == audio_path)
            # auto_stop 会用时间戳重命名 audio_name（silence_detection.py 内 tasks 更新）
            check("audio_name 非空且与 tasks 当前值一致",
                  bool(c["audio_name"]) and c["audio_name"] == sd.tasks.get(task_id, {}).get("audio_name"))
        loop_errs = calls.get("loop_errors", [])
        check("事件循环无未处理异常（尤其 ensure_future TypeError）",
              not any("coroutine or an awaitable" in m for m in loop_errs) and not loop_errs)

        loop.set_exception_handler(None)
    finally:
        sd.stop_recording_with_stream = orig_stop
        sd.run_pipeline_task = orig_pipeline
        sd.save_task_to_disk = orig_save
        sd.push_realtime_msg = orig_push
        sd.cleanup_silence_detection = orig_cleanup
        sd.tasks.pop(task_id, None)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if FAIL else 0)
