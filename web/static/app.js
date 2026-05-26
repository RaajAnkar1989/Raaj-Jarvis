if (window.__JARVIS_PWA__) throw new Error("already loaded");
window.__JARVIS_PWA__ = true;

const $ = (sel) => document.querySelector(sel);

const logEl = $("#log");
const hudEl = $("#hud");
const stateLabel = $("#stateLabel");
const faceImg = $("#faceImg");
const activateHint = $("#activateHint");
const micNote = $("#micNote");
const chatToggleBtn = $("#chatToggleBtn");
const logPanel = $("#logPanel");
const brainHint = $("#brainHint");
const settingsModel = $("#settingsModel");
const settingsProvider = $("#settingsProvider");
const settingsConn = $("#settingsConn");
const todayTime = $("#todayTime");
const todayDate = $("#todayDate");
const timerCount = $("#timerCount");
const barTimers = $("#barTimers");
const barSession = $("#barSession");
const sessionVal = $("#sessionVal");
const taskCount = $("#taskCount");
const recentApps = $("#recentApps");
const stateChip = $("#stateChip");
const statusHint = $("#statusHint");
const stopBtn = $("#stopBtn");
const settingsVoice = $("#settingsVoice");
const settingsPersonality = $("#settingsPersonality");
const settingsSpeed = $("#settingsSpeed");
const speedLabel = $("#speedLabel");
const gmailClientId = $("#gmailClientId");
const gmailConnectBtn = $("#gmailConnectBtn");
const gmailStatusLine = $("#gmailStatusLine");
const gmailRedirectHint = $("#gmailRedirectHint");
const chatForm = $("#chatForm");
const chatInput = $("#chatInput");
const micBtn = $("#micBtn");
const micLabel = $("#micLabel");
const muteBtn = $("#muteBtn");
const installBtn = $("#installBtn");
const settingsBtn = $("#settingsBtn");
const clockEl = $("#clock");
const connDot = $("#connDot");
const modelLabel = $("#modelLabel");
const backendLabel = $("#backendLabel");
const voiceModeLabel = $("#voiceModeLabel");
const fileZone = $("#fileZone");
const fileInput = $("#fileInput");
const fileHint = $("#fileHint");
const clearFileBtn = $("#clearFileBtn");
const setupOverlay = $("#setupOverlay");
const settingsSidebar = $("#settingsSidebar");
const backendUrlInput = $("#backendUrl");
const settingsBackendUrl = $("#settingsBackendUrl");
const setupError = $("#setupError");
const memoryHint = $("#memoryHint");
const barCpu = $("#barCpu");
const barMem = $("#barMem");
const barDisk = $("#barDisk");
const barBatt = $("#barBatt");
const cpuVal = $("#cpuVal");
const memVal = $("#memVal");
const diskVal = $("#diskVal");
const battVal = $("#battVal");
const remindersList = $("#remindersList");
const jarvisStatus = $("#jarvisStatus");
const visualizer = $("#visualizer");
const mobBatt = $("#mobBatt");
const mobMem = $("#mobMem");
const mobTimers = $("#mobTimers");
const mobSession = $("#mobSession");

const STORAGE_KEY = "jarvis_api";
const CLIENT_KEY = "jarvis_client_id";
const PREFS_KEY = "raajarvis_prefs";
const ALARM_KEY = "raajarvis_alarms";
const RECENT_KEY = "raajarvis_recent";
const VOICE_ACTIVE_KEY = "raajarvis_voice_on";

let lastLogText = "";
let lastLogAt = 0;
let chatSending = false;
let micKeepAliveTimer = null;

let heartbeatTimer = null;
let lastPong = Date.now();
let reconnectAttempts = 0;
const scheduledAlarms = new Map();
let localAlarmItems = [];

function loadLocalAlarms() {
  try {
    return JSON.parse(localStorage.getItem(ALARM_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveLocalAlarms(items) {
  localAlarmItems = items;
  localStorage.setItem(ALARM_KEY, JSON.stringify(items.slice(-30)));
  renderRemindersList();
}

function upsertLocalAlarm(date, time, message) {
  const items = loadLocalAlarms().filter(
    (a) => !(a.date === date && a.time === time && a.message === message)
  );
  items.push({ date, time, message, source: "phone" });
  saveLocalAlarms(items);
}

function restoreLocalAlarmsOnBoot() {
  for (const item of loadLocalAlarms()) {
    if (item.date && item.time) {
      schedulePhoneAlarm(item.date, item.time, item.message || "Reminder");
    }
  }
}

function pushRecent(label) {
  if (!label || !recentApps) return;
  let items = [];
  try {
    items = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    items = [];
  }
  items = [label, ...items.filter((x) => x !== label)].slice(0, 5);
  localStorage.setItem(RECENT_KEY, JSON.stringify(items));
  renderRecentApps(items);
}

function renderRecentApps(items = []) {
  if (!recentApps) return;
  if (!items.length) {
    try {
      items = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    } catch {
      items = [];
    }
  }
  recentApps.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "jarvis-hud-empty";
    li.textContent = "No recent activity";
    recentApps.appendChild(li);
    return;
  }
  for (const name of items) {
    const li = document.createElement("li");
    li.textContent = name;
    recentApps.appendChild(li);
  }
}

function updateModelDisplay(data) {
  const model = data?.model || "—";
  const provider = (data?.provider || "ollama").toUpperCase();
  const online = !!data?.ok;
  if (settingsModel) settingsModel.textContent = model;
  if (settingsProvider) settingsProvider.textContent = provider;
  if (settingsConn) settingsConn.textContent = online ? "Connected" : "Offline";
  if (modelLabel) modelLabel.textContent = model;
  if (brainHint) {
    brainHint.textContent = online
      ? `${provider} · ${model}`
      : "ADD BRAIN KEY IN SETTINGS";
  }
}

function updateSessionUi(state) {
  const s = (state || "OFFLINE").toUpperCase();
  let pct = 20;
  let label = "Idle";
  if (s === "LISTENING" || s === "RECORDING") {
    pct = 100;
    label = voiceActive ? "Listening" : "Ready";
  } else if (s === "THINKING") {
    pct = 65;
    label = "Thinking";
  } else if (s === "SPEAKING") {
    pct = 80;
    label = "Speaking";
  } else if (s === "OFFLINE") {
    pct = 5;
    label = "Offline";
  }
  if (barSession) barSession.style.width = `${pct}%`;
  if (sessionVal) sessionVal.textContent = label;
  if (mobSession) mobSession.textContent = label;
}

function updateTimerUi(count) {
  const n = Number(count) || 0;
  if (timerCount) timerCount.textContent = String(n);
  if (barTimers) barTimers.style.width = `${Math.min(100, n * 25)}%`;
  if (mobTimers) mobTimers.textContent = String(n);
  if (taskCount) {
    taskCount.textContent = n ? `${n} reminder${n === 1 ? "" : "s"}` : "No open tasks";
  }
}

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
  } catch {
    return {};
  }
}

function savePrefs(p) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(p));
}

function speedToRate(pct) {
  const n = Number(pct) || 0;
  return n >= 0 ? `+${n}%` : `${n}%`;
}

function rateLabel(pct) {
  const n = Number(pct) || 0;
  return n === 0 ? "Normal" : n > 0 ? `Faster (+${n}%)` : `Slower (${n}%)`;
}

function updateGmailStatusUI(status) {
  if (!status) return;
  if (gmailClientId && status.client_id && !gmailClientId.value.trim()) {
    gmailClientId.value = status.client_id;
  }
  if (gmailStatusLine) {
    if (status.connected) {
      gmailStatusLine.textContent = "✓ Gmail & Calendar connected";
      gmailStatusLine.style.color = "var(--pri)";
    } else if (status.has_client_id) {
      gmailStatusLine.textContent = "Client ID saved — tap Connect Gmail to sign in";
      gmailStatusLine.style.color = "";
    } else {
      gmailStatusLine.textContent = "Not connected";
      gmailStatusLine.style.color = "";
    }
  }
  if (gmailConnectBtn) {
    gmailConnectBtn.textContent = status.connected ? "Reconnect Gmail" : "Connect Gmail";
  }
}

async function loadGmailStatus() {
  const base = apiBase();
  if (!base) return;
  try {
    const res = await fetch(`${base}/api/gmail/status`, { headers: apiHeaders() });
    if (res.ok) updateGmailStatusUI(await res.json());
    const uriRes = await fetch(`${base}/api/gmail/oauth/redirect-uris`, { headers: apiHeaders() });
    if (uriRes.ok && gmailRedirectHint) {
      const { redirect_uris: uris } = await uriRes.json();
      if (uris?.length) {
        gmailRedirectHint.innerHTML =
          "Add this redirect URI in Google Cloud Console:<br><code>" +
          uris.map((u) => u.replace(/</g, "&lt;")).join("</code><br><code>") +
          "</code>";
      }
    }
  } catch {
    /* ignore */
  }
}

async function connectGmail() {
  const base = apiBase();
  if (!base) throw new Error("Connect to your Mac backend first.");
  const clientId = gmailClientId?.value?.trim();
  if (!clientId) throw new Error("Paste your Google Client ID first.");

  await fetch(`${base}/api/gmail/settings`, {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ client_id: clientId }),
  });

  if (gmailStatusLine) gmailStatusLine.textContent = "Opening Google sign-in…";

  const popup = window.open(`${base}/api/gmail/oauth/start`, "_blank", "noopener");
  if (!popup) {
    window.location.href = `${base}/api/gmail/oauth/start`;
  }

  let attempts = 0;
  const poll = setInterval(async () => {
    attempts += 1;
    try {
      const res = await fetch(`${base}/api/gmail/status`, { headers: apiHeaders() });
      if (res.ok) {
        const status = await res.json();
        updateGmailStatusUI(status);
        if (status.connected || attempts > 60) clearInterval(poll);
      }
    } catch {
      /* ignore */
    }
    if (attempts > 60) clearInterval(poll);
  }, 2000);
}

async function applySettingsToBackend() {
  const base = apiBase();
  if (!base) return;
  const voice = settingsVoice?.value;
  const personality = settingsPersonality?.value;
  const speed = settingsSpeed?.value ?? 12;
  await fetch(`${base}/api/settings`, {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      voice,
      personality,
      tts_rate: speedToRate(speed),
      owner: "Raaj",
    }),
  });
  const gid = gmailClientId?.value?.trim();
  if (gid) {
    await fetch(`${base}/api/gmail/settings`, {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ client_id: gid }),
    });
  }
  savePrefs({ voice, personality, speed });
}

async function loadSettingsFromBackend() {
  const base = apiBase();
  const prefs = loadPrefs();
  if (settingsVoice && prefs.voice) settingsVoice.value = prefs.voice;
  if (settingsPersonality && prefs.personality) settingsPersonality.value = prefs.personality;
  if (settingsSpeed && prefs.speed != null) settingsSpeed.value = prefs.speed;
  if (speedLabel && settingsSpeed) speedLabel.textContent = rateLabel(settingsSpeed.value);
  if (!base) return;
  try {
    const res = await fetch(`${base}/api/settings`, { headers: apiHeaders() });
    if (res.ok) {
      const data = await res.json();
      if (settingsVoice && data.voice) settingsVoice.value = data.voice;
      if (settingsPersonality && data.personality) settingsPersonality.value = data.personality;
      if (data.tts_rate && settingsSpeed) {
        const m = String(data.tts_rate).match(/([+-]?\d+)/);
        if (m) settingsSpeed.value = m[1];
      }
      if (speedLabel && settingsSpeed) speedLabel.textContent = rateLabel(settingsSpeed.value);
    }
    const statusRes = await fetch(`${base}/api/status`, { headers: apiHeaders() });
    if (statusRes.ok) updateModelDisplay(await statusRes.json());
    await loadGmailStatus();
  } catch {
    /* ignore */
  }
}

function interruptJarvis() {
  stopPlayback();
  audioQueue = Promise.resolve();
  jarvisSpeaking = false;
  if (stopBtn) stopBtn.classList.add("hidden");
  updateMicState();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "interrupt", client_id: clientId() }));
  } else if (apiBase()) {
    fetch(`${apiBase()}/api/interrupt`, { method: "POST", headers: apiHeaders() }).catch(() => {});
  }
  setState("LISTENING");
}

function playReminderAlert(message) {
  appendLog(`⏰ REMINDER — ${message || "Timer done"}`);
  if (Notification.permission === "granted") {
    new Notification("JARVIS Reminder", {
      body: message || "Timer finished",
      requireInteraction: true,
    });
  }
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      const ctx = new AudioCtx();
      const beep = (freq, t0, dur, vol = 0.4) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.value = vol;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + t0);
        osc.stop(ctx.currentTime + t0 + dur);
      };
      beep(880, 0, 0.18);
      beep(988, 0.22, 0.18);
      beep(1175, 0.44, 0.28);
      beep(880, 0.8, 0.18);
      beep(1175, 1.02, 0.35);
    }
  } catch {
    /* ignore */
  }
  if (navigator.vibrate) {
    navigator.vibrate([180, 80, 180, 80, 320]);
  }
  const hud = document.getElementById("hud");
  if (hud) {
    hud.classList.add("reminder-flash");
    setTimeout(() => hud.classList.remove("reminder-flash"), 4000);
  }
  if (jarvisStatus) {
    jarvisStatus.textContent = "Reminder!";
    jarvisStatus.classList.add("live");
    setTimeout(() => {
      if (jarvisStatus.textContent === "Reminder!") {
        jarvisStatus.textContent = heroStatusText(backendState);
      }
    }, 5000);
  }
}

function schedulePhoneAlarm(date, time, message) {
  if (!date || !time) return;
  const when = new Date(`${date}T${time}:00`);
  if (Number.isNaN(when.getTime())) return;
  const ms = when.getTime() - Date.now();
  if (ms <= 0) return;
  const id = `${date}_${time}_${message}`;
  if (scheduledAlarms.has(id)) return;
  const timer = setTimeout(() => {
    scheduledAlarms.delete(id);
    playReminderAlert(message);
  }, ms);
  scheduledAlarms.set(id, timer);
  upsertLocalAlarm(date, time, message);
  appendLog(`SYS: Phone alarm set for ${date} ${time}`);
}

async function ensureNotifications() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    await Notification.requestPermission();
  }
}

function clientId() {
  let id = localStorage.getItem(CLIENT_KEY);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || `c_${Date.now()}`;
    localStorage.setItem(CLIENT_KEY, id);
  }
  return id;
}

function apiHeaders(extra = {}) {
  const headers = {
    "X-Jarvis-Client-Id": clientId(),
    ...extra,
  };
  const base = apiBase();
  if (base && base.includes(".loca.lt")) {
    headers["Bypass-Tunnel-Reminder"] = "true";
  }
  return headers;
}

function setBar(el, valEl, pct) {
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  if (el) el.style.width = `${v}%`;
  if (valEl) valEl.textContent = `${Math.round(v)}%`;
}

let ws = null;
let wsConnecting = false;
let reconnectTimer = null;
let muted = false;
let jarvisSpeaking = false;
let backendState = "STANDBY";
let voiceActive = false;
let installPrompt = null;
let audioQueue = Promise.resolve();
let currentAudio = null;

// VAD always-on voice
let vadStream = null;
let vadCtx = null;
let vadAnalyser = null;
let vadFrame = null;
let vadRecorder = null;
let vadChunks = [];
let vadRecording = false;
let vadSpeechSeen = false;
let vadSilenceSince = 0;

function savedApi() {
  const v = localStorage.getItem(STORAGE_KEY);
  return v ? v.replace(/\/$/, "") : "";
}

function bakedApi() {
  const v = window.__JARVIS_API__;
  return v && String(v).trim() ? String(v).trim().replace(/\/$/, "") : "";
}

function isAutoConnect() {
  return !!(bakedApi() || window.__JARVIS_NETLIFY_PROXY__);
}

async function fetchDiscoveryUrl() {
  const cfg = window.__JARVIS_DISCOVERY__;
  const sources = cfg?.sources?.length
    ? cfg.sources
    : (cfg?.url ? [{ url: cfg.url }] : []);
  for (const source of sources) {
    try {
      const headers = {};
      if (source.accept) headers.Accept = source.accept;
      const res = await fetch(`${source.url}?t=${Date.now()}`, {
        signal: AbortSignal.timeout(12000),
        cache: "no-store",
        headers,
      });
      if (!res.ok) continue;
      const raw = (await res.text()).trim();
      const line = raw.split("\n").find((l) => l.startsWith("https://")) || raw;
      const url = line.trim().replace(/\/$/, "");
      if (url.startsWith("https://")) return url;
    } catch {
      /* try next source */
    }
  }
  return null;
}

async function discoverBackend() {
  const url = await fetchDiscoveryUrl();
  if (!url) return null;
  try {
    await testBackend(url);
    return url;
  } catch {
    return null;
  }
}

let reconnecting = false;

async function reconnectIfStale() {
  if (reconnecting || isAutoConnect()) return;
  reconnecting = true;
  try {
    const url = await discoverBackend();
    if (!url) return;
    const saved = savedApi();
    if (url !== saved) {
      localStorage.setItem(STORAGE_KEY, url);
      setupOverlay?.classList.add("hidden");
      connectWs();
      await refreshStatus();
    }
  } finally {
    reconnecting = false;
  }
}

function startHealthWatch() {
  setInterval(async () => {
    const base = apiBase();
    if (!base || isAutoConnect()) return;
    try {
      await testBackend(base);
      setConn(true);
    } catch {
      setConn(false);
      if (brainHint) brainHint.textContent = "Reconnecting to your Mac…";
      await reconnectIfStale();
    }
  }, 20000);
}

async function discoverBackendWithRetry(maxMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const url = await discoverBackend();
    if (url) return url;
    if (statusHint) statusHint.textContent = "Looking for JARVIS on your Mac…";
    await new Promise((r) => setTimeout(r, 4000));
  }
  return null;
}

async function connectDiscovered(url) {
  localStorage.setItem(STORAGE_KEY, url);
  setupOverlay.classList.add("hidden");
  connectWs();
  refreshStatus();
  setInterval(refreshMetrics, 4000);
  startHealthWatch();
}

function apiBase() {
  if (window.__JARVIS_NETLIFY_PROXY__) {
    return window.location.origin;
  }
  const baked = bakedApi();
  if (baked) return baked;
  const saved = savedApi();
  if (saved) return saved;
  const { origin, port, hostname } = window.location;
  if (port === "8765" || hostname === "localhost" || hostname === "127.0.0.1") {
    return origin;
  }
  return "";
}

function wsUrl() {
  const direct = window.__JARVIS_WS_URL__;
  if (direct && String(direct).trim()) {
    const u = String(direct).trim().replace(/\/$/, "");
    return u.endsWith("/ws") ? u : `${u}/ws`;
  }
  return apiBase().replace(/^http/, "ws") + "/ws";
}

function shortBackend(url) {
  if (!url) return "Not set";
  try {
    const u = new URL(url);
    return u.hostname + (u.port ? `:${u.port}` : "");
  } catch {
    return url.slice(0, 24);
  }
}

function appendLog(text) {
  const now = Date.now();
  if (text === lastLogText && now - lastLogAt < 1500) return;
  lastLogText = text;
  lastLogAt = now;

  const line = document.createElement("div");
  const lower = text.toLowerCase();
  let display = text;
  if (lower.startsWith("you:")) {
    line.className = "you";
    display = text.replace(/^you:\s*/i, "");
  } else if (lower.startsWith("jarvis:") || lower.startsWith("raajarvis:")) {
    line.className = "ai";
    display = text.replace(/^(jarvis|raajarvis):\s*/i, "");
  } else if (lower.includes("err")) {
    line.className = "err";
  } else if (lower.startsWith("file:")) {
    line.className = "sys";
  } else {
    line.className = "sys";
  }
  line.textContent = display;
  logEl.appendChild(line);
  while (logEl.children.length > 12) logEl.removeChild(logEl.firstChild);
  logEl.scrollTop = logEl.scrollHeight;
}

function setConn(ok) {
  connDot.className = "conn-dot " + (ok ? "online" : "offline");
  connDot.title = ok ? "Connected to backend" : "Backend offline";
  if (hudEl) hudEl.classList.toggle("online", ok);
  if (!ok) updateSessionUi("OFFLINE");
}

function heroStatusText(state) {
  const s = (state || "").toUpperCase();
  if (s === "LISTENING" || s === "RECORDING") return "Listening";
  if (s === "SPEAKING") return "Speaking";
  if (s === "THINKING") return "Thinking";
  if (s === "OFFLINE") return "Offline";
  return "Tap to activate";
}

function setHeroMode(state) {
  if (!hudEl) return;
  hudEl.classList.remove("speaking", "listening", "thinking");
  const s = (state || "").toUpperCase();
  const live = s === "LISTENING" || s === "RECORDING" || s === "SPEAKING" || s === "THINKING";
  if (s === "SPEAKING") hudEl.classList.add("speaking");
  else if (s === "LISTENING" || s === "RECORDING") hudEl.classList.add("listening");
  else if (s === "THINKING") hudEl.classList.add("thinking");

  const listening = s === "LISTENING" || s === "RECORDING";
  if (visualizer) visualizer.classList.toggle("hidden", !listening);
  if (stateLabel) {
    stateLabel.classList.toggle("hidden", listening);
    if (!listening) stateLabel.textContent = s || "STANDBY";
  }
  if (jarvisStatus) {
    jarvisStatus.textContent = heroStatusText(s);
    jarvisStatus.classList.toggle("live", live);
  }
  updateSessionUi(s);
}

function setState(state) {
  const label = state || "STANDBY";
  backendState = label;
  if (stateLabel) stateLabel.textContent = label;
  if (stateChip) stateChip.textContent = label;
  setHeroMode(label);

  if (label === "SPEAKING") {
    jarvisSpeaking = true;
    if (statusHint) statusHint.textContent = "Tap Stop or speak to interrupt";
    if (stopBtn) stopBtn.classList.remove("hidden");
  } else {
    jarvisSpeaking = false;
    if (stopBtn) stopBtn.classList.add("hidden");
    if (label === "LISTENING") {
      if (statusHint) {
        statusHint.textContent = voiceActive
          ? "Listening — speak naturally"
          : muted
            ? "Mic muted"
            : "Tap mic to talk";
      }
    } else if (label === "THINKING") {
      if (statusHint) statusHint.textContent = "Thinking…";
    } else if (label === "MUTED") {
      if (statusHint) statusHint.textContent = "Mic muted";
    } else if (label === "RECORDING") {
      if (statusHint) statusHint.textContent = "Listening…";
    } else if (statusHint) {
      statusHint.textContent = apiBase() ? "Raajarvis ready" : "Connecting…";
    }
  }
  updateMicState();
}

function updateMicState() {
  if (micBtn) micBtn.classList.toggle("active", voiceActive);
  if (activateHint) {
    activateHint.textContent = voiceActive ? "LISTENING — TAP MIC TO STOP" : "TAP TO ACTIVATE";
  }
  if (micNote && voiceActive) {
    micNote.textContent = "Mic stays on until you tap again";
  } else if (micNote) {
    micNote.textContent = "TAP MIC · ALLOW MICROPHONE WHEN ASKED";
  }
}

function stopPlayback() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
}

function speakBrowserFallback(text) {
  if (!text || !window.speechSynthesis) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    window.speechSynthesis.speak(u);
  } catch {
    /* ignore */
  }
}

function playSpeech(base64Audio, text = "") {
  if (!base64Audio) {
    speakBrowserFallback(text);
    return;
  }
  audioQueue = audioQueue.then(() => new Promise((resolve) => {
    stopPlayback();
    const bytes = Uint8Array.from(atob(base64Audio), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    jarvisSpeaking = true;
    setState("SPEAKING");
    updateMicState();
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (currentAudio === audio) currentAudio = null;
      jarvisSpeaking = false;
      updateMicState();
      if (voiceActive && !vadFrame) vadLoop();
      resolve();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      jarvisSpeaking = false;
      updateMicState();
      speakBrowserFallback(text);
      resolve();
    };
    audio.play().catch(() => {
      speakBrowserFallback(text);
      resolve();
    });
  }));
}

async function testBackend(url) {
  const clean = url.replace(/\/$/, "");
  const headers = {};
  if (clean.includes(".loca.lt")) {
    headers["Bypass-Tunnel-Reminder"] = "true";
  }
  if (clean.includes("ngrok")) {
    headers["ngrok-skip-browser-warning"] = "true";
  }
  const res = await fetch(`${clean}/api/status`, {
    headers,
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error("Backend unreachable");
  return res.json();
}

async function saveBackend(url) {
  const clean = url.trim().replace(/\/$/, "");
  if (!clean) throw new Error("Enter a backend URL");
  if (window.location.protocol === "https:" && clean.startsWith("http://")) {
    throw new Error(
      "HTTPS app cannot use http:// backend. On your Mac run ./run_remote.sh and paste the https:// URL shown."
    );
  }
  const data = await testBackend(clean);
  localStorage.setItem(STORAGE_KEY, clean);
  if (data.model) modelLabel.textContent = data.model;
  setupOverlay.classList.add("hidden");
  closeSettings();
  connectWs();
  refreshStatus();
  return data;
}

function showSetupIfNeeded() {
  if (isAutoConnect()) {
    return false;
  }
  if (!apiBase()) {
    setupOverlay.classList.remove("hidden");
    return true;
  }
  return false;
}

function connectWs() {
  const base = apiBase();
  if (!base) return;
  if (wsConnecting || (ws && ws.readyState === WebSocket.OPEN)) return;
  wsConnecting = true;
  if (ws) {
    try { ws.close(); } catch (_) {}
    ws = null;
  }

  ws = new WebSocket(wsUrl());

  ws.onopen = () => {
    wsConnecting = false;
    reconnectAttempts = 0;
    lastPong = Date.now();
    setConn(true);
    appendLog("SYS: Connected to Raajarvis.");
    if (!logEl.querySelector(".ai")) {
      appendLog("Raajarvis: Iron HUD active. I'm online whenever your Mac is running.");
    }
    ws.send(JSON.stringify({ type: "register", client_id: clientId() }));
    ws.send(JSON.stringify({ type: "ping" }));
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
        const busy = jarvisSpeaking
          || backendState === "THINKING"
          || backendState === "SPEAKING"
          || backendState === "RECORDING";
        const limit = busy ? 180000 : 90000;
        if (Date.now() - lastPong > limit) {
          try { ws.close(); } catch (_) {}
        }
      }
    }, 8000);
  };

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    if (msg.type === "log") {
      const lower = msg.text.toLowerCase();
      if (lower.startsWith("jarvis:") || lower.startsWith("raajarvis:")) return;
      appendLog(msg.text);
      if (lower.includes("youtube")) pushRecent("YouTube");
      else if (lower.includes("whatsapp")) pushRecent("WhatsApp");
    }
    if (msg.type === "state") setState(msg.value);
    if (msg.type === "speech") {
      appendLog(`Raajarvis: ${msg.text}`);
      playSpeech(msg.audio, msg.text);
    }
    if (msg.type === "pong") lastPong = Date.now();
    if (msg.type === "interrupted") interruptJarvis();
    if (msg.type === "alarm") {
      schedulePhoneAlarm(msg.date, msg.time, msg.message);
      loadReminders();
    }
    if (msg.type === "muted") {
      muted = !!msg.value;
      muteBtn.textContent = muted ? "Mic off" : "Mic on";
      updateMicState();
    }
    if (msg.type === "file") {
      if (msg.name) {
        fileHint.textContent = `📎 ${msg.name}`;
        clearFileBtn.classList.remove("hidden");
      } else {
        fileHint.textContent = "Drop PDF, DOC, MP3, etc. or tap to upload";
        clearFileBtn.classList.add("hidden");
      }
    }
    if (msg.type === "file_index" && msg.summary) {
      fileHint.textContent = `📎 ${msg.name}`;
      clearFileBtn.classList.remove("hidden");
      appendLog(`SYS: Indexed — ${msg.summary.slice(0, 120)}…`);
    }
    if (msg.type === "memory") {
      updateMemoryHint(msg.entries || {}, msg.chat_count || 0);
    }
  };

  ws.onclose = () => {
    wsConnecting = false;
    ws = null;
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    setConn(false);
    if (!reconnectTimer && apiBase()) {
      reconnectAttempts += 1;
      const delay = Math.min(1500 + reconnectAttempts * 800, 8000);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWs();
        refreshStatus();
      }, delay);
    }
  };

  ws.onerror = () => ws.close();
}

async function sendChat(text, source = "text") {
  const trimmed = text.trim();
  if (!trimmed) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "chat", text: trimmed, client_id: clientId(), source }));
    return;
  }
  await fetch(`${apiBase()}/api/chat`, {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text: trimmed, client_id: clientId(), source }),
  });
}

async function transcribeBlob(blob) {
  if (blob.size < 1500) throw new Error("too short");
  const fd = new FormData();
  fd.append("audio", blob, "speech.webm");
  const res = await fetch(`${apiBase()}/api/transcribe`, {
    method: "POST",
    headers: apiHeaders(),
    body: fd,
  });
  if (!res.ok) throw new Error("transcribe failed");
  return (await res.json()).text;
}

function getMimeType() {
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
    return "audio/webm;codecs=opus";
  }
  if (MediaRecorder.isTypeSupported("audio/mp4")) return "audio/mp4";
  return "audio/webm";
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await fetch(`${apiBase()}/api/upload`, {
    method: "POST",
    headers: apiHeaders(),
    body: fd,
  });
  if (!res.ok) throw new Error("upload failed");
  const data = await res.json();
  if (data.name) pushRecent(data.name);
  return data;
}

async function clearFile() {
  await fetch(`${apiBase()}/api/upload`, { method: "DELETE" });
  fileHint.textContent = "Drop a file here or tap to upload";
  clearFileBtn.classList.add("hidden");
}

function stopVadRecording() {
  if (vadRecorder && vadRecorder.state === "recording") {
    vadRecorder.stop();
  }
}

function startVadRecording() {
  if (vadRecording || !vadStream || jarvisSpeaking || muted) return;
  vadChunks = [];
  vadRecording = true;
  vadSpeechSeen = false;
  vadSilenceSince = 0;
  vadRecorder = new MediaRecorder(vadStream, { mimeType: getMimeType() });
  vadRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) vadChunks.push(e.data);
  };
  vadRecorder.onstop = async () => {
    vadRecording = false;
    if (!vadChunks.length || jarvisSpeaking) return;
    const blob = new Blob(vadChunks, { type: vadRecorder.mimeType });
    try {
      const text = await transcribeBlob(blob);
      if (text) await sendChat(text, "voice");
    } catch {
      /* ignore short noise */
    }
  };
  vadRecorder.start();
}

function vadLoop() {
  if (!voiceActive || !vadAnalyser) return;

  const data = new Uint8Array(vadAnalyser.frequencyBinCount);
  vadAnalyser.getByteFrequencyData(data);
  let sum = 0;
  for (let i = 0; i < data.length; i++) sum += data[i];
  const level = sum / data.length;
  const now = performance.now();

  if (jarvisSpeaking && level > 20) {
    interruptJarvis();
    vadFrame = requestAnimationFrame(vadLoop);
    return;
  }

  if (jarvisSpeaking || muted) {
    if (vadRecording) stopVadRecording();
    vadFrame = requestAnimationFrame(vadLoop);
    return;
  }

  if (level > 16) {
    vadSilenceSince = 0;
    if (!vadRecording) startVadRecording();
    vadSpeechSeen = true;
  } else if (vadRecording && vadSpeechSeen) {
    if (!vadSilenceSince) vadSilenceSince = now;
    if (now - vadSilenceSince > 1500) {
      stopVadRecording();
      vadSpeechSeen = false;
      vadSilenceSince = 0;
    }
  }

  vadFrame = requestAnimationFrame(vadLoop);
}

function watchMicStream() {
  if (!vadStream) return;
  for (const track of vadStream.getAudioTracks()) {
    track.onended = () => {
      if (voiceActive && !muted) {
        appendLog("SYS: Mic reconnecting…");
        reactivateVoice();
      }
    };
  }
}

async function reactivateVoice() {
  const wasActive = voiceActive;
  deactivateVoice();
  if (wasActive) {
    await new Promise((r) => setTimeout(r, 400));
    await activateVoice();
  }
}

function startMicKeepAlive() {
  stopMicKeepAlive();
  micKeepAliveTimer = setInterval(async () => {
    if (!voiceActive || muted) return;
    if (vadCtx?.state === "suspended") {
      try { await vadCtx.resume(); } catch { /* ignore */ }
    }
    const tracks = vadStream?.getAudioTracks() || [];
    if (!tracks.length || tracks[0].readyState === "ended") {
      await reactivateVoice();
      return;
    }
    if (!vadFrame && voiceActive && !jarvisSpeaking) vadLoop();
  }, 8000);
}

function stopMicKeepAlive() {
  if (micKeepAliveTimer) clearInterval(micKeepAliveTimer);
  micKeepAliveTimer = null;
}

async function activateVoice() {
  if (voiceActive || muted) return;
  await ensureNotifications();
  try {
    vadStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    vadCtx = new AudioContext();
    await vadCtx.resume().catch(() => {});
    const source = vadCtx.createMediaStreamSource(vadStream);
    vadAnalyser = vadCtx.createAnalyser();
    vadAnalyser.fftSize = 1024;
    source.connect(vadAnalyser);
    voiceActive = true;
    sessionStorage.setItem(VOICE_ACTIVE_KEY, "1");
    watchMicStream();
    startMicKeepAlive();
    appendLog("SYS: Mic on — stays active until you tap mic again.");
    setState("LISTENING");
    updateMicState();
    vadLoop();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "mute", value: false }));
    }
  } catch {
    appendLog("ERR: Microphone permission denied.");
  }
}

function deactivateVoice() {
  voiceActive = false;
  sessionStorage.removeItem(VOICE_ACTIVE_KEY);
  stopMicKeepAlive();
  if (vadFrame) cancelAnimationFrame(vadFrame);
  vadFrame = null;
  stopVadRecording();
  if (vadStream) {
    vadStream.getTracks().forEach((t) => t.stop());
    vadStream = null;
  }
  if (vadCtx) {
    vadCtx.close().catch(() => {});
    vadCtx = null;
  }
  vadAnalyser = null;
  updateMicState();
  appendLog("SYS: Mic off.");
}

async function refreshMetrics() {
  const base = apiBase();
  if (!base) return;
  try {
    const res = await fetch(`${base}/api/metrics`, { headers: apiHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    const host = data.host || {};
    setBar(barCpu, cpuVal, host.cpu);
    setBar(barMem, memVal, host.memory);
    setBar(barDisk, diskVal, host.disk);
    if (data.file?.summary) {
      fileHint.textContent = `📎 ${data.file.name || "file"}`;
      clearFileBtn.classList.remove("hidden");
    }
  } catch {
    /* ignore */
  }
  if (navigator.getBattery) {
    try {
      const batt = await navigator.getBattery();
      const pct = (batt.level || 0) * 100;
      setBar(barBatt, battVal, pct);
      if (mobBatt) mobBatt.textContent = `${Math.round(pct)}%`;
    } catch {
      setBar(barBatt, battVal, 0);
      if (mobBatt) mobBatt.textContent = "—";
    }
  } else {
    if (battVal) battVal.textContent = "N/A";
    if (mobBatt) mobBatt.textContent = "N/A";
  }
  if (memVal && mobMem) mobMem.textContent = memVal.textContent;
}

function updateMemoryHint(entries, chatCount = 0) {
  if (!memoryHint) return;
  const keys = Object.keys(entries || {});
  const parts = [];
  if (chatCount > 0) parts.push(`${chatCount} msgs this device`);
  if (keys.length) parts.push(`${keys.length} facts saved`);
  memoryHint.textContent = parts.length
    ? parts.join(" · ")
    : "Session saved on this device";
}

async function loadMemory() {
  const base = apiBase();
  if (!base) return;
  try {
    const res = await fetch(`${base}/api/memory`, { headers: apiHeaders() });
    if (res.ok) {
      const data = await res.json();
      updateMemoryHint(data.entries || {}, data.chat_count || 0);
    }
  } catch {
    /* ignore */
  }
}

async function refreshStatus() {
  const base = apiBase();
  if (!base) return;
  try {
    const data = await testBackend(base);
    updateModelDisplay(data);
    setConn(true);
    const st = data.state || "READY";
    setState(st);
    if (statusHint) {
      statusHint.textContent = `Ollama · ${data.model || "ready"}`;
      statusHint.classList.remove("hidden");
    }
    if (data.file_name) {
      fileHint.textContent = data.file_name;
      clearFileBtn.classList.remove("hidden");
      pushRecent(data.file_name);
    }
    await refreshMetrics();
    await loadMemory();
    await loadReminders();
  } catch {
    setConn(false);
    updateModelDisplay({ ok: false });
    if (statusHint) statusHint.textContent = "Mac offline — reconnecting…";
    setHeroMode("OFFLINE");
    reconnectIfStale();
  }
}

function renderRemindersList(serverItems = []) {
  if (!remindersList) return;
  const merged = [];
  const seen = new Set();
  for (const item of [...serverItems, ...loadLocalAlarms()]) {
    const key = `${item.date}|${item.time}|${item.message}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(item);
  }
  merged.sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`));
  remindersList.innerHTML = "";
  if (!merged.length) {
    const li = document.createElement("li");
    li.className = "reminder-empty";
    li.textContent = "No reminders";
    remindersList.appendChild(li);
    updateTimerUi(0);
    return;
  }
  for (const item of merged.slice(0, 8)) {
    const li = document.createElement("li");
    if (item.source === "phone") li.classList.add("phone");
    const time = document.createElement("span");
    time.className = "rem-time";
    time.textContent = `${item.date} ${item.time}`;
    li.appendChild(time);
    li.appendChild(document.createTextNode(item.message || "Reminder"));
    remindersList.appendChild(li);
  }
  updateTimerUi(merged.length);
}

async function loadReminders() {
  const base = apiBase();
  let serverItems = [];
  if (base) {
    try {
      const res = await fetch(`${base}/api/reminders`, { headers: apiHeaders() });
      if (res.ok) {
        const data = await res.json();
        serverItems = data.reminders || [];
      }
    } catch {
      /* ignore */
    }
  }
  renderRemindersList(serverItems);
  updateTimerUi(
    serverItems.length + loadLocalAlarms().length
  );
}

function openSettings() {
  if (settingsBackendUrl) settingsBackendUrl.value = apiBase();
  loadSettingsFromBackend();
  settingsSidebar?.classList.remove("hidden");
  if (settingsSidebar) settingsSidebar.setAttribute("aria-hidden", "false");
}

function closeSettings() {
  settingsSidebar?.classList.add("hidden");
  if (settingsSidebar) settingsSidebar.setAttribute("aria-hidden", "true");
}

function tickClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateStr = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }).toUpperCase();
  if (clockEl) clockEl.textContent = now.toLocaleTimeString([], { hour12: false });
  if (todayTime) todayTime.textContent = timeStr;
  if (todayDate) todayDate.textContent = dateStr;
}

// Events
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || chatSending) return;
  chatSending = true;
  chatInput.value = "";
  try {
    await sendChat(text, "text");
  } finally {
    setTimeout(() => { chatSending = false; }, 800);
  }
});

micBtn.addEventListener("click", () => {
  if (muted) return;
  if (jarvisSpeaking) {
    interruptJarvis();
    if (!voiceActive) activateVoice();
    return;
  }
  if (voiceActive) deactivateVoice();
  else activateVoice();
});

if (stopBtn) stopBtn.addEventListener("click", () => interruptJarvis());

if (settingsSpeed) {
  settingsSpeed.addEventListener("input", () => {
    if (speedLabel) speedLabel.textContent = rateLabel(settingsSpeed.value);
  });
}

muteBtn.addEventListener("click", () => {
  muted = !muted;
  muteBtn.textContent = muted ? "Mic off" : "Mic on";
  if (muted && voiceActive) deactivateVoice();
  updateMicState();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "mute", value: muted }));
  }
});

settingsBtn.addEventListener("click", () => openSettings());

$("#closeSettingsBtn").addEventListener("click", () => closeSettings());

chatToggleBtn?.addEventListener("click", () => {
  logPanel?.classList.toggle("hidden");
});

gmailConnectBtn?.addEventListener("click", async () => {
  try {
    await connectGmail();
  } catch (e) {
    if (gmailStatusLine) gmailStatusLine.textContent = e.message || "Connect failed";
  }
});

$("#saveSettingsBtn").addEventListener("click", async () => {
  try {
    await applySettingsToBackend();
    if (settingsBackendUrl?.value?.trim()) {
      await saveBackend(settingsBackendUrl.value);
    }
    $("#settingsStatus").textContent = "Saved";
    closeSettings();
    appendLog("SYS: Settings saved.");
  } catch (e) {
    $("#settingsStatus").textContent = e.message || "Save failed";
  }
});

$("#saveBackendBtn").addEventListener("click", async () => {
  setupError.classList.add("hidden");
  try {
    await saveBackend(backendUrlInput.value);
  } catch (e) {
    setupError.textContent = e.message || "Could not connect. Is ./run_pwa.sh running?";
    setupError.classList.remove("hidden");
  }
});

fileZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  fileInput.value = "";
  if (!file || !apiBase()) return;
  try {
    await uploadFile(file);
  } catch {
    appendLog("ERR: File upload failed.");
  }
});

fileZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  fileZone.classList.add("drag");
});
fileZone.addEventListener("dragleave", () => fileZone.classList.remove("drag"));
fileZone.addEventListener("drop", async (e) => {
  e.preventDefault();
  fileZone.classList.remove("drag");
  const file = e.dataTransfer?.files?.[0];
  if (!file || !apiBase()) return;
  try {
    await uploadFile(file);
  } catch {
    appendLog("ERR: File upload failed.");
  }
});

clearFileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  clearFile().catch(() => {});
});

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installPrompt = e;
  installBtn.classList.remove("hidden");
});

installBtn.addEventListener("click", async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  installBtn.classList.add("hidden");
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").then((r) => r.update()).catch(() => {});
}

setInterval(tickClock, 1000);
tickClock();

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && apiBase()) {
    connectWs();
    refreshStatus();
    if (voiceActive) {
      if (vadCtx?.state === "suspended") vadCtx.resume().catch(() => {});
      if (!vadFrame) vadLoop();
    }
  }
});

async function boot() {
  renderRecentApps();
  localAlarmItems = loadLocalAlarms();
  renderRemindersList();
  ensureNotifications();
  restoreLocalAlarmsOnBoot();

  if (window.__JARVIS_DISCOVERY__?.url && !isAutoConnect()) {
    const fresh = await discoverBackend();
    if (fresh) {
      const saved = savedApi();
      if (saved !== fresh) {
        localStorage.setItem(STORAGE_KEY, fresh);
      }
    } else {
      const saved = savedApi();
      if (saved) {
        try {
          await testBackend(saved);
        } catch {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    }
  }

  if (isAutoConnect() || apiBase()) {
    if (!showSetupIfNeeded()) {
      connectWs();
      refreshStatus();
      loadSettingsFromBackend();
      setInterval(refreshMetrics, 8000);
      setInterval(loadReminders, 30000);
      startHealthWatch();
      if (sessionStorage.getItem(VOICE_ACTIVE_KEY) === "1") {
        setTimeout(() => activateVoice(), 800);
      }
    }
    return;
  }

  if (window.__JARVIS_DISCOVERY__?.url) {
    if (statusHint) statusHint.textContent = "Connecting to Raajarvis…";
    const url = await discoverBackendWithRetry(90000);
    if (url) {
      appendLog("SYS: Connected.");
      await connectDiscovered(url);
      loadSettingsFromBackend();
      startHealthWatch();
      return;
    }
  }

  showSetupIfNeeded();
}

boot();
