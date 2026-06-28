import path from "path";
import fs from "fs";
import initSqlJs, { Database as SqlJsDatabase } from "sql.js";

interface CookieEntry {
  name: string;
  value: string;
  domain: string;
}

export type BrowserType = "chrome" | "edge";

let sqlWasmReady = false;
let sqlJsLib: Awaited<ReturnType<typeof initSqlJs>> | null = null;

async function ensureSqlWasm(): Promise<void> {
  if (sqlWasmReady) return;
  const wasmPath = require.resolve("sql.js/dist/sql-wasm.wasm");
  sqlJsLib = await initSqlJs({ locateFile: () => wasmPath });
  sqlWasmReady = true;
}

export class CookieExtractor {
  private getCookieDbPath(browser: BrowserType): string {
    const localAppData = process.env.LOCALAPPDATA || "";
    if (!localAppData) {
      throw new Error("LOCALAPPDATA environment variable not set");
    }

    const browserPaths: Record<BrowserType, string> = {
      chrome: path.join(localAppData, "Google", "Chrome", "User Data", "Default", "Network", "Cookies"),
      edge: path.join(localAppData, "Microsoft", "Edge", "User Data", "Default", "Network", "Cookies"),
    };

    return browserPaths[browser];
  }

  async extract(browser: BrowserType, domainFilter?: string): Promise<CookieEntry[]> {
    const dbPath = this.getCookieDbPath(browser);

    if (!fs.existsSync(dbPath)) {
      return [];
    }

    const tmpPath = this.copyDb(dbPath);

    try {
      await ensureSqlWasm();
      return this.readCookies(tmpPath, domainFilter);
    } catch (err) {
      console.error("[CookieExtractor] sql.js failed:", err);
      return [];
    } finally {
      try { fs.unlinkSync(tmpPath); } catch { /* cleanup */ }
    }
  }

  private readCookies(dbPath: string, domainFilter?: string): CookieEntry[] {
    const buffer = fs.readFileSync(dbPath);
    if (!sqlJsLib) throw new Error("sql.js not initialized");
    const db: SqlJsDatabase = new sqlJsLib.Database(new Uint8Array(buffer));
    const cookies: CookieEntry[] = [];

    try {
      if (domainFilter) {
        // Parameterized query to prevent SQL injection
        const stmt = db.prepare(
          "SELECT name, value, host_key FROM cookies WHERE host_key LIKE ?"
        );
        stmt.bind([`%${domainFilter}%`]);
        while (stmt.step()) {
          const row = stmt.getAsObject();
          cookies.push({
            name: String(row.name ?? ""),
            value: String(row.value ?? ""),
            domain: String(row.host_key ?? ""),
          });
        }
        stmt.free();
      } else {
        const rows = db.exec("SELECT name, value, host_key FROM cookies");
        if (rows.length > 0) {
          const columns = rows[0].columns;
          const nameIdx = columns.indexOf("name");
          const valueIdx = columns.indexOf("value");
          const hostIdx = columns.indexOf("host_key");
          for (const row of rows[0].values) {
            cookies.push({
              name: String(row[nameIdx] ?? ""),
              value: String(row[valueIdx] ?? ""),
              domain: String(row[hostIdx] ?? ""),
            });
          }
        }
      }
    } finally {
      db.close();
    }

    return cookies;
  }

  formatAsHeader(cookies: CookieEntry[]): string {
    return cookies
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");
  }

  private copyDb(dbPath: string): string {
    const tmpDir = path.join(process.env.TEMP || "/tmp", "nsp-cookie-tmp");
    if (!fs.existsSync(tmpDir)) {
      fs.mkdirSync(tmpDir, { recursive: true });
    }
    const tmpPath = path.join(tmpDir, `cookies-${Date.now()}.db`);
    fs.copyFileSync(dbPath, tmpPath);
    return tmpPath;
  }
}
