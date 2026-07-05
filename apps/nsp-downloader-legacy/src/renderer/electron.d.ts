// Extend React CSSProperties with Electron-specific CSS properties
// (e.g. -webkit-app-region used by frameless BrowserWindow).

import 'react';

declare module 'react' {
  interface CSSProperties {
    WebkitAppRegion?: string;
  }
}
