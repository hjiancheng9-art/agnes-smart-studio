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
  const downloadBar = read('src/renderer/components/DownloadBar.tsx');
  const background = read('extension/background.js');

  // Universal platform support — all platforms handled by yt-dlp natively
  assertIncludes(parser, 'getCookieFallbacks', 'universal cookie fallback chain');
  assertIncludes(parser, 'DEFAULT_MEDIA_FORMAT_ID', 'media default format');
  assertIncludes(parser, 'DEFAULT_VIDEO_FORMAT_ID', 'video default format');
  assertIncludes(parser, 'DEFAULT_AUDIO_FORMAT_ID', 'audio default format');
  assertIncludes(parser, 'downloadDefaultMedia', 'photo/media download path');
  assertIncludes(parser, 'downloadAudio', 'audio download path');
  assertIncludes(parser, 'buildFormatSelector', 'universal format selector');
  assertIncludes(parser, 'buildDownloadAttempts', 'download retry chain');
  assertIncludes(parser, 'hasAudioStream', 'audio validation');
  assertIncludes(parser, 'best*[vcodec!=none][acodec!=none]', 'video+audio combined fallback');
  assertIncludes(parser, 'bestaudio/bestaudio*[abr>0]/bestaudio[acodec!=none]/best', 'audio-only fallback');

  // DownloadBar: open video matching
  // DownloadBar: open video matching with expanded file exclusion list
  assertIncludes(downloadBar, 'safetensors|ckpt|pt|pth|onnx|gguf|ggml|tflite', 'AI model extensions excluded from yt-dlp');
  assertIncludes(downloadBar, 'whl|jar|war|dll|so|dylib', 'dev package extensions excluded from yt-dlp');

  // Extension background: platform candidate domains still present
  assertIncludes(background, 'xiaohongshu.com', 'Xiaohongshu extension candidate domain');
  assertIncludes(background, 'kuaishou.com', 'Kuaishou extension candidate domain');

  console.log('[PASS] Social video / universal platform regression checks passed.');
} catch (err) {
  console.error('[FAIL] Social video / universal platform regression checks failed.');
  console.error(err.message);
  process.exit(1);
}
