const state = {
  pageMode: "landing", // "landing" | "workspace"
  activeView: "chat",
  activeProjectId: null,
  activeProject: null,
  activeTab: "research",
  selectedFormat: "9:16",
  selectedStyle: "Viral Typography",
  selectedModel: "instant",
  models: [],
  voices: {},
  pollTimer: null,
  chatSessions: [],
  currentChatId: null,
  chatHistory: [],
  authToken: localStorage.getItem("nx_auth_token") || "",
  guestId: localStorage.getItem("nx_guest_id") || (() => {
    const id = "g_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("nx_guest_id", id);
    return id;
  })(),
  currentUser: null,
  authMode: "login",
  authConfig: { google_client_id: "", otp_required: false },
  showcaseItems: [],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(text) {
  // Parse simple pipe Markdown tables before inline formatting
  const lines = String(text ?? "").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i].trim().startsWith("|") && i + 1 < lines.length && /^\|[\s:-]+\|/.test(lines[i + 1].trim())) {
      const headers = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        i++;
      }
      const fmtCell = (c) => esc(c).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
      const ths = headers.map((h) => `<th>${fmtCell(h)}</th>`).join("");
      const trs = rows.map((r) => `<tr>${r.map((c) => `<td>${fmtCell(c)}</td>`).join("")}</tr>`).join("");
      blocks.push(`<table class="md-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`);
    } else {
      blocks.push(lines[i]);
      i++;
    }
  }
  let s = blocks
    .map((b) => (b.startsWith("<table ") ? b : esc(b)))
    .join("\n");
  s = s.replace(/```(?:\w*)\n([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
  s = s.replace(/^---+$/gm, "<hr style='border:none;border-top:1px solid var(--border);margin:12px 0;'/>");
  s = s.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "<em>$1</em>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/(^|\n)\s*[-*]\s+/g, "$1• ");
  return `<div class="md-body">${s}</div>`;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  $("#toastStack").appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

async function api(url, opts = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Guest-Id": state.guestId,
    ...(opts.headers || {}),
  };
  if (state.authToken) headers["Authorization"] = `Bearer ${state.authToken}`;
  const res = await fetch(url, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

window.openLightbox = (src, caption = "") => {
  $("#lightboxImg").src = src;
  $("#lightboxCap").textContent = caption;
  $("#lightbox").classList.remove("hidden");
};

function copyText(txt, label = "Copied") {
  navigator.clipboard.writeText(txt).then(() => toast(`${label} copied.`));
}

/* ==================== PAGE & VIEW NAVIGATION ==================== */
function openLanding() {
  state.pageMode = "landing";
  $("#landingView").classList.remove("hidden");
  $("#workspaceView").classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "instant" });
  triggerReveals();
}

function openWorkspace(viewName = "chat") {
  state.pageMode = "workspace";
  $("#landingView").classList.add("hidden");
  $("#workspaceView").classList.remove("hidden");
  switchView(viewName);
  if (viewName === "chat") setTimeout(() => $("#chatInput")?.focus(), 60);
}

function switchView(viewName) {
  state.activeView = viewName;
  $$(".mode-tab").forEach((t) => t.classList.toggle("active", t.dataset.view === viewName));
  $$(".rail-btn[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === viewName));
  $$(".view-panel").forEach((v) => v.classList.toggle("active", v.id === `view-${viewName}`));
}

/* ==================== SCROLL REVEAL ==================== */
function triggerReveals() {
  const els = $$(".reveal");
  if (!("IntersectionObserver" in window)) {
    els.forEach((el) => el.classList.add("visible"));
    return;
  }
  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add("visible");
          obs.unobserve(en.target);
        }
      });
    },
    { threshold: 0.01, rootMargin: "120px 0px" }
  );
  els.forEach((el) => obs.observe(el));
  // Safety guarantee: ensure every section is 100% visible even on fast anchor jumps
  setTimeout(() => els.forEach((el) => el.classList.add("visible")), 450);
}

/* ==================== BOOTSTRAP ==================== */
async function initStudio() {
  loadSavedChats();
  bindEvents();
  triggerReveals();
  await Promise.all([loadMeta(), loadShowcase(), loadProjects(), loadCurrentUser()]);
  loadInitialTrends();

  // Direct route support: /login, /signup, /chat, /studio
  const p = window.location.pathname.toLowerCase();
  if (p === "/login") openAuthModal("login");
  else if (p === "/signup") openAuthModal("signup");
  else if (p === "/chat") openWorkspace("chat");
  else if (p === "/studio") openWorkspace("factory");
}

/* ==================== HOMEPAGE SHOWCASE GALLERY ==================== */
async function loadShowcase() {
  const grid = $("#showcaseGrid");
  if (!grid) return;
  try {
    const data = await api("/api/showcase");
    const items = data.items || [];
    state.showcaseItems = items;
    if (!items.length) {
      grid.innerHTML = `<div class="showcase-skeleton">Create your first studio video to see it featured here.</div>`;
      return;
    }
    grid.innerHTML = items
      .map(
        (it, idx) => `
      <article class="showcase-card" data-sh-idx="${idx}">
        <div class="showcase-thumb-wrap">
          ${
            it.poster_url
              ? `<img src="${esc(it.poster_url)}" alt="${esc(it.title)}" loading="lazy" />`
              : `<video src="${esc(it.video_url)}" muted playsinline preload="metadata"></video>`
          }
          <div class="showcase-overlay">
            <div class="sc-badges">
              <span class="sc-pill">${esc(it.badge || it.style)}</span>
              <span class="sc-pill">${esc(it.language)} • ${esc(it.duration)}</span>
            </div>
            <div class="sc-play-circle" aria-label="Play video">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"/></svg>
            </div>
            <div></div>
          </div>
        </div>
        <div class="showcase-body">
          <div class="showcase-title">${esc(it.title)}</div>
          <div class="showcase-meta">${esc(it.subtitle)}</div>
        </div>
      </article>`
      )
      .join("");

    $$(".showcase-card").forEach((card) => {
      card.onclick = () => openVideoModal(state.showcaseItems[parseInt(card.dataset.shIdx, 10)]);
    });
  } catch {
    grid.innerHTML = `<div class="showcase-skeleton">Unable to load gallery right now.</div>`;
  }
}

function openVideoModal(item) {
  if (!item) return;
  $("#vmTitle").textContent = item.title;
  $("#vmMeta").textContent = `${item.style} • ${item.language} • ${item.duration}`;
  const player = $("#vmPlayer");
  player.src = item.video_url;
  if (item.poster_url) player.poster = item.poster_url;
  $("#videoModal").classList.remove("hidden");
  player.play().catch(() => {});
}

function closeVideoModal() {
  const player = $("#vmPlayer");
  player.pause();
  player.removeAttribute("src");
  player.load();
  $("#videoModal").classList.add("hidden");
}

/* ==================== AUTH & QUOTA ==================== */
async function loadCurrentUser() {
  if (!state.authToken) {
    renderAuthUI();
    return;
  }
  try {
    const res = await api("/api/auth/me");
    state.currentUser = res.user || null;
    if (!state.currentUser) {
      state.authToken = "";
      localStorage.removeItem("nx_auth_token");
    }
  } catch {
    state.currentUser = null;
  }
  renderAuthUI();
}

function renderAuthUI() {
  const u = state.currentUser;
  $("#guestFooter").classList.toggle("hidden", !!u);
  $("#userFooter").classList.toggle("hidden", !u);
  $("#btnTopLogin").classList.toggle("hidden", !!u);
  $("#landNavGuest").classList.toggle("hidden", !!u);
  $("#landNavUser").classList.toggle("hidden", !u);

  const welcomeTitle = $(".welcome-title");
  const quotaPill = $("#studioQuotaPill");
  if (u) {
    const firstName = u.name.split(" ")[0];
    $("#userAvatar").textContent = u.initials || "U";
    $("#userName").textContent = u.name;
    const planLabel = u.plan === "pro" ? "Creator Pro" : u.plan === "agency" ? "Agency Studio" : "Free Trial";
    $("#userPlanLabel").textContent = planLabel;
    if (welcomeTitle) welcomeTitle.textContent = `Good to see you, ${firstName}`;
    if (quotaPill) {
      if (u.free_videos_remaining === null) {
        quotaPill.textContent = `${planLabel} • Unlimited`;
      } else if (u.free_videos_remaining > 0) {
        quotaPill.textContent = `${u.free_videos_remaining} Free Video Remaining`;
      } else {
        quotaPill.textContent = "Free Trial Used • Upgrade";
      }
    }
  } else {
    if (welcomeTitle) welcomeTitle.textContent = "Where should we start?";
    if (quotaPill) quotaPill.textContent = "1 Free Trial Video ($0)";
  }
}

function openAuthModal(mode = "login") {
  state.authMode = mode;
  $("#authModal").classList.remove("hidden");
  $("#authError").classList.add("hidden");
  switchAuthMode(mode);
}

function switchAuthMode(mode) {
  state.authMode = mode;
  $$(".auth-tab").forEach((t) => t.classList.toggle("active", t.dataset.authMode === mode));
  const isSignup = mode === "signup";
  $("#authNameWrap").classList.toggle("hidden", !isSignup);
  $("#realEmailHint")?.classList.toggle("hidden", !isSignup);
  const showOtp = isSignup && !!state.authConfig.otp_required;
  $("#btnSendOtp")?.classList.toggle("hidden", !showOtp);
  $("#authOtpWrap")?.classList.toggle("hidden", !showOtp);
  $("#authInfo")?.classList.add("hidden");
  $("#authError")?.classList.add("hidden");
  $("#authTitle").textContent = isSignup ? "Create your account" : "Welcome back";
  $("#authSubtitle").textContent = isSignup
    ? "Sign up with Google or a real email to unlock your free Full HD studio video ($0)."
    : "Sign in with Google or your email to access Video Studio & saved projects.";
  $("#btnAuthSubmit").textContent = isSignup ? "Create account" : "Sign in";
  const swFoot = $("#authSwitchFoot");
  if (swFoot) {
    swFoot.querySelector("span").textContent = isSignup ? "Already have an account?" : "New to NEXUS?";
    $("#btnQuickSwitchAuth").textContent = isSignup ? "Sign in instead" : "Create a free account";
  }
}

function initGoogleSignIn() {
  const cid = state.authConfig.google_client_id;
  const fallbackBtn = $("#btnGoogleFallback");
  const container = $("#googleBtnContainer");
  if (!cid || !window.google || !window.google.accounts || !window.google.accounts.id) {
    if (fallbackBtn) {
      fallbackBtn.classList.remove("hidden");
      fallbackBtn.onclick = () => {
        if (!cid) {
          toast("Google Sign-In activates as soon as GOOGLE_CLIENT_ID is added in settings. Use your real email below!");
        } else {
          window.google?.accounts?.id?.prompt();
        }
      };
    }
    return;
  }
  window.google.accounts.id.initialize({
    client_id: cid,
    callback: async (response) => {
      try {
        const res = await api("/api/auth/google", { method: "POST", body: JSON.stringify({ credential: response.credential }) });
        state.authToken = res.token;
        state.currentUser = res.user;
        localStorage.setItem("nx_auth_token", res.token);
        $("#authModal").classList.add("hidden");
        renderAuthUI();
        toast(`Signed in with Google as ${res.user.name}!`);
        if (state.pageMode === "landing") openWorkspace("chat");
      } catch (err) {
        const errBox = $("#authError");
        errBox.textContent = err.message;
        errBox.classList.remove("hidden");
      }
    },
  });
  if (container) {
    container.innerHTML = "";
    window.google.accounts.id.renderButton(container, { theme: "outline", size: "large", width: 380, text: "continue_with", shape: "pill" });
    if (fallbackBtn) fallbackBtn.classList.add("hidden");
  }
}

/* ==================== METADATA, MODELS & 38 GLOBAL VOICES ==================== */
async function loadMeta() {
  try {
    const meta = await api("/api/meta");
    state.models = meta.models || [
      { id: "instant", name: "Instant", tagline: "Ultra-fast replies for everyday chat" },
      { id: "fast", name: "Fast", tagline: "Balanced intelligence & creative studio" },
      { id: "medium", name: "Medium", tagline: "Deep reasoning, strategy & studio scripts" },
    ];
    state.voices = meta.voices || {};
    state.authConfig = meta.auth_config || { google_client_id: "", otp_required: false };
    renderModelControls();
    populateVoiceSelect();
    setTimeout(initGoogleSignIn, 500);
  } catch (e) {}
}

function populateVoiceSelect() {
  const sel = $("#voiceSelect");
  if (!sel) return;
  const legacyKeys = new Set(["urdu_male", "urdu_female", "hindi_male", "hindi_female", "en_male", "en_female"]);
  const grouped = {};
  Object.entries(state.voices).forEach(([k, v]) => {
    if (legacyKeys.has(k)) return;
    const g = v.group || "Global";
    if (!grouped[g]) grouped[g] = [];
    grouped[g].push({ key: k, label: v.label });
  });

  let html = `<option value="auto" selected>Auto Match Selected Language</option>`;
  Object.entries(grouped).forEach(([grp, list]) => {
    html += `<optgroup label="${esc(grp)} Voices">` +
      list.map((it) => `<option value="${esc(it.key)}">${esc(it.label)}</option>`).join("") +
      `</optgroup>`;
  });
  sel.innerHTML = html;
}

function getSelectedModelObj() {
  return state.models.find((m) => m.id === state.selectedModel) || state.models[0] || { id: "instant", name: "Instant" };
}

function renderModelControls() {
  const current = getSelectedModelObj();
  $("#activeModelLabel").textContent = current.name;

  const menu = $("#modelDropdownMenu");
  menu.innerHTML = state.models
    .map(
      (m) => `
      <button class="md-item ${m.id === state.selectedModel ? "active" : ""}" data-mid="${esc(m.id)}">
        <span class="md-item-title"><span>${esc(m.name)}</span><span>${m.id === state.selectedModel ? "✓" : ""}</span></span>
        <span class="md-item-sub">${esc(m.tagline || "")}</span>
      </button>`
    )
    .join("");

  $$("#modelDropdownMenu .md-item").forEach((b) => {
    b.onclick = () => {
      state.selectedModel = b.dataset.mid;
      renderModelControls();
      menu.classList.add("hidden");
    };
  });

  const pills = $("#studioModelPills");
  if (pills) {
    pills.innerHTML = state.models
      .map((m) => `<button class="seg-pill ${m.id === state.selectedModel ? "active" : ""}" data-mid="${esc(m.id)}">${esc(m.name)}</button>`)
      .join("");
    $$("#studioModelPills .seg-pill").forEach((b) => {
      b.onclick = () => {
        state.selectedModel = b.dataset.mid;
        renderModelControls();
      };
    });
  }
}

/* ==================== LOCAL CHAT HISTORY ==================== */
function loadSavedChats() {
  try {
    state.chatSessions = JSON.parse(localStorage.getItem("nx_chats_v3") || "[]");
  } catch {
    state.chatSessions = [];
  }
  renderChatSidebar();
}

function saveChats() {
  localStorage.setItem("nx_chats_v3", JSON.stringify(state.chatSessions.slice(0, 25)));
  renderChatSidebar();
}

function renderChatSidebar() {
  const list = $("#chatHistoryList");
  if (!state.chatSessions.length) {
    list.innerHTML = `<div class="sb-empty">No recent chats</div>`;
    return;
  }
  list.innerHTML = state.chatSessions
    .map(
      (c) => `
    <button class="sb-item ${state.currentChatId === c.id ? "active" : ""}" data-cid="${esc(c.id)}">
      <span style="overflow:hidden; text-overflow:ellipsis;">${esc(c.title)}</span>
    </button>`
    )
    .join("");
  $$("#chatHistoryList .sb-item").forEach((b) => {
    b.onclick = () => openSavedChat(b.dataset.cid);
  });
}

function startNewChat() {
  state.currentChatId = null;
  state.chatHistory = [];
  $("#chatMessages").innerHTML = "";
  $("#chatStage").classList.add("is-empty");
  openWorkspace("chat");
  renderChatSidebar();
  $("#chatInput").focus();
}

function openSavedChat(cid) {
  const found = state.chatSessions.find((c) => c.id === cid);
  if (!found) return;
  state.currentChatId = cid;
  state.chatHistory = found.messages || [];
  const wrap = $("#chatMessages");
  wrap.innerHTML = "";
  for (const m of state.chatHistory) {
    appendChatBubble(m.role, m.html || esc(m.content));
  }
  $("#chatStage").classList.toggle("is-empty", state.chatHistory.length === 0);
  openWorkspace("chat");
  renderChatSidebar();
}

/* ==================== ULTRA-FAST HUMAN-LIKE STREAMING CHAT ==================== */
function appendChatBubble(role, html) {
  $("#chatStage").classList.remove("is-empty");
  const wrap = $("#chatMessages");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = `<div class="msg-bubble">${html}</div>`;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
  return div;
}

async function sendChat(overrideMsg = null) {
  const input = $("#chatInput");
  const msg = (overrideMsg !== null ? overrideMsg : input.value).trim();
  if (!msg) return;
  if (overrideMsg === null) {
    input.value = "";
    input.style.height = "auto";
  }

  openWorkspace("chat");
  appendChatBubble("user", esc(msg));

  if (!state.currentChatId) {
    state.currentChatId = "chat_" + Date.now();
    state.chatSessions.unshift({ id: state.currentChatId, title: msg.slice(0, 38), messages: [] });
  }
  state.chatHistory.push({ role: "user", content: msg });

  const sendBtn = $("#btnSendChat");
  sendBtn.disabled = true;
  const thinkingEl = appendChatBubble(
    "assistant",
    `<div class="activity-pill"><span class="act-dot"></span><span class="act-text">Thinking...</span></div><div class="reply-body"></div>`
  );
  const bubble = thinkingEl.querySelector(".msg-bubble");
  const actPill = bubble.querySelector(".activity-pill");
  const actText = bubble.querySelector(".act-text");
  const replyBody = bubble.querySelector(".reply-body");

  try {
    const reqHeaders = { "Content-Type": "application/json", "X-Guest-Id": state.guestId };
    if (state.authToken) reqHeaders["Authorization"] = `Bearer ${state.authToken}`;
    const resp = await fetch("/api/chat/stream", {
      method: "POST",
      headers: reqHeaders,
      body: JSON.stringify({
        message: msg,
        history: state.chatHistory.slice(-14).map((m) => ({ role: m.role, content: m.content })),
        active_project_id: state.activeProjectId,
        model_profile: state.selectedModel,
        force_browser: false,
      }),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalText = "";
    let finalHtml = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const chunk of parts) {
        const line = chunk.trim();
        if (!line.startsWith("data:")) continue;
        let ev;
        try {
          ev = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }

        if (ev.type === "activity" || ev.type === "status") {
          actText.textContent = ev.text || "Thinking...";
        } else if (ev.type === "final") {
          finalText = ev.reply || "Done.";
          actPill.classList.add("hidden");

          if (ev.action === "login_required") {
            finalHtml = `${renderMarkdown(finalText)}
              <div class="chat-action-card">
                <div><strong>Sign In Required for Video Studio</strong><div style="font-size:12px; color:var(--text-2);">Chat is 100% free! Sign in with Google or a real email to create your free HD video.</div></div>
                <button class="btn-primary-pill btn-sm" onclick="openAuthModal('signup')">Sign in / Sign up</button>
              </div>`;
          } else if (ev.action === "quota_limit") {
            finalHtml = `${renderMarkdown(finalText)}
              <div class="chat-action-card">
                <div><strong>Free Video Limit Reached</strong><div style="font-size:12px; color:var(--text-2);">Upgrade to Creator Pro for unlimited Full HD global videos.</div></div>
                <button class="btn-primary-pill btn-sm" onclick="switchView('plans')">View Plans</button>
              </div>`;
          } else if (ev.action === "start_video" && ev.project) {
            state.activeProjectId = ev.project.id;
            state.activeProject = ev.project;
            loadProjects();
            loadCurrentUser();
            clearTimeout(state.pollTimer);
            state.pollTimer = setTimeout(refreshActiveProject, 1200);
            finalHtml = `${renderMarkdown(finalText)}
              <div class="chat-action-card">
                <div><strong>5-Agent Video Studio Launched</strong><div style="font-size:12px; color:var(--text-2);">${esc(ev.project.topic)} (${esc(ev.project.format)} • ~${ev.project.duration_sec}s)</div></div>
                <button class="btn-primary-pill btn-sm" onclick="openProjectFromChat('${esc(ev.project.id)}')">Open Video Studio</button>
              </div>`;
          } else if (ev.action === "edit_scene" && ev.project) {
            state.activeProject = ev.project;
            clearTimeout(state.pollTimer);
            state.pollTimer = setTimeout(refreshActiveProject, 1200);
            finalHtml = `${renderMarkdown(finalText)}
              <div class="chat-action-card">
                <div><strong>Scene Updated &amp; Re-Rendering</strong></div>
                <button class="btn-outline-sm" onclick="openProjectFromChat('${esc(ev.project.id)}')">Open Studio</button>
              </div>`;
          } else {
            const safeAttr = encodeURIComponent(finalText);
            finalHtml = `${renderMarkdown(finalText)}
              <div class="msg-actions-row">
                <button class="msg-copy-btn" onclick="copyEncoded('${safeAttr}')">Copy</button>
              </div>`;
          }

          replyBody.innerHTML = finalHtml;
          $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
        } else if (ev.type === "error") {
          actPill.classList.add("hidden");
          finalText = ev.message || "Something went wrong. Please try again.";
          replyBody.innerHTML = `<span style="color:var(--rose);">${esc(finalText)}</span>`;
        }
      }
    }

    state.chatHistory.push({ role: "assistant", content: finalText, html: bubble.innerHTML });
    const sess = state.chatSessions.find((s) => s.id === state.currentChatId);
    if (sess) sess.messages = state.chatHistory;
    saveChats();
  } catch (e) {
    bubble.innerHTML = `<span style="color:var(--rose);">Error: ${esc(e.message)}</span>`;
  } finally {
    sendBtn.disabled = false;
  }
}

window.openAuthModal = openAuthModal;
window.copyEncoded = (enc) => copyText(decodeURIComponent(enc), "Response");
window.openProjectFromChat = (pid) => selectProject(pid);
window.switchView = switchView;

/* ==================== PROJECTS & 5-AGENT VIDEO STUDIO ==================== */
async function loadProjects() {
  try {
    const data = await api("/api/projects");
    const list = $("#projectList");
    const projects = data.projects || [];
    if (!projects.length) {
      list.innerHTML = `<div class="sb-empty">No videos yet</div>`;
      return;
    }
    list.innerHTML = projects
      .slice(0, 12)
      .map(
        (p) => `
      <button class="sb-item ${state.activeProjectId === p.id ? "active" : ""}" data-pid="${esc(p.id)}">
        <span style="overflow:hidden; text-overflow:ellipsis;">${esc(p.topic)}</span>
        <span class="sb-item-sub">${p.status === "completed" ? "✓" : p.status === "running" ? "●" : esc(p.format)}</span>
      </button>`
      )
      .join("");
    $$("#projectList .sb-item").forEach((b) => (b.onclick = () => selectProject(b.dataset.pid)));
  } catch (e) {}
}

async function selectProject(pid) {
  state.activeProjectId = pid;
  openWorkspace("factory");
  await refreshActiveProject();
  loadProjects();
}

async function refreshActiveProject() {
  if (!state.activeProjectId) return;
  try {
    const proj = await api(`/api/projects/${state.activeProjectId}`);
    state.activeProject = proj;
    renderProjectState(proj);
    if (proj.status === "running" || proj.status === "queued") {
      clearTimeout(state.pollTimer);
      state.pollTimer = setTimeout(refreshActiveProject, 1800);
    } else {
      loadProjects();
      loadShowcase();
    }
  } catch (e) {}
}

async function launchProduction() {
  if (!state.currentUser) {
    openAuthModal("signup");
    toast("Sign in with Google or a real email to create your free HD video.");
    return;
  }
  const topic = $("#topicInput").value.trim();
  if (!topic) {
    toast("Please enter a video topic first.");
    $("#topicInput").focus();
    return;
  }
  const btn = $("#btnLaunchTeam");
  btn.disabled = true;
  btn.querySelector("span").textContent = "Launching...";
  try {
    const proj = await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({
        topic,
        format: state.selectedFormat,
        language: $("#languageSelect").value,
        voice: $("#voiceSelect").value,
        duration_sec: parseInt($("#durationSelect").value, 10),
        visual_style: state.selectedStyle,
        caption_animation: $("#captionAnimSelect").value,
        visual_mode: $("#visualModeSelect").value,
        model_profile: state.selectedModel,
        approval_mode: $("#chkApproval").checked,
        use_live_browser: false,
        enable_captions: $("#chkCaptions").checked,
        enable_music: $("#chkMusic").checked,
      }),
    });
    state.activeProjectId = proj.id;
    state.activeProject = proj;
    state.activeTab = "research";
    renderProjectState(proj);
    loadProjects();
    loadCurrentUser();
    toast("5-Agent Video Studio launched.");
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(refreshActiveProject, 1200);
  } catch (e) {
    toast(e.message);
    if (e.status === 401) openAuthModal("signup");
    else if (e.status === 402) switchView("plans");
  } finally {
    btn.disabled = false;
    btn.querySelector("span").textContent = "Create Video";
  }
}

function renderProjectState(proj) {
  const badge = $("#projectStatusBadge");
  badge.className = `status-pill ${proj.status}`;
  badge.textContent = `${proj.status.toUpperCase()} • ${proj.topic.slice(0, 34)}`;

  const emps = proj.employees || {};
  let doneCount = 0;
  let workingBoost = 0;
  ["emp1", "emp2", "emp3", "emp4", "emp5"].forEach((ek, i) => {
    const info = emps[ek] || { status: "idle" };
    const card = $(`.step-card[data-emp="${ek}"]`);
    const orb = $(`#orb-${ek}`);
    const meta = $(`#meta-${ek}`);

    card.classList.remove("working", "done");
    orb.className = "step-dot";

    if (info.status === "working") {
      card.classList.add("working");
      orb.classList.add("working");
      meta.textContent = "Working...";
      workingBoost = 10;
    } else if (info.status === "done") {
      card.classList.add("done");
      orb.classList.add("done");
      meta.textContent = `Done • ${info.elapsed || 0}s`;
      doneCount += 1;
    } else if (info.status === "error") {
      orb.classList.add("error");
      meta.textContent = "Retry";
    } else {
      meta.textContent = "Standby";
    }

    if (i > 0) $(`#cond-${i}`).classList.toggle("lit", (emps[`emp${i}`] || {}).status === "done");
  });

  const fill = $("#pipelineProgressFill");
  if (fill) fill.style.width = `${Math.min(100, doneCount * 20 + workingBoost)}%`;

  if (proj.status === "completed" && proj.editor && !proj._autoSwitched) {
    proj._autoSwitched = true;
    setActiveInspectorTab("cinema");
  } else if (proj.status === "awaiting_approval") {
    setActiveInspectorTab("script");
  }

  $("#approvalBanner").classList.toggle("hidden", proj.status !== "awaiting_approval");
  $("#stageEmpty").classList.add("hidden");

  renderPaneResearch(proj);
  renderPaneStrategy(proj);
  renderPaneScript(proj);
  renderPaneAssets(proj);
  renderPaneCinema(proj);
  renderConsole(proj.logs || []);
  setActiveInspectorTab(state.activeTab);
}

function setActiveInspectorTab(tab) {
  state.activeTab = tab;
  $$(".step-card").forEach((c) => c.classList.toggle("active", c.dataset.tab === tab));
  ["research", "strategy", "script", "assets", "cinema"].forEach((t) => {
    $(`#pane-${t}`).classList.toggle("hidden", t !== tab || !state.activeProject);
  });
}

function renderPaneResearch(proj) {
  const pane = $("#pane-research");
  const r = proj.research;
  if (!r) {
    pane.innerHTML = `<div class="empty-state"><h3>Researcher Scanning Live Demand...</h3><p>Analyzing YouTube, Instagram, Facebook &amp; live search signals.</p></div>`;
    return;
  }
  const yt = (r.platforms || {}).youtube || {};
  const ig = (r.platforms || {}).instagram || {};
  const fb = (r.platforms || {}).facebook || {};
  const seo = r.seo_intelligence || {};

  pane.innerHTML = `
    <div class="info-card accent">
      <h4>01 • Research Summary <span class="status-pill ok">Demand Score: ${seo.demand_score || 85}/100</span></h4>
      <p>${esc(r.executive_summary)}</p>
    </div>
    <div class="card-grid-3">
      <div class="info-card yt"><h4>YouTube</h4><ul>${(yt.trending_angles || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div class="info-card ig"><h4>Instagram Reels</h4><ul>${(ig.trending_angles || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div class="info-card fb"><h4>Facebook</h4><ul>${(fb.trending_angles || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    </div>
    <div class="card-grid-2">
      <div class="info-card">
        <h4>Top Search Keywords</h4>
        <div class="kw-cloud">
          ${(seo.youtube_autocomplete || []).slice(0, 7).map((k) => `<span class="kw-pill yt-pill">YT: ${esc(k)}</span>`).join("")}
          ${(seo.google_autocomplete || []).slice(0, 7).map((k) => `<span class="kw-pill">G: ${esc(k)}</span>`).join("")}
        </div>
      </div>
      <div class="info-card">
        <h4>Key Facts &amp; Insights</h4>
        <ul>${(r.key_facts_and_insights || []).slice(0, 5).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
    </div>
  `;
}

function renderPaneStrategy(proj) {
  const pane = $("#pane-strategy");
  const st = proj.strategy;
  if (!st) {
    pane.innerHTML = `<div class="empty-state"><h3>Strategist Building Blueprint...</h3><p>Designing pacing, hook structure, and retention beats.</p></div>`;
    return;
  }
  const pb = st.platform_playbooks || {};
  const tc = st.thumbnail_concept || {};
  const scenes = st.scene_blueprint || [];

  pane.innerHTML = `
    <div class="info-card accent">
      <h4>02 • Master Content Strategy</h4>
      <p><strong>Winning Angle:</strong> ${esc(st.winning_angle)}</p>
      <p style="margin-top:6px;"><strong>Hook:</strong> ${esc(st.hook_strategy)}</p>
      <p style="margin-top:6px;"><strong>Cover Concept:</strong> ${esc(tc.headline || "")} — ${esc(tc.subline || "")}</p>
    </div>
    <div class="card-grid-3">
      <div class="info-card yt"><h4>YouTube Plan</h4><p>${esc((pb.youtube || {}).goal || "")}</p></div>
      <div class="info-card ig"><h4>Instagram Plan</h4><p>${esc((pb.instagram || {}).goal || "")}</p></div>
      <div class="info-card fb"><h4>Facebook Plan</h4><p>${esc((pb.facebook || {}).goal || "")}</p></div>
    </div>
    <div class="info-card" style="margin-top:14px;">
      <h4>Scene Timeline (${scenes.length} Scenes)</h4>
      <div class="card-grid-2">
        ${scenes.map((s) => `<div class="step-row"><span class="step-tag">S0${s.scene_number} • ${s.target_seconds || 6}s</span><div><strong>${esc(s.role)}</strong><p style="font-size:12px; color:var(--text-2);">${esc(s.beat_summary)}</p></div></div>`).join("")}
      </div>
    </div>
  `;
}

function renderPaneScript(proj) {
  const pane = $("#pane-script");
  const sc = proj.script;
  if (!sc) {
    pane.innerHTML = `<div class="empty-state"><h3>Scriptwriter Drafting...</h3><p>Writing narration, synced kinetic captions &amp; social SEO packs.</p></div>`;
    return;
  }
  const pack = sc.social_pack || {};
  const yt = pack.youtube || {};
  const ig = pack.instagram || {};
  const fb = pack.facebook || {};

  pane.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
      <div><h3 style="font-size:16px;">03 • Storyboard: ${esc(sc.video_title || proj.topic)}</h3><span style="font-size:12px; color:var(--text-2);">Edit any scene below and click Save &amp; Re-Render.</span></div>
      <button class="btn-primary-pill btn-sm" id="btnSaveRerender">Save &amp; Re-Render</button>
    </div>
    <div id="storyboardEditor">
      ${(sc.scenes || [])
        .map(
          (s, idx) => `
        <div class="scene-card" data-sidx="${idx}">
          <span class="scene-badge">SCENE 0${s.scene_number} • ${esc(s.role)}</span>
          <div class="scene-fields">
            <div><label>Spoken Narration</label><textarea rows="2" class="ed-narration">${esc(s.narration)}</textarea></div>
            <div><label>On-Screen Caption</label><textarea rows="2" class="ed-subtitle">${esc(s.subtitle_text)}</textarea></div>
            <div><label>Visual Search Query</label><input type="text" class="ed-vquery" value="${esc(s.visual_query)}" /></div>
            <div><label>Visual Art Prompt</label><input type="text" class="ed-aiprompt" value="${esc(s.ai_image_prompt)}" /></div>
          </div>
        </div>`
        )
        .join("")}
    </div>
    <div class="card-grid-3">
      <div class="info-card yt"><h4>YouTube Pack <button class="btn-copy" id="copyYT">Copy</button></h4><p><strong>${esc(yt.title || "")}</strong></p><p style="margin-top:6px; white-space:pre-line; font-size:12px;">${esc(yt.description || "")}</p><p style="margin-top:6px; font-size:11.5px; color:#b91c1c;">${esc((yt.tags || []).join(", "))}</p></div>
      <div class="info-card ig"><h4>Instagram Pack <button class="btn-copy" id="copyIG">Copy</button></h4><p style="white-space:pre-line;">${esc(ig.caption || "")}</p><p style="margin-top:8px; color:var(--accent); font-size:12px;">${esc((ig.hashtags || []).join(" "))}</p></div>
      <div class="info-card fb"><h4>Facebook Pack <button class="btn-copy" id="copyFB">Copy</button></h4><p style="white-space:pre-line;">${esc(fb.post_copy || "")}</p><p style="margin-top:8px; color:var(--accent); font-size:12px;">${esc((fb.hashtags || []).join(" "))}</p></div>
    </div>
  `;

  $("#copyYT").onclick = () => copyText(`${yt.title || ""}\n\n${yt.description || ""}\n\nTags: ${(yt.tags || []).join(", ")}`, "YouTube Pack");
  $("#copyIG").onclick = () => copyText(`${ig.caption || ""}\n\n${(ig.hashtags || []).join(" ")}`, "Instagram Pack");
  $("#copyFB").onclick = () => copyText(`${fb.post_copy || ""}\n\n${(fb.hashtags || []).join(" ")}`, "Facebook Pack");

  $("#btnSaveRerender").onclick = async () => {
    const updatedScenes = $$("#storyboardEditor .scene-card").map((card, i) => ({
      ...(sc.scenes[i] || {}),
      scene_number: i + 1,
      narration: card.querySelector(".ed-narration").value,
      subtitle_text: card.querySelector(".ed-subtitle").value,
      visual_query: card.querySelector(".ed-vquery").value,
      ai_image_prompt: card.querySelector(".ed-aiprompt").value,
    }));
    await api(`/api/projects/${proj.id}/scenes`, { method: "POST", body: JSON.stringify({ scenes: updatedScenes, rerender: true }) });
    toast("Saved! Re-rendering video...");
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(refreshActiveProject, 1000);
  };
}

function renderPaneAssets(proj) {
  const pane = $("#pane-assets");
  const pr = proj.producer;
  if (!pr) {
    pane.innerHTML = `<div class="empty-state"><h3>Producer Recording Voice &amp; Visuals...</h3><p>Generating word-synced voiceovers, HD visuals, and cover thumbnail.</p></div>`;
    return;
  }
  const ts = Date.now();
  pane.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
      <div><h3 style="font-size:16px;">04 • Voice &amp; Visual Assets</h3><span style="font-size:12px; color:var(--text-2);">${esc(pr.voice_label)} • ${pr.total_duration_sec}s</span></div>
      <img src="/media/projects/${esc(proj.id)}/thumbnail.png?t=${ts}" style="height:60px; border-radius:8px; border:1px solid var(--border); cursor:pointer;" onclick="openLightbox('/media/projects/${esc(proj.id)}/thumbnail.png?t=${ts}', 'Cover Thumbnail')" />
    </div>
    <div class="asset-scene-grid">
      ${(pr.scenes || [])
        .map((s) => {
          const mediaUrl = `/media/projects/${esc(proj.id)}/assets/${esc(s.visual_file)}?t=${ts}`;
          const audioUrl = `/media/projects/${esc(proj.id)}/assets/${esc(s.audio_file)}?t=${ts}`;
          const vtag = s.visual_type === "video"
            ? `<video class="asset-preview" src="${mediaUrl}" muted loop autoplay playsinline></video>`
            : `<img class="asset-preview" src="${mediaUrl}" onclick="openLightbox('${mediaUrl}', 'Scene 0${s.scene_number}')" />`;
          return `<div class="asset-card">${vtag}<div class="asset-body"><div style="font-size:11px; font-family:var(--font-mono); color:var(--text-3);">SCENE 0${s.scene_number} • ${s.duration_sec}s</div><div style="font-size:12px; color:var(--text-2);">${esc(s.subtitle_text)}</div><audio controls src="${audioUrl}"></audio></div></div>`;
        })
        .join("")}
    </div>
  `;
}

function renderPaneCinema(proj) {
  const pane = $("#pane-cinema");
  const ed = proj.editor;
  if (!ed) {
    pane.innerHTML = `<div class="empty-state"><h3>Final Screening Room</h3><p>Your finished Full HD video, animated captions, and social upload pack will appear here.</p></div>`;
    return;
  }
  const ts = Date.now();
  const isVertical = proj.format === "9:16";
  const videoUrl = `/media/projects/${esc(proj.id)}/${esc(ed.video_file)}?t=${ts}`;
  const thumbUrl = `/media/projects/${esc(proj.id)}/thumbnail.png?t=${ts}`;

  pane.innerHTML = `
    <div class="cinema-layout">
      <div class="${isVertical ? "phone-frame" : "widescreen-frame"}">
        <video controls playsinline src="${videoUrl}" poster="${thumbUrl}"></video>
      </div>
      <div>
        <span class="status-pill ok">Final Master Ready</span>
        <h2 style="font-size:20px; margin-top:10px;">${esc((proj.script || {}).video_title || proj.topic)}</h2>
        <div class="cinema-specs">
          <span class="status-pill">${esc(ed.resolution)}</span>
          <span class="status-pill">${ed.duration_sec}s</span>
          <span class="status-pill">${ed.size_mb} MB</span>
          <span class="status-pill">${ed.fps} FPS</span>
        </div>
        <div class="action-btn-row">
          <a class="btn-primary-pill btn-sm" style="text-decoration:none;" href="/api/projects/${esc(proj.id)}/download/final_video.mp4">Download MP4</a>
          <a class="btn-outline-sm" style="text-decoration:none;" href="/api/projects/${esc(proj.id)}/download/thumbnail.png">Thumbnail</a>
          <a class="btn-outline-sm" style="text-decoration:none;" href="/api/projects/${esc(proj.id)}/download/subtitles.srt">Subtitles (.srt)</a>
          <a class="btn-outline-sm" style="text-decoration:none;" href="/api/projects/${esc(proj.id)}/download/social_media_pack.md">Upload Pack</a>
          <button class="btn-outline-sm" id="btnOpenFolder">Open Folder</button>
        </div>
        <div class="thumb-preview-box">
          <div class="mini-label" style="margin-bottom:8px;">Cover Thumbnail</div>
          <img src="${thumbUrl}" onclick="openLightbox('${thumbUrl}', 'Video Thumbnail')" alt="Thumbnail" />
        </div>
      </div>
    </div>
  `;
  $("#btnOpenFolder").onclick = async () => {
    await api(`/api/projects/${proj.id}/open-folder`, { method: "POST" });
    toast("Opened project folder.");
  };
}

function renderConsole(logs) {
  $("#consoleCount").textContent = `${logs.length} events ▾`;
  const body = $("#consoleBody");
  const cleanMsg = (m) =>
    String(m || "").replace(/\b(GROQ|GEMINI|OPENROUTER|POLLINATIONS|CEREBRAS|FFMPEG|EDGE TTS)\b/gi, "NEXUS");
  body.innerHTML = logs.map((l) => `<div class="log-line"><span class="lt">[${esc(l.time)}]</span><span>${esc(cleanMsg(l.msg))}</span></div>`).join("");
  body.scrollTop = body.scrollHeight;
}

/* ==================== GLOBAL SEARCH TREND RADAR ==================== */
async function loadInitialTrends() {
  try {
    const data = await api("/api/seo/trends?geo=US");
    if ((data.trends || []).length) {
      $("#seoResults").innerHTML = `
        <div class="clean-card inspector-box">
          <h4 style="margin-bottom:10px;">Live Breakout Search Trends (Click any topic to create a video)</h4>
          <div class="kw-cloud">
            ${data.trends
              .map((t) => `<span class="kw-pill" onclick="sendKeywordToVideo('${esc(t.topic).replace(/'/g, "\\'")}')">${esc(t.topic)} <small style="color:var(--text-3);">(${esc(t.traffic)})</small></span>`)
              .join("")}
          </div>
        </div>`;
    }
  } catch (e) {}
}

window.sendKeywordToVideo = (kw) => {
  $("#topicInput").value = kw;
  openWorkspace("factory");
  toast(`Topic loaded: "${kw}"`);
};

async function runSeoRadarUI() {
  const topic = $("#seoTopicInput").value.trim();
  if (!topic) return toast("Enter a keyword to scan live trends.");
  const btn = $("#btnRunSeoRadar");
  btn.disabled = true;
  btn.textContent = "Scanning...";
  try {
    const d = await api("/api/seo/radar", { method: "POST", body: JSON.stringify({ topic, geo: $("#seoGeoSelect").value }) });
    $("#seoResults").innerHTML = `
      <div class="clean-card inspector-box">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <h3>Live Search Demand: "${esc(d.topic)}"</h3>
          <span class="status-pill ok">Demand Score: ${d.demand_score}/100</span>
        </div>
        <div class="card-grid-2">
          <div class="info-card yt"><h4>YouTube Searches (${(d.youtube_autocomplete || []).length})</h4><div class="kw-cloud">${(d.youtube_autocomplete || []).map((k) => `<span class="kw-pill yt-pill" onclick="sendKeywordToVideo('${esc(k).replace(/'/g, "\\'")}')">YT: ${esc(k)}</span>`).join("")}</div></div>
          <div class="info-card accent"><h4>Google Searches (${(d.google_autocomplete || []).length})</h4><div class="kw-cloud">${(d.google_autocomplete || []).map((k) => `<span class="kw-pill" onclick="sendKeywordToVideo('${esc(k).replace(/'/g, "\\'")}')">G: ${esc(k)}</span>`).join("")}</div></div>
        </div>
        <div class="card-grid-2">
          <div class="info-card"><h4>High-Intent Questions</h4><div class="kw-cloud">${(d.high_intent_questions || []).map((k) => `<span class="kw-pill" onclick="sendKeywordToVideo('${esc(k).replace(/'/g, "\\'")}')">${esc(k)}</span>`).join("")}</div></div>
          <div class="info-card"><h4>Breakout Trends (${esc(d.geo)})</h4><div class="kw-cloud">${(d.daily_breakout_trends || []).map((t) => `<span class="kw-pill" onclick="sendKeywordToVideo('${esc(t.topic).replace(/'/g, "\\'")}')">${esc(t.topic)} (${esc(t.traffic)})</span>`).join("")}</div></div>
        </div>
      </div>`;
  } catch (e) {
    toast(`Error: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Scan Trends";
  }
}

/* ==================== VOICE PREVIEW HELPER ==================== */
async function playVoiceSample(vkey, btnEl = null) {
  const audio = $("#voicePreviewPlayer");
  $$(".voice-sample-row").forEach((r) => r.classList.remove("playing"));
  if (btnEl) btnEl.classList.add("playing");
  try {
    audio.src = `/api/voices/preview/${encodeURIComponent(vkey)}?t=${Date.now()}`;
    await audio.play();
    audio.onended = () => { if (btnEl) btnEl.classList.remove("playing"); };
  } catch {
    if (btnEl) btnEl.classList.remove("playing");
    toast("Could not preview voice right now.");
  }
}

/* ==================== EVENTS ==================== */
function bindEvents() {
  // Landing <-> Workspace transitions
  $$("[data-open-workspace]").forEach((b) => (b.onclick = () => openWorkspace(b.dataset.openWorkspace)));
  $$("[data-open-auth]").forEach((b) => (b.onclick = () => openAuthModal(b.dataset.openAuth)));
  $("#btnBackHome").onclick = openLanding;
  $("#btnBrandHome").onclick = openLanding;
  $("#btnTopHome").onclick = openLanding;

  // Homepage live voice samples
  $$(".voice-sample-row").forEach((b) => {
    b.onclick = () => playVoiceSample(b.dataset.demoVoice, b);
  });

  // Video Modal
  $("#btnCloseVideoModal").onclick = closeVideoModal;
  $("#videoModal").onclick = (e) => { if (e.target.id === "videoModal") closeVideoModal(); };
  $("#btnVmCreateOwn").onclick = () => { closeVideoModal(); openWorkspace("factory"); };

  // Workspace navigation
  $$(".mode-tab").forEach((t) => (t.onclick = () => switchView(t.dataset.view)));
  $$(".rail-btn[data-view]").forEach((b) => (b.onclick = () => switchView(b.dataset.view)));
  $$("[data-goto-view]").forEach((b) => (b.onclick = () => openWorkspace(b.dataset.gotoView)));

  $("#btnNewChat").onclick = startNewChat;
  $("#btnToggleSidebar").onclick = () => {
    $("#historySidebar").classList.add("collapsed");
    $("#btnReopenSidebar").classList.remove("hidden");
  };
  $("#btnReopenSidebar").onclick = () => {
    $("#historySidebar").classList.remove("collapsed");
    $("#btnReopenSidebar").classList.add("hidden");
  };

  $$(".sb-item[data-quick-chat]").forEach((b) => (b.onclick = () => sendChat(b.dataset.quickChat)));

  // Chat Pill Composer
  $("#btnSendChat").onclick = () => sendChat();
  $("#chatInput").addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 150) + "px";
  });
  $("#chatInput").onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  };
  $$(".starter-card[data-msg]").forEach((c) => (c.onclick = () => sendChat(c.dataset.msg)));

  $("#btnPlusMenu").onclick = (e) => {
    e.stopPropagation();
    $("#plusPopover").classList.toggle("hidden");
    $("#modelDropdownMenu").classList.add("hidden");
  };
  $("#btnModelDrop").onclick = (e) => {
    e.stopPropagation();
    $("#modelDropdownMenu").classList.toggle("hidden");
    $("#plusPopover").classList.add("hidden");
  };
  document.addEventListener("click", () => {
    $("#plusPopover").classList.add("hidden");
    $("#modelDropdownMenu").classList.add("hidden");
  });
  $$("#plusPopover button[data-plus-prompt]").forEach((b) => {
    b.onclick = () => { $("#plusPopover").classList.add("hidden"); sendChat(b.dataset.plusPrompt); };
  });
  $$("#plusPopover button[data-goto]").forEach((b) => {
    b.onclick = () => { $("#plusPopover").classList.add("hidden"); switchView(b.dataset.goto); };
  });

  // Video Studio Controls
  $$("#formatGroup .seg-pill").forEach((b) => {
    b.onclick = () => {
      $$("#formatGroup .seg-pill").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.selectedFormat = b.dataset.val;
    };
  });
  $$("#styleCards .style-chip").forEach((b) => {
    b.onclick = () => {
      $$("#styleCards .style-chip").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.selectedStyle = b.dataset.style;
    };
  });
  $$(".idea-chip").forEach((c) => (c.onclick = () => { $("#topicInput").value = c.dataset.topic; $("#topicInput").focus(); }));
  $$(".step-card").forEach((c) => (c.onclick = () => setActiveInspectorTab(c.dataset.tab)));

  $("#btnLaunchTeam").onclick = launchProduction;
  $("#topicInput").onkeydown = (e) => { if (e.key === "Enter") launchProduction(); };
  $("#btnApproveRender").onclick = async () => {
    if (!state.activeProjectId) return;
    await api(`/api/projects/${state.activeProjectId}/approve`, { method: "POST" });
    toast("Approved! Rendering final video...");
    refreshActiveProject();
  };

  $("#btnPreviewVoice").onclick = async () => {
    let vkey = $("#voiceSelect").value;
    if (vkey === "auto") {
      const lang = $("#languageSelect").value.toLowerCase();
      const map = {
        urdu: "urdu_female_noor", hindi: "hindi_female_ananya", arabic: "ar_zariyah_sa",
        spanish: "es_dalia_mx", french: "fr_denise", german: "de_katja",
        portuguese: "pt_francisca_br", turkish: "tr_emel", indonesian: "id_gadis",
        italian: "it_elsa", japanese: "ja_nanami", korean: "ko_sunhi",
        chinese: "zh_xiaoxiao", russian: "ru_svetlana",
      };
      vkey = Object.entries(map).find(([k]) => lang.includes(k))?.[1] || "en_ava_multi";
    }
    const btn = $("#btnPreviewVoice");
    btn.textContent = "Playing...";
    btn.disabled = true;
    await playVoiceSample(vkey);
    btn.textContent = "Listen";
    btn.disabled = false;
  };

  // Auth Full-Page Screen
  $("#btnOpenLogin").onclick = () => openAuthModal("login");
  $("#btnTopLogin").onclick = () => openAuthModal("login");
  $("#btnOpenSignup").onclick = () => openAuthModal("signup");
  $("#btnCloseAuth").onclick = () => {
    $("#authModal").classList.add("hidden");
    if (window.location.pathname === "/login" || window.location.pathname === "/signup") {
      history.replaceState(null, "", "/");
    }
  };
  $$(".auth-tab").forEach((t) => (t.onclick = () => switchAuthMode(t.dataset.authMode)));
  $("#btnQuickSwitchAuth").onclick = () => switchAuthMode(state.authMode === "login" ? "signup" : "login");
  $("#btnTogglePw").onclick = () => {
    const inp = $("#authPassInput");
    const isPw = inp.type === "password";
    inp.type = isPw ? "text" : "password";
    $("#btnTogglePw").textContent = isPw ? "Hide" : "Show";
  };

  $("#btnSendOtp").onclick = async () => {
    const email = $("#authEmailInput").value.trim();
    const errBox = $("#authError");
    const infoBox = $("#authInfo");
    errBox.classList.add("hidden");
    infoBox.classList.add("hidden");
    if (!email) {
      errBox.textContent = "Enter your real email address first.";
      errBox.classList.remove("hidden");
      return;
    }
    const btn = $("#btnSendOtp");
    btn.disabled = true;
    btn.textContent = "Sending...";
    try {
      const res = await api("/api/auth/send-otp", { method: "POST", body: JSON.stringify({ email }) });
      infoBox.textContent = res.message || "6-digit OTP sent to your email!";
      infoBox.classList.remove("hidden");
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    } finally {
      btn.disabled = false;
      btn.textContent = "Send OTP";
    }
  };

  $("#authForm").onsubmit = async (e) => {
    e.preventDefault();
    const errBox = $("#authError");
    errBox.classList.add("hidden");
    const email = $("#authEmailInput").value.trim();
    const password = $("#authPassInput").value;
    const name = $("#authNameInput").value.trim();
    const otp_code = ($("#authOtpInput")?.value || "").trim();
    try {
      const endpoint = state.authMode === "signup" ? "/api/auth/register" : "/api/auth/login";
      const payload = state.authMode === "signup" ? { name, email, password, otp_code } : { email, password };
      const res = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
      state.authToken = res.token;
      state.currentUser = res.user;
      localStorage.setItem("nx_auth_token", res.token);
      $("#authModal").classList.add("hidden");
      $("#authPassInput").value = "";
      renderAuthUI();
      toast(`Welcome, ${res.user.name}!`);
      if (state.pageMode === "landing") openWorkspace("chat");
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    }
  };

  $("#btnLogout").onclick = async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch {}
    state.authToken = "";
    state.currentUser = null;
    localStorage.removeItem("nx_auth_token");
    renderAuthUI();
    toast("Signed out.");
  };

  $("#btnToggleConsole").onclick = () => $("#consoleBody").classList.toggle("collapsed");
  $("#btnRunSeoRadar").onclick = runSeoRadarUI;

  $$("[data-select-plan]").forEach((b) => {
    b.onclick = async () => {
      if (!state.currentUser) {
        openAuthModal("signup");
        toast("Create an account or sign in to choose a plan.");
        return;
      }
      const planId = b.dataset.selectPlan.toLowerCase();
      try {
        const res = await api("/api/auth/plan", { method: "POST", body: JSON.stringify({ plan_id: planId }) });
        state.currentUser = res.user;
        renderAuthUI();
        toast(`Plan updated to ${planId.toUpperCase()}.`);
      } catch (e) {
        toast(e.message);
      }
    };
  });

  $("#btnCloseLightbox").onclick = () => $("#lightbox").classList.add("hidden");
  $("#lightbox").onclick = (e) => { if (e.target.id === "lightbox") $("#lightbox").classList.add("hidden"); };
}

initStudio();
