# 本地引擎组件 · 内网离线包目录与校验（WP-G G-4 交付物）

适用场景：政企内网无法访问 GitHub / ModelScope，需人工导入本地引擎组件与模型权重。
决策依据：[WP-G 派工说明 §3](WP-G-R8-PACKAGING-DISPATCH.md)（D-G1 独立引擎包、D-G3 运行时数据锚点）。

## 1. 目录布局（三条安装通道共用，D-G1 子项①）

引擎组件（只读代码包，≈1GB，onedir）：

```
<引擎根>/
├── OMSEngine.exe            # Windows 可执行体（mac 为 OMSEngine，无扩展名）
├── _internal/               # PyInstaller 冻结运行时（含 torch/funasr/modelscope）
└── engine-manifest.json     # 版本 / 协议版本 / 逐文件 SHA256（build/make_engine_manifest.py 产出）
```

`<引擎根>` 落位位置（主程序搜索序，见 `core/engine_paths.py`）：

| 优先 | 位置 | 说明 |
|---|---|---|
| ① | `OMS_ENGINE_DIR` 环境变量指向目录 | 运维/CI 显式覆盖 |
| ② | settings `engine.local.engine_dir` | 管理员在应用内配置 |
| ③ | `<主程序 exe 同级>/engine/` | Win Inno `[Components]` 安装布局（G-4） |
| ④ | Win `%LOCALAPPDATA%\OpenMeetingScribe\engine\`；mac `~/Library/Application Support/OpenMeetingScribe/engine/` | 应用内一键落位（G-4b）/ 离线包导入目标 |

模型权重（运行时数据，≈2.0GB，D-G3 锚点，与代码包分离）：

```
<模型目录>/                  # Win %LOCALAPPDATA%\OpenMeetingScribe\models\
│                            # mac ~/Library/Application Support/OpenMeetingScribe/models/
│                            # 开发态 data/models/
├── hub/<modelscope_id>/...  # ModelScope SDK 缓存布局
└── .integrity.json          # 完整性清单（相对路径 → sha256/size）
```

## 2. 离线包获取

- **引擎组件 zip**：`Build Engine Package` workflow（`.github/workflows/build-engine.yml`）产物
  `OMSEngine-<platform>.zip` + `.zip.sha256`（平台标签：`windows-amd64` / `darwin-arm64`）。
- **模型权重**：在有网机器上用应用内「下载全部」拉齐 `<模型目录>/hub/` 与 `.integrity.json`，
  整目录打包。必装三件（seaco-paraformer-zh / fsmn-vad / cam-plus ≈976MB）+
  可选 ct-punc（1.0GB，D-G2：可选件缺失不影响 ready 判定）。

## 3. 导入与校验

引擎组件（二选一）：

1. **应用内导入**（推荐）：管理员调用
   `POST /api/engine/component/install-local`，body `{"zip_path": "<离线包路径>", "sha256": "<可选>"}`
   ——自动完成 zip 整体 SHA256 → 解包 → manifest 逐文件校验 → 原子换入锚点 `engine/`。
2. **手工落位**：解压 zip 到上表 ③/④ 任一位置，保证 `<引擎根>/engine-manifest.json` 与
   可执行体同级。手工校验：
   ```
   shasum -a 256 OMSEngine-<platform>.zip     # 对照 .zip.sha256
   ```

模型权重：整目录复制到 `<模型目录>`（保持 `hub/` 与 `.integrity.json` 相对结构），
应用内「设置 → 本地引擎 → 完整性校验」（`POST /api/engine/verify`）逐文件核对 SHA256，
篡改/缺失会被拒载（`models_tampered` / `models_missing`）。

## 4. 版本兼容

- 主包 ↔ 引擎包以 `engine-manifest.json.protocol_version` 握手（对端
  `core/engine_worker.py PROTOCOL_VERSION`）；不匹配 → **拒绝启动**并提示
  「请升级本地引擎组件」，不静默回退云端（D-G1 子项③）。
- 离线导入时请核对 manifest `engine_version` 与主程序 VERSION 的兼容矩阵
  （同 minor 版本线内协议版本一致；跨线升级先换引擎包再换主包亦可——握手双向拒绝不匹配组合）。

## 5. 卸载/回滚

- 引擎组件为只读代码包：删除 `<引擎根>` 即回滚（应用内换入采用
  `engine.new` → `engine` 原子交换，旧版本临时保留为 `engine.old` 后清理）。
- 权重与日志在用户数据锚点，卸载主程序不删除（重装免重复下载）。
