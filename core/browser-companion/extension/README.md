# V2 Browser Companion

V2 Browser Companion is a Chrome/Edge Manifest V3 extension for manual web-brain provider handoff. It helps V2 work with ChatGPT Web, Gemini Web, Google Opal, Veo/Flow, Kling, Jimeng, Runway, and Luma without pretending those sites are APIs.

## Safety Boundary

- The extension does not read account passwords.
- The extension does not read cookies.
- The extension does not store API keys.
- The extension does not bypass login, CAPTCHA, quota, watermark, paid access, or platform limits.
- The extension does not auto-submit generation requests.
- The user must review and submit prompts manually.

## Install in Chrome or Edge

1. Open `chrome://extensions` or `edge://extensions`.
2. Enable developer mode.
3. Choose `Load unpacked`.
4. Select the `browser-extension` directory.
5. Keep V2 running locally, usually at `http://127.0.0.1:4366`.

## Workflow

1. In V2, ask for a web provider task, such as `Use Gemini web to analyze this video`.
2. V2 creates a browser companion task.
3. Open the extension popup and click `Pull task`.
4. Click `Open provider`.
5. On the provider page, use the floating panel to copy or try filling the prompt.
6. Submit manually on the provider website.
7. Select useful text or a result link, then click `Send selected result`.
8. V2 records the result as a project external artifact.

## Manual Fallback

If the extension cannot find the input box or the site layout changes, copy the prompt from V2 or the extension panel, paste it manually, then paste or import the result through V2's browser companion result endpoint.

## Supported Providers

- ChatGPT Web
- Gemini Web
- Google Opal
- Veo / Flow
- Kling
- Jimeng
- Runway
- Luma

Each provider has its own adapter under `providers/`. Adapters are conservative: they try to find common prompt fields, but they stop and ask for manual paste when unsure.
