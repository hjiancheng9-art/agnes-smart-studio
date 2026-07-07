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
    id: 'runway_manual',
    matchUrl: url => /https:\/\/(app\.)?runwayml\.com\//.test(url),
    getProviderName: () => 'Runway',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'Runway input not found. Paste manually after login and project selection.',
    buildUserInstructions: () => 'Use Runway manually. When generation completes, send selected text or the result link to V2.'
  });
}());
