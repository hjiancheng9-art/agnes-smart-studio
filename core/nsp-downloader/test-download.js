const https = require('https');

const url = 'https://cableav.video/info-206429.html';

console.log('Fetching page:', url);
https.get(url, {
  headers: {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
  }
}, (resp) => {
  let data = '';
  resp.on('data', (chunk) => data += chunk);
  resp.on('end', () => {
    console.log('\n=== Page fetched successfully ===\n');

    // Look for Playerjs configuration
    const playerjsMatch = data.match(/var player = new Playerjs\(\{([^}]+)\}\);/);
    if (playerjsMatch) {
      console.log('✓ Found Playerjs configuration');
      console.log('Raw config:', playerjsMatch[1]);

      try {
        const config = JSON.parse('{' + playerjsMatch[1] + '}');
        console.log('\n✓ Parsed configuration:');
        console.log('  - file:', config.file);
        console.log('  - width:', config.width);
        console.log('  - height:', config.height);

        if (config.file) {
          console.log('\n=== VIDEO URL READY ===');
          console.log(config.file);
          console.log('========================\n');

          // Test direct download
          console.log('\nTesting direct download of video...');
          const videoUrl = config.file;
          https.get(videoUrl, {
            headers: {
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
              'Referer': url
            }
          }, (videoResp) => {
            console.log('Video response:', videoResp.statusCode, videoResp.headers['content-type']);

            if (videoResp.statusCode === 200) {
              console.log('\n✓ Video URL is accessible!');
              console.log('Download URL:', videoUrl);
            } else {
              console.log('\n✗ Video URL returned non-200 status');
            }
          }).on('error', (err) => {
            console.error('Video download test failed:', err.message);
          });
        }
      } catch (e) {
        console.error('✗ Failed to parse Playerjs config:', e);
      }
    } else {
      console.log('✗ No Playerjs configuration found');
      console.log('\nLooking for alternative video patterns...');

      // Look for other patterns
      const mp4Match = data.match(/https?:\/\/[^\s"\'<>]+\.mp4/);
      if (mp4Match) {
        console.log('✓ Found MP4 URL:', mp4Match[0]);
      }
    }

    console.log('\n=== Extraction complete ===');
  });
}).on('error', (err) => {
  console.error('✗ Page fetch failed:', err.message);
  console.error(err.stack);
});
