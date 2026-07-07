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
    const media = document.querySelector('video[src], img[src], a[href*=".mp4"], a[href*="download"]');
    return {
      resultText: String(window.getSelection()?.toString() || '').trim(),
      resultUrl: media?.src || media?.href || window.location.href
    };
  }
  window.V2BrowserCompanionProviders ||= [];
  window.V2BrowserCompanionProviders.push({
    id: 'jimeng_manual',
    matchUrl: url => /https:\/\/(jimeng\.jianying\.com|jimeng-ai\.com)\//.test(url),
    getProviderName: () => 'Jimeng',
    findPromptInput,
    fillPrompt,
    getSelectedResult,
    getKnownLimitMessage: () => 'Jimeng input not found. Paste manually; generation remains user-confirmed only.',
    buildUserInstructions: () => 'Use Jimeng manually. Send selected text, image, or video link back to V2 when ready.'
  });
}());
