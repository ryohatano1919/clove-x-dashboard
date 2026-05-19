// Injected by scripts/server.py to add persona-edit and post-regenerate UI
// onto the existing static dashboard pages.
(function () {
  const css = `
    .ce-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
    .ce-btn {
      cursor: pointer;
      background: #eef5fb;
      color: #1d9bf0;
      border: 1px solid #cfe3f4;
      padding: 6px 10px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .ce-btn:hover { background: #d8e9f5; }
    .ce-btn[disabled] { opacity: 0.55; cursor: progress; }
    .ce-btn.ce-danger { color: #b73e3e; border-color: #f0c8c8; background: #fdf1f1; }
    .ce-btn.ce-primary { background: #1d9bf0; color: #fff; border-color: #1d9bf0; }
    .ce-btn.ce-primary:hover { background: #1a8cd8; }
    .ce-status { font-size: 0.75rem; color: #888; align-self: center; }
    .ce-status.ok { color: #2e7d32; }
    .ce-status.err { color: #b73e3e; }

    .ce-modal-backdrop {
      position: fixed; inset: 0; background: rgba(0,0,0,0.45);
      display: flex; align-items: center; justify-content: center;
      z-index: 9999; padding: 16px;
    }
    .ce-modal {
      background: #fff; border-radius: 14px; max-width: 760px; width: 100%;
      max-height: 90vh; display: flex; flex-direction: column;
      box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    }
    .ce-modal header { padding: 14px 18px; border-bottom: 1px solid #eee;
      display: flex; justify-content: space-between; align-items: center; }
    .ce-modal header h2 { font-size: 1rem; margin: 0; color: #1d9bf0; }
    .ce-modal textarea {
      flex: 1; border: none; padding: 14px 18px; font-family: ui-monospace,
      SFMono-Regular, Menlo, monospace; font-size: 0.85rem; resize: none;
      outline: none; line-height: 1.55;
    }
    .ce-modal footer {
      padding: 12px 18px; border-top: 1px solid #eee;
      display: flex; gap: 8px; justify-content: flex-end; align-items: center;
    }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  function el(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "onclick") e.addEventListener("click", v);
      else e.setAttribute(k, v);
    }
    for (const c of [].concat(children)) {
      if (c == null) continue;
      e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return e;
  }

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(path, opts);
    const text = await r.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { error: text }; }
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  function buildIntentUrl(text) {
    return "https://twitter.com/intent/tweet?text=" + encodeURIComponent(text);
  }

  function getTodayJst() {
    const d = new Date(Date.now() + 9 * 60 * 60 * 1000);
    return d.toISOString().slice(0, 10);
  }

  // Replicates load_persona_summary() in scripts/render_dashboard.py:
  // pull the lines under "## 基本プロフィール" up to the next "## " heading,
  // keep the first 7 non-empty lines.
  function extractProfileSummary(md) {
    const lines = md.split(/\r?\n/);
    const out = [];
    let capturing = false;
    for (const line of lines) {
      if (line.startsWith("## 基本プロフィール")) { capturing = true; continue; }
      if (capturing) {
        if (line.startsWith("## ")) break;
        const t = line.trim();
        if (t) out.push(t);
      }
    }
    return out.slice(0, 7).join("\n");
  }

  function updateProfileDiv(card, md) {
    const profileEl = card.querySelector(".profile");
    if (!profileEl) return;
    const summary = extractProfileSummary(md) || "(プロフィール未取得)";
    profileEl.innerHTML = "";
    summary.split("\n").forEach((line, i) => {
      if (i > 0) profileEl.appendChild(document.createElement("br"));
      profileEl.appendChild(document.createTextNode(line));
    });
  }

  // -------- Persona edit modal --------
  function openPersonaModal(slug, onSaved) {
    const backdrop = el("div", { class: "ce-modal-backdrop" });
    const modal = el("div", { class: "ce-modal" });
    const title = el("h2", {}, `${slug} ペルソナ編集`);
    const closeBtn = el("button", { class: "ce-btn", onclick: () => backdrop.remove() }, "×");
    const header = el("header", {}, [title, closeBtn]);

    const ta = el("textarea", { spellcheck: "false" });
    ta.value = "読み込み中…";
    ta.disabled = true;
    ta.style.minHeight = "55vh";

    const status = el("span", { class: "ce-status" }, "");
    const cancel = el("button", { class: "ce-btn", onclick: () => backdrop.remove() }, "キャンセル");
    const save = el("button", { class: "ce-btn ce-primary" }, "保存");
    const footer = el("footer", {}, [status, cancel, save]);

    modal.appendChild(header);
    modal.appendChild(ta);
    modal.appendChild(footer);
    backdrop.appendChild(modal);
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
    document.body.appendChild(backdrop);

    api("GET", `/api/persona/${encodeURIComponent(slug)}`)
      .then((d) => { ta.value = d.content || ""; ta.disabled = false; ta.focus(); })
      .catch((e) => { ta.value = "読み込み失敗: " + e.message; });

    save.addEventListener("click", async () => {
      save.disabled = true;
      status.className = "ce-status";
      status.textContent = "保存中…";
      try {
        await api("PUT", `/api/persona/${encodeURIComponent(slug)}`, { content: ta.value });
        status.className = "ce-status ok";
        status.textContent = "保存しました";
        if (onSaved) onSaved(ta.value);
        setTimeout(() => backdrop.remove(), 600);
      } catch (e) {
        status.className = "ce-status err";
        status.textContent = "失敗: " + e.message;
        save.disabled = false;
      }
    });
  }

  // -------- Regenerate post --------
  async function regeneratePost(card, slug, statusEl) {
    statusEl.className = "ce-status";
    statusEl.textContent = "生成中…(10〜30秒)";
    try {
      const d = await api("POST", `/api/generate/${encodeURIComponent(slug)}?date=${getTodayJst()}`);
      const postEl = card.querySelector(".post-text");
      if (postEl) postEl.textContent = d.text;
      const cc = card.querySelector(".char-count");
      if (cc) cc.textContent = `${[...d.text].length}字`;
      // refresh intent URLs
      card.querySelectorAll("a.post-button").forEach((a) => {
        a.href = buildIntentUrl(d.text);
      });
      statusEl.className = "ce-status ok";
      statusEl.textContent = "更新しました";
      setTimeout(() => { statusEl.textContent = ""; }, 2500);
    } catch (e) {
      statusEl.className = "ce-status err";
      statusEl.textContent = "失敗: " + e.message;
    }
  }

  // -------- Wire each card --------
  function enhanceCard(card) {
    const slug = card.getAttribute("data-slug");
    if (!slug) return;
    if (card.querySelector(".ce-actions")) return;

    const status = el("span", { class: "ce-status" }, "");
    const editBtn = el("button", {
      class: "ce-btn",
      onclick: () => openPersonaModal(slug, (newContent) => updateProfileDiv(card, newContent)),
    }, "✏ ペルソナ編集");
    const regenBtn = el("button", {
      class: "ce-btn",
      onclick: async (e) => {
        e.currentTarget.disabled = true;
        await regeneratePost(card, slug, status);
        e.currentTarget.disabled = false;
      },
    }, "🔄 投稿を再生成");

    const actions = el("div", { class: "ce-actions" }, [editBtn, regenBtn, status]);

    const postText = card.querySelector(".post-text");
    if (postText && postText.parentNode) {
      postText.parentNode.insertBefore(actions, postText.nextSibling);
    } else {
      card.appendChild(actions);
    }
  }

  function run() {
    document.querySelectorAll("article.card[data-slug]").forEach(enhanceCard);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
