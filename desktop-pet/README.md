# 宝贝桌面宠物 🎀（SVG 版）

圆脸微胖 · 侧面麻花辫 · 牛仔背带裤 · 可爱风的 Windows 桌面宠物。
用 **Electron + TypeScript** 搭建，角色用 **SVG/CSS 手绘**——无需任何 Live2D 模型素材即可运行。

[![Electron](https://img.shields.io/badge/electron-31-47848F)](package.json)
[![TypeScript](https://img.shields.io/badge/typescript-5.5-3178C6)](package.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 交互一览
| 行为 | 效果 |
|---|---|
| 鼠标移动 | 眼球 + 头部自然跟随（视差追踪） |
| 悬停角色 | 开心表情 + 轻微摇晃 |
| 点击头部 | 摸头动作 + 爱心粒子 |
| 点击身体 | 害羞表情 + 后退半步 |
| 按住拖动 | 移动整个窗口 |
| 空白区域 | 鼠标穿透到桌面 |
| 闲置 3 秒 | 呼吸循环 |
| 持续闲置 | 随机小动作（打哈欠 / 整理辫子 / 看手机） |
| 右键托盘 | 显示/隐藏 · 重置位置 · 音效开关 · 退出 |
| 重启 | 自动恢复上次窗口位置与音量状态 |

## 目录结构
```
desktop-pet/
├─ package.json            # 依赖与脚本
├─ tsconfig.json           # TS 编译配置（src → dist）
├─ electron-builder.yml    # 打包配置（nsis 安装包 + portable 便携版）
├─ src/
│  ├─ main.ts              # 主进程：透明窗口 / 托盘 / IPC / 配置持久化
│  └─ preload.ts           # 预加载：安全暴露 petAPI 给渲染层
├─ renderer/
│  ├─ index.html           # 角色 SVG + 样式
│  ├─ renderer.js          # 交互状态机 + 命中检测 + 拖拽 + 闲置动作
│  └─ tray.png             # 托盘图标（脚本生成，可替换）
├─ resources/              # 素材热替换目录（随包分发，见其中 README）
├─ docs/
│  ├─ prompt.md            # 原始需求提示词
│  └─ interactive-icon.html# 网页版角色 demo（浏览器直接打开，无需 Electron）
├─ dist/                   # tsc 输出（自动生成）
└─ release/                # 打包产物（自动生成）
```

## 运行 / 调试 / 打包

```bash
# 1) 安装依赖（首次；若 electron 二进制未下载，执行 npm approve-scripts electron）
npm install

# 2) 开发运行（先编译再启动）
npm start

# 3) 监听式编译（改 TS 自动重编，另开一个终端配合 electron . 使用）
npm run dev

# 4) 只打免安装目录版（快速验证打包结果，产物在 release/win-unpacked/）
npm run pack:dir

# 5) 打正式安装包 + 便携版 exe（产物在 release/）
npm run dist

# 6) 只打便携版单文件 exe
npm run dist:portable
```

> 调试渲染层：在 `src/main.ts` 的 `createWindow()` 里临时加 `win.webContents.openDevTools({ mode: 'detach' })`。

## 常见坑点及解决方案

**1. 鼠标穿透失效 / 整块窗口挡住桌面**
- 根因：透明窗口默认整块可点。本项目用 `win.setIgnoreMouseEvents(true, { forward: true })` 让窗口默认穿透，同时 `forward:true` 保证 `mousemove` 仍能传进渲染进程。
- 渲染层用 `document.elementFromPoint()` 做命中检测：指针在角色实心像素上才通过 IPC 关闭穿透（可点/可拖），离开立即恢复穿透。
- 若仍失效：确认 `renderer/index.html` 里 `html,body{background:transparent}` 未被覆盖，且 `.char *{pointer-events:none}` 存在。

**2. 透明窗口有灰色/黑色边框**
- 关闭窗口阴影：`hasShadow:false`。Windows 上开启 `transparent:true` 时不要再设背景色。

**3. 打包后路径错误 / 加载空白**
- 主进程用 `path.join(__dirname, '..', 'renderer', 'index.html')` 定位渲染文件，`__dirname` 打包后指向 `app.asar/dist`，`..` 回到 `app.asar` 根再进 `renderer`，需保证 `electron-builder.yml` 的 `files` 包含 `renderer/**/*`（已包含）。
- 配置文件写在 `app.getPath('userData')`，绝不要写安装目录（无写权限）。

**4. 托盘图标不显示**
- `renderer/tray.png` 是脚本生成的 32×32 占位图。要换成正式图标，替换该文件即可；安装包图标另配 `build/icon.ico`（256×256）。

**5. 始终置顶被其它全屏应用压住**
- 已用 `setAlwaysOnTop(true, 'screen-saver')` + `setVisibleOnAllWorkspaces`。全屏独占游戏仍可能盖住，属系统限制。

**6. 便携版首次启动杀软报警**
- 未签名 exe 的常见现象。个人使用可忽略；正式分发需代码签名证书，在 `electron-builder.yml` 的 `win` 下配 `certificateFile`/`certificatePassword`。

## 内存 / 占用优化

- **离屏暂停**：窗口 `hide` 时主进程发 `visibility=false`，渲染层停止跟随渲染与眨眼定时器（`rendering` 开关），显著降低隐藏态占用。
- **IPC 去抖**：命中检测的穿透切换只在状态变化时发一次 IPC（`lastInteractive`），避免每帧通信。
- **写盘防抖**：窗口移动 400ms 内合并一次配置写入。
- **单实例锁**：`requestSingleInstanceLock()` 防止重复进程叠加占用。
- 进一步可选：闲置很久后降低 `render` 频率，或在 `webPreferences` 关闭不需要的特性。

## 升级到真·Live2D

想换成会呼吸、辫子会甩的真模型时，按 `resources/README.md` 的分层与参数命名规范准备 `.moc3/.model3.json/纹理`，引入 `pixi.js@7` + `pixi-live2d-display`，把 `renderer.js` 里对 SVG 的 class 操作换成对 Live2D 参数（`ParamAngleX` 等）的赋值即可，交互状态机与主进程无需改动。

## License

[MIT](LICENSE) © 2026 zzdjjdd
