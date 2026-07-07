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
    const selected = String(window.getSelection()?.toString() || '').trim();
    const media = document.querySelector('video[src], img[src], a[href*="download"], a[href*="blob:"]');
    return {
      resultText: selected,
      resultUrl: media?.src || media?.href || window.location.href
    };
  }
  window.V2BrowserCompanionProviders ||= [];
  window.V2BrowserCompanionProviders.push({
    id: 'google_opal_manual',
    matchUrl: url => /https:\/\/opal\.withgoogle\.com\//.test(url),
    getProviderName: () => 'Google Opal',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'Opal input not found. Paste manually and keep platform limits visible.',
    buildUserInstructions: () => 'Submit manually in Opal. After output appears, select text or a media link and send it to V2.'
  });
}());
