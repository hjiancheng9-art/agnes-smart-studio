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
  const parser = read('src/main/video-parser.ts');

  // Universal platform support — no per-platform URL detection needed
  assertIncludes(parser, 'getRefererForUrl', 'universal referer derivation');
  assertIncludes(parser, 'getCookieFallbacks', 'universal cookie fallback');
  assertIncludes(parser, 'getCommonYtdlpArgs', 'shared yt-dlp args');
  assertIncludes(parser, 'DEFAULT_AUDIO_FORMAT_ID', 'audio format selector');
  assertIncludes(parser, 'downloadAudio', 'audio download function');
  assertIncludes(parser, '--extract-audio', 'music extraction');
  assertIncludes(parser, 'buildDownloadAttempts', 'download retry chain');
  assertIncludes(parser, 'hasAudioStream', 'audio validation');
  assertIncludes(parser, 'bestaudio/bestaudio*[abr>0]', 'audio quality fallback');

  // DownloadBar: open video URL detection
  const downloadBar = read('src/renderer/components/DownloadBar.tsx');
  assertIncludes(downloadBar, '// Any http/https URL that isn', 'open video matching comment');

  console.log('[PASS] Douyin / universal video regression checks passed.');
} catch (err) {
  console.error('[FAIL] Douyin / universal video regression checks failed.');
  console.error(err.message);
  process.exit(1);
}
