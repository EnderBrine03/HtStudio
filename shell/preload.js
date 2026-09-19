const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  config: () => ipcRenderer.invoke('config'),
  download: () => ipcRenderer.invoke('download'),
  play: () => ipcRenderer.invoke('play'),
  win: (a) => ipcRenderer.send('win', a),
  onProgress: (cb) => ipcRenderer.on('progress', (_, d) => cb(d)),
  onState: (cb) => ipcRenderer.on('state', (_, s) => cb(s))
});
