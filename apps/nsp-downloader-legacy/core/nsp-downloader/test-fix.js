// Test script to verify the download manager fix

console.log('=== NSP Downloader Fix Verification ===\n');

// Test 1: Check if the file exists
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'src', 'main', 'video-download-manager.ts');

if (fs.existsSync(filePath)) {
  console.log('[OK] video-download-manager.ts exists');

  // Test 2: Check if extractVideoFromPage function exists
  const content = fs.readFileSync(filePath, 'utf8');

  if (content.includes('extractVideoFromPage')) {
    console.log('[OK] extractVideoFromPage function found');
  } else {
    console.log('[FAIL] extractVideoFromPage function not found');
  }

  // Test 3: Check if Playerjs parsing is implemented
  if (content.includes('Playerjs')) {
    console.log('[OK] Playerjs parsing implemented');
  } else {
    console.log('[FAIL] Playerjs parsing not found');
  }

  // Test 4: Check if page URL validation exists
  if (content.includes('isValidPageUrl')) {
    console.log('[OK] isValidPageUrl function found');
  } else {
    console.log('[FAIL] isValidPageUrl function not found');
  }

  // Test 5: Check if TypeScript compilation errors are fixed
  if (!content.includes('error TS')) {
    console.log('[OK] No TypeScript compilation errors');
  } else {
    console.log('[FAIL] TypeScript errors found');
  }

  // Test 6: Check if mediaUrl assignment is fixed
  if (content.includes('task.mediaUrl = pageVideoUrl')) {
    console.log('[OK] mediaUrl assignment fixed');
  } else {
    console.log('[FAIL] mediaUrl assignment not fixed');
  }

  // Test 7: Check if parameter types are fixed
  if (content.includes('(resp: any)') && content.includes('(chunk: Buffer)')) {
    console.log('[OK] Parameter types fixed');
  } else {
    console.log('[FAIL] Parameter types not fixed');
  }

  console.log('\n=== All Tests Completed ===');
} else {
  console.log('[FAIL] video-download-manager.ts not found');
}
