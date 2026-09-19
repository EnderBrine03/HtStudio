// HtStudio shell: Python bootstrapper tarafından
//   electron.exe <shell-klasörü> --project=<açılmış-proje-klasörü>
// şeklinde başlatılır. ZIP'i Python açtığı için burada ek paket gerekmez.
const { app, BrowserWindow, ipcMain, net, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');

const arg = (n) => {
  const a = process.argv.find((x) => x.startsWith('--' + n + '='));
  return a ? a.slice(n.length + 3) : null;
};

const projectArg = arg('project');
const payloadDir = projectArg && fs.existsSync(projectArg) ? projectArg : null;
const payloadErr = projectArg && !payloadDir ? 'Proje klasörü bulunamadı.' : null;
const payloadHash = payloadDir ? path.basename(payloadDir).replace(/^htstudio-/, '') : '';

const dataDir = () => path.join(app.getPath('userData'), 'app');
const bases = () => [payloadDir, dataDir(), __dirname].filter(Boolean);

const DEFAULTS = {
  id: '', name: 'HtStudio App', version: '1.0.0', developer: '', description: '',
  target: { type: 'html', path: 'app/index.html' },
  window: { width: 1100, height: 700, fullscreen: false, resizable: true },
  gui: { shape: 'horizontal', accent: '#3b6bff', background: { color: '#0d0d1a', image: '', video: '' } },
  download: { url: '', file: '', force: false }
};

function find(rel, list) {
  if (!rel) return null;
  if (path.isAbsolute(rel)) return fs.existsSync(rel) ? rel : null;
  for (const b of list || bases()) {
    const p = path.join(b, rel);
    // Proje klasörünün dışına çıkan yolları reddet
    if (path.relative(b, p).startsWith('..')) continue;
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function loadConfig() {
  let user = {};
  const file = find('launcher.json', [payloadDir, __dirname].filter(Boolean));
  try { if (file) user = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { console.error(e); }
  const c = { ...DEFAULTS, ...user };
  for (const k of ['target', 'window', 'gui', 'download']) c[k] = { ...DEFAULTS[k], ...(user[k] || {}) };
  c.gui.background = { ...DEFAULTS.gui.background, ...((user.gui || {}).background || {}) };
  // Her uygulamanın localStorage/IndexedDB verisi ayrı tutulur (Package Name)
  c.id = String(user.id || payloadHash || 'dev').replace(/[^a-zA-Z0-9._-]/g, '_');
  return c;
}

let cfg, launcher, appWin;
const send = (ch, data) => launcher && !launcher.isDestroyed() && launcher.webContents.send(ch, data);

function createLauncher() {
  const vertical = cfg.gui.shape === 'vertical';
  launcher = new BrowserWindow({
    width: vertical ? 420 : 1000, height: vertical ? 760 : 620,
    frame: false, resizable: false, show: false, backgroundColor: cfg.gui.background.color,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true }
  });
  launcher.once('ready-to-show', () => launcher.show());
  launcher.loadFile('launcher.html');
}

function openWindow(url) {
  const w = cfg.window;
  appWin = new BrowserWindow({
    width: w.width, height: w.height, fullscreen: !!w.fullscreen, resizable: w.resizable !== false,
    autoHideMenuBar: true, title: cfg.name,
    webPreferences: { contextIsolation: true, partition: 'persist:' + cfg.id }
  });
  appWin.webContents.setWindowOpenHandler(() => ({ action: 'allow' }));
  appWin.loadURL(url);
  appWin.on('closed', () => { appWin = null; send('state', 'idle'); });
  send('state', 'running');
}

function runExe(p) {
  try {
    const child = spawn(p, [], { cwd: path.dirname(p), detached: true, stdio: 'ignore' });
    child.on('error', () => shell.openPath(p)); // UAC isteyenler için
    child.unref();
    return { ok: true };
  } catch { shell.openPath(p); return { ok: true }; }
}

ipcMain.handle('config', () => {
  const c = JSON.parse(JSON.stringify(cfg));
  const bg = c.gui.background;
  for (const k of ['image', 'video']) {
    const p = find(bg[k], [payloadDir, __dirname].filter(Boolean));
    bg[k] = p ? pathToFileURL(p).href : '';
  }
  return c;
});

ipcMain.handle('download', () => new Promise((resolve) => {
  if (payloadErr) return resolve({ ok: false, error: payloadErr });
  const d = cfg.download;
  if (!d.url) return resolve({ ok: true, skipped: true });
  let name = d.file;
  try { name = name || path.basename(new URL(d.url).pathname); } catch {}
  if (!name) return resolve({ ok: false, error: 'download.file belirtilmeli.' });
  const dest = path.join(dataDir(), path.basename(name));
  if (fs.existsSync(dest) && !d.force) return resolve({ ok: true, cached: true });
  fs.mkdirSync(dataDir(), { recursive: true });
  const out = fs.createWriteStream(dest + '.part');
  const req = net.request(d.url);
  req.on('response', (r) => {
    if (r.statusCode >= 400) return resolve({ ok: false, error: 'İndirme hatası (' + r.statusCode + ')' });
    const total = parseInt([].concat(r.headers['content-length'] || 0)[0], 10) || 0;
    let got = 0;
    r.on('data', (c) => { got += c.length; out.write(c); send('progress', { got, total }); });
    r.on('end', () => out.end(() => { fs.renameSync(dest + '.part', dest); resolve({ ok: true }); }));
    r.on('error', (e) => resolve({ ok: false, error: e.message }));
  });
  req.on('error', (e) => resolve({ ok: false, error: e.message }));
  req.end();
}));

ipcMain.handle('play', () => {
  const t = cfg.target;
  if (t.type === 'url') { openWindow(t.path); return { ok: true }; }
  const p = find(t.path);
  if (!p) return { ok: false, error: 'Dosya bulunamadı: ' + t.path };
  if (t.type === 'exe') return runExe(p);
  openWindow(pathToFileURL(p).href);
  return { ok: true };
});

ipcMain.on('win', (_, action) => {
  if (action === 'min') launcher.minimize();
  if (action === 'close') app.quit();
});

app.whenReady().then(() => { cfg = loadConfig(); createLauncher(); });
app.on('window-all-closed', () => app.quit());
