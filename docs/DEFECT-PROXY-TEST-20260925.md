---
title: 体验代理模式转写失败缺陷单（2026-09-25 项目方实测）
description: task 464af449 实测「转写没发生+纪要报错」的取证与派工依据
version: "0.2.0"
status: draft
created: 2026-09-25
---

# DEFECT-PROXY-TEST-20260925

## 0. 现场

- 会议：`录音 2026-09-25 10:09`（task `464af449-ce24-4a2e-b56e-0fe0ddc29a0e`），引擎=体验代理（cloud），设备=MacBook Pro麦克风。
- 现象：录制期间实时转写上屏≈0；停止后管线在 transcribe 阶段（45%）失败，页面报 `ASR proxy error: {"detail":"转写任务失败: SUCCESS_WITH_NO_VALID_FRAGMENT"}`，纪要未生成。
- 取证材料：`data/recordings/464af449_20260925_100815.wav`、`data/tasks/464af449*.json(l)`、`logs/server.log:47240-47382`。

## 1. 结论（主单）

**本次失败不是代理链路故障，是录到的音频接近数字静音。** 证据链：

| # | 证据 | 出处 |
|---|---|---|
| E1 | 归一化检测「音量过低 max=-91.0dB」，按既有策略叠加上限增益 +40dB 后仍仅约 -51dB | server.log:47291（core/audio 归一化） |
| E2 | 会中 VAD 统计：语音段=0、静音段=20、语音占比 0.0% | server.log:47275（声纹聚类统计行） |
| E3 | 实时流式转写全程仅 1 句定稿（-91dB 底噪下疑为幻觉句） | server.log:47273 |
| E4 | 离线 paraformer-v2 服务端 VAD 判整段无有效语音 → SUCCESS_WITH_NO_VALID_FRAGMENT，错误分类/文案透传均正常（category=audio，可读建议） | task JSON + core/errors.py:183 |

与 CHANGELOG 已修复过的 Windows 低音量案例同源（服务端 VAD 静音拒绝），但本次音量更低一个数量级，指向**采集端无有效输入**：macOS 麦克风权限未授予承载服务/ffmpeg 的进程、设备被系统静音、或默认输入设备错误。avfoundation 在权限缺失时不报错、只输出静音，与 E1 表现吻合。

**项目方动作（先于派工）**：系统设置→隐私与安全性→麦克风，确认运行 Open Meeting Scribe 服务的宿主进程（Terminal / Python）已授权；确认 MacBook Pro 麦克风未静音；完成后录一段 10 秒有声样音重试。若样音仍 -90dB 级，则升级为采集代码缺陷。

## 2. 派生缺陷（代码侧，待派工）

### DEF-PROXY-02：实时转写兜底未生效（确定性缺陷）

- 设计：批转写抛非瞬时错误时，`_try_realtime_fallback()`（pipeline_runner.py:153,483）应用 `realtime_full_transcript` 降级出纪要，避免整单失败。
- 实际：任务 JSON 无 `realtime_full_transcript` 字段，日志无「[录制] 全量实时转写已保存」行——实时 ASR 报 1 句定稿，但该句未进入 `realtime_full_transcripts`（写入路径 realtime_store.py:91 依赖 `push_realtime_msg` type=sentence）。兜底被静默跳过，整单失败。
- 对比：09-24 两场会议该行正常（505句→407条 / 8句→3条），且**定稿数与保存数长期不一致**，疑 stop 时序竞态或句尾定稿丢失，需一并查。
- 验收：构造静音+有实时句场景，命中降级出纪要、`transcript_source=realtime_fallback`；补 stop 竞态用例。

### DEF-PROXY-03：WAV 落盘时长 ≈ 实际录制的 1/3（待定性）

- 录制墙钟 85.9s（任务 JSON audio_duration），流线程共读 136 块；但 WAV 数据仅 27.1s（433835 帧 @16kHz）。85.9/27.1≈3.17，与 48k→16k 的 3 倍比率可疑吻合，疑 ffmpeg avfoundation 链路（audio_recording.py:344 `aresample=16000,asplit=2` 双输出）存在采样率误配或丢块。
- 与 E1 可能同根（权限静音时 avfoundation 行为异常）也可能独立，需工程师用有声样音复采定性。
- 验收：有声样音录制，WAV 时长与墙钟偏差 <2%。

### DEF-DEVICE-01：录音设备选择「保存不进去」死循环（确定性前端缺陷）+ 不持久化设计缺口

- 现场（09-25 上午，项目方报「选了 MacBook Pro麦克风，返回再进设置又没了」）：audit.log 全量仅 1 条 `POST /api/record/device`（10:19:04，值=空串→后端切 auto-detect，server.log:47430）；此后 10+ 次进设置页 GET 均无保存 POST 伴随——用户选择从未送达后端。
- 根因 A（前端，确定性）：`frontend/src/views/SettingsView.vue:973` `_deviceInitialized` 守卫假定 watch 首次触发必为回显赋值并跳过；但回显仅在 `current_device` 非空时发生（:960 falsy 检查）。当前值一旦为空串，用户第一次真实选择被吞、不发 POST，重进页面回显仍空 → 死循环。修法方向：守卫改为「仅消费 loadDevices 回显那一次赋值」（显式标志位），或 watch 内比对新值与已知后端态。
- 根因 B（设计缺口，需产品裁决）：`app/store.py:59` 设备选择仅改内存变量，docstring 明示「不持久化，重启后恢复默认」，不写 data/settings.json。macOS 默认值恰为 "MacBook Pro麦克风" 掩盖了该问题；改选其他设备（如 BlackHole 2ch）后重启即静默丢失。**是否升格为持久化配置（写 settings.json + 启动时读取）待项目方拍板**；若拍板持久化，需同步 settings_store 读写与数据流向矩阵口径。
- 验收：① current_device 为空态下首次选择即发出 POST；② 连续切换设备各 1 次均落 POST；③（若做持久化）重启后 GET /api/record/devices 回显上次选择。
- 临时绕行（已告知项目方）：先选「自动」再选回目标设备，第二次变更不被吞。

## 3. 边界与排期建议

- 拟 Owner：后端工程师（a4cdbd0ca795）。现队列 RT-P0-FIX 在途在前，本两单与其同属录音/管线域，建议同会话串行。
- DEF-DEVICE-01 根因 A 属前端，拟 Owner 前端开发工程师（d1b77737cde5），与 DC-R2-a/AM-F1 同会话串行；根因 B 若裁决持久化则前后端各半，届时拆单。
- 不改代理服务端；SUCCESS_WITH_NO_VALID_FRAGMENT 的报错文案与分类本次表现符合预期，不动。
