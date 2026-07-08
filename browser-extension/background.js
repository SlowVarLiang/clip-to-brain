const DEFAULTS = {
  apiBase: "http://127.0.0.1:8765",
  apiKey: "",
  pollIntervalMs: 3000,
  pollTimeoutMs: 30 * 60 * 1000,
  useClipApi: true,
};

const activeJobs = new Map();

async function ensureApiPermission(apiBase) {
  try {
    const origin = new URL(apiBase).origin;
    if (origin.startsWith("http://127.0.0.1") || origin.startsWith("http://localhost")) {
      return true;
    }
    const granted = await chrome.permissions.contains({ origins: [`${origin}/*`] });
    if (granted) return true;
    return chrome.permissions.request({ origins: [`${origin}/*`] });
  } catch {
    return false;
  }
}

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

function apiHeaders(apiKey) {
  const h = { "Content-Type": "application/json" };
  if (apiKey) h["X-API-Key"] = apiKey;
  return h;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function notify(title, message) {
  chrome.notifications.create({ type: "basic", title, message: message.slice(0, 240) });
}

function pushTabMessage(tabId, payload) {
  if (!tabId) return;
  chrome.tabs.sendMessage(tabId, payload).catch(() => {});
}

async function submitClip(url, settings) {
  const base = settings.apiBase.replace(/\/$/, "");
  await ensureApiPermission(base);

  const endpoint = settings.useClipApi ? "/clip" : "/ingest";
  const body = settings.useClipApi
    ? { url, account: "default-creator" }
    : { url };

  const res = await fetch(`${base}${endpoint}`, {
    method: "POST",
    headers: apiHeaders(settings.apiKey),
    body: JSON.stringify(body),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || data.detail || `归档请求失败 (${res.status})`);
  }
  if (!data.job_id) {
    throw new Error(data.error || "未返回 job_id");
  }
  return data.job_id;
}

async function pollClipJob(jobId, settings) {
  const base = settings.apiBase.replace(/\/$/, "");
  const started = Date.now();
  const statusPath = settings.useClipApi ? "/clip" : "/ingest";

  while (Date.now() - started < settings.pollTimeoutMs) {
    const res = await fetch(`${base}${statusPath}/${jobId}`, {
      headers: apiHeaders(settings.apiKey),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `轮询失败 (${res.status})`);
    }

    const status = data.status;
    if (status === "QUEUEING" || status === "RUNNING") {
      await sleep(settings.pollIntervalMs);
      continue;
    }

    const result = data.result || {};
    if (status === "SUCCESS" && result.success !== false) {
      return result;
    }
    const err = result.error || result.next_step || "归档失败";
    throw new Error(err);
  }

  throw new Error("归档超时，请稍后在 Obsidian 检查或重试");
}

function formatDoneMessage(result) {
  const note = result.relative_path || result.note_path || "已归档";
  const shortName = note.split(/[\\/]/).pop() || note;
  let msg = shortName;
  if (result.value_rating) msg += ` · ${result.value_rating}`;
  if (result.remix_angles?.length) {
    msg += `\n💡 ${result.remix_angles[0]}`;
  }
  return { shortName, msg };
}

async function runClipJob(jobId, settings, tabId) {
  try {
    const result = await pollClipJob(jobId, settings);
    const { shortName, msg } = formatDoneMessage(result);
    notify("Lumis 已入库", msg);
    pushTabMessage(tabId, { type: "INGEST_DONE", result, displayName: shortName });
    return { ok: true, result };
  } catch (err) {
    const msg = String(err.message || err);
    notify("Lumis 归档失败", msg);
    pushTabMessage(tabId, { type: "INGEST_ERROR", error: msg });
    return { ok: false, error: msg };
  } finally {
    activeJobs.delete(jobId);
  }
}

async function handleIngest(url, tabId) {
  if (!url || !url.startsWith("http")) {
    const err = "无法识别当前页面链接";
    notify("Lumis 归档", err);
    return { ok: false, error: err };
  }

  const settings = await getSettings();

  try {
    const jobId = await submitClip(url, settings);
    activeJobs.set(jobId, { tabId, url, started: Date.now() });
    notify("Lumis 丢链", "已提交，解析/转写/萃取中…");
    pushTabMessage(tabId, { type: "INGEST_PROGRESS", message: "已提交，处理中…" });

    runClipJob(jobId, settings, tabId);

    return { ok: true, queued: true, job_id: jobId };
  } catch (err) {
    const msg = String(err.message || err);
    notify("Lumis 归档失败", msg);
    pushTabMessage(tabId, { type: "INGEST_ERROR", error: msg });
    return { ok: false, error: msg };
  }
}

const PAGE_PATTERNS = [
  "*://*.youtube.com/watch*",
  "*://youtu.be/*",
  "*://*.bilibili.com/video/*",
  "*://*.xiaohongshu.com/*",
  "*://*.xhslink.com/*",
  "*://weixin.qq.com/sph/*",
  "*://*.weixin.qq.com/sph/*",
  "*://channels.weixin.qq.com/*",
  "*://mp.weixin.qq.com/s/*",
  "*://*.douyin.com/video/*",
  "*://*.douyin.com/note/*",
];

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "lumis-ingest-page",
      title: "丢链归档到 Lumis",
      contexts: ["page", "video", "link"],
      documentUrlPatterns: PAGE_PATTERNS,
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "lumis-ingest-page" || !tab?.id) return;
  const url = info.linkUrl || (await getUrlFromTab(tab));
  handleIngest(url, tab.id);
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "INGEST_URL") {
    handleIngest(msg.url, sender.tab?.id)
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }
  if (msg.type === "PING") {
    sendResponse({ ok: true });
    return false;
  }
  if (msg.type === "CHECK_API") {
    getSettings()
      .then(async (s) => {
        await ensureApiPermission(s.apiBase);
        const res = await fetch(`${s.apiBase.replace(/\/$/, "")}/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
    return true;
  }
  if (msg.type === "GET_SETTINGS") {
    getSettings().then(sendResponse);
    return true;
  }
});

async function getUrlFromTab(tab) {
  if (!tab?.id) return tab?.url || "";
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => (typeof extractVideoUrl === "function" ? extractVideoUrl() : location.href),
    });
    return result || tab.url;
  } catch {
    return tab.url;
  }
}
