// 测试下载器下载视频功能

const https = require('https');
const fs = require('fs');
const path = require('path');

const videoUrl = 'https://img1.128100.xyz/upload/thumbs/2023/07/12/hSnQbF90tY9zE0XpfCkMUtA5Y6uJGeB0/preview.mp4';
const downloadDir = path.join(__dirname, 'downloads');
const outputFile = path.join(downloadDir, 'test-video.mp4');

// 确保目录存在
if (!fs.existsSync(downloadDir)) {
    fs.mkdirSync(downloadDir, { recursive: true });
}

console.log('=== NSP 下载器视频下载测试 ===\n');
console.log('视频URL:', videoUrl);
console.log('输出文件:', outputFile);
console.log('');

// 下载函数
function downloadVideo(url, output) {
    return new Promise((resolve, reject) => {
        const req = https.get(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
                'Referer': 'https://cableav.video/info-206429.html'
            }
        }, (resp) => {
            console.log('响应状态:', resp.statusCode);
            console.log('Content-Type:', resp.headers['content-type'] || 'N/A');
            console.log('Content-Length:', resp.headers['content-length'] || 'N/A');

            let data = [];
            let downloaded = 0;
            const total = parseInt(resp.headers['content-length'] || '0');

            resp.on('data', (chunk) => {
                data.push(chunk);
                downloaded += chunk.length;
                if (total > 0) {
                    const progress = (downloaded / total) * 100;
                    process.stdout.write(`\r进度: ${progress.toFixed(1)}% (${downloaded}/${total} bytes)`);
                }
            });

            resp.on('end', () => {
                const buffer = Buffer.concat(data);
                fs.writeFileSync(output, buffer);

                console.log('\n\n[OK] 下载完成!');
                console.log('文件:', output);
                console.log('大小:', buffer.length, 'bytes');
                console.log('验证:', buffer.length > 0 ? '✓ 有效' : '✗ 无效');
                resolve(buffer.length);
            });

            resp.on('error', (err) => {
                console.error('\n[ERROR] 下载失败:', err.message);
                reject(err);
            });
        });

        req.on('error', (err) => {
            console.error('\n[ERROR] 请求失败:', err.message);
            reject(err);
        });

        req.setTimeout(60000, () => {
            req.destroy();
            reject(new Error('下载超时 (60秒)'));
        });
    });
}

// 执行下载
downloadVideo(videoUrl, outputFile)
    .then(size => {
        console.log('\n=== 测试成功 ===');
        console.log(`视频已成功下载，大小: ${size} 字节`);
        process.exit(0);
    })
    .catch(error => {
        console.log('\n=== 测试失败 ===');
        console.log('错误:', error.message);
        console.log('\n建议:');
        console.log('1. 检查网络连接');
        console.log('2. 确认URL是否有效');
        console.log('3. 尝试使用其他下载工具测试网络');
        console.log('4. 检查防火墙设置');
        process.exit(1);
    });
