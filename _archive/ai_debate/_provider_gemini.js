(function () {
  function findPromptInput() {
    return document.querySelector('rich-textarea div[contenteditable="true"], textarea, [contenteditable="true"]');
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
  function extractGeneratedMedia() {
    var images = [];
    var videos = [];
    document.querySelectorAll('img[src]').forEach(function(img) {
      var src = img.src;
      if (/generated|output|result/i.test(img.alt || '') || img.naturalWidth > 300) {
        images.push({ url: src, alt: img.alt || '' });
      }
    });
    document.querySelectorAll('video source[src]').forEach(function(v) {
      videos.push({ url: v.src });
    });
    return { images, videos };
  }
  function getSelectedResult() {
    var media = extractGeneratedMedia();
    return {
      resultText: String(window.getSelection()?.toString() || '').trim(),
      resultUrl: window.location.href,
      images: media.images,
      videos: media.videos,
      localFileHint: media.videos.length ? 'generated-video' : 'generated-image'
    };
  }
  window.V2BrowserCompanionProviders ||= [];
  window.V2BrowserCompanionProviders.push({
    id: 'gemini_web_manual',
    matchUrl: url => /https:\/\/gemini\.google\.com\//.test(url),
    getProviderName: () => 'Gemini Web',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'Gemini input not found. Paste manually after login or after the page finishes loading.',
    buildUserInstructions: () => 'Use Gemini for vision / QC / video generation. Download the output if needed, then select text or "Send selected result".'
  });
}());
