const $ = (id) => document.getElementById(id);

let sessionId = null;
let agentName = "Александра";
let recognizing = false;
let recognition = null;
let voiceProfile = null;
let currentAudio = null;
let ttsVoice = "ru-RU-SvetlanaNeural";
let ttsEngine = "elevenlabs";
let audioUnlocked = false;
let pendingAudioUrl = null;

function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  try {
    const a = new Audio();
    a.src =
      "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
    a.volume = 0.01;
    a.play().catch(() => {});
  } catch {}
}

function showPlayButton(show) {
  const b = $("btnPlayAudio");
  if (!b) return;
  if (show) b.classList.remove("hidden");
  else b.classList.add("hidden");
}

async function playUrl(url) {
  if (currentAudio) {
    try {
      currentAudio.pause();
    } catch {}
  }
  const audio = new Audio(url);
  currentAudio = audio;
  audio.onended = () => {
    try {
      URL.revokeObjectURL(url);
    } catch {}
    showPlayButton(false);
    pendingAudioUrl = null;
  };
  await audio.play();
  showPlayButton(false);
}

function sniffAudio(buf) {
  const u8 = new Uint8Array(buf.slice(0, 12));
  if (u8[0] === 0xff && (u8[1] & 0xe0) === 0xe0) return "audio/mpeg";
  if (u8[0] === 0x49 && u8[1] === 0x44 && u8[2] === 0x33) return "audio/mpeg";
  if (u8[0] === 0x52 && u8[1] === 0x49 && u8[2] === 0x46 && u8[3] === 0x46) return "audio/wav";
  if (u8[0] === 0x4f && u8[1] === 0x67 && u8[2] === 0x67 && u8[3] === 0x53) return "audio/ogg";
  return null;
}

async function speak(text) {
  if (!text) return;
  const status = $("saveStatus");
  try {
    if (currentAudio) {
      currentAudio.pause();
      try {
        if (currentAudio.src && currentAudio.src.startsWith("blob:")) {
          URL.revokeObjectURL(currentAudio.src);
        }
      } catch {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    if (ttsEngine === "clone" && status) status.textContent = "Генерация голоса (CPU)…";
    if (ttsEngine === "elevenlabs" && status) status.textContent = "ElevenLabs…";

    const voiceForApi =
      ttsEngine === "elevenlabs"
        ? ($("elevenlabs_voice_id") && $("elevenlabs_voice_id").value.trim()) || ttsVoice
        : ttsVoice;

    const r = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: voiceForApi, engine: ttsEngine }),
    });

    const ct = (r.headers.get("content-type") || "").toLowerCase();
    const buf = await r.arrayBuffer();
    const head = new TextDecoder("utf-8", { fatal: false }).decode(buf.slice(0, 300));

    if (!r.ok) throw new Error(head || r.statusText);
    if (!buf.byteLength) {
      throw new Error("Пустое аудио (0 байт). Проверьте API key, Voice ID и интернет сервера.");
    }

    const sniffed = sniffAudio(buf);
    if (!sniffed) {
      throw new Error(
        "Ответ не аудио (" + buf.byteLength + " байт, Content-Type=" + ct + "):\n" + head
      );
    }

    const blob = new Blob([buf], { type: sniffed });
    const url = URL.createObjectURL(blob);
    pendingAudioUrl = url;
    if (status) status.textContent = "";

    try {
      await playUrl(url);
    } catch (playErr) {
      const m = String(playErr && playErr.message ? playErr.message : playErr);
      showPlayButton(true);
      if (status) status.textContent = "Нажмите «▶ Слушать»";
      if (!/interact|NotAllowedError|play\(\)/i.test(m)) {
        console.warn("play failed, file looks valid — use ▶ Слушать", playErr);
      }
    }
  } catch (e) {
    console.warn("TTS failed", e);
    if (status) status.textContent = "";
    const msg = String(e && e.message ? e.message : e);
    if (/interact|NotAllowedError|play\(\)/i.test(msg)) {
      showPlayButton(true);
      return;
    }
    if (ttsEngine === "clone" || ttsEngine === "elevenlabs") {
      alert(
        (ttsEngine === "elevenlabs" ? "ElevenLabs не сработал.\n\n" : "Клон XTTS не сработал.\n\n") +
          msg.slice(0, 800)
      );
      return;
    }
    if (!window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ru-RU";
    speechSynthesis.speak(u);
  }
}

async function api(path, opts = {}) {
  const ctrl = new AbortController();
  const ms = opts.timeoutMs || 12000;
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const { timeoutMs, ...fetchOpts } = opts;
    const r = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(fetchOpts.headers || {}) },
      signal: ctrl.signal,
      ...fetchOpts,
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error(t || r.statusText);
    }
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) return r.json();
    return r;
  } catch (e) {
    if (e && e.name === "AbortError") {
      throw new Error(`Таймаут ${ms}мс: ${path} (бэкенд/Ollama не отвечают)`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
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
  const v = value || "elevenlabs";
  if (v === "elevenlabs" || v.startsWith("elevenlabs")) {
    ttsEngine = "elevenlabs";
    ttsVoice = ($("elevenlabs_voice_id") && $("elevenlabs_voice_id").value.trim()) || "";
  } else if (v.startsWith("clone:")) {
    ttsEngine = "clone";
    ttsVoice = "ru-RU-SvetlanaNeural";
  } else if (v.startsWith("edge:")) {
    ttsEngine = "edge";
    ttsVoice = v.slice("edge:".length);
  }
  if ($("tts_engine")) $("tts_engine").value = ttsEngine;
  if ($("tts_voice")) $("tts_voice").value = ttsVoice;
  const box = $("elevenlabs_box");
  if (box) box.style.display = ttsEngine === "elevenlabs" ? "" : "none";
  updateTtsHint();
}

function syncVoicePickFromState() {
  const pick = $("tts_voice_pick");
  if (!pick) return;
  if (ttsEngine === "elevenlabs") pick.value = "elevenlabs";
  else if (ttsEngine === "clone") pick.value = "clone:andrey";
  else pick.value = `edge:${ttsVoice}`;
  const box = $("elevenlabs_box");
  if (box) box.style.display = ttsEngine === "elevenlabs" ? "" : "none";
}

function updateTtsHint() {
  const hint = $("ttsHint");
  if (!hint) return;
  if (ttsEngine === "elevenlabs") {
    hint.textContent =
      "Модель eleven_multilingual_v2. Если звук не играет сам — нажмите «▶ Слушать» (ограничение браузера).";
  } else if (ttsEngine === "clone") {
    hint.textContent = "Локальный XTTS — медленно на CPU.";
  } else {
    hint.textContent = "Microsoft Neural — быстро, не ваш голос.";
  }
}

async function refreshHealth() {
  const el = $("health");
  const cs = $("cloneStatus");
  try {
    const h = await api("/api/health");
    const eng =
      h.tts_engine === "elevenlabs"
        ? "ElevenLabs"
        : h.tts_engine === "clone"
          ? "XTTS"
          : "Edge";
    if (h.ok) {
      el.className = "health ok";
      el.textContent = `Ollama OK · ${h.model} · голос: ${eng}`;
    } else {
      el.className = "health bad";
      el.textContent = `Ollama: нет модели ${h.model}. Установите: ollama pull ${h.model}`;
    }
    if (cs) {
      const parts = [];
      if (h.elevenlabs) {
        parts.push(
          h.elevenlabs.configured
            ? `ElevenLabs API: OK${h.elevenlabs.voice_id_set ? " · Voice ID задан" : " · нужен Voice ID"}`
            : "ElevenLabs: нет API key"
        );
      }
      if (h.clone) {
        parts.push(
          h.clone.speaker_ok
            ? `Сэмпл XTTS OK`
            : `Сэмпл XTTS: нет файла`
        );
      }
      cs.textContent = parts.join(" · ");
    }
  } catch {
    el.className = "health bad";
    el.textContent =
      "Ollama/API недоступны: " + String(err && err.message ? err.message : err).slice(0, 120);
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
  ttsEngine = s.tts_engine || "elevenlabs";
  if ($("tts_voice")) $("tts_voice").value = ttsVoice;
  if ($("tts_engine")) $("tts_engine").value = ttsEngine;
  if ($("elevenlabs_voice_id")) {
    $("elevenlabs_voice_id").value = s.elevenlabs_voice_id || "";
  }
  if ($("elevenlabs_api_key")) {
    $("elevenlabs_api_key").placeholder = s.elevenlabs_api_key_set
      ? "ключ уже сохранён — введите новый чтобы заменить"
      : "xi-... API key";
    $("elevenlabs_api_key").value = "";
  }
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
    elevenlabs_api_key: ($("elevenlabs_api_key") && $("elevenlabs_api_key").value.trim()) || "",
    elevenlabs_voice_id: ($("elevenlabs_voice_id") && $("elevenlabs_voice_id").value.trim()) || "",
    elevenlabs_model: "eleven_multilingual_v2",
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
$("btnReset").onclick = () => {
  unlockAudio();
  resetCall().catch((e) => alert(e.message));
};
$("btnSend").onclick = () => {
  unlockAudio();
  sendMessage();
};
$("btnMic").onclick = () => {
  unlockAudio();
  toggleMic();
};
if ($("btnPlayAudio")) {
  $("btnPlayAudio").onclick = () => {
    unlockAudio();
    if (pendingAudioUrl) playUrl(pendingAudioUrl).catch((e) => alert(e.message));
  };
}
$("btnTestVoice").onclick = () => {
  unlockAudio();
  const pick = $("tts_voice_pick");
  if (pick) applyVoicePick(pick.value);
  if (ttsEngine === "elevenlabs") {
    ttsVoice = ($("elevenlabs_voice_id") && $("elevenlabs_voice_id").value.trim()) || ttsVoice;
  }
  speak(
    ttsEngine === "elevenlabs"
      ? "Здравствуйте! Это тест голоса Андрея через ElevenLabs."
      : ttsEngine === "clone"
        ? "Здравствуйте! Это тест клона голоса XTTS."
        : "Здравствуйте! Это тест голоса Microsoft Neural."
  );
};
if ($("tts_voice_pick")) {
  $("tts_voice_pick").onchange = () => {
    applyVoicePick($("tts_voice_pick").value);
  };
}
$("message").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    unlockAudio();
    sendMessage();
  }
});
document.addEventListener("click", () => unlockAudio(), { once: true });

(async function boot() {
  initSpeech();
  try {
    await loadScript();
  } catch (e) {
    console.error(e);
    const st = $("saveStatus");
    if (st) st.textContent = "Нет связи с API: " + String(e.message || e).slice(0, 100);
  }
  await refreshHealth();
  try {
    await resetCall();
  } catch (e) {
    console.error(e);
  }
  setInterval(refreshHealth, 15000);
})();
