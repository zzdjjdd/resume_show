/**
 * 预加载脚本：在隔离上下文中安全地暴露一组受限 API 给渲染进程。
 * 渲染进程通过 window.petAPI.* 与主进程通信，无法直接访问 Node。
 */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('petAPI', {
  // 命中检测：切换窗口是否可交互（false=鼠标穿透到桌面）。
  setInteractive: (on: boolean) => ipcRenderer.send('set-interactive', on),

  // 拖拽三段式：按下 / 移动 / 松开，坐标为屏幕绝对坐标。
  dragStart: (x: number, y: number) => ipcRenderer.send('drag-start', { x, y }),
  dragMove:  (x: number, y: number) => ipcRenderer.send('drag-move',  { x, y }),
  dragEnd:   () => ipcRenderer.send('drag-end'),

  // 读取初始配置（静音等）。
  getConfig: (): Promise<{ muted: boolean }> => ipcRenderer.invoke('get-config'),

  // 主进程 → 渲染进程 的事件订阅。
  onMute:       (cb: (muted: boolean) => void)  => ipcRenderer.on('mute', (_e, v) => cb(v)),
  onVisibility: (cb: (visible: boolean) => void) => ipcRenderer.on('visibility', (_e, v) => cb(v)),
});
