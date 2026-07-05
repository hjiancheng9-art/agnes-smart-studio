const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

function assertIncludes(content, needle, label) {
  if (!content.includes(needle)) {
    throw new Error(`${label} is missing: ${needle}`);
  }
}

try {
  const main = read('src/main/index.ts');
  const ipc = read('src/main/ipc-handlers.ts');
  const clipboard = read('src/main/clipboard-monitor.ts');
  const manifest = read('extension/manifest.json');

  assertIncludes(main, 'isAria2SupportedUrl', 'HTTP bridge URL validation');
  assertIncludes(main, 'ed2k', 'HTTP bridge magnet/ed2k support');
  assertIncludes(ipc, 'isSupportedDownloadUrl', 'IPC URL validation');
  assertIncludes(ipc, 'ed2k', 'IPC magnet/ed2k support');
  assertIncludes(clipboard, 'thunder', 'clipboard thunder support');
  assertIncludes(clipboard, "Buffer.from(encoded, 'base64')", 'clipboard thunder normalization');
  assertIncludes(manifest, '"contextMenus"', 'context menu permission');
  assertIncludes(manifest, '"webRequest"', 'webRequest permission');

  console.log('[PASS] Download interception regression checks passed.');
} catch (err) {
  console.error('[FAIL] Download interception regression checks failed.');
  console.error(err.message);
  process.exit(1);
}
