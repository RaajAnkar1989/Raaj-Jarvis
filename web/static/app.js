if (window.__JARVIS_PWA__) throw new Error("already loaded");
window.__JARVIS_PWA__ = true;

const $ = (sel) => document.querySelector(sel);

const logEl = $("#log");
const hudEl = $("#hud");
const stateLabel = $("#stateLabel");
const statusHint = $("#statusHint");
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
const settingsOverlay = $("#settingsOverlay");
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

const STORAGE_KEY = "jarvis_api";
const CLIENT_KEY = "jarvis_client_id";

function clientId() {
  let id = localStorage.getItem(CLIENT_KEY);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || `c_${Date.now()}`;
    localStorage.setItem(CLIENT_KEY, id);
  }
  return id;
}

function apiHeaders(extra = {}) {
  return {
    "X-Jarvis-Client-Id": clientId(),
    ...extra,
  };
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

function apiBase() {
  const saved = savedApi();
  if (saved) return saved;
  const { origin, port, hostname } = window.location;
  if (port === "8765" || hostname === "localhost" || hostname === "127.0.0.1") {
    return origin;
  }
  return "";
}

function wsUrl() {
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
  else if (lower.startsWith("jarvis:")) line.className = "ai";
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
}

function setState(state) {
  hudEl.className = "hud";
  const label = state || "OFFLINE";
  stateLabel.textContent = label;

  if (label === "SPEAKING") {
    jarvisSpeaking = true;
    hudEl.classList.add("speaking");
    statusHint.textContent = "JARVIS is speaking…";
    updateMicState();
  } else {
    jarvisSpeaking = false;
    if (label === "LISTENING") {
      hudEl.classList.add("listening");
      statusHint.textContent = voiceActive
        ? "Voice active — just speak naturally"
        : muted
          ? "Microphone muted"
          : "Tap mic once to activate voice, or type below";
    } else if (label === "THINKING") {
      hudEl.classList.add("thinking");
      statusHint.textContent = "Processing…";
    } else if (label === "MUTED") {
      hudEl.classList.add("muted");
      statusHint.textContent = "Microphone muted";
    } else if (label === "RECORDING") {
      hudEl.classList.add("listening");
      statusHint.textContent = "Listening…";
    } else {
      statusHint.textContent = apiBase() ? "Connecting…" : "Set backend URL in settings";
    }
    updateMicState();
  }
}

function updateMicState() {
  micBtn.disabled = muted || jarvisSpeaking;
  micBtn.classList.toggle("active", voiceActive);
  if (voiceActive) {
    micLabel.textContent = jarvisSpeaking ? "Speaking…" : "Voice active — speak now";
    voiceModeLabel.textContent = "Always-on";
  } else {
    micLabel.textContent = muted ? "Mic muted" : "Tap to activate voice";
    voiceModeLabel.textContent = "Tap to activate";
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
  const res = await fetch(`${url.replace(/\/$/, "")}/api/status`, {
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error("Backend unreachable");
  return res.json();
}

async function saveBackend(url) {
  const clean = url.trim().replace(/\/$/, "");
  if (!clean) throw new Error("Enter a backend URL");
  if (window.location.protocol === "https:" && clean.startsWith("http://")) {
    throw new Error(
      "HTTPS app cannot use http:// backend. Use Cloudflare Tunnel (https) or open http://YOUR-MAC-IP:8765 directly."
    );
  }
  const data = await testBackend(clean);
  localStorage.setItem(STORAGE_KEY, clean);
  backendLabel.textContent = shortBackend(clean);
  if (data.model) modelLabel.textContent = data.model;
  setupOverlay.classList.add("hidden");
  settingsOverlay.classList.add("hidden");
  connectWs();
  refreshStatus();
  return data;
}

function showSetupIfNeeded() {
  if (!apiBase()) {
    setupOverlay.classList.remove("hidden");
    return true;
  }
  backendLabel.textContent = shortBackend(apiBase());
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
    setConn(true);
    appendLog("SYS: Connected to JARVIS core.");
    ws.send(JSON.stringify({ type: "register", client_id: clientId() }));
    ws.send(JSON.stringify({ type: "ping" }));
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
      appendLog(`Jarvis: ${msg.text}`);
      playSpeech(msg.audio);
    }
    if (msg.type === "hello" && msg.lan_url) {
      appendLog(`SYS: Backend LAN URL: ${msg.lan_url}`);
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
    setConn(false);
    if (!reconnectTimer && apiBase()) {
      appendLog("SYS: Reconnecting…");
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWs();
      }, 2500);
    }
  };

  ws.onerror = () => ws.close();
}

async function sendChat(text) {
  const trimmed = text.trim();
  if (!trimmed) return;
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
  if (voiceActive || muted || jarvisSpeaking) return;
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
    appendLog("SYS: Voice activated — speak naturally.");
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
    memoryHint.textContent = "Device memory: JARVIS will remember your name, likes, and notes.";
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
    if (data.model) modelLabel.textContent = data.model;
    setConn(true);
    if (data.state) setState(data.state);
    if (data.file_name) {
      fileHint.textContent = `📎 ${data.file_name}`;
      clearFileBtn.classList.remove("hidden");
    }
    await refreshMetrics();
    await loadMemory();
  } catch {
    setConn(false);
    modelLabel.textContent = "—";
  }
}

function tickClock() {
  clockEl.textContent = new Date().toLocaleTimeString([], { hour12: false });
}

// Events
chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = chatInput.value;
  chatInput.value = "";
  sendChat(text);
});

micBtn.addEventListener("click", () => {
  if (muted || jarvisSpeaking) return;
  if (voiceActive) deactivateVoice();
  else activateVoice();
});

muteBtn.addEventListener("click", () => {
  muted = !muted;
  muteBtn.textContent = muted ? "Mic off" : "Mic on";
  if (muted && voiceActive) deactivateVoice();
  updateMicState();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "mute", value: muted }));
  }
});

settingsBtn.addEventListener("click", () => {
  settingsBackendUrl.value = apiBase();
  settingsOverlay.classList.remove("hidden");
});

$("#closeSettingsBtn").addEventListener("click", () => {
  settingsOverlay.classList.add("hidden");
});

$("#saveSettingsBtn").addEventListener("click", async () => {
  try {
    await saveBackend(settingsBackendUrl.value);
    appendLog("SYS: Backend updated.");
  } catch (e) {
    $("#settingsStatus").textContent = e.message || "Connection failed";
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

if (!showSetupIfNeeded()) {
  connectWs();
  refreshStatus();
  setInterval(refreshMetrics, 4000);
}
