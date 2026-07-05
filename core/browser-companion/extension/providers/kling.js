(function () {
  function findPromptInput() {
    return document.querySelector('textarea, [contenteditable="true"], input[type="text"]');
  }
  async function fillPrompt(prompt) {
    const input = findPromptInput();
    if (!input) return false;
    input.focus();
    if ('value' in input) input.value = prompt;
    else input.textContent = prompt;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: prompt }));
    return true;
  }
  function getSelectedResult() {
    const media = document.querySelector('video[src], a[href*=".mp4"], a[href*="download"]');
    return {
      resultText: String(window.getSelection()?.toString() || '').trim(),
      resultUrl: media?.src || media?.href || window.location.href
    };
  }
  window.V2BrowserCompanionProviders ||= [];
  window.V2BrowserCompanionProviders.push({
    id: 'kling_manual',
    matchUrl: url => /https:\/\/([^/]+\.)?klingai\.com\//.test(url),
    getProviderName: () => 'Kling',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'Kling input not found. Paste manually; the companion will not bypass login or quota.',
    buildUserInstructions: () => 'Use Kling manually. When the clip is ready, select the result text or media link and send it to V2.'
  });
}());
