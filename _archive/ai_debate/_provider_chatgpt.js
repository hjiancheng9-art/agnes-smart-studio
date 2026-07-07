(function () {
  function findPromptInput() {
    return document.querySelector('#prompt-textarea, textarea, [contenteditable="true"]');
  }
  async function fillPrompt(prompt) {
    const input = findPromptInput();
    if (!input) return false;
    input.focus();
    if (input.tagName === 'TEXTAREA') input.value = prompt;
    else input.textContent = prompt;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: prompt }));
    return true;
  }
  // Extract DALL-E generated image URLs from the conversation
  function extractGeneratedImages() {
    var images = [];
    var candidates = document.querySelectorAll(
      'img[alt*="Generated"], img[alt*="DALL"], img[alt*="image"], ' +
      'img[src*="oaidalleapiprodscus"], img[src*="files.oaiusercontent.com"], ' +
      'img[src*="openai.com"], article[data-testid] img, ' +
      'div[data-message-author-role="assistant"] img[src]'
    );
    candidates.forEach(function(img) {
      var src = img.src || img.getAttribute('data-src') || '';
      if (src && /https?:\/\//.test(src) && !/favicon|avatar|icon/i.test(src)) {
        images.push({ url: src, alt: img.alt || '', width: img.naturalWidth, height: img.naturalHeight });
      }
    });
    if (!images.length) {
      var assistantBlocks = document.querySelectorAll('[data-message-author-role="assistant"]');
      var last = assistantBlocks[assistantBlocks.length - 1];
      if (last) {
        last.querySelectorAll('img[src]').forEach(function(img) {
          var src = img.src;
          if (src && /https?:\/\//.test(src) && img.naturalWidth > 200) {
            images.push({ url: src, alt: img.alt || '', width: img.naturalWidth, height: img.naturalHeight });
          }
        });
      }
    }
    return images;
  }
  function guessDownloadName(images) {
    if (!images || !images.length) return '';
    var src = images[0].url || '';
    var m = src.match(/\/(img-[^/?]+\.(png|jpg|webp))/i);
    if (m) return m[1];
    var m2 = src.match(/\/([^/?]+\.(png|jpg|webp))/i);
    return m2 ? m2[1] : '';
  }
  function getSelectedResult() {
    var images = extractGeneratedImages();
    return {
      resultText: String(window.getSelection()?.toString() || '').trim(),
      resultUrl: window.location.href,
      images: images,
      localFileHint: guessDownloadName(images) || 'downloads'
    };
  }
  window.V2BrowserCompanionProviders ||= [];
  window.V2BrowserCompanionProviders.push({
    id: 'chatgpt_web_manual',
    matchUrl: url => /https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(url),
    getProviderName: () => 'ChatGPT Web',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'ChatGPT input not found. Paste manually after login or after the page finishes loading.',
    buildUserInstructions: () => 'Review prompt, submit manually, wait for DALL-E to finish. Download the generated image, then "Send selected result" to capture text + image URLs.'
  });
}());
