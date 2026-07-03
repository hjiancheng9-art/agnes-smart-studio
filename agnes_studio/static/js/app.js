/**
 * Agnes 多模态工作室 v2.0 — 前端逻辑
 */

// ============================================================
// 初始化
// ============================================================

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initModeSwitches();
  await loadConfig();
});

// ---- 标签切换 ----
function initTabs() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

// ---- 模式切换 (图片: 文生图/图生图) ----
function initModeSwitches() {
  document.querySelectorAll(".mode-switch").forEach(sw => {
    sw.addEventListener("click", (e) => {
      const btn = e.target.closest(".mode-btn");
      if (!btn) return;
      sw.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      // 图片面板: 切换参考图显示
      if (btn.dataset.mode === "i2i") {
        document.getElementById("img-ref-row").classList.remove("hidden");
      } else if (btn.dataset.mode === "t2i") {
        document.getElementById("img-ref-row").classList.add("hidden");
      }
      // 视频面板: 切换参考图显示
      if (btn.dataset.mode === "i2v") {
        document.getElementById("vid-ref-row").classList.remove("hidden");
      } else if (btn.dataset.mode === "t2v") {
        document.getElementById("vid-ref-row").classList.add("hidden");
      }
    });
  });
}

// ---- 加载配置 ----
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();

    // 图片尺寸
    const imgSize = document.getElementById("img-size-preset");
    for (const [label, size] of Object.entries(cfg.image_sizes || {})) {
      imgSize.appendChild(new Option(label, size));
    }

    // 视频分辨率
    const vidRes = document.getElementById("vid-resolution");
    for (const [label, [w, h]] of Object.entries(cfg.video_resolutions || {})) {
      vidRes.appendChild(new Option(`${label}`, `${w},${h}`));
    }
    // 默认选 720P
    vidRes.value = "1280,720";

    // 视频模型
    const vidModel = document.getElementById("vid-model");
    for (const [key, info] of Object.entries(cfg.video_models || {})) {
      vidModel.appendChild(new Option(info.label, info.value));
    }

    // API Key 状态
    if (cfg.has_api_key) {
      const badge = document.getElementById("key-status");
      badge.textContent = "🔑 已配置";
      badge.classList.add("ok");
    }
  } catch (err) {
    console.error("加载配置失败:", err);
  }
}

// ---- 图片尺寸切换 ----
function onImageSizePreset() {
  const size = document.getElementById("img-size-preset").value;
  if (!size) return;
  const [w, h] = size.split("x");
  document.getElementById("img-width").value = w;
  document.getElementById("img-height").value = h;
}

// ---- 视频分辨率切换 ----
function onVideoResolution() {
  const val = document.getElementById("vid-resolution").value;
  if (!val) return;
  const [w, h] = val.split(",");
  document.getElementById("vid-width").value = w;
  document.getElementById("vid-height").value = h;
}


// ============================================================
// 图片生成
// ============================================================

async function generateImage() {
  const prompt = document.getElementById("img-prompt").value.trim();
  if (!prompt) { toast("请输入提示词", "error"); return; }

  const btn = document.getElementById("btn-img-generate");
  const resultDiv = document.getElementById("img-result");
  btn.disabled = true;
  btn.textContent = "⏳ 生成中...";
  resultDiv.innerHTML = '<div class="spinner"></div>';

  const sizePreset = document.getElementById("img-size-preset").value;
  const customW = document.getElementById("img-width").value;
  const customH = document.getElementById("img-height").value;

  const body = {
    prompt,
    size: sizePreset || `${customW}x${customH}`,
    custom_width: customW ? parseInt(customW) : null,
    custom_height: customH ? parseInt(customH) : null,
    quality: document.getElementById("img-quality").value,
    style: document.getElementById("img-style").value,
    num_images: parseInt(document.getElementById("img-num").value) || 1,
    seed: document.getElementById("img-seed").value ? parseInt(document.getElementById("img-seed").value) : null,
  };

  // 图生图
  const imgRef = document.getElementById("img-ref").value.trim();
  if (imgRef && !document.getElementById("img-ref-row").classList.contains("hidden")) {
    body.image_url = imgRef;
  }

  try {
    const res = await fetch("/api/image/generate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json();

    if (data.ok && data.images?.length) {
      resultDiv.innerHTML = data.images.map(url =>
        `<div><img src="${url}" alt="generated" loading="lazy"><div class="result-meta">${prompt.slice(0, 100)}</div></div>`
      ).join("");
      toast(`生成了 ${data.images.length} 张图片`, "ok");
    } else {
      resultDiv.innerHTML = `<div class="error-msg">❌ ${data.error || '生成失败'}</div>`;
      toast(data.error || "生成失败", "error");
    }
  } catch (err) {
    resultDiv.innerHTML = `<div class="error-msg">❌ 网络错误: ${err.message}</div>`;
    toast("网络错误", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "🚀 生成图片";
  }
}


// ============================================================
// 视频生成
// ============================================================

async function generateVideo() {
  const prompt = document.getElementById("vid-prompt").value.trim();
  if (!prompt) { toast("请输入提示词", "error"); return; }

  const btn = document.getElementById("btn-vid-generate");
  const resultDiv = document.getElementById("vid-result");
  const pollDiv = document.getElementById("vid-poll");
  btn.disabled = true;
  btn.textContent = "⏳ 提交中...";
  resultDiv.innerHTML = '<div class="spinner"></div><p style="margin-top:8px;color:var(--text2)">正在提交视频生成任务...</p>';
  pollDiv.classList.add("hidden");

  const body = {
    prompt,
    model: document.getElementById("vid-model").value,
    width: parseInt(document.getElementById("vid-width").value) || 1280,
    height: parseInt(document.getElementById("vid-height").value) || 720,
    duration: parseInt(document.getElementById("vid-duration").value) || 5,
    fps: parseInt(document.getElementById("vid-fps").value) || 24,
    seed: document.getElementById("vid-seed").value ? parseInt(document.getElementById("vid-seed").value) : null,
    negative_prompt: document.getElementById("vid-neg").value.trim() || "",
  };

  const imgRef = document.getElementById("vid-ref").value.trim();
  if (imgRef && !document.getElementById("vid-ref-row").classList.contains("hidden")) {
    body.image_url = imgRef;
  }

  try {
    const res = await fetch("/api/video/generate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json();

    btn.disabled = false;
    btn.textContent = "🎥 生成视频";

    if (!data.ok) {
      resultDiv.innerHTML = `<div class="error-msg">❌ ${data.error || '生成失败'}</div>`;
      toast(data.error || "生成失败", "error");
      return;
    }

    const vid = data.video_id;
    if (!vid) {
      resultDiv.innerHTML = `<div class="error-msg">⚠️ 未返回 video_id，请检查响应</div>
        <pre style="font-size:11px;text-align:left;margin-top:8px;">${JSON.stringify(data.raw, null, 2)}</pre>`;
      return;
    }

    resultDiv.innerHTML = `<p style="color:var(--green)">✅ 任务已提交</p>
      <p style="font-size:14px;margin-top:8px">Video ID: <code style="color:var(--accent2)">${vid}</code></p>
      <p style="color:var(--text2);font-size:12px;margin-top:4px">正在轮询状态...</p>`;

    // 自动轮询
    pollDiv.classList.remove("hidden");
    pollDiv.className = "poll-status";
    await pollVideo(vid, pollDiv, resultDiv);

  } catch (err) {
    resultDiv.innerHTML = `<div class="error-msg">❌ 网络错误: ${err.message}</div>`;
    toast("网络错误", "error");
    btn.disabled = false;
    btn.textContent = "🎥 生成视频";
  }
}

async function pollVideo(videoId, pollDiv, resultDiv) {
  let attempts = 0;
  const maxAttempts = 120; // 最多 4 分钟

  while (attempts < maxAttempts) {
    await sleep(2000);
    attempts++;

    try {
      const res = await fetch("/api/video/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: videoId }),
      });
      const data = await res.json();

      if (!data.ok) {
        pollDiv.textContent = `查询失败: ${data.error}`;
        pollDiv.className = "poll-status failed";
        return;
      }

      const status = data.status?.toLowerCase();
      pollDiv.textContent = `⏳ 状态: ${status || 'unknown'} (第 ${attempts} 次查询)`;

      if (status === "completed") {
        pollDiv.textContent = `✅ 视频生成完成! (${attempts * 2}s)`;
        pollDiv.className = "poll-status done";

        if (data.video_url) {
          resultDiv.innerHTML = `
            <video controls autoplay loop style="max-width:100%;border-radius:8px">
              <source src="${data.video_url}" type="video/mp4">
            </video>
            <div class="result-meta">Video ID: ${videoId}</div>`;
        } else {
          resultDiv.innerHTML += `<div class="result-meta">状态: completed | 请使用 Video ID 查询下载链接</div>`;
        }
        return;
      }

      if (status === "failed") {
        pollDiv.textContent = `❌ 视频生成失败`;
        pollDiv.className = "poll-status failed";
        return;
      }
    } catch (err) {
      pollDiv.textContent = `轮询出错: ${err.message}`;
      pollDiv.className = "poll-status failed";
      return;
    }
  }

  pollDiv.textContent = `⏰ 轮询超时 (${maxAttempts * 2}s)，请稍后手动查询`;
  pollDiv.className = "poll-status failed";
}


// ============================================================
// 视频查询
// ============================================================

async function queryVideo() {
  const videoId = document.getElementById("query-id").value.trim();
  if (!videoId) { toast("请输入 video_id", "error"); return; }

  const resultDiv = document.getElementById("query-result");
  resultDiv.innerHTML = '<div class="spinner"></div>';

  try {
    const res = await fetch("/api/video/query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId }),
    });
    const data = await res.json();
    renderQueryResult(data, resultDiv);
  } catch (err) {
    resultDiv.innerHTML = `<div class="error-msg">❌ ${err.message}</div>`;
  }
}

async function queryAndWait() {
  const videoId = document.getElementById("query-id").value.trim();
  if (!videoId) { toast("请输入 video_id", "error"); return; }

  const resultDiv = document.getElementById("query-result");
  resultDiv.innerHTML = '<div class="spinner"></div><p>正在等待视频完成...</p>';

  let attempt = 0;
  while (attempt < 120) {
    await sleep(2000);
    attempt++;
    try {
      const res = await fetch("/api/video/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: videoId }),
      });
      const data = await res.json();
      const status = data.status?.toLowerCase();

      if (status === "completed" || status === "failed") {
        renderQueryResult(data, resultDiv);
        return;
      }
      resultDiv.innerHTML = `<div class="spinner"></div><p>⏳ 状态: ${status || 'unknown'} (${attempt * 2}s)</p>`;
    } catch (err) {
      resultDiv.innerHTML = `<div class="error-msg">❌ ${err.message}</div>`;
      return;
    }
  }
  resultDiv.innerHTML = '<div class="error-msg">⏰ 轮询超时</div>';
}

function renderQueryResult(data, resultDiv) {
  if (!data.ok) {
    resultDiv.innerHTML = `<div class="error-msg">❌ ${data.error || '查询失败'}</div>`;
    return;
  }

  let html = `<div style="text-align:left;font-size:14px">`;
  html += `<p><strong>Video ID:</strong> <code>${data.video_id || '-'}</code></p>`;
  html += `<p><strong>状态:</strong> <span style="color:${data.status==='completed'?'var(--green)':'var(--accent2)'}">${data.status || '-'}</span></p>`;

  if (data.video_url) {
    html += `<video controls style="max-width:100%;margin-top:12px;border-radius:8px">
      <source src="${data.video_url}" type="video/mp4"></video>`;
  }
  html += `<details style="margin-top:12px"><summary>Raw Response</summary>
    <pre style="font-size:11px;overflow-x:auto">${JSON.stringify(data.raw, null, 2)}</pre></details>`;
  html += `</div>`;
  resultDiv.innerHTML = html;
}


// ============================================================
// API Key 管理
// ============================================================

function showKeyDialog() {
  document.getElementById("key-dialog").classList.remove("hidden");
  document.getElementById("key-input").focus();
}

function closeKeyDialog() {
  document.getElementById("key-dialog").classList.add("hidden");
}

async function saveApiKey() {
  const key = document.getElementById("key-input").value.trim();
  if (!key) { toast("请输入 API Key", "error"); return; }

  try {
    const res = await fetch("/api/set-key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById("key-status").textContent = "🔑 已配置";
      document.getElementById("key-status").classList.add("ok");
      closeKeyDialog();
      toast("API Key 已保存", "ok");
    } else {
      toast(data.error || "保存失败", "error");
    }
  } catch (err) {
    toast("网络错误", "error");
  }
}


// ============================================================
// 工具函数
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function toast(msg, type = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}
