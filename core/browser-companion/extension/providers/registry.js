/* Provider registry — all available providers and lookup by URL. */

import { ProviderAdapter } from './adapter-base.js';

// ── Define adapters ──

export const chatgptAdapter = new ProviderAdapter({
  name: 'ChatGPT',
  hosts: ['chatgpt.com', 'chat.openai.com'],
  selectors: {
    promptInput: [
      '#prompt-textarea',
      "div[contenteditable='true']",
      'textarea',
    ],
    sendButton: [
      "button[data-testid='send-button']",
      "button[aria-label*='Send']",
      "button[aria-label*='发送']",
    ],
    responseRoot: [
      "[data-message-author-role='assistant']:last-of-type",
      'main',
    ],
  },
});

export const geminiAdapter = new ProviderAdapter({
  name: 'Gemini',
  hosts: ['gemini.google.com'],
  selectors: {
    promptInput: [
      "rich-textarea div[contenteditable='true']",
      'textarea',
      "div[contenteditable='true']",
    ],
    sendButton: [
      "button[aria-label*='Send']",
      "button[aria-label*='送信']",
    ],
    responseRoot: [
      'message-content:last-of-type',
      'main',
    ],
  },
});

export const deepseekAdapter = new ProviderAdapter({
  name: 'DeepSeek',
  hosts: ['chat.deepseek.com'],
  selectors: {
    promptInput: [
      'textarea',
      "div[contenteditable='true']",
    ],
    sendButton: [
      "button[type='submit']",
      "button[aria-label*='Send']",
      "button[aria-label*='发送']",
    ],
    responseRoot: [
      '.ds-markdown:last-of-type',
      'main',
    ],
  },
});

// ── Video platform adapters (minimal) ──

export const opalAdapter = new ProviderAdapter({
  name: 'Opal',
  hosts: ['opal.withgoogle.com'],
  selectors: { promptInput: ['textarea'], sendButton: ["button[type='submit']"] },
});

export const klingAdapter = new ProviderAdapter({
  name: 'Kling',
  hosts: ['klingai.com'],
  selectors: { promptInput: ['textarea'], sendButton: ["button[type='submit']"] },
});

export const runwayAdapter = new ProviderAdapter({
  name: 'Runway',
  hosts: ['runwayml.com', 'app.runwayml.com'],
  selectors: { promptInput: ['textarea'], sendButton: ["button[type='submit']"] },
});

export const lumaAdapter = new ProviderAdapter({
  name: 'Luma',
  hosts: ['lumalabs.ai'],
  selectors: { promptInput: ['textarea'], sendButton: ["button[type='submit']"] },
});

// ── Registry ──

const allAdapters = [
  chatgptAdapter,
  geminiAdapter,
  deepseekAdapter,
  opalAdapter,
  klingAdapter,
  runwayAdapter,
  lumaAdapter,
];

export function getAdapterForLocation(url) {
  const href = url || location.href;
  return allAdapters.find((a) => a.matches(href)) || null;
}

export function registerAdapter(adapter) {
  allAdapters.push(adapter);
}

// Expose for content-script
window.__CRUX_PROVIDER_REGISTRY__ = {
  getAdapterForLocation,
  allAdapters,
};
