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

  // Universal platform support (no more per-platform gating)
  assertIncludes(parser, "'--impersonate', 'chrome'", 'global browser impersonation');
  assertIncludes(parser, "'--no-update'", 'version update suppress');
  assertIncludes(parser, 'getCookieFallbacks', 'cookie fallback chain');
  assertIncludes(parser, "return ['chrome', 'edge', 'firefox', undefined]", 'universal cookie fallback');
  assertIncludes(parser, 'execYtDlpWithCookieFallbacks', 'yt-dlp fallback runner');
  assertIncludes(parser, 'spawnYtDlpDownload', 'yt-dlp download runner');
  assertIncludes(parser, 'hasAudioStream', 'post-download audio validation');
  assertIncludes(parser, 'DEFAULT_MEDIA_FORMAT_ID', 'media default format');
  assertIncludes(parser, 'DEFAULT_VIDEO_FORMAT_ID', 'video default format');
  assertIncludes(parser, 'DEFAULT_AUDIO_FORMAT_ID', 'audio default format (music platforms)');
  assertIncludes(parser, 'downloadDefaultMedia', 'photo download path');
  assertIncludes(parser, 'downloadAudio', 'audio download path (music platforms)');
  assertIncludes(parser, 'buildFormatSelector', 'universal format selector');
  assertIncludes(parser, 'best*[vcodec!=none][acodec!=none]', 'combined audio-video fallback');
  assertIncludes(parser, 'bestaudio/bestaudio*[abr>0]/bestaudio[acodec!=none]/best', 'audio-only fallback');
  assertIncludes(parser, '--extract-audio', 'music extraction flag');
  assertIncludes(parser, '--dump-single-json', 'yt-dlp json dump');
  assertIncludes(parser, 'formatYtdlpError', 'yt-dlp error formatting');

  // DownloadBar: open matching
  const downloadBar = read('src/renderer/components/DownloadBar.tsx');
  assertIncludes(downloadBar, '// Any http/https URL that isn', 'DownloadBar open video matching');
  assertIncludes(downloadBar, "return true", 'DownloadBar fallthrough to parse');

  console.log('[PASS] TikTok / universal video regression checks passed.');
} catch (err) {
  console.error('[FAIL] TikTok / universal video regression checks failed.');
  console.error(err.message);
  process.exit(1);
}
