/**
 * 主进程：负责创建透明置顶窗口、系统托盘、配置持久化，以及与渲染进程的 IPC 通信。
 * 设计目标：低占用、鼠标穿透可靠、退出/隐藏行为清晰。
 */
import { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } from 'electron';
import * as path from 'path';
import * as fs from 'fs';

// ---------- 配置持久化 ----------
// 配置存放在用户数据目录（%APPDATA%/宝贝桌面宠物/pet-config.json），避免写入安装目录导致权限问题。
interface PetConfig {
  x: number | null;      // 上次窗口左上角 X（null=居中偏下默认位置）
  y: number | null;      // 上次窗口左上角 Y
  muted: boolean;        // 是否静音
}
const CONFIG_PATH = path.join(app.getPath('userData'), 'pet-config.json');
const DEFAULT_CONFIG: PetConfig = { x: null, y: null, muted: false };

function loadConfig(): PetConfig {
  try {
    const raw = fs.readFileSync(CONFIG_PATH, 'utf-8');
    return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_CONFIG };  // 首次启动或文件损坏时回退默认值
  }
}
function saveConfig(cfg: PetConfig): void {
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf-8');
  } catch (e) {
    console.error('保存配置失败：', e);
  }
}

let config: PetConfig = DEFAULT_CONFIG;
let win: BrowserWindow | null = null;
let tray: Tray | null = null;

// 窗口尺寸（角色画布）。透明窗口本身比角色略大，留出爱心粒子飘出的空间。
const WIN_W = 320;
const WIN_H = 360;

// ---------- 创建主窗口 ----------
function createWindow(): void {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;

  // 计算初始位置：优先用上次保存的，否则默认放到屏幕右下角上方一点。
  const startX = config.x ?? sw - WIN_W - 40;
  const startY = config.y ?? sh - WIN_H - 10;

  win = new BrowserWindow({
    width: WIN_W,
    height: WIN_H,
    x: startX,
    y: startY,
    transparent: true,      // 透明背景
    frame: false,           // 无边框
    resizable: false,
    hasShadow: false,       // 关闭窗口阴影，否则透明区会有灰边
    alwaysOnTop: true,      // 始终置顶
    skipTaskbar: true,      // 不在任务栏显示（靠托盘管理）
    fullscreenable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,   // 安全：隔离渲染上下文
      nodeIntegration: false,
    },
  });

  // 置顶层级设为悬浮窗级别，尽量压过大多数应用。
  win.setAlwaysOnTop(true, 'screen-saver');
  // 在所有工作区可见（多桌面场景）。
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  win.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));

  // 关键：默认让整个窗口鼠标穿透，且 forward:true 使 mousemove 仍能传给渲染进程做命中检测。
  win.setIgnoreMouseEvents(true, { forward: true });

  // 窗口移动后记录位置（防抖，避免频繁写盘）。
  let moveTimer: NodeJS.Timeout | null = null;
  win.on('move', () => {
    if (!win) return;
    const [x, y] = win.getPosition();
    config.x = x; config.y = y;
    if (moveTimer) clearTimeout(moveTimer);
    moveTimer = setTimeout(() => saveConfig(config), 400);
  });

  // 内存优化：窗口隐藏时通知渲染层暂停渲染循环（离屏暂停）。
  win.on('hide', () => win?.webContents.send('visibility', false));
  win.on('show', () => win?.webContents.send('visibility', true));
}

// ---------- 系统托盘 ----------
function createTray(): void {
  // 用一个内置的简单图标（16x16 纯色圆点）避免依赖外部 ico；打包时可替换 build/icon.ico。
  const iconPath = path.join(__dirname, '..', 'renderer', 'tray.png');
  let img = nativeImage.createFromPath(iconPath);
  if (img.isEmpty()) {
    // 兜底：生成一个 1x1 占位，保证托盘能创建成功。
    img = nativeImage.createEmpty();
  }
  tray = new Tray(img);
  tray.setToolTip('宝贝桌面宠物');
  rebuildTrayMenu();

  // 左键点击托盘：快速显示/隐藏。
  tray.on('click', () => toggleVisible());
}

function rebuildTrayMenu(): void {
  if (!tray) return;
  const visible = win?.isVisible() ?? true;
  const menu = Menu.buildFromTemplate([
    {
      label: visible ? '隐藏角色' : '显示角色',
      click: () => toggleVisible(),
    },
    {
      label: '重置位置',
      click: () => resetPosition(),
    },
    {
      label: config.muted ? '开启音效' : '关闭音效',
      click: () => toggleMute(),
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => { app.quit(); },
    },
  ]);
  tray.setContextMenu(menu);
}

// ---------- 托盘动作 ----------
function toggleVisible(): void {
  if (!win) return;
  if (win.isVisible()) win.hide();
  else win.show();
  rebuildTrayMenu();
}

function resetPosition(): void {
  if (!win) return;
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  const x = sw - WIN_W - 40;
  const y = sh - WIN_H - 10;
  win.setPosition(x, y);
  config.x = x; config.y = y;
  saveConfig(config);
}

function toggleMute(): void {
  config.muted = !config.muted;
  saveConfig(config);
  win?.webContents.send('mute', config.muted);
  rebuildTrayMenu();
}

// ---------- IPC：渲染进程 → 主进程 ----------

// 命中检测结果：渲染进程判断鼠标是否落在角色不透明像素上，据此切换穿透。
ipcMain.on('set-interactive', (_e, interactive: boolean) => {
  if (!win) return;
  // interactive=true → 关闭穿透（可点击/拖拽）；false → 打开穿透（点桌面）。
  win.setIgnoreMouseEvents(!interactive, { forward: true });
});

// 拖拽窗口：渲染进程按住角色时上报位移，由主进程移动窗口（比 -webkit-app-region 更可控）。
let dragOffset: { dx: number; dy: number } | null = null;
ipcMain.on('drag-start', (_e, pos: { x: number; y: number }) => {
  if (!win) return;
  const [wx, wy] = win.getPosition();
  dragOffset = { dx: pos.x - wx, dy: pos.y - wy };
});
ipcMain.on('drag-move', (_e, pos: { x: number; y: number }) => {
  if (!win || !dragOffset) return;
  win.setPosition(Math.round(pos.x - dragOffset.dx), Math.round(pos.y - dragOffset.dy));
});
ipcMain.on('drag-end', () => { dragOffset = null; });

// 渲染进程查询初始配置（静音状态等）。
ipcMain.handle('get-config', () => ({ muted: config.muted }));

// ---------- 应用生命周期 ----------
// 单实例锁：避免重复启动多个宠物。
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => { win?.show(); });

  app.whenReady().then(() => {
    config = loadConfig();
    createWindow();
    createTray();
  });
}

// 所有窗口关闭不退出（托盘常驻），仅在托盘“退出”里显式 app.quit() 时结束。
// 我们的窗口只隐藏不关闭，正常情况下本事件不会触发；即便触发也不做任何事以保持常驻。
app.on('window-all-closed', () => {
  // 故意留空：不调用 app.quit()，让托盘继续存活。
});
