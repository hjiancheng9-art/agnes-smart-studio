const https = require('https');
const fs = require('fs');
const path = require('path');

const ARIA2_VERSION = '1.37.0';
const ARIA2_URL = `https://github.com/aria2/aria2/releases/download/release-${ARIA2_VERSION}/aria2-${ARIA2_VERSION}-win-64bit-build1.zip`;

// Simplified: download via releases page
// For MVP, users manually download aria2c.exe and place it in resources/
console.log(`Please download aria2c from: ${ARIA2_URL}`);
console.log('Extract aria2c.exe to resources/aria2c.exe');
console.log('This script will auto-download in a future version.');
