import { contextBridge, ipcRenderer } from 'electron';

const api = {
  download: {
    getActive: () => ipcRenderer.invoke('download:getActive'),
    getWaiting: (offset: number, num: number) => ipcRenderer.invoke('download:getWaiting', offset, num),
  },
  float: {
    showMain: () => ipcRenderer.invoke('float:showMain'),
    hide: () => ipcRenderer.invoke('float:hide'),
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
