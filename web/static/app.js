if (window.__JARVIS_PWA__) throw new Error("already loaded");
window.__JARVIS_PWA__ = true;

const $ = (sel) => document.querySelector(sel);

const logEl = $("#log");
const hudEl = $("#hud");
const stateLabel = $("#stateLabel");
const stateChip = $("#stateChip");
const statusHint = $("#statusHint");
const stopBtn = $("#stopBtn");
const settingsVoice = $("#settingsVoice");
const settingsPersonality = $("#settingsPersonality");
const settingsSpeed = $("#settingsSpeed");
const speedLabel = $("#speedLabel");
const gmailClientId = $("#gmailClientId");
const gmailClientSecret = $("#gmailClientSecret");
const gmailRefreshToken = $("#gmailRefreshToken");
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
const sidebarBackdrop = $("#sidebarBackdrop");
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
const heroHud = $("#heroHud");
const heroState = $("#heroState");
const clockDisplay = $("#clockDisplay");
const remindersList = $("#remindersList");

const STORAGE_KEY = "jarvis_api";
const CLIENT_KEY = "jarvis_client_id";
const PREFS_KEY = "raajarvis_prefs";
const ALARM_KEY = "raajarvis_alarms";

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
  const gsec = gmailClientSecret?.value?.trim();
  const gref = gmailRefreshToken?.value?.trim();
  if (gid && gsec && gref) {
    await fetch(`${base}/api/gmail/settings`, {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        client_id: gid,
        client_secret: gsec,
        refresh_token: gref,
      }),
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

function schedulePhoneAlarm(date, time, message) {
  if (!date || !time) return;
  const when = new Date(`${date}T${time}:00`);
  if (Number.isNaN(when.getTime())) return;
  const ms = when.getTime() - Date.now();
  if (ms <= 0) return;
  const id = `${date}_${time}_${message}`;
  if (scheduledAlarms.has(id)) return;
  const timer = setTimeout(async () => {
    scheduledAlarms.delete(id);
    if (Notification.permission === "granted") {
      new Notification("Raajarvis Reminder", { body: message });
    }
    appendLog(`SYS: Reminder — ${message}`);
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.value = 0.15;
      osc.start();
      setTimeout(() => osc.stop(), 400);
    } catch {
      /* ignore */
    }
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

async function discoverBackend() {
  const cfg = window.__JARVIS_DISCOVERY__;
  if (!cfg?.url) return null;
  try {
    const res = await fetch(`${cfg.url}?t=${Date.now()}`, {
      signal: AbortSignal.timeout(12000),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const raw = (await res.text()).trim();
    const line = raw.split("\n").find((l) => l.startsWith("https://")) || raw;
    const url = line.trim().replace(/\/$/, "");
    if (!url.startsWith("https://")) return null;
    await testBackend(url);
    return url;
  } catch {
    return null;
  }
}

async function discoverBackendWithRetry(maxMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const url = await discoverBackend();
    if (url) return url;
    statusHint.textContent = "Looking for JARVIS on your Mac…";
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
  const line = document.createElement("div");
  const lower = text.toLowerCase();
  if (lower.startsWith("you:")) line.className = "you";
  else if (lower.startsWith("jarvis:") || lower.startsWith("raajarvis:")) line.className = "ai";
  else if (lower.includes("err")) line.className = "err";
  else if (lower.startsWith("file:")) line.className = "sys";
  else line.className = "sys";
  line.textContent = text;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function setConn(ok) {
  connDot.className = "conn-dot " + (ok ? "online" : "offline");
  connDot.title = ok ? "Connected to backend" : "Backend offline";
  if (stateChip) {
    stateChip.classList.toggle("online", ok);
    stateChip.classList.toggle("offline", !ok);
    if (!ok && stateChip.textContent !== "SPEAKING" && stateChip.textContent !== "LISTENING") {
      stateChip.textContent = ok ? "ONLINE" : "OFFLINE";
    }
  }
  if (heroHud) {
    heroHud.classList.toggle("online", ok);
    if (!ok && heroState) heroState.textContent = "OFFLINE";
  }
}

function setHeroMode(state) {
  if (!heroHud) return;
  heroHud.classList.remove("speaking", "listening", "thinking");
  const s = (state || "").toUpperCase();
  if (s === "SPEAKING") heroHud.classList.add("speaking");
  else if (s === "LISTENING" || s === "RECORDING") heroHud.classList.add("listening");
  else if (s === "THINKING") heroHud.classList.add("thinking");
  if (heroState) heroState.textContent = s || "STANDBY";
}

function setState(state) {
  const label = state || "STANDBY";
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
  micBtn.disabled = muted;
  micBtn.classList.toggle("active", voiceActive);
  if (voiceActive) {
    micLabel.textContent = jarvisSpeaking ? "Interrupt — speak" : "Listening…";
    voiceModeLabel.textContent = "Voice on";
  } else {
    micLabel.textContent = muted ? "Mic muted" : "Tap to talk";
    voiceModeLabel.textContent = muted ? "Muted" : "Tap mic";
  }
}

function stopPlayback() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
}

function playSpeech(base64Audio) {
  if (!base64Audio) return;
  audioQueue = audioQueue.then(() => new Promise((resolve) => {
    stopPlayback();
    const bytes = Uint8Array.from(atob(base64Audio), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    jarvisSpeaking = true;
    updateMicState();
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (currentAudio === audio) currentAudio = null;
      jarvisSpeaking = false;
      updateMicState();
      resolve();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      jarvisSpeaking = false;
      updateMicState();
      resolve();
    };
    audio.play().catch(() => resolve());
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
        if (Date.now() - lastPong > 45000) {
          try { ws.close(); } catch (_) {}
        }
      }
    }, 15000);
  };

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    if (msg.type === "log") {
      if (!msg.text.toLowerCase().startsWith("jarvis:")) {
        appendLog(msg.text);
      }
    }
    if (msg.type === "state") setState(msg.value);
    if (msg.type === "speech") {
      appendLog(`Raajarvis: ${msg.text}`);
      playSpeech(msg.audio);
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
      updateMemoryHint(msg.entries || {});
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
      const delay = Math.min(2500 + reconnectAttempts * 1000, 12000);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWs();
      }, delay);
    }
  };

  ws.onerror = () => ws.close();
}

async function sendChat(text) {
  const trimmed = text.trim();
  if (!trimmed) return;
  appendLog(`You: ${trimmed}`);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "chat", text: trimmed, client_id: clientId() }));
    return;
  }
  await fetch(`${apiBase()}/api/chat`, {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text: trimmed, client_id: clientId() }),
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
  return res.json();
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
      if (text) await sendChat(text);
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
    if (now - vadSilenceSince > 700) {
      stopVadRecording();
      vadSpeechSeen = false;
      vadSilenceSince = 0;
    }
  }

  vadFrame = requestAnimationFrame(vadLoop);
}

async function activateVoice() {
  if (voiceActive || muted) return;
  await ensureNotifications();
  try {
    vadStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    vadCtx = new AudioContext();
    const source = vadCtx.createMediaStreamSource(vadStream);
    vadAnalyser = vadCtx.createAnalyser();
    vadAnalyser.fftSize = 1024;
    source.connect(vadAnalyser);
    voiceActive = true;
    appendLog("SYS: Voice on — speak anytime.");
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
  appendLog("SYS: Voice session ended.");
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
      setBar(barBatt, battVal, (batt.level || 0) * 100);
    } catch {
      setBar(barBatt, battVal, 0);
    }
  } else {
    if (battVal) battVal.textContent = "N/A";
  }
}

function updateMemoryHint(entries) {
  if (!memoryHint) return;
  const keys = Object.keys(entries || {});
  if (!keys.length) {
    memoryHint.textContent = "Raajarvis remembers your preferences on this device.";
    return;
  }
  const preview = keys.slice(-3).map((k) => {
    const v = entries[k]?.value || entries[k];
    return `${k}: ${String(v).slice(0, 40)}`;
  }).join(" · ");
  memoryHint.textContent = `Remembers (${keys.length}): ${preview}`;
}

async function loadMemory() {
  const base = apiBase();
  if (!base) return;
  try {
    const res = await fetch(`${base}/api/memory`, { headers: apiHeaders() });
    if (res.ok) {
      const data = await res.json();
      updateMemoryHint(data.entries || {});
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
    if (data.model && modelLabel) modelLabel.textContent = data.model;
    setConn(true);
    if (stateChip) stateChip.classList.add("online");
    const st = data.state || "READY";
    setState(st);
    if (statusHint) statusHint.textContent = `Ollama online · ${data.model || "ready"}`;
    if (data.file_name) {
      fileHint.textContent = `📎 ${data.file_name}`;
      clearFileBtn.classList.remove("hidden");
    }
    await refreshMetrics();
    await loadMemory();
    await loadReminders();
  } catch {
    setConn(false);
    if (modelLabel) modelLabel.textContent = "Mac offline";
    if (statusHint) statusHint.textContent = "Cannot reach Mac — is jarvis-stack running?";
    setHeroMode("OFFLINE");
    if (stateChip) {
      stateChip.textContent = "OFFLINE";
      stateChip.classList.add("offline");
    }
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
    li.textContent = "No upcoming reminders";
    remindersList.appendChild(li);
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
}

function openSettings() {
  if (settingsBackendUrl) settingsBackendUrl.value = apiBase();
  loadSettingsFromBackend();
  settingsSidebar?.classList.add("open");
  sidebarBackdrop?.classList.remove("hidden");
  if (settingsSidebar) settingsSidebar.setAttribute("aria-hidden", "false");
}

function closeSettings() {
  settingsSidebar?.classList.remove("open");
  sidebarBackdrop?.classList.add("hidden");
  if (settingsSidebar) settingsSidebar.setAttribute("aria-hidden", "true");
}

function tickClock() {
  const now = new Date().toLocaleTimeString([], { hour12: false });
  if (clockEl) clockEl.textContent = now;
  if (clockDisplay) clockDisplay.textContent = now;
}

// Events
chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = chatInput.value;
  chatInput.value = "";
  sendChat(text);
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
sidebarBackdrop?.addEventListener("click", () => closeSettings());

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
  }
});

async function boot() {
  localAlarmItems = loadLocalAlarms();
  renderRemindersList();

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
      return;
    }
  }

  showSetupIfNeeded();
}

boot();
