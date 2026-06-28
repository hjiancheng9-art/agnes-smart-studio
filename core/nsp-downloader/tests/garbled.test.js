// Test: verify no garbled chars exist in the project
const { execSync } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'scripts', 'scan-garbled.js');

try {
  execSync(`node "${scriptPath}"`, {
    cwd: path.join(__dirname, '..'),
    encoding: 'utf8',
  });
  console.log('[PASS] Garbled character scan passed.');
} catch (err) {
  console.error('[FAIL] Garbled characters found.');
  process.exit(1);
}
