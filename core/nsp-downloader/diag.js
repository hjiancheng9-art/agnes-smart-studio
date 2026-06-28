
// === NSP Diagnostic - 在 cableav.video 页面控制台运行 ===
(function() {
  var results = {};
  
  // 1. 检查 page-hook 是否被注入
  results.pageHookInjected = typeof window.__nsp_page_hook !== 'undefined';
  
  // 2. 直接从 HTML 搜 m3u8
  var html = document.documentElement.outerHTML;
  var re = /https?:\/\/[^"'\s<>]+\.(?:m3u8|mp4)[^"'\s<>]*/gi;
  var rawMatches = [];
  var m;
  while ((m = re.exec(html)) !== null) {
    rawMatches.push(m[0]);
  }
  results.rawHTMLMatches = rawMatches;
  
  // 3. 检查 iframe
  var iframes = document.querySelectorAll('iframe');
  results.iframeCount = iframes.length;
  results.iframeSrcs = [];
  for (var i = 0; i < iframes.length; i++) {
    results.iframeSrcs.push(iframes[i].src);
  }
  
  // 4. 检查 content.js 是否在运行 (通过检查 fetch hook)
  results.fetchHooked = window.fetch.toString().indexOf('nsp') > -1 || window.fetch.toString().indexOf('[native code]') === -1;
  
  // 5. 手动发送 postMessage 模拟 page-hook 报告
  var testUrl = rawMatches[0];
  if (testUrl) {
    window.postMessage({
      source: 'nsp-page-hook',
      url: testUrl,
      label: 'M3U8'
    }, '*');
    results.testPostMessageSent = true;
  }
  
  console.log('=== NSP Diagnostic ===');
  console.log(JSON.stringify(results, null, 2));
  return results;
})();
