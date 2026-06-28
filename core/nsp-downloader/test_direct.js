
// === 直接测试：在 cableav 页面控制台粘贴运行 ===
(async function() {
  console.log('=== NSP Direct Test ===');
  
  // 1. 直接从 HTML 搜 m3u8
  var html = document.documentElement.outerHTML;
  var re = /https?:\/\/[^"'\s<>]+\.(?:m3u8|mp4)[^"'\s<>]*/gi;
  var matches = [];
  var m;
  while ((m = re.exec(html)) !== null) matches.push(m[0]);
  console.log('HTML media URLs:', matches);
  
  // 2. 检查 iframe
  var iframes = document.querySelectorAll('iframe');
  console.log('Iframes:', iframes.length);
  for (var i = 0; i < iframes.length; i++) {
    console.log('  iframe[' + i + '] src:', iframes[i].src);
  }
  
  // 3. 尝试写入 chrome.storage.local
  if (matches[0]) {
    try {
      await chrome.storage.local.set({ 'nsp_test_url': matches[0] });
      var read = await chrome.storage.local.get('nsp_test_url');
      console.log('storage write/read test:', read.nsp_test_url ? 'OK' : 'FAIL');
    } catch(e) {
      console.log('storage error:', e.message);
    }
  }
  
  // 4. 检查 chrome.runtime.sendMessage 是否可用
  try {
    chrome.runtime.sendMessage({ type: 'ping' }, function(resp) {
      console.log('sendMessage response:', resp);
    });
    console.log('sendMessage sent (async)');
  } catch(e) {
    console.log('sendMessage error:', e.message);
  }
  
  console.log('=== Test Complete ===');
})();
