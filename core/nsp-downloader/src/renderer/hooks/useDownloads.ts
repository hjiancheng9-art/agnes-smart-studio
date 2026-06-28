import { create } from 'zustand';

interface DownloadTask {
  gid: string;
  status: string;
  totalLength: string;
  completedLength: string;
  downloadSpeed: string;
  uploadSpeed: string;
  files?: Array<{ path: string; length: string }>;
  errorMessage?: string;
  errorCode?: string;
}

interface DownloadStore {
  tasks: DownloadTask[];
  refresh: () => Promise<void>;
}

export const useDownloadStore = create<DownloadStore>((set) => ({
  tasks: [],
  refresh: async () => {
    try {
      const api = (window as any).electronAPI;
      if (!api) return;

      const [active, waiting, stopped] = await Promise.all([
        api.download.getActive(),
        api.download.getWaiting(0, 100),
        api.download.getStopped(0, 100),
      ]);

      const all: DownloadTask[] = [
        ...(active || []),
        ...(waiting || []),
        ...(stopped || []),
      ];

      set({ tasks: all });
    } catch (err) {
      // aria2 might not be ready yet
    }
  },
}));
