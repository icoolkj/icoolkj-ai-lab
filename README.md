# icoolkj-ai-lab
icoolkj AI研究实验室，收集自研 AI 工程原型、GUI辅助工具与各类实验脚本。

> 官网：https://icoolkj.com

## 项目说明
本仓库存放一系列独立小工具原型，每个工具都是独立目录，自带源码、依赖清单、截图文档。

## 工具列表
- ✅ **tts_gui_tool**：FishAudio + Windows本地TTS语音合成GUI工具
    - 支持FishAudio在线API合成
    - 支持降级使用Windows原生语音
    - 界面截图存放在 `tts_gui_tool/screenshots/`

## 目录规范
- `xxx_tool/`：单个工具源码目录
- `xxx_tool/screenshots/`：工具界面演示截图（提交仓库）
- `xxx_tool/release_bin/`：本地打包输出exe（.gitignore忽略，不上传仓库）
- `xxx_tool/build` / `xxx_tool/dist` / `*.spec`：PyInstaller打包临时产物，忽略

## 开源协议
[MIT](./LICENSE)

Copyright © 2026 icoolkj.com
