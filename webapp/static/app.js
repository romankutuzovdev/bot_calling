const $ = (id) => document.getElementById(id);

let sessionId = null;
let agentName = "Александра";
let recognizing = false;
let recognition = null;
let voiceProfile = null;
let currentAudio = null;
let ttsVoice = "ru-RU-SvetlanaNeural";
let ttsEngine = "clone";

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return r;
}

function addBubble(role, text, flag = null) {
  const chat = $("chat");
  const div = document.createElement("div");
  div.className = `bubble ${role}` + (flag ? " flag" : "");
  const who = role === "bot" ? agentName : "Вы";
  div.innerHTML = `<span class="who">${who}</span>${escapeHtml(text)}`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function applyVoicePick(value) {
  const v = value || "clone:andrey";
  if (v.startsWith("clone:")) {
    ttsEngine = "clone";
    ttsVoice = "ru-RU-SvetlanaNeural";
  } else if (v.startsWith("edge:")) {
    ttsEngine = "edge";
    ttsVoice = v.slice("edge:".length);
  }
  if ($("tts_engine")) $("tts_engine").value = ttsEngine;
  if ($("tts_voice")) $("tts_voice").value = ttsVoice;
  updateTtsHint();
}

function syncVoicePickFromState() {
  const pick = $("tts_voice_pick");
  if (!pick) return;
  if (ttsEngine === "clone") pick.value = "clone:andrey";
  else pick.value = `edge:${ttsVoice}`;
}

function updateTtsHint() {
  const hint = $("ttsHint");
  if (!hint) return;
  if (ttsEngine === "clone") {
    hint.textContent =
      "Выбран Андрей (XTTS). Речь из voices/my_voice_22k.wav. На CPU 20–90 сек на фразу. Нужен pip install torch + coqui-tts.";
  } else {
    hint.textContent = "Выбран Microsoft Neural — быстро, но не клон сэмпла.";
  }
}

async function speak(text) {
  if (!text) return;
  const status = $("saveStatus");
  try {
    if (currentAudio) {
      currentAudio.pause();
      URL.revokeObjectURL(currentAudio.src);
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    if (ttsEngine === "clone" && status) {
      status.textContent = "Генерация голоса (CPU)…";
    }

    const r = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: ttsVoice, engine: ttsEngine }),
    });
    if (!r.ok) throw new Error(await r.text());
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    audio.onended = () => URL.revokeObjectURL(url);
    if (status) status.textContent = "";
    await audio.play();
  } catch (e) {
    console.warn("TTS failed, fallback speechSynthesis", e);
    if (status) status.textContent = "";
    if (!window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ru-RU";
    speechSynthesis.speak(u);
  }
}

async function refreshHealth() {
  const el = $("health");
  const cs = $("cloneStatus");
  try {
    const h = await api("/api/health");
    const eng = h.tts_engine === "clone" ? "XTTS" : "Edge";
    if (h.ok) {
      el.className = "health ok";
      el.textContent = `Ollama OK · ${h.model} · голос: ${eng}`;
    } else {
      el.className = "health bad";
      el.textContent = `Ollama: нет модели ${h.model}. Установите: ollama pull ${h.model}`;
    }
    if (cs && h.clone) {
      cs.textContent = h.clone.speaker_ok
        ? `Сэмпл голоса OK: ${h.clone.speaker_path}`
        : `Нет сэмпла. ${h.clone.note || ""} Проверьте: dir C:\\bot_calling\\voices`;
      if (!h.clone.speaker_ok && h.clone.root) {
        cs.textContent += ` (root=${h.clone.root})`;
      }
    }
  } catch {
    el.className = "health bad";
    el.textContent = "Ollama недоступна (http://127.0.0.1:11434)";
  }
}

async function loadScript() {
  const s = await api("/api/script");
  $("agent_name").value = s.agent_name || "";
  $("company").value = s.company || "";
  $("opening").value = s.opening || "";
  $("system_prompt").value = s.system_prompt || "";
  $("ollama_model").value = s.ollama_model || "qwen2.5:3b";
  $("ollama_url").value = s.ollama_url || "http://127.0.0.1:11434";
  ttsVoice = s.tts_voice || "ru-RU-SvetlanaNeural";
  ttsEngine = s.tts_engine || "clone";
  if ($("tts_voice")) $("tts_voice").value = ttsVoice;
  if ($("tts_engine")) $("tts_engine").value = ttsEngine;
  syncVoicePickFromState();
  updateTtsHint();
  agentName = s.agent_name || "Бот";
}

async function saveScript() {
  const pick = $("tts_voice_pick");
  if (pick) applyVoicePick(pick.value);
  ttsVoice = $("tts_voice").value;
  ttsEngine = $("tts_engine").value;
  const body = {
    agent_name: $("agent_name").value.trim(),
    company: $("company").value.trim(),
    opening: $("opening").value.trim(),
    system_prompt: $("system_prompt").value.trim(),
    ollama_model: $("ollama_model").value.trim(),
    ollama_url: $("ollama_url").value.trim(),
    temperature: 0.45,
    tts_engine: ttsEngine,
    tts_voice: ttsVoice,
    tts_rate: "+8%",
    speaker_wav: "voices/my_voice_22k.wav",
  };
  await api("/api/script", { method: "PUT", body: JSON.stringify(body) });
  agentName = body.agent_name;
  $("saveStatus").textContent = "Сохранено";
  setTimeout(() => ($("saveStatus").textContent = ""), 2000);
  await refreshHealth();
}

async function resetCall() {
  $("chat").innerHTML = "";
  voiceProfile = null;
  $("profile").classList.add("hidden");
  const data = await api("/api/session/reset", { method: "POST" });
  sessionId = data.session_id;
  agentName = data.agent_name || agentName;
  addBubble("bot", data.opening);
  await speak(data.opening);
}

async function sendMessage(text) {
  const message = (text || $("message").value).trim();
  if (!message) return;
  $("message").value = "";
  addBubble("user", message);
  $("btnSend").disabled = true;
  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        message,
        voice_profile: voiceProfile,
      }),
    });
    sessionId = data.session_id;
    agentName = data.agent_name || agentName;
    addBubble("bot", data.reply, data.flag);
    await speak(data.reply);
    if (data.flag === "CLOSE_DEAL") addBubble("bot", "✓ Заявка зафиксирована");
    if (data.flag === "END_CALL") addBubble("bot", "Звонок завершён");
  } catch (e) {
    addBubble("bot", `Ошибка: ${e.message}`);
  } finally {
    $("btnSend").disabled = false;
    $("message").focus();
  }
}

async function sampleVoiceProfile(stream, ms = 1200) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  src.connect(analyser);
  const data = new Float32Array(analyser.fftSize);

  await new Promise((r) => setTimeout(r, ms));
  analyser.getFloatTimeDomainData(data);
  let sum = 0;
  for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
  const energy = Math.sqrt(sum / data.length);

  const sr = ctx.sampleRate;
  let bestLag = 0;
  let bestCorr = -1;
  const minLag = Math.floor(sr / 350);
  const maxLag = Math.floor(sr / 70);
  for (let lag = minLag; lag < maxLag; lag++) {
    let corr = 0;
    for (let i = 0; i < data.length - lag; i++) corr += data[i] * data[i + lag];
    corr /= data.length - lag;
    if (corr > bestCorr) {
      bestCorr = corr;
      bestLag = lag;
    }
  }
  const pitch = bestLag > 0 ? sr / bestLag : 0;
  let gender = "unknown";
  if (pitch > 0 && pitch < 160) gender = "male";
  else if (pitch > 185) gender = "female";

  let emotion = "neutral";
  if (energy > 0.08) emotion = "engaged";
  if (energy > 0.12) emotion = "tense";
  if (energy < 0.03) emotion = "calm";

  let tempo = "medium";
  if (energy > 0.07) tempo = "fast";
  if (energy < 0.035) tempo = "slow";

  try { await ctx.close(); } catch {}

  voiceProfile = { gender, emotion, tempo };
  const g = { male: "мужской", female: "женский", unknown: "неясно" }[gender];
  const e = { calm: "спокойный", engaged: "вовлечённый", tense: "напряжённый", neutral: "нейтральный" }[emotion];
  const t = { slow: "медленный", medium: "средний", fast: "быстрый" }[tempo];
  const el = $("profile");
  el.classList.remove("hidden");
  el.textContent = `Голос: пол≈${g} · эмоция≈${e} · темп≈${t} (F0≈${pitch.toFixed(0)} Hz)`;
  return voiceProfile;
}

function initSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    $("btnMic").disabled = true;
    $("btnMic").title = "Голос не поддерживается в этом браузере (нужен Chrome/Edge)";
    return;
  }
  recognition = new SR();
  recognition.lang = "ru-RU";
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onstart = () => {
    recognizing = true;
    $("btnMic").classList.add("active");
  };
  recognition.onend = () => {
    recognizing = false;
    $("btnMic").classList.remove("active");
  };
  recognition.onerror = () => {
    recognizing = false;
    $("btnMic").classList.remove("active");
  };
  recognition.onresult = (ev) => {
    let finalText = "";
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const t = ev.results[i][0].transcript;
      if (ev.results[i].isFinal) finalText += t;
      else interim += t;
    }
    $("message").value = (finalText || interim).trim();
    if (finalText.trim()) sendMessage(finalText.trim());
  };
}

async function toggleMic() {
  if (!recognition) return;
  if (recognizing) {
    recognition.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    sampleVoiceProfile(stream).catch(() => {});
    setTimeout(() => stream.getTracks().forEach((t) => t.stop()), 1500);
  } catch {}
  recognition.start();
}

$("btnSave").onclick = () => saveScript().catch((e) => alert(e.message));
$("btnReset").onclick = () => resetCall().catch((e) => alert(e.message));
$("btnSend").onclick = () => sendMessage();
$("btnMic").onclick = () => toggleMic();
$("btnTestVoice").onclick = () => {
  const pick = $("tts_voice_pick");
  if (pick) applyVoicePick(pick.value);
  speak(
    ttsEngine === "clone"
      ? "Здравствуйте! Это тест клона голоса Андрея."
      : "Здравствуйте! Это тест голоса Microsoft Neural."
  );
};
if ($("tts_voice_pick")) {
  $("tts_voice_pick").onchange = () => {
    applyVoicePick($("tts_voice_pick").value);
  };
}
$("message").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

(async function boot() {
  initSpeech();
  await loadScript();
  await refreshHealth();
  await resetCall();
  setInterval(refreshHealth, 15000);
})();
