(function () {
  const BTN_ID = "lumis-archive-btn";
  const TOAST_ID = "lumis-archive-toast";

  function extractVideoUrl() {
    const href = location.href;
    try {
      const u = new URL(href);
      const host = u.hostname.toLowerCase();

      if (host.includes("youtube.com") && u.pathname === "/watch") {
        const v = u.searchParams.get("v");
        if (v) return `https://www.youtube.com/watch?v=${v}`;
      }
      if (host === "youtu.be") {
        const id = u.pathname.replace(/^\//, "").split("/")[0];
        if (id) return `https://www.youtube.com/watch?v=${id}`;
      }
      if (host.includes("bilibili.com") && u.pathname.includes("/video/")) {
        return `${u.origin}${u.pathname.split("?")[0]}`;
      }
      if (host.includes("xiaohongshu.com")) {
        if (u.pathname.includes("/discovery/item/") || u.pathname.includes("/explore/")) {
          return href.split("#")[0];
        }
      }
      if (host.includes("xhslink.com")) {
        return href.split("#")[0];
      }
      if (host.includes("weixin.qq.com") && u.pathname.includes("/sph/")) {
        return href.split("#")[0];
      }
      if (host.includes("channels.weixin.qq.com")) {
        return href.split("#")[0];
      }
      if (host.includes("mp.weixin.qq.com") && u.pathname.startsWith("/s")) {
        return href.split("#")[0];
      }
      if (host.includes("douyin.com") && (u.pathname.includes("/video/") || u.pathname.includes("/note/"))) {
        return href.split("#")[0];
      }
    } catch {
      /* ignore */
    }
    return href.split("#")[0];
  }

  window.extractVideoUrl = extractVideoUrl;

  function showToast(text, kind) {
    let el = document.getElementById(TOAST_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = TOAST_ID;
      document.documentElement.appendChild(el);
    }
    el.className = kind === "error" ? "lumis-toast lumis-toast-error" : "lumis-toast";
    el.textContent = text;
    el.style.display = "block";
    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(() => {
      el.style.display = "none";
    }, kind === "error" ? 12000 : 10000);
  }

  function platformLabel() {
    const host = location.hostname.toLowerCase();
    if (host.includes("youtube") || host === "youtu.be") return "YouTube";
    if (host.includes("bilibili")) return "B站";
    if (host.includes("xiaohongshu") || host.includes("xhslink")) return "小红书";
    if (host.includes("weixin.qq.com") && location.pathname.includes("/sph/")) return "视频号";
    if (host.includes("channels.weixin")) return "视频号";
    if (host.includes("mp.weixin.qq.com")) return "公众号";
    if (host.includes("douyin")) return "抖音";
    return "内容";
  }

  function ensureButton() {
    if (document.getElementById(BTN_ID)) return;

    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.title = "Clip-to-Brain：解析 + 转写 + 结构化笔记";
    btn.innerHTML = `<span class="lumis-btn-icon">📥</span><span class="lumis-btn-text">丢链归档</span>`;
    btn.addEventListener("click", onClick);
    document.documentElement.appendChild(btn);
  }

  function setButtonState(state, detail) {
    const btn = document.getElementById(BTN_ID);
    if (!btn) return;
    btn.classList.remove("lumis-busy", "lumis-done", "lumis-error");
    const text = btn.querySelector(".lumis-btn-text");
    if (state === "idle") {
      text.textContent = "丢链归档";
    } else if (state === "busy") {
      btn.classList.add("lumis-busy");
      text.textContent = "处理中…";
    } else if (state === "done") {
      btn.classList.add("lumis-done");
      text.textContent = detail ? "已入库 ✓" : "完成 ✓";
    } else if (state === "error") {
      btn.classList.add("lumis-error");
      text.textContent = "失败 ✗";
      btn.title = detail || "归档失败";
    }
  }

  function onClick() {
    const btn = document.getElementById(BTN_ID);
    if (btn?.classList.contains("lumis-busy")) return;

    const url = extractVideoUrl();
    setButtonState("busy");
    showToast(`正在提交 ${platformLabel()} 归档…`);

    chrome.runtime.sendMessage({ type: "INGEST_URL", url }, (res) => {
      if (chrome.runtime.lastError) {
        const err = chrome.runtime.lastError.message || "扩展通信失败";
        setButtonState("error", err);
        showToast(`${err} — 请到 chrome://extensions 重新加载扩展`, "error");
        setTimeout(() => setButtonState("idle"), 8000);
        return;
      }
      if (!res?.ok) {
        setButtonState("error", res?.error);
        showToast(res?.error || "提交失败", "error");
        setTimeout(() => setButtonState("idle"), 8000);
        return;
      }
      if (res.queued) {
        showToast("已提交！解析/转写/萃取中，完成后会通知（约 1–5 分钟）");
        return;
      }
      setButtonState("done", res.result?.relative_path);
      showToast(`已入库：${res.result?.relative_path || "成功"}`);
      setTimeout(() => setButtonState("idle"), 8000);
    });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "INGEST_PROGRESS") {
      setButtonState("busy");
      showToast(msg.message || "处理中…");
    }
    if (msg.type === "INGEST_DONE") {
      setButtonState("done", msg.displayName || msg.result?.relative_path);
      const name = msg.displayName || msg.result?.relative_path || "成功";
      let toast = `已入库：${name}`;
      if (msg.result?.remix_angles?.length) {
        toast += `\n💡 ${msg.result.remix_angles[0]}`;
      }
      showToast(toast);
      setTimeout(() => setButtonState("idle"), 12000);
    }
    if (msg.type === "INGEST_ERROR") {
      setButtonState("error", msg.error);
      showToast(msg.error || "归档失败", "error");
      setTimeout(() => setButtonState("idle"), 8000);
    }
  });

  function init() {
    ensureButton();
    setButtonState("idle");
    const label = platformLabel();
    const btn = document.getElementById(BTN_ID);
    if (btn) btn.title = `${label} · Clip-to-Brain 丢链归档`;

    chrome.runtime.sendMessage({ type: "PING" }, (res) => {
      if (chrome.runtime.lastError || !res?.ok) {
        showToast("扩展后台未就绪，请重新加载扩展", "error");
      }
    });
  }

  init();

  let lastPath = location.pathname + location.search;
  const observer = new MutationObserver(() => {
    const now = location.pathname + location.search;
    if (now !== lastPath) {
      lastPath = now;
      setButtonState("idle");
      ensureButton();
    }
  });
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
