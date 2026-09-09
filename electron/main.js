// ChipNest 桌面壳：内置启动 FastAPI 后端，就绪后开窗加载应用。
// 运行要求：Node 18+；开发用 CHIPNEST_DEV=1 指向 vite dev server。
// 打包产物（electron-builder）不含 Python——双击免 Python 版需要后续
// PyInstaller 把后端打成 exe（下方 spawn 分支预留：见 resolvePython）。
'use strict';

const { app, BrowserWindow } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

const BACKEND_DIR = path.join(__dirname, '..', 'backend');
const BACKEND_PORT = 8765;
const DEV_URL = 'http://127.0.0.1:5173';
const PROD_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const IS_DEV = process.env.CHIPNEST_DEV === '1';

let backendProc = null;
let mainWindow = null;
let quitting = false;

// ---------- 单实例锁 ----------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// ---------- Python 探测（预留 PyInstaller exe 分支） ----------
function resolvePython() {
  const candidates = [];
  const venvPy = path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe');
  candidates.push(venvPy); // 1) 仓库内虚拟环境（开发/便携运行）
  candidates.push('python'); // 2) PATH 上的 python
  candidates.push('py'); // 3) Windows py launcher
  return candidates;
}

// ---------- 后端进程 ----------
function backendRuntimeEnv() {
  const env = { ...process.env };
  // 打包/便携运行时把数据与日志重定向到 userData（Program Files 不可写）
  env.CHIPNEST_DB = path.join(app.getPath('userData'), 'chipnest.db');
  env.CHIPNEST_LOG_DIR = path.join(app.getPath('userData'), 'logs');
  if (app.isPackaged) {
    // 打包态：前端静态资源由后端 exe 托管（extraResources/frontend_dist）
    env.CHIPNEST_FRONTEND_DIST = path.join(process.resourcesPath, 'frontend_dist');
  }
  return env;
}

function startBackend() {
  const logDir = app.isPackaged
    ? path.join(app.getPath('userData'), 'logs')
    : path.join(BACKEND_DIR, 'logs');
  try { fs.mkdirSync(logDir, { recursive: true }); } catch { /* 忽略 */ }
  const logOut = fs.openSync(path.join(logDir, 'electron_backend.out.log'), 'a');
  const logErr = fs.openSync(path.join(logDir, 'electron_backend.err.log'), 'a');

  const env = backendRuntimeEnv();

  let command;
  let args = [];
  let cwd = undefined;
  if (app.isPackaged) {
    // 免 Python 模式：直接跑 PyInstaller 后端 exe（extraResources/backend/）
    command = path.join(process.resourcesPath, 'backend', 'chipnest-backend.exe');
  } else {
    const python = resolvePython().shift();
    command = python;
    args = ['-m', 'uvicorn', 'app.main:app',
            '--host', '127.0.0.1', '--port', String(BACKEND_PORT)];
    cwd = BACKEND_DIR;
  }

  // windowsHide: true 严禁黑框；stdio 指向文件日志
  backendProc = spawn(command, args, {
    cwd, env,
    windowsHide: true,
    stdio: ['ignore', logOut, logErr],
  });
  backendProc.on('error', (err) => {
    console.error('[chipnest] 后端启动失败：', err.message,
                  '（打包版请确认 resources/backend/chipnest-backend.exe 存在；',
                  '开发版请确认 backend/.venv 已安装依赖）');
  });
  backendProc.on('exit', (code) => {
    console.error('[chipnest] 后端进程退出 code=', code);
    if (!quitting) app.exit(1);
  });
}

// ---------- 健康轮询 ----------
function waitBackend(timeoutMs, intervalMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(
        { host: '127.0.0.1', port: BACKEND_PORT, path: '/api/v1/health' },
        (res) => {
          res.resume();
          resolve(res.statusCode === 200);
        },
      );
      req.on('error', () => {
        if (Date.now() > deadline) { reject(new Error('后端就绪超时')); return; }
        setTimeout(tick, intervalMs);
      });
    };
    tick();
  });
}

// ---------- 窗口 ----------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 1080,
    minHeight: 720,
    autoHideMenuBar: true,
    backgroundColor: '#1f1c19',
    title: 'ChipNest · 智能元件管家',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadURL(IS_DEV ? DEV_URL : PROD_URL);
  // 冒烟模式：加载完成后自动退出（CI/自检用，弹窗仅一闪而过）
  if (process.env.CHIPNEST_SMOKE === '1') {
    mainWindow.webContents.on('did-finish-load', async () => {
      console.log('[chipnest-smoke] 页面加载成功，探测数据接口…');
      const probe = await mainWindow.webContents
        .executeJavaScript(
          "Promise.all(['/api/v1/layout','/api/v1/components','/api/v1/system/status']" +
          ".map(p => fetch(p).then(r => r.status).catch(() => 0)))",
        )
        .catch(() => [0, 0, 0]);
      console.log('[chipnest-smoke] probe =', JSON.stringify(probe));
      if (probe.length === 3 && probe.every((s) => s === 200)) {
        console.log('[chipnest-smoke] 数据接口全部 200，冒烟通过');
        setTimeout(() => app.quit(), 600);
      } else {
        console.error('[chipnest-smoke] 数据接口异常，冒烟失败');
        app.exit(3);
      }
    });
    mainWindow.webContents.on('did-fail-load', (_e, code, desc) => {
      console.error('[chipnest-smoke] 页面加载失败', code, desc);
      app.exit(2);
    });
  }
  mainWindow.on('closed', () => { mainWindow = null; });
}

// ---------- 生命周期 ----------
app.whenReady().then(async () => {
  startBackend();
  try {
    await waitBackend(30000, 400);
    createWindow();
  } catch (err) {
    console.error('[chipnest]', err.message);
    app.exit(1);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// 退出前杀后端进程树（Windows：taskkill /T /F，含 uvicorn 子进程）
function killBackendTree() {
  if (!backendProc || backendProc.pid === undefined) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(backendProc.pid), '/T', '/F'],
            { windowsHide: true, stdio: 'ignore' });
    } else {
      backendProc.kill('SIGTERM');
    }
  } catch { /* 进程已消失则忽略 */ }
}

app.on('before-quit', () => {
  quitting = true;
  killBackendTree();
});
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});