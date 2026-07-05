// UI init: set text on elements that were moved from HTML to keep HTML ASCII-only
document.getElementById("appTitle").textContent = t("title");
document.getElementById("status").textContent = t("scanning");
document.getElementById("scan").textContent = t("rescan");

const listEl = document.getElementById("list");
const statusEl = document.getElementById("status");
const scanButton = document.getElementById("scan");

function renderEmpty() {
  listEl.innerHTML = `<div class="empty">${t("noMedia")}</div>`;
  statusEl.textContent = t("noMediaStatus");
}

function buildVariantButton(variant, itemIdx, onDownload) {
  const button = document.createElement("button");
  button.className = "variant";

  if (variant.unsupported) {
    const displayUrl = variant.url;
    const isBlob = displayUrl.startsWith("blob:");
    const isDash = !isBlob;
    button.textContent = isBlob ? t("unsupportedBlob") : t("unsupportedDash");
    button.disabled = true;
    return button;
  }

  if (variant.sending) {
    button.textContent = t("sending");
    button.disabled = true;
    return button;
  }

  if (variant.success) {
    button.textContent = t("added");
    button.disabled = true;
    return button;
  }

  if (variant.error) {
    button.textContent = t("retry");
    return button;
  }

  button.textContent = variant.label || t("line");
  return button;
}

async function requestProbe(url, itemIdx, buttonEl) {
  const variants = document.querySelector(`.variants[data-item="${itemIdx}"]`);
  if (variants) variants.innerHTML = t("probing");

  try {
    const res = await chrome.runtime.sendMessage({ type: "probe-media", url });
    if (variants) {
      if (!res || res.error) {
        variants.textContent = (res && res.error) || t("probeFailed");
        return;
      }

      if (res.drm) {
        const warn = document.createElement("div");
        warn.className = "warning";
        warn.textContent = t("drmWarning");
        variants.appendChild(warn);
      }

      const onDownloadFn = async function(probeUrl) {
        try {
          const result = await chrome.runtime.sendMessage({ type: "send-download", url: probeUrl, referer: url });
          return result;
        } catch (err) {
          return { success: false, error: err.message };
        }
      };

      for (const variant of res.variants || []) {
        const vBtn = document.createElement("button");
        vBtn.className = "variant";
        vBtn.textContent = variant.label || t("line");
        vBtn.onclick = async () => {
          vBtn.textContent = t("sending");
          vBtn.disabled = true;
          const result = await onDownloadFn(variant.url);
          vBtn.textContent = result && result.success ? t("added") : t("retry");
          if (!result.success) vBtn.disabled = false;
        };
        variants.appendChild(vBtn);
      }
    }
  } catch (err) {
    if (variants) variants.textContent = (err && err.message) || t("probeFailed");
  }
}

function renderItems(items) {
  listEl.innerHTML = "";

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const url = item.url;
    const isUnsupported = url.startsWith("blob:") || url.toLowerCase().includes(".mpd");

    const div = document.createElement("div");
    div.className = "item";

    const topRow = document.createElement("div");
    topRow.className = "row";

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = item.title || t("video");
    topRow.appendChild(title);

    const meta = document.createElement("span");
    meta.className = "label";
    meta.textContent = item.label || t("media");
    topRow.appendChild(meta);

    div.appendChild(topRow);

    // Download action row
    const actionRow = document.createElement("div");
    actionRow.className = "row";
    actionRow.style.justifyContent = "flex-start";
    actionRow.style.gap = "8px";

    const download = document.createElement("button");
    download.textContent = isUnsupported ? t("notSupported") : t("download");
    download.disabled = isUnsupported;
    if (isUnsupported) {
    download.title = t("notSupportedHint") + " — DASH/M4S";
    }
    if (!isUnsupported) {
      download.onclick = async () => {
        download.textContent = t("sending");
        download.disabled = true;
        try {
          const res = await chrome.runtime.sendMessage({ type: "send-download", url: item.url, referer: item.pageUrl });
          download.textContent = res && res.success ? t("added") : t("retry");
          if (!res || !res.success) download.disabled = false;
        } catch (err) {
          download.textContent = t("retry");
          download.disabled = false;
        }
      };
    }
    actionRow.appendChild(download);

    const probe = document.createElement("button");
    probe.className = "secondary";
    probe.textContent = t("probe");
    const progState = { probing: false };
    probe.onclick = async () => {
      if (progState.probing) return;
      progState.probing = true;
      probe.textContent = t("probing");
      try {
        const res = await chrome.runtime.sendMessage({ type: "probe-media", url: item.url });
        probe.textContent = res && res.success ? t("refresh") : t("retry");
      } catch (err) {
        probe.textContent = t("retry");
      }
      progState.probing = false;
    };
    actionRow.appendChild(probe);

    const copy = document.createElement("button");
    copy.className = "secondary";
    copy.textContent = t("copy");
    copy.onclick = async () => {
      await navigator.clipboard.writeText(item.url);
      copy.textContent = t("copied");
      setTimeout(() => { copy.textContent = t("copy"); }, 1500);
    };
    actionRow.appendChild(copy);

    div.appendChild(actionRow);

    // Variants row
    if (item.type === "video" || url.toLowerCase().includes(".m3u8")) {
      const variants = document.createElement("div");
      variants.className = "variants";
      variants.setAttribute("data-item", String(i));
      div.appendChild(variants);
      requestProbe(item.url, i, probe);
    }

    listEl.appendChild(div);
  }
}

async function scan() {
  statusEl.textContent = t("scanning");
  scanButton.textContent = t("scanning");
  scanButton.disabled = true;

  try {
    // Direct approach: inject scanner into active tab and get results back
    let tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    let tab = tabs[0];
    if (!tab || !tab.id) { renderEmpty(); scanButton.textContent = t("rescan"); scanButton.disabled = false; return; }

    // Inject a self-contained scanner script
    let results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: function() {
        var found = [];
        var seen = {};
        
        function labelFor(u) {
          if (/\.m3u8/i.test(u)) return 'M3U8';
          if (/\.mpd/i.test(u)) return 'DASH';
          if (/\.mp4/i.test(u)) return 'MP4';
          if (/\.m4s/i.test(u)) return 'M4S';
          if (/\.ts/i.test(u)) return 'TS';
          if (/\.flv/i.test(u)) return 'FLV';
          if (/\.webm/i.test(u)) return 'WEBM';
          if (/\/m3u8\//i.test(u)) return 'M3U8';
          return 'MEDIA';
        }
        
        function add(url, label) {
          if (!url || seen[url]) return;
          seen[url] = true;
          var lbl = label || labelFor(url);
          try {
            var u = new URL(url, location.href);
            found.push({ url: u.href, pageUrl: location.href, title: document.title || lbl, label: lbl, timestamp: Date.now() });
          } catch(e) {
            found.push({ url: url, pageUrl: location.href, title: document.title || lbl, label: lbl, timestamp: Date.now() });
          }
        }
        
        // 1. Search raw HTML for media URLs
        try {
          var html = document.documentElement.outerHTML || document.body.innerHTML || '';
          var re = /https?:\/\/[^"'\s<>]+\.(?:m3u8|mp4|mpd|m4s|ts|flv|webm|mkv)[^"'\s<>]*/gi;
          var m;
          while ((m = re.exec(html)) !== null) add(m[0]);
          var re2 = /https?:\/\/[^"'\s<>]*\/m3u8\/[^"'\s<>]*/gi;
          while ((m = re2.exec(html)) !== null) add(m[0]);
        } catch(e) {}
        
        // 2. Scan iframe src attributes
        document.querySelectorAll('iframe').forEach(function(el) {
          var src = el.src || el.getAttribute('data-src') || '';
          if (!src) return;
          // Check if src itself contains media URL
          if (/\.(?:m3u8|mp4|mpd|m4s|ts|flv|webm|mkv)/i.test(src)) add(src);
          // Extract from query params
          try {
            var u = new URL(src, location.href);
            ['video','url','src','file','source','play','v','vid','mp4','m3u8','hls','dash'].forEach(function(p) {
              var val = u.searchParams.get(p);
              if (val && /\.(?:m3u8|mp4|mpd|m4s|ts|flv|webm|mkv)/i.test(val)) add(val);
            });
          } catch(e) {}
        });
        
        // 3. Scan video/audio/source elements
        document.querySelectorAll('video, audio, source').forEach(function(el) {
          var url = el.currentSrc || el.src;
          if (url) add(url);
        });
        
        // 4. Scan data attributes
        ['data-video','data-url','data-src','data-mp4','data-m3u8','data-file','data-source'].forEach(function(attr) {
          document.querySelectorAll('[' + attr + ']').forEach(function(el) {
            var val = el.getAttribute(attr);
            if (val && /\.(?:m3u8|mp4|mpd|m4s|ts|flv|webm|mkv)/i.test(val)) add(val);
          });
        });
        
        return found;
      }
    });

    // Collect results from all frames
    let items = [];
    let seenUrls = {};
    for (let r of results) {
      if (r.result && Array.isArray(r.result)) {
        for (let item of r.result) {
          if (!seenUrls[item.url]) {
            seenUrls[item.url] = true;
            items.push(item);
          }
        }
      }
    }

    if (items.length > 0) {
      statusEl.textContent = tFormat("foundMedia", items.length);
      renderItems(items);
    } else {
      renderEmpty();
    }
  } catch (err) {
    renderEmpty();
  }

  scanButton.textContent = t("rescan");
  scanButton.disabled = false;
}

// Clear list button
const toolbar = document.querySelector(".toolbar");
const clearBtn = document.createElement("button");
clearBtn.className = "secondary";
clearBtn.textContent = t("clearList");
clearBtn.onclick = async () => {
  listEl.innerHTML = "";
  statusEl.textContent = t("noMediaStatus");
  // Also clear storage
  let all = await chrome.storage.local.get(null);
  let keys = Object.keys(all).filter(function(k) { return k.startsWith('nsp_media_'); });
  if (keys.length > 0) chrome.storage.local.remove(keys);
};
toolbar.appendChild(clearBtn);

scanButton.onclick = scan;
scan();
