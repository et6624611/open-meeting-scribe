# CI 合入指引 — 本地引擎 workflow（WP-D）

对象：`.github/workflows/ci-local-engine-v2.yml（原 ci-local-engine.yml，因 GitHub 元数据注册异常改名重注册）`（PRD-LOCAL-ENGINE §13 WP-D / R8 / AC-7）。

## Job ↔ AC 对照

| Job | 对应契约 | 守护内容 |
|---|---|---|
| `windows-freeze-smoke` | R8（实施首任务）/ R5 实施约束①②③ | Windows 上 PyInstaller `--onedir` 冻结 torch+funasr 引擎替身包可构建、可运行：import → spawn 子进程（freeze_support）→ AutoModel 加载链 → generate 推理路径；全程零真实模型下载 |
| `cloud-package-size-guard` | AC-7（云包零增长） | 云精简主包三重守护：静态检查（requirements / spec excludes / 模块级 import）→ Analysis TOC 冻结图侵入扫描 → 主包体积阈值回归（`cloud-size-baseline.json`） |

触发策略：PR 只跑体积守护（~20min）；push main（触及打包相关文件）两者都跑；每周日 schedule 跑冻结冒烟跟踪上游；dispatch 可勾选。

## 失败排查优先级

### windows-freeze-smoke
1. **先跑没跑过「未冻结基线冒烟」step**：未冻结就失败 = `stub_engine.py`/fixture 逻辑问题（本地 `python stub_engine.py --fixtures <dir>` 可复现）；未冻结通过、冻结失败才是 PyInstaller 问题。
2. **冻结冒烟超时/卡死**：优先怀疑 spawn 子进程重执行（`__main__` guard + `freeze_support()` 是否被改动）；其次 Windows Defender 扫描拖慢首启 import（Spike 实测冻结态 funasr import 最高 86s，本机预验证 81s，step timeout 30min 已留量）。
3. **`tables.register` 相关 OSError（could not get source code）**：冻结态 `__main__` 无源码，替身注册必须直写 `tables.model_classes[...]`，不要改回官方装饰器（见 stub_engine.py 内注释）。
4. **「MODELSCOPE_CACHE 出现文件」fail**：说明有代码路径触达真实模型下载——检查是否有人把 model 参数从本地 fixture 路径改成了 hub 名称。
5. PyInstaller 构建失败：看 `wp-d-freeze-smoke-logs` artifact；`--collect-all` 三件套（funasr/modelscope/torch）是 Spike 验证配方，勿减。

### cloud-package-size-guard
1. **静态侵入守护 fail**：有本地引擎依赖混入云包面——按报错定位（requirements.txt 混入 torch/funasr/modelscope、spec excludes 被删、app/core 出现模块级 import）。
2. **TOC 冻结图扫描 fail**：即使懒加载（函数内 import），PyInstaller 静态分析也会把 funasr/torch 拉进云包模块图——需在 `build/pyinstaller.spec` excludes 补充对应项（改 spec 属云包工作包范围，非本目录）。
3. **体积回归 fail**：先看 `cloud-size-report` artifact 里 measured/baseline/hard_cap；超 hard_cap（300MB）≈ 组件侵入，超 baseline+10% 需归因增量来源。
4. **bootstrap 期**：`baseline_mb=null` 时首次绿灯后，把报告中 `suggested_baseline_mb` 回填 `cloud-size-baseline.json` 并提交，此后才有精确回归线。

## 版本与环境

冒烟依赖锁定在 `requirements-smoke.txt`（Python 3.11 + torch 2.14.0 + funasr 1.4.16，与 R8 Spike 实测环境同源）；升级须重跑冻结冒烟确认（schedule 周跑即为此设）。主包构建环境与 `build-windows.yml` 相同（Python 3.12 + requirements.txt），不含 ffmpeg/安装器组装。
