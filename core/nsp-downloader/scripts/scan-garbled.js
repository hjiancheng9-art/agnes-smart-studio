const fs = require('fs');
const path = require('path');

const GARBLED_CHARS = ['鍥', '閸', '鐢', '绱', '鏉', '悆', '殑', '掑', '曠'];

const SOURCE_DIRS = ['src', 'locales', 'extension'];
const SKIP_DIRS = ['node_modules', 'dist', '.git'];
const EXTENSIONS = ['.ts', '.tsx', '.js', '.json', '.html', '.css', '.conf', '.md'];

function scanFile(filePath) {
  // Check for UTF-8 BOM (EF BB BF) first — policy requires UTF-8 without BOM.
  const buf = fs.readFileSync(filePath);
  if (buf.length >= 3 && buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF) {
    return [{ file: filePath, line: 1, char: 'BOM', context: 'UTF-8 BOM detected (EF BB BF)' }];
  }

  const content = buf.toString('utf8');
  const issues = [];

  for (const char of GARBLED_CHARS) {
    let idx = -1;
    while ((idx = content.indexOf(char, idx + 1)) !== -1) {
      const line = content.substring(0, idx).split('\n').length;
      const context = content.substring(Math.max(0, idx - 20), idx + 20);
      issues.push({ file: filePath, line, char, context: context.trim() });
    }
  }

  return issues;
}

function walkDir(dir) {
  const results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    if (SKIP_DIRS.some((d) => fullPath.includes(d))) continue;

    if (entry.isDirectory()) {
      results.push(...walkDir(fullPath));
    } else if (entry.isFile() && EXTENSIONS.some((ext) => entry.name.endsWith(ext))) {
      results.push(fullPath);
    }
  }

  return results;
}

function main() {
  const root = path.resolve(__dirname, '..');
  const allIssues = [];

  for (const dir of SOURCE_DIRS) {
    const fullDir = path.join(root, dir);
    if (!fs.existsSync(fullDir)) continue;

    const files = walkDir(fullDir);
    for (const file of files) {
      const issues = scanFile(file);
      allIssues.push(...issues);
    }
  }

  if (allIssues.length > 0) {
    console.error(`\n[FAIL] Found ${allIssues.length} garbled character(s):\n`);
    for (const issue of allIssues) {
      console.error(`  ${issue.file}:${issue.line}  "${issue.char}"  context: ...${issue.context}...`);
    }
    console.error('\nFix all encoding issues before committing.\n');
    process.exit(1);
  }

  console.log('[PASS] No garbled characters detected.');
  process.exit(0);
}

main();
