/* Orchestrates UI: WebSocket, voice, timers, keyboard shortcuts */

(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    ws: null,
    running: false,
    runStartedAt: 0,
    stageStartedAt: 0,
    stageBudget: 0,
    timerHandle: null,
    mediaRecorder: null,
    recognition: null,
    images: {},
    forceMock: false,
  };

  window.__lastImages = state.images;

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    state.ws = ws;
    ws.onopen = () => setStatus("Conectado");
    ws.onclose = () => {
      setStatus("Reconectando…");
      setTimeout(connect, 1200);
    };
    ws.onerror = () => setStatus("Erro no WebSocket");
    ws.onmessage = (ev) => {
      try {
        handleEvent(JSON.parse(ev.data));
      } catch (e) {
        console.error(e);
      }
    };
  }

  function send(msg) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify(msg));
    }
  }

  function setStatus(text) {
    $("status-line").textContent = text;
  }

  function handleEvent(e) {
    const t = e.type;
    if (t === "hello") {
      state.forceMock = !!e.force_mock;
      if (state.forceMock) $("chk-mock").checked = true;
      // warm connections when page opens (real mode)
      if (!state.forceMock) send({ action: "warmup_ping" });
      return;
    }
    if (t === "transcript") {
      $("transcript").textContent = e.text || "";
      if (!e.final) $("transcript").classList.add("live");
      else $("transcript").classList.remove("live");
      return;
    }
    if (t === "run_started" || t === "replay_started") {
      onRunStart(e);
      return;
    }
    if (t === "stage_started") {
      Graph.setStage(e.stage);
      $("active-pattern").textContent = `${e.pattern} · ${e.talk_name}`;
      state.stageStartedAt = performance.now();
      state.stageBudget = e.budget_seconds || 0;
      $("timer-stage-label").textContent = (e.talk_name || e.stage || "ETAPA").toUpperCase();
      $("timer-budget").textContent = state.stageBudget ? `/ ${fmt(state.stageBudget)}` : "";
      $("stream-text").textContent = "";
      return;
    }
    if (t === "stage_finished") {
      Graph.finishStage(e.stage);
      return;
    }
    if (t === "agent_started") {
      Graph.setAgentActive(e.agent, true);
      $("active-agent-label").textContent = e.label || Graph.LABELS[e.agent] || e.agent;
      if (!e.dimmed) $("stream-text").textContent = "";
      return;
    }
    if (t === "agent_delta") {
      Graph.setAgentActive(e.agent, true);
      $("stream-text").textContent += e.delta || "";
      $("stream-text").scrollTop = $("stream-text").scrollHeight;
      return;
    }
    if (t === "agent_finished") {
      Graph.setAgentActive(e.agent, false);
      return;
    }
    if (t === "agent_message") {
      Graph.sendMessage(e.from, e.to);
      return;
    }
    if (t === "image_ready") {
      const url = e.url || e.path;
      if (e.kind && url) {
        state.images[e.kind] = url;
        window.__lastImages = state.images;
      }
      return;
    }
    if (t === "run_finished") {
      onRunFinish(e);
      return;
    }
    if (t === "replay_finished") {
      state.running = false;
      stopTimers();
      setStatus("Replay concluído");
      return;
    }
    if (t === "info") {
      setStatus(e.message || "");
      return;
    }
    if (t === "error") {
      setStatus(e.message || "Erro");
      state.running = false;
      stopTimers();
      return;
    }
    if (t === "warmup_result") {
      const ok = e.result && !e.result.skipped;
      setStatus(ok ? "Warmup de modelos ok" : "Warmup pulado / sem Azure");
    }
  }

  function onRunStart(e) {
    state.running = true;
    state.images = {};
    window.__lastImages = state.images;
    Proposal.hide();
    Graph.reset();
    state.runStartedAt = performance.now();
    state.stageStartedAt = performance.now();
    startTimers();
    if (e.request) $("transcript").textContent = e.request;
    if (e.company) setStatus(`Rodando · ${e.company}${e.mock || e.type === "replay_started" ? " · mock/replay" : ""}`);
    $("stream-text").textContent = "";
  }

  function onRunFinish(e) {
    state.running = false;
    stopTimers();
    const total = e.total_seconds != null ? e.total_seconds : (performance.now() - state.runStartedAt) / 1000;
    $("timer-total").textContent = fmt(total);
    setStatus(`Concluído em ${fmt(total)}`);
    // brief beat then proposal reveal
    setTimeout(() => {
      Proposal.show({
        company: e.company,
        proposal_md: e.proposal_md,
        images: e.images,
        stage_times: e.stage_times,
        total_seconds: total,
      });
    }, 600);
  }

  function startTimers() {
    stopTimers();
    state.timerHandle = setInterval(() => {
      if (!state.runStartedAt) return;
      const total = (performance.now() - state.runStartedAt) / 1000;
      const stage = (performance.now() - state.stageStartedAt) / 1000;
      $("timer-total").textContent = fmt(total);
      $("timer-stage").textContent = fmt(stage);
    }, 200);
  }

  function stopTimers() {
    if (state.timerHandle) clearInterval(state.timerHandle);
    state.timerHandle = null;
  }

  function fmt(sec) {
    const s = Math.max(0, Math.floor(sec));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }

  function startRun() {
    const text = $("request-input").value.trim() ||
      "Preciso de uma proposta de treinamento de agentes de IA para a empresa Contoso";
    $("transcript").textContent = text;
    send({
      action: "start",
      request: text,
      mock: $("chk-mock").checked,
    });
  }

  function startReplay() {
    send({ action: "replay", speed: 1 });
    setStatus("Replay…");
  }

  function markGolden() {
    send({ action: "mark_golden" });
  }

  /* ---- Voice ---- */
  function setupVoice() {
    const btn = $("btn-mic");
    let pressTimer = null;

    btn.addEventListener("mousedown", () => beginVoice());
    btn.addEventListener("mouseup", () => endVoice());
    btn.addEventListener("mouseleave", () => endVoice());
    btn.addEventListener("touchstart", (ev) => {
      ev.preventDefault();
      beginVoice();
    });
    btn.addEventListener("touchend", () => endVoice());

    window.addEventListener("keydown", (ev) => {
      if (ev.code === "Space" && !ev.repeat && document.activeElement !== $("request-input")) {
        ev.preventDefault();
        beginVoice();
      }
      if (ev.key === "r" && !ev.shiftKey && document.activeElement !== $("request-input")) {
        ev.preventDefault();
        startReplay();
      }
      if (ev.key === "R" && ev.shiftKey) {
        ev.preventDefault();
        markGolden();
      }
    });
    window.addEventListener("keyup", (ev) => {
      if (ev.code === "Space" && document.activeElement !== $("request-input")) {
        ev.preventDefault();
        endVoice();
      }
    });
  }

  function beginVoice() {
    $("btn-mic").classList.add("recording");
    if ($("chk-webspeech").checked && "webkitSpeechRecognition" in window) {
      startWebSpeech();
      return;
    }
    startMediaRecorder();
  }

  function endVoice() {
    $("btn-mic").classList.remove("recording");
    if (state.recognition) {
      try { state.recognition.stop(); } catch (_) {}
      state.recognition = null;
    }
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }
  }

  function startWebSpeech() {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) {
      setStatus("Web Speech indisponível — use texto ou backend");
      startMediaRecorder();
      return;
    }
    const rec = new Rec();
    state.recognition = rec;
    rec.lang = "pt-BR";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (event) => {
      let interim = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      const text = (finalText || interim).trim();
      $("transcript").textContent = text;
      $("transcript").classList.toggle("live", !finalText);
      if (finalText) {
        $("request-input").value = finalText;
        startRun();
      }
    };
    rec.onerror = () => setStatus("Web Speech falhou — tente texto");
    rec.start();
  }

  async function startMediaRecorder() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const rec = new MediaRecorder(stream);
      state.mediaRecorder = rec;
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        const fd = new FormData();
        fd.append("file", blob, "audio.webm");
        try {
          const res = await fetch("/api/transcribe", { method: "POST", body: fd });
          const data = await res.json();
          if (data.ok && data.text) {
            $("request-input").value = data.text;
            $("transcript").textContent = data.text;
            startRun();
          } else {
            setStatus(data.error || "Transcrição indisponível — use Web Speech ou texto");
          }
        } catch (err) {
          setStatus("Falha ao enviar áudio");
        }
      };
      rec.start();
    } catch (err) {
      setStatus("Microfone indisponível — use a caixa de texto");
    }
  }

  /* ---- Boot ---- */
  function boot() {
    Graph.init($("graph"));
    connect();
    setupVoice();
    $("btn-start").addEventListener("click", startRun);
    $("btn-replay").addEventListener("click", startReplay);
    $("btn-golden").addEventListener("click", markGolden);
    $("btn-stop").addEventListener("click", () => send({ action: "stop" }));
    $("btn-print").addEventListener("click", () => window.print());
    $("btn-back").addEventListener("click", () => Proposal.hide());
    $("request-input").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") startRun();
    });
    // Prefer mock checkbox if server started with --mock
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg) => {
        if (cfg.force_mock) $("chk-mock").checked = true;
      })
      .catch(() => {});
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
