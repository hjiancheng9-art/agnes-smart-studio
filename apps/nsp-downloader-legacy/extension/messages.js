// Messages for the extension popup UI.
// Chinese copy lives here so source JS/HTML stay ASCII-only.
const MSG = {
  "zh-CN": {
    title: "网速加加",
    scanning: "扫描中",
    rescan: "重新扫描",
    noMedia: "没有发现媒体。请先播放视频，或点击重新扫描。",
    noMediaStatus: "未发现媒体",
    unsupportedBlob: "暂不支持 Blob",
    unsupportedDash: "暂不支持 DASH/M4S",
    sending: "发送中...",
    added: "已添加",
    retry: "重试",
    probeFailed: "探测失败",
    drmWarning: "检测到受保护流，暂不支持下载。",
    line: "线路",
    foundMedia: mediaCount => `发现 ${mediaCount} 个媒体`,
    video: "视频",
    media: "媒体",
    notSupported: "暂不支持",
    download: "下载",
    probe: "探测",
    probing: "探测中...",
    refresh: "刷新",
    copy: "复制",
    copied: "已复制",
    clearList: "清空列表",
    notSupportedHint: "这是 DASH/Blob 分离流，当前版本只能识别，暂不能直接下载。",
  },
  en: {
    title: "NetSpeedPro",
    scanning: "Scanning",
    rescan: "Rescan",
    noMedia: "No media found. Play a video first, or click Rescan.",
    noMediaStatus: "No media found",
    unsupportedBlob: "Blob not supported",
    unsupportedDash: "DASH/M4S not supported",
    sending: "Sending...",
    added: "Added",
    retry: "Retry",
    probeFailed: "Probe failed",
    drmWarning: "DRM-protected stream detected, download not supported.",
    line: "Line",
    foundMedia: mediaCount => `${mediaCount} media found`,
    video: "Video",
    media: "Media",
    notSupported: "N/A",
    download: "Download",
    probe: "Probe",
    probing: "Probing...",
    refresh: "Refresh",
    copy: "Copy",
    copied: "Copied",
    clearList: "Clear list",
    notSupportedHint: "DASH/Blob split stream; can be detected but not downloaded in this version.",
  },
};
// Auto-detect language
const lang = (navigator.language || "en").startsWith("zh") ? "zh-CN" : "en";
function t(key) { return MSG[lang][key] || MSG.en[key] || key; }
function tFormat(key, ...args) {
  const fn = MSG[lang][key] || MSG.en[key];
  return typeof fn === "function" ? fn(...args) : fn || key;
}
