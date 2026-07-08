const apiBaseEl = document.getElementById("apiBase");
const apiKeyEl = document.getElementById("apiKey");
const apiKeySection = document.getElementById("apiKeySection");
const authHintEl = document.getElementById("authHint");
const saveBtn = document.getElementById("saveBtn");
const testBtn = document.getElementById("testBtn");
const ingestBtn = document.getElementById("ingestBtn");
const statusEl = document.getElementById("status");

const DEFAULT_API = "http://127.0.0.1:8765";

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = "status" + (kind ? ` ${kind}` : "");
}

function updateAuthUi(authRequired) {
  if (authRequired) {
    authHintEl.textContent = "服务端已启用 API Key 验证，请在下方填写";
    authHintEl.className = "auth-hint need-key";
    apiKeySection.open = true;
  } else {
    authHintEl.textContent = "本地默认无需 API Key，留空即可";
    authHintEl.className = "auth-hint";
  }
}

function apiBaseValue() {
  return apiBaseEl.value.trim() || DEFAULT_API;
}

async function fetchJson(url, ms = 5000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    const res = await fetch(url, { signal: controller.signal });
    return res;
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("连接超时，请确认 API 已启动");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function probeApi(apiBase) {
  const base = apiBase.replace(/\/$/, "");

  const healthRes = await fetchJson(`${base}/health`);
  if (healthRes.ok) {
    return { ...(await healthRes.json()), legacy: false };
  }

  if (healthRes.status === 404) {
    const rootRes = await fetchJson(`${base}/`);
    if (rootRes.ok) {
      return {
        status: "ok",
        auth_required: false,
        legacy: true,
        hint: "API 版本较旧，请重启 video-parser 以使用 /ingest 归档",
      };
    }
    throw new Error(`HTTP ${rootRes.status}`);
  }

  throw new Error(`HTTP ${healthRes.status}`);
}

async function testApiConnection({ silent = false } = {}) {
  const apiBase = apiBaseValue();
  if (!silent) setStatus("测试中…");

  try {
    const data = await probeApi(apiBase);
    updateAuthUi(Boolean(data.auth_required));
    const suffix = data.auth_required ? "（需 API Key）" : "（无需 Key）";
    if (!silent) {
      if (data.legacy) {
        setStatus(`API 已连接（旧版）⚠ 请重启服务后归档 ${suffix}`, "ok");
      } else {
        setStatus(`API 连接正常 ✓ ${suffix}`, "ok");
      }
    }
    return { ok: true, data };
  } catch (err) {
    const msg = String(err.message || err);
    if (!silent) {
      setStatus(
        `连接失败：${msg}。请重启 API：cd video-parser && .venv\\Scripts\\python.exe -m parser.server`,
        "err"
      );
    }
    return { ok: false, error: msg };
  }
}

chrome.runtime.sendMessage({ type: "GET_SETTINGS" }, (settings) => {
  if (chrome.runtime.lastError || !settings) {
    apiBaseEl.value = DEFAULT_API;
    document.getElementById("dashLink").href = `${DEFAULT_API}/clip/dashboard`;
    testApiConnection({ silent: true });
    return;
  }
  apiBaseEl.value = settings.apiBase || DEFAULT_API;
  apiKeyEl.value = settings.apiKey || "";
  document.getElementById("dashLink").href = `${apiBaseEl.value.replace(/\/$/, "")}/clip/dashboard`;
  testApiConnection({ silent: true });
});

saveBtn.addEventListener("click", async () => {
  const apiBase = apiBaseValue();
  await chrome.storage.sync.set({
    apiBase,
    apiKey: apiKeyEl.value.trim(),
  });
  document.getElementById("dashLink").href = `${apiBase.replace(/\/$/, "")}/clip/dashboard`;
  try {
    const origin = new URL(apiBase).origin;
    if (!origin.includes("127.0.0.1") && !origin.includes("localhost")) {
      await chrome.permissions.request({ origins: [`${origin}/*`] });
    }
  } catch {
    /* ignore */
  }
  setStatus("已保存", "ok");
});

testBtn.addEventListener("click", async () => {
  await chrome.storage.sync.set({
    apiBase: apiBaseValue(),
    apiKey: apiKeyEl.value.trim(),
  });
  await testApiConnection();
});

ingestBtn.addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus("无活动标签页", "err");
    return;
  }

  const ping = await testApiConnection({ silent: true });
  if (!ping.ok) {
    setStatus(`API 未连接：${ping.error}`, "err");
    return;
  }
  if (ping.data?.legacy) {
    setStatus("API 版本过旧，缺少 /ingest。请重启 video-parser 后再归档", "err");
    return;
  }

  setStatus("已提交，请查看系统通知…");
  chrome.tabs.sendMessage(tab.id, { type: "PING" }, () => {
    chrome.scripting.executeScript(
      {
        target: { tabId: tab.id },
        func: () => (typeof extractVideoUrl === "function" ? extractVideoUrl() : location.href),
      },
      (results) => {
        const url = results?.[0]?.result || tab.url;
        chrome.runtime.sendMessage({ type: "INGEST_URL", url }, (res) => {
          if (chrome.runtime.lastError) {
            setStatus(chrome.runtime.lastError.message, "err");
            return;
          }
          if (res?.ok) {
            setStatus(res.result?.relative_path || "归档完成", "ok");
          } else {
            setStatus(res?.error || "失败", "err");
          }
        });
      }
    );
  });
});
