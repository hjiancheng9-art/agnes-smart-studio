const https = require('https');
const fs = require('fs');
const path = require('path');

const videoUrl = 'https://img1.128100.xyz/upload/thumbs/2023/07/12/hSnQbF90tY9zE0XpfCkMUtA5Y6uJGeB0/preview.mp4';
const outputDir = path.join(__dirname, 'downloads');
const outputFile = path.join(outputDir, 'final-download.mp4');

// 确保目录存在
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

console.log('=== NSP 下载器 - 最终下载测试 ===\n');
console.log('视频URL:', videoUrl);
console.log('输出文件:', outputFile);
console.log('');

let retryCount = 0;
const maxRetries = 5;

function downloadWithRetry(url, dest, attempt = 1) {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    console.log(`\n[尝试 ${attempt}/${maxRetries}] 开始下载...`);
    console.log(`开始时间: ${new Date().toLocaleTimeString()}`);

    const req = https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
        'Referer': 'https://cableav.video/info-206429.html',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Connection': 'keep-alive'
      },
      timeout: 180000,  // 3分钟超时
      rejectUnauthorized: false
    }, (resp) => {
      console.log(`响应状态: ${resp.statusCode}`);
      console.log(`Content-Type: ${resp.headers['content-type'] || 'N/A'}`);
      console.log(`Content-Length: ${resp.headers['content-length'] || 'N/A'}`);

      if (resp.statusCode !== 200 && resp.statusCode !== 206) {
        console.error(`[ERROR] HTTP ${resp.statusCode}`);
        if (attempt < maxRetries) {
          const delay = attempt * 5000;
          console.log(`等待${delay/1000}秒后重试...`);
          setTimeout(() => downloadWithRetry(url, dest, attempt + 1).then(resolve).catch(reject), delay);
        } else {
          reject(new Error(`HTTP ${resp.statusCode}`));
        }
        return;
      }

      const total = parseInt(resp.headers['content-length'] || '0', 10);
      let downloaded = 0;
      const chunks = [];
      const startTimeDownload = Date.now();

      resp.on('data', (chunk) => {
        chunks.push(chunk);
        downloaded += chunk.length;

        if (total > 0) {
          const progress = (downloaded / total) * 100;
          const elapsed = (Date.now() - startTimeDownload) / 1000;
          const speed = downloaded / 1024 / 1024 / elapsed;
          const remaining = total > 0 ? ((total - downloaded) / speed / 1024 / 1024).toFixed(0) : 'N/A';
          process.stdout.write(`\r进度: ${progress.toFixed(1)}% | ${downloaded}/${total} bytes | ${speed.toFixed(1)} MB/s | 剩余: ${remaining}s`);
        }
      });

      resp.on('end', () => {
        const buffer = Buffer.concat(chunks);
        fs.writeFileSync(dest, buffer);

        const elapsed = (Date.now() - startTime) / 1000;
        const finalSpeed = buffer.length / 1024 / 1024 / elapsed;

        console.log('\n\n[OK] 下载完成!');
        console.log('文件:', dest);
        console.log('大小:', buffer.length, 'bytes');
        console.log('耗时:', elapsed.toFixed(1), '秒');
        console.log('平均速度:', finalSpeed.toFixed(1), 'MB/s');
        console.log('验证:', buffer.length > 0 ? '✓ 有效' : '✗ 无效');

        if (buffer.length > 0) {
          console.log('文件头:', buffer.slice(0, 16).toString('hex'));
          console.log('文件尾:', buffer.slice(-16).toString('hex'));
        }

        resolve(buffer.length);
      });

      resp.on('error', (err) => {
        console.error('\n[ERROR] 响应错误:', err.message);
        if (attempt < maxRetries) {
          const delay = attempt * 5000;
          console.log(`等待${delay/1000}秒后重试...`);
          setTimeout(() => downloadWithRetry(url, dest, attempt + 1).then(resolve).catch(reject), delay);
        } else {
          reject(new Error(`响应错误: ${err.message}`));
        }
      });
    });

    req.on('error', (err) => {
      console.error('\n[ERROR] 请求错误:', err.message);
      if (attempt < maxRetries) {
        const delay = attempt * 5000;
        console.log(`等待${delay/1000}秒后重试...`);
        setTimeout(() => downloadWithRetry(url, dest, attempt + 1).then(resolve).catch(reject), delay);
      } else {
        reject(new Error(`请求错误: ${err.message}`));
      }
    });

    req.setTimeout(180000, () => {
      req.destroy();
      console.error('\n[ERROR] 下载超时 (180秒)');
      if (attempt < maxRetries) {
        const delay = attempt * 5000;
        console.log(`等待${delay/1000}秒后重试...`);
        setTimeout(() => downloadWithRetry(url, dest, attempt + 1).then(resolve).catch(reject), delay);
      } else {
        reject(new Error('下载超时'));
      }
    });
  });
}

console.log('开始下载...\n');
console.log('='.repeat(60));

downloadWithRetry(videoUrl, outputFile, 1)
  .then(size => {
    console.log('\n' + '='.repeat(60));
    console.log('=== 下载成功 ===');
    console.log(`视频已成功下载，大小: ${size} 字节`);
    console.log('='.repeat(60));
    process.exit(0);
  })
  .catch(error => {
    console.log('\n' + '='.repeat(60));
    console.log('=== 下载失败 ===');
    console.log('错误:', error.message);
    console.log('='.repeat(60));
    console.log('\n建议:');
    console.log('1. 检查网络连接');
    console.log('2. 尝试使用代理');
    console.log('3. 检查URL是否有效');
    console.log('4. 稍后重试');
    console.log('5. 检查防火墙设置');
    process.exit(1);
  });
