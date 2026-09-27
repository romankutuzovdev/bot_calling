const $ = (id) => document.getElementById(id);

let sessionId = null;
let agentName = "Александра";
let recognizing = false;
let recognition = null;
let voiceProfile = null;
let currentAudio = null;
let ttsVoice = "08aoIyv8fQNQEj9A0YX6";
let ttsEngine = "elevenlabs";
let audioUnlocked = false;
let pendingAudioUrl = null;
let callActive = false;
let botSpeaking = false;
let listenTimer = null;
let sendingVoice = false;
let showLog = false;

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

function setCallStatus(mode, text) {
  const el = $("callStatus");
  const stage = $("phoneStage");
  const card = document.querySelector(".chat-card");
  if (!el) return;
  if (!mode) {
    el.className = "call-status idle";
    el.textContent = text || "Нажмите «Начать звонок»";
    if (stage) stage.className = "phone-stage";
    if (card) card.classList.remove("in-call");
    return;
  }
  el.className = "call-status " + mode;
  el.textContent = text || "";
  if (stage) {
    stage.className = "phone-stage";
    if (mode === "speaking" || mode === "thinking") stage.classList.add("is-speaking");
    if (mode === "listening") stage.classList.add("is-listening");
  }
  if (card && callActive) card.classList.add("in-call");
}

function setLiveCaption(text, show) {
  const el = $("liveCaption");
  if (!el) return;
  if (!show || !text) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.classList.remove("hidden");
  el.textContent = text;
}

function syncPhoneHeader() {
  const name = ($("agent_name") && $("agent_name").value.trim()) || agentName || "Александра";
  const company = ($("company") && $("company").value.trim()) || "МультиГлобал Групп";
  if ($("phoneName")) $("phoneName").textContent = name;
  if ($("phoneCompany")) $("phoneCompany").textContent = company;
  if ($("phoneAvatar")) $("phoneAvatar").textContent = (name[0] || "А").toUpperCase();
}

function updateCallButton() {
  const b = $("btnReset");
  const logBtn = $("btnToggleLog");
  if (!b) return;
  if (callActive) {
    b.textContent = "Сбросить трубку";
    b.classList.remove("primary");
    b.classList.add("ghost");
    if (logBtn) {
      logBtn.classList.remove("hidden");
      logBtn.textContent = "Скрыть текст";
    }
  } else {
    b.textContent = "Начать звонок";
    b.classList.add("primary");
    b.classList.remove("ghost");
    if (logBtn) logBtn.classList.add("hidden");
  }
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
  return new Promise((resolve, reject) => {
    audio.onended = () => {
      try {
        URL.revokeObjectURL(url);
      } catch {}
      showPlayButton(false);
      pendingAudioUrl = null;
      resolve();
    };
    audio.onerror = () => reject(new Error("audio play error"));
    audio
      .play()
      .then(() => {
        showPlayButton(false);
      })
      .catch(reject);
  });
}

function sniffAudio(buf) {
  const u8 = new Uint8Array(buf.slice(0, 12));
  if (u8[0] === 0xff && (u8[1] & 0xe0) === 0xe0) return "audio/mpeg";
  if (u8[0] === 0x49 && u8[1] === 0x44 && u8[2] === 0x33) return "audio/mpeg";
  if (u8[0] === 0x52 && u8[1] === 0x49 && u8[2] === 0x46 && u8[3] === 0x46) return "audio/wav";
  if (u8[0] === 0x4f && u8[1] === 0x67 && u8[2] === 0x67 && u8[3] === 0x53) return "audio/ogg";
  return null;
}

function stopListening() {
  if (listenTimer) {
    clearTimeout(listenTimer);
    listenTimer = null;
  }
  if (recognition && recognizing) {
    try {
      recognition.stop();
    } catch {}
  }
}

function scheduleListen() {
  if (!callActive || botSpeaking || sendingVoice) return;
  if (listenTimer) clearTimeout(listenTimer);
  listenTimer = setTimeout(() => {
    listenTimer = null;
    if (callActive && !botSpeaking && !sendingVoice) startListening();
  }, 350);
}

async function startListening() {
  if (!recognition || !callActive || botSpeaking || recognizing || sendingVoice) return;
  setCallStatus("listening", "Слушаю вас… говорите");
  try {
    recognition.start();
  } catch (e) {
    // already started — retry shortly
    scheduleListen();
  }
}

async function ensureMicOnce() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    sampleVoiceProfile(stream).catch(() => {});
    setTimeout(() => stream.getTracks().forEach((t) => t.stop()), 900);
    return true;
  } catch (e) {
    setCallStatus("listening", "Нет доступа к микрофону — разрешите в браузере");
    return false;
  }
}

async function speak(text) {
  if (!text) return;
  const status = $("saveStatus");
  botSpeaking = true;
  stopListening();
  setCallStatus(callActive ? "speaking" : null, callActive ? "Бот говорит…" : "");
  try {
    if (currentAudio) {
      try {
        currentAudio.pause();
      } catch {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    if (ttsEngine === "clone" && status) status.textContent = "Генерация голоса (CPU)…";
    if (ttsEngine === "elevenlabs" && status) status.textContent = "ElevenLabs…";

    const voiceForApi =
      ($("tts_voice_pick") && $("tts_voice_pick").value.trim()) ||
      ($("elevenlabs_voice_id") && $("elevenlabs_voice_id").value.trim()) ||
      ttsVoice ||
      CORPORAT_VOICE_ID;

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
    await new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "ru-RU";
      u.onend = resolve;
      u.onerror = resolve;
      speechSynthesis.speak(u);
    });
  } finally {
    botSpeaking = false;
    if (callActive) scheduleListen();
    else setCallStatus(null);
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

const CORPORAT_VOICE_ID = "08aoIyv8fQNQEj9A0YX6";
const MY_BOICE_VOICE_ID = "ucPFZZGlUSewYNikXxqt";
const KNOWN_EL_VOICES = [
  { voice_id: CORPORAT_VOICE_ID, name: "Corporat", label: "Corporat" },
  { voice_id: MY_BOICE_VOICE_ID, name: "My Boice", label: "My Boice" },
];

function applyVoicePick(value) {
  const id = (value || CORPORAT_VOICE_ID).trim();
  const known = KNOWN_EL_VOICES.find((v) => v.voice_id === id);
  ttsEngine = "elevenlabs";
  ttsVoice = known ? known.voice_id : CORPORAT_VOICE_ID;
  if ($("tts_engine")) $("tts_engine").value = "elevenlabs";
  if ($("tts_voice")) $("tts_voice").value = ttsVoice;
  if ($("tts_voice_pick")) $("tts_voice_pick").value = ttsVoice;
  if ($("elevenlabs_voice_id")) $("elevenlabs_voice_id").value = ttsVoice;
  if ($("elevenlabs_voice_pick")) $("elevenlabs_voice_pick").value = ttsVoice;
  const box = $("elevenlabs_box");
  if (box) box.style.display = "";
  updateTtsHint();
}

function syncVoicePickFromState() {
  const id =
    ttsEngine === "elevenlabs" && ttsVoice && KNOWN_EL_VOICES.some((v) => v.voice_id === ttsVoice)
      ? ttsVoice
      : CORPORAT_VOICE_ID;
  applyVoicePick(id);
}

function updateTtsHint() {
  const hint = $("ttsHint");
  if (!hint) return;
  const name = (KNOWN_EL_VOICES.find((v) => v.voice_id === ttsVoice) || {}).name || "Corporat";
  hint.textContent = `Выбран голос: ${name}. Нажмите «Прослушать голос» или «Сохранить скрипт».`;
}

async function loadElevenLabsVoices() {
  // Только квота — в UI ровно 2 голоса
  const quota = $("elQuotaHint");
  const pick = $("tts_voice_pick");
  if (pick) {
    const current =
      ($("elevenlabs_voice_id") && $("elevenlabs_voice_id").value.trim()) ||
      ttsVoice ||
      CORPORAT_VOICE_ID;
    pick.value = KNOWN_EL_VOICES.some((v) => v.voice_id === current) ? current : CORPORAT_VOICE_ID;
    applyVoicePick(pick.value);
  }
  try {
    const data = await api("/api/elevenlabs/voices", { timeoutMs: 45000 });
    if (quota) {
      const s = data.subscription;
      if (s && s.ok) {
        const left = s.characters_remaining;
        const replies = s.approx_replies_left;
        quota.textContent =
          `План: ${s.tier || "?"} · использовано ${s.character_count}/${s.character_limit || "?"} символов` +
          (left != null
            ? ` · осталось ≈${left} (~${replies} коротких реплик / ~${s.approx_minutes_tts} мин речи)`
            : "");
      } else {
        quota.textContent =
          "Free обычно 10 000 символов/мес. Лимит: " + ((s && s.error) || data.error || "—");
      }
    }
  } catch (e) {
    if (quota) quota.textContent = "Не удалось загрузить лимит: " + String(e.message || e).slice(0, 80);
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
  ttsEngine = "elevenlabs";
  const savedId = (s.elevenlabs_voice_id || s.tts_voice || CORPORAT_VOICE_ID).trim();
  ttsVoice = KNOWN_EL_VOICES.some((v) => v.voice_id === savedId) ? savedId : CORPORAT_VOICE_ID;
  if ($("elevenlabs_api_key")) {
    $("elevenlabs_api_key").placeholder = s.elevenlabs_api_key_set
      ? "ключ уже сохранён — введите новый чтобы заменить"
      : "xi-... API key";
    $("elevenlabs_api_key").value = "";
  }
  applyVoicePick(ttsVoice);
  agentName = s.agent_name || "Бот";
  syncPhoneHeader();
  await loadElevenLabsVoices();
}

async function saveScript() {
  applyVoicePick(($("tts_voice_pick") && $("tts_voice_pick").value) || CORPORAT_VOICE_ID);
  const body = {
    agent_name: $("agent_name").value.trim(),
    company: $("company").value.trim(),
    opening: $("opening").value.trim(),
    system_prompt: $("system_prompt").value.trim(),
    ollama_model: $("ollama_model").value.trim(),
    ollama_url: $("ollama_url").value.trim(),
    temperature: 0.45,
    tts_engine: "elevenlabs",
    tts_voice: ttsVoice,
    tts_rate: "+8%",
    speaker_wav: "voices/my_voice_22k.wav",
    elevenlabs_api_key: ($("elevenlabs_api_key") && $("elevenlabs_api_key").value.trim()) || "",
    elevenlabs_voice_id: ttsVoice || CORPORAT_VOICE_ID,
    elevenlabs_model: "eleven_multilingual_v2",
  };
  await api("/api/script", { method: "PUT", body: JSON.stringify(body) });
  agentName = body.agent_name;
  $("saveStatus").textContent = "Сохранено";
  setTimeout(() => ($("saveStatus").textContent = ""), 2000);
  await refreshHealth();
}

async function endCall(reason) {
  callActive = false;
  stopListening();
  botSpeaking = false;
  sendingVoice = false;
  updateCallButton();
  setLiveCaption("", false);
  const card = document.querySelector(".chat-card");
  if (card) card.classList.remove("in-call");
  if (reason) {
    setCallStatus(null, reason);
    addBubble("bot", reason);
  } else {
    setCallStatus(null);
  }
}

async function startCall() {
  unlockAudio();
  callActive = true;
  showLog = true;
  if ($("chat")) $("chat").classList.remove("hidden");
  updateCallButton();
  syncPhoneHeader();
  setCallStatus("speaking", "Соединение…");
  setLiveCaption("", false);
  $("chat").innerHTML = "";
  if ($("message")) $("message").value = "";
  voiceProfile = null;
  $("profile").classList.add("hidden");

  const micOk = await ensureMicOnce();
  if (!micOk) {
    callActive = false;
    updateCallButton();
    return;
  }

  try {
    const data = await api("/api/session/reset", { method: "POST" });
    sessionId = data.session_id;
    agentName = data.agent_name || agentName;
    syncPhoneHeader();
    addBubble("bot", data.opening);
    setLiveCaption(data.opening, true);
    await speak(data.opening);
  } catch (e) {
    addBubble("bot", "Ошибка старта: " + (e.message || e));
    setCallStatus("listening", "Не удалось начать — попробуйте ещё раз");
    callActive = false;
    updateCallButton();
  }
}

async function resetCall() {
  callActive = false;
  stopListening();
  updateCallButton();
  setCallStatus(null);
  setLiveCaption("", false);
  const card = document.querySelector(".chat-card");
  if (card) card.classList.remove("in-call");
  $("chat").innerHTML = "";
  if ($("chat")) $("chat").classList.remove("hidden");
  voiceProfile = null;
  $("profile").classList.add("hidden");
  try {
    const data = await api("/api/session/reset", { method: "POST" });
    sessionId = data.session_id;
    agentName = data.agent_name || agentName;
    syncPhoneHeader();
  } catch (e) {
    console.error(e);
  }
}

async function sendMessage(text) {
  const message = (text || $("message").value).trim();
  if (!message) return;
  $("message").value = "";
  addBubble("user", message);
  $("btnSend").disabled = true;
  sendingVoice = true;
  stopListening();
  if (callActive) {
    setCallStatus("thinking", "Думает…");
    setLiveCaption("Вы: " + message, true);
  }
  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        message,
        voice_profile: voiceProfile,
      }),
      timeoutMs: 120000,
    });
    sessionId = data.session_id;
    agentName = data.agent_name || agentName;
    addBubble("bot", data.reply, data.flag);
    if (callActive) setLiveCaption(data.reply, true);
    await speak(data.reply);
    if (data.flag === "CLOSE_DEAL") {
      await endCall("Заявка зафиксирована. До свидания!");
    } else if (data.flag === "END_CALL") {
      await endCall("Звонок завершён. До свидания!");
    }
  } catch (e) {
    addBubble("bot", `Ошибка: ${e.message}`);
    if (callActive) {
      setCallStatus("listening", "Ошибка связи — говорите ещё раз");
      scheduleListen();
    }
  } finally {
    sendingVoice = false;
    $("btnSend").disabled = false;
    if (!callActive) $("message").focus();
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
    if (callActive) setCallStatus("listening", "Слушаю вас… говорите");
  };
  recognition.onend = () => {
    recognizing = false;
    $("btnMic").classList.remove("active");
    // нон-стоп: снова слушаем, пока звонок идёт
    if (callActive && !botSpeaking && !sendingVoice) scheduleListen();
  };
  recognition.onerror = (ev) => {
    recognizing = false;
    $("btnMic").classList.remove("active");
    const err = ev && ev.error;
    // no-speech / aborted — нормально, просто перезапускаем
    if (callActive && err && err !== "aborted" && err !== "no-speech") {
      setCallStatus("listening", "Не расслышала, говорите ещё раз…");
    }
    if (callActive && !botSpeaking && !sendingVoice) scheduleListen();
  };
  recognition.onresult = (ev) => {
    let finalText = "";
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const t = ev.results[i][0].transcript;
      if (ev.results[i].isFinal) finalText += t;
      else interim += t;
    }
    const shown = (finalText || interim).trim();
    if (shown) {
      if ($("message")) $("message").value = shown;
      if (callActive) setLiveCaption("Вы: " + shown, true);
    }
    if (finalText.trim()) {
      stopListening();
      sendMessage(finalText.trim());
    }
  };
}

async function toggleMic() {
  if (!recognition) return;
  if (recognizing) {
    recognition.stop();
    return;
  }
  if (callActive) {
    startListening();
    return;
  }
  await ensureMicOnce();
  try {
    recognition.start();
  } catch {}
}

$("btnSave").onclick = () => saveScript().catch((e) => alert(e.message));
if ($("btnToggleLog")) {
  $("btnToggleLog").onclick = () => {
    showLog = !showLog;
    const chat = $("chat");
    if (!chat) return;
    if (showLog) chat.classList.remove("hidden");
    else chat.classList.add("hidden");
    $("btnToggleLog").textContent = showLog ? "Скрыть текст" : "Показать текст";
  };
}
$("btnReset").onclick = () => {
  unlockAudio();
  if (callActive) {
    endCall("Звонок завершён вами.");
  } else {
    startCall().catch((e) => alert(e.message));
  }
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
  applyVoicePick(($("tts_voice_pick") && $("tts_voice_pick").value) || CORPORAT_VOICE_ID);
  const name = (KNOWN_EL_VOICES.find((v) => v.voice_id === ttsVoice) || {}).name || "Corporat";
  speak(`Здравствуйте! Это тест голоса ${name}.`);
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
  updateCallButton();
  syncPhoneHeader();
  setCallStatus(null);
  applyVoicePick(CORPORAT_VOICE_ID);
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
