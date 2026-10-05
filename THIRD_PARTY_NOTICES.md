---
title: "Third-Party Notices / 第三方许可声明"
description: "本项目使用的开源第三方组件及其许可证信息 / Third-party open-source components and their license information."
tags: ["license", "third-party", "compliance"]
created_at: "2026-09-17"
updated_at: "2026-10-05"
version: "1.0.0"
author: "et6624611"
status: "published"
category: "legal"
---

# Third-Party Notices / 第三方许可声明

Open Meeting Scribe is licensed under AGPL-3.0-or-later. This project includes the following third-party open-source software under their respective licenses.

> 本声明覆盖**随仓库分发**的代码依赖与**引导下载**的模型权重两类。模型权重不随仓库分发，由用户在首次启用本地引擎时按需下载，许可以 ModelScope 各模型页公示为准。

---

## Runtime

### Python
- **License**: PSF-2.0
- **Repository**: https://www.python.org/

### Node.js
- **License**: MIT
- **Repository**: https://github.com/nodejs/node

---

## Frontend Dependencies

### Vue 3
- **License**: MIT
- **Copyright**: Copyright (c) 2018-present, Yuxi (Evan) You and contributors
- **Repository**: https://github.com/vuejs/core

### Vue Router
- **License**: MIT
- **Copyright**: Copyright (c) 2019-present, Yuxi (Evan) You and contributors
- **Repository**: https://github.com/vuejs/router

### Pinia
- **License**: MIT
- **Copyright**: Copyright (c) 2019-present, Yuxi (Evan) You and contributors
- **Repository**: https://github.com/vuejs/pinia

### Vue I18n
- **License**: MIT
- **Copyright**: Copyright (c) 2020 kazuya kawaguchi
- **Repository**: https://github.com/intlify/vue-i18n

### Vite
- **License**: MIT
- **Copyright**: Copyright (c) 2019-present, Yuxi (Evan) You and contributors
- **Repository**: https://github.com/vitejs/vite

### Mermaid
- **License**: MIT
- **Copyright**: Copyright (c) 2014-2023 Mermaid contributors
- **Repository**: https://github.com/mermaid-js/mermaid

### Axios
- **License**: MIT
- **Copyright**: Copyright (c) 2014-present Matt Zabriskie
- **Repository**: https://github.com/axios/axios

### vue-virtual-scroller
- **License**: MIT
- **Copyright**: Copyright (c) 2017 Guillaume Chau
- **Repository**: https://github.com/Akryum/vue-virtual-scroller

---

## Backend Dependencies

### FastAPI
- **License**: MIT
- **Copyright**: Copyright (c) 2018 Sebastián Ramírez
- **Repository**: https://github.com/tiangolo/fastapi

### Uvicorn
- **License**: BSD-3-Clause
- **Copyright**: Copyright © 2017-present, Encode OSS Ltd. All rights reserved.
- **Repository**: https://github.com/encode/uvicorn

### DashScope SDK
- **License**: Apache-2.0
- **Copyright**: Copyright (c) Alibaba Cloud
- **Repository**: https://github.com/aliyun/alibabacloud-bailian-speech-demo

### PyJWT
- **License**: MIT
- **Copyright**: Copyright (c) 2015 José Padilla
- **Repository**: https://github.com/jpadilla/pyjwt

### NumPy
- **License**: BSD-3-Clause
- **Repository**: https://github.com/numpy/numpy

### python-docx
- **License**: MIT
- **Repository**: https://github.com/python-openxml/python-docx

### PyPDF2
- **License**: BSD-3-Clause
- **Repository**: https://github.com/py-pdf/PyPDF2

### Babel
- **License**: BSD-3-Clause
- **Repository**: https://github.com/python-babel/babel

### pywebview
- **License**: BSD-3-Clause
- **Repository**: https://github.com/r0x0r/pywebview

---

## Local Engine（可选，引导下载）

本地引擎组件（FunASR 推理框架 + ModelScope 模型权重）**不随仓库分发**。首次启用本地引擎时由 `core/model_registry.py` 引导用户从 ModelScope 下载到本机缓存目录。以下条目仅供溯源，许可以 ModelScope 各模型页为准。

### FunASR
- **License**: MIT
- **Repository**: https://github.com/modelscope/FunASR
- **用途**: 本地 ASR 全管线推理框架（含说话人分离与声纹嵌入提取）

### PyTorch
- **License**: BSD-3-Clause
- **Repository**: https://github.com/pytorch/pytorch
- **用途**: FunASR 与张量计算底座

### ModelScope 模型权重（四项）

| 模型 | ModelScope ID | 用途 | 大小 |
|---|---|---|---|
| SeACo-Paraformer 中文转写 | `iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch` | 转写主模型 | ~944 MB |
| FSMN-VAD 语音活动检测 | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | 语音活动检测 | ~3.9 MB |
| CAM++ 说话人/声纹 | `iic/speech_campplus_sv_zh-cn_16k-common` | 说话人分离与声纹共用 | ~28 MB |
| CT-Transformer 标点恢复（可选） | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | 标点恢复，可裁剪 | ~1.0 GB |

许可说明：上述权重由 ModelScope 平台分发，使用前请阅读对应模型页的使用条款；本项目不内置、不修改、不再分发上述权重。

---

## Build / Packaging

### PyInstaller
- **License**: GPL-2.0-or-later（含 bootloader 例外，允许打包生成闭源/开源可执行文件而不传染目标产物）
- **Repository**: https://github.com/pyinstaller/pyinstaller

### ffmpeg（Docker 镜像内置）
- **License**: LGPL-2.1-or-later（默认构建配置，未启用 GPL 组件）
- **Repository**: https://ffmpeg.org/
- **说明**: 仅 Docker 镜像内置用于音视频解码；源码安装路径下由用户系统提供

---

## License Texts

### MIT License
```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### BSD-3-Clause License
```
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED.
```

### Apache-2.0 License (excerpt)
```
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
```

### LGPL-2.1 License (excerpt)
```
This library is free software; you can redistribute it and/or modify it under
the terms of the GNU Lesser General Public License as published by the Free
Software Foundation; either version 2.1 of the License, or (at your option)
any later version.

This library is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
details.

    https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
```
