'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('chipnest', {
  chooseBackupDirectory: () => ipcRenderer.invoke('chipnest:backup-directory'),
});
