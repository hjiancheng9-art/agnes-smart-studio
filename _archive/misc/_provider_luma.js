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
    id: 'luma_manual',
    matchUrl: url => /https:\/\/([^/]+\.)?lumalabs\.ai\//.test(url),
    getProviderName: () => 'Luma',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'Luma input not found. Paste manually and submit yourself.',
    buildUserInstructions: () => 'Use Luma manually. Send the completed clip link or selected result text to V2.'
  });
}());
