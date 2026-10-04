(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    messages: [{
      role: "system",
      content: "You are the TJ Trading OS copilot. Be concise. Never claim guaranteed returns. Respect risk limits and never suggest bypassing live-trading safety gates."
    }],
    recorder: null,
    stream: null,
    chunks: [],
    recording: false,
  };

  const ui = {
    provider: $("provider"), baseUrlWrap: $("baseUrlWrap"), baseUrl: $("baseUrl"),
    aiKey: $("aiKey"), model: $("model"), fetchModels: $("fetchModels"),
    useForEngine: $("useForEngine"), modelStatus: $("modelStatus"),
    fishKey: $("fishKey"), fetchAudio: $("fetchAudio"), voice: $("voice"),
    fishModel: $("fishModel"), audioStatus: $("audioStatus"),
    systemBadge: $("systemBadge"), brokerBadge: $("brokerBadge"),
    engineBadge: $("engineBadge"), killBadge: $("killBadge"),
    riskMetric: $("riskMetric"), positionMetric: $("positionMetric"), modeMetric: $("modeMetric"),
    checkMt5: $("checkMt5"), mt5Details: $("mt5Details"),
    engineDetails: $("engineDetails"), engineStatusText: $("engineStatusText"),
    startEngine: $("startEngine"), scanNow: $("scanNow"), stopEngine: $("stopEngine"),
    emergencyStop: $("emergencyStop"), resumeEngine: $("resumeEngine"),
    refreshProposals: $("refreshProposals"), proposalList: $("proposalList"),
    refreshEvents: $("refreshEvents"), eventList: $("eventList"),
    chatFab: $("chatFab"), chatPanel: $("chatPanel"), closeChat: $("closeChat"),
    messages: $("messages"), chatForm: $("chatForm"), chatInput: $("chatInput"),
    voiceBtn: $("voiceBtn"), orbWrap: $("orbWrap"), voiceOrb: $("voiceOrb"), orbLabel: $("orbLabel"),
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"
    }[c]));
  }

  async function json(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {"Content-Type":"application/json", ...(options.headers || {})},
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`);
    return payload;
  }

  function addMessage(role, text) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.textContent = text;
    ui.messages.appendChild(div);
    ui.messages.scrollTop = ui.messages.scrollHeight;
  }

  function setOrb(mode, label) {
    ui.orbWrap.classList.remove("hidden");
    ui.voiceOrb.className = "voice-orb active";
    if (mode === "thinking") ui.voiceOrb.classList.add("thinking");
    if (mode === "speaking") ui.voiceOrb.classList.add("speaking");
    ui.orbLabel.textContent = label;
  }

  function hideOrb() {
    ui.voiceOrb.className = "voice-orb";
    ui.orbWrap.classList.add("hidden");
  }

  async function loadHealth() {
    try {
      const h = await json("/health");
      ui.systemBadge.textContent = "SYSTEM ONLINE";
      ui.systemBadge.classList.remove("warn");
      ui.riskMetric.textContent = `${(h.risk_per_trade * 100).toFixed(2)}%`;
      ui.positionMetric.textContent = h.max_open_positions;
      ui.modeMetric.textContent = "CONFIRMED LIVE";
      ui.brokerBadge.textContent = h.live_enabled && h.live_armed ? "LIVE ARMED" : "LIVE LOCKED";
    } catch {
      ui.systemBadge.textContent = "SYSTEM OFFLINE";
      ui.systemBadge.classList.add("warn");
    }
  }

  async function loadProviders() {
    try {
      const data = await json("/ai/providers");
      ui.provider.innerHTML = "";
      for (const p of data.providers) {
        const option = document.createElement("option");
        option.value = p.id;
        option.textContent = p.label;
        ui.provider.appendChild(option);
      }
      providerChanged();
    } catch (err) {
      ui.modelStatus.textContent = err.message;
    }
  }

  function providerChanged() {
    const custom = ui.provider.value === "openai-compatible";
    ui.baseUrlWrap.classList.toggle("hidden", !custom);
    if (!custom) ui.baseUrl.value = "";
    ui.model.innerHTML = '<option value="">Select a model</option>';
  }

  async function fetchModels() {
    if (!ui.aiKey.value.trim()) {
      ui.modelStatus.textContent = "Enter an AI provider API key first.";
      return;
    }
    ui.fetchModels.disabled = true;
    ui.modelStatus.textContent = "Fetching models…";
    try {
      const data = await json("/ai/models/fetch", {
        method: "POST",
        body: JSON.stringify({
          provider: ui.provider.value,
          api_key: ui.aiKey.value,
          base_url: ui.baseUrl.value || null,
        }),
      });
      ui.model.innerHTML = "";
      for (const id of data.models) {
        const option = document.createElement("option");
        option.value = id;
        option.textContent = id;
        ui.model.appendChild(option);
      }
      ui.modelStatus.textContent = `${data.models.length} models loaded.`;
    } catch (err) {
      ui.modelStatus.textContent = err.message;
    } finally {
      ui.fetchModels.disabled = false;
    }
  }

  async function configureEngineAI() {
    if (!ui.aiKey.value.trim() || !ui.model.value) {
      ui.modelStatus.textContent = "Fetch a model and enter its API key first.";
      return;
    }
    try {
      const data = await json("/engine/ai/configure", {
        method: "POST",
        body: JSON.stringify({
          provider: ui.provider.value,
          api_key: ui.aiKey.value,
          base_url: ui.baseUrl.value || null,
          model: ui.model.value,
        }),
      });
      ui.modelStatus.textContent = `Engine AI: ${data.provider} / ${data.model}`;
      await refreshEngine();
    } catch (err) {
      ui.modelStatus.textContent = err.message;
    }
  }

  async function fetchAudio() {
    if (!ui.fishKey.value.trim()) {
      ui.audioStatus.textContent = "Enter your Fish Audio API key first.";
      return;
    }
    ui.fetchAudio.disabled = true;
    ui.audioStatus.textContent = "Fetching Fish voices…";
    try {
      const data = await json("/voice/fish/models/fetch", {
        method: "POST",
        body: JSON.stringify({api_key: ui.fishKey.value, page_size: 100, page_number: 1}),
      });
      ui.voice.innerHTML = '<option value="">Default voice</option>';
      for (const item of data.models) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.title;
        ui.voice.appendChild(option);
      }
      ui.audioStatus.textContent = `${data.models.length} Fish voices loaded.`;
    } catch (err) {
      ui.audioStatus.textContent = err.message;
    } finally {
      ui.fetchAudio.disabled = false;
    }
  }

  function aiReady() {
    if (!ui.aiKey.value.trim()) throw new Error("Connect an AI provider first.");
    if (!ui.model.value) throw new Error("Fetch and select an AI model first.");
  }

  async function askAI(userText) {
    aiReady();
    state.messages.push({role:"user", content:userText});
    addMessage("user", userText);
    setOrb("thinking", "Thinking");
    try {
      const data = await json("/ai/chat", {
        method:"POST",
        body:JSON.stringify({
          provider:ui.provider.value,
          api_key:ui.aiKey.value,
          base_url:ui.baseUrl.value || null,
          model:ui.model.value,
          messages:state.messages,
        }),
      });
      state.messages.push({role:"assistant", content:data.message});
      addMessage("assistant", data.message);
      return data.message;
    } catch (err) {
      addMessage("error", err.message);
      throw err;
    } finally {
      if (!state.recording) hideOrb();
    }
  }

  async function speak(text) {
    if (!ui.fishKey.value.trim()) return;
    setOrb("speaking", "Speaking");
    const response = await fetch("/voice/fish/tts", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        api_key:ui.fishKey.value,
        text,
        reference_id:ui.voice.value || null,
        model:ui.fishModel.value,
        format:"mp3",
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Fish Audio TTS failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    await new Promise((resolve, reject) => {
      audio.addEventListener("ended", resolve, {once:true});
      audio.addEventListener("error", reject, {once:true});
      audio.play().catch(reject);
    });
    URL.revokeObjectURL(url);
    hideOrb();
  }

  async function startRecording() {
    if (!ui.fishKey.value.trim()) throw new Error("Fish Audio API key is required for voice conversation.");
    aiReady();
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error("This browser does not support microphone voice capture.");
    }
    state.stream = await navigator.mediaDevices.getUserMedia({audio:true});
    state.chunks = [];
    state.recorder = new MediaRecorder(state.stream);
    state.recorder.addEventListener("dataavailable", e => {
      if (e.data.size) state.chunks.push(e.data);
    });
    state.recorder.addEventListener("stop", transcribeRecording, {once:true});
    state.recorder.start();
    state.recording = true;
    ui.voiceBtn.textContent = "■";
    setOrb("listening", "Listening — tap stop when finished");
  }

  function stopRecording() {
    if (!state.recorder || state.recorder.state === "inactive") return;
    state.recording = false;
    ui.voiceBtn.textContent = "●";
    state.recorder.stop();
    state.stream?.getTracks().forEach(track => track.stop());
  }

  async function transcribeRecording() {
    setOrb("thinking", "Transcribing");
    try {
      const blob = new Blob(state.chunks, {type: state.recorder?.mimeType || "audio/webm"});
      const form = new FormData();
      form.append("api_key", ui.fishKey.value);
      form.append("audio", blob, "voice.webm");
      const response = await fetch("/voice/fish/asr", {method:"POST", body:form});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Fish Audio transcription failed");
      if (!payload.text) throw new Error("No speech was detected.");
      const answer = await askAI(payload.text);
      await speak(answer);
    } catch (err) {
      addMessage("error", err.message);
      hideOrb();
    }
  }

  async function checkMt5() {
    ui.checkMt5.disabled = true;
    try {
      const s = await json("/broker/mt5/status");
      ui.brokerBadge.textContent = s.trade_allowed ? "MT5 CONNECTED" : "MT5 READ ONLY";
      ui.brokerBadge.classList.toggle("warn", !s.trade_allowed);
      ui.mt5Details.innerHTML = `
        <div><span>Account</span><strong>${escapeHtml(s.login)}</strong></div>
        <div><span>Server</span><strong>${escapeHtml(s.server)}</strong></div>
        <div><span>Balance</span><strong>${escapeHtml(s.balance)} ${escapeHtml(s.currency)}</strong></div>
        <div><span>Equity</span><strong>${escapeHtml(s.equity)} ${escapeHtml(s.currency)}</strong></div>
        <div><span>Open positions</span><strong>${escapeHtml(s.positions)}</strong></div>`;
    } catch (err) {
      ui.brokerBadge.textContent = "MT5 DISCONNECTED";
      ui.brokerBadge.classList.add("warn");
      ui.mt5Details.innerHTML = `<div><span>Status</span><strong>${escapeHtml(err.message)}</strong></div>`;
    } finally {
      ui.checkMt5.disabled = false;
    }
  }

  async function refreshEngine() {
    try {
      const s = await json("/engine/status");
      ui.engineBadge.textContent = s.running ? "ANALYSIS RUNNING" : "ANALYSIS STOPPED";
      ui.engineBadge.classList.toggle("warn", !s.running);
      ui.killBadge.textContent = s.kill_switch ? "KILL SWITCH ACTIVE" : "KILL SWITCH READY";
      ui.killBadge.classList.toggle("danger-chip", s.kill_switch);
      ui.engineDetails.innerHTML = `
        <div><span>AI</span><strong>${escapeHtml(s.ai_configured ? (s.ai_provider + " / " + s.ai_model) : "Not configured")}</strong></div>
        <div><span>Symbols</span><strong>${escapeHtml(s.symbols.join(", "))}</strong></div>
        <div><span>Timeframe</span><strong>${escapeHtml(s.timeframe)}</strong></div>
        <div><span>Last cycle</span><strong>${escapeHtml(s.last_cycle_at || "—")}</strong></div>`;
      if (s.last_error) ui.engineStatusText.textContent = s.last_error;
    } catch (err) {
      ui.engineStatusText.textContent = err.message;
    }
  }

  async function engineAction(path) {
    try {
      const data = await json(path, {method:"POST"});
      ui.engineStatusText.textContent = data.last_error || "Engine command completed.";
      await Promise.all([refreshEngine(), refreshProposals(), refreshEvents()]);
    } catch (err) {
      ui.engineStatusText.textContent = err.message;
    }
  }

  async function resumeKillSwitch() {
    if (!window.confirm("Reset the emergency kill switch?")) return;
    try {
      await json("/engine/resume", {
        method:"POST",
        headers:{"X-Engine-Confirm":"RESUME"},
      });
      ui.engineStatusText.textContent = "Kill switch reset.";
      await refreshEngine();
    } catch (err) {
      ui.engineStatusText.textContent = err.message;
    }
  }

  async function refreshProposals() {
    try {
      const data = await json("/engine/proposals?limit=20");
      const rows = data.proposals || [];
      if (!rows.length) {
        ui.proposalList.innerHTML = '<div class="empty-state">No proposals yet. Configure AI and run the scanner.</div>';
        return;
      }
      ui.proposalList.innerHTML = rows.map(p => {
        const ready = p.status === "ready";
        const execute = ready
          ? `<button class="execute-proposal" data-id="${p.id}" type="button">Execute Live</button>`
          : `<span class="proposal-status">${escapeHtml(p.status)}</span>`;
        return `<article class="proposal-card">
          <div class="proposal-top">
            <div><strong>${escapeHtml(p.symbol)} · ${escapeHtml(String(p.side).toUpperCase())}</strong>
            <span>#${p.id} · ${escapeHtml(p.strategy)}</span></div>
            ${execute}
          </div>
          <div class="proposal-grid">
            <div><span>Volume</span><strong>${escapeHtml(p.volume_lots)}</strong></div>
            <div><span>Reference</span><strong>${escapeHtml(p.reference_entry)}</strong></div>
            <div><span>Stop</span><strong>${escapeHtml(p.stop_loss)}</strong></div>
            <div><span>Target</span><strong>${escapeHtml(p.take_profit)}</strong></div>
            <div><span>Risk cash</span><strong>${escapeHtml(p.estimated_risk_cash)}</strong></div>
            <div><span>AI confidence</span><strong>${(Number(p.ai_confidence) * 100).toFixed(0)}%</strong></div>
          </div>
          <p>${escapeHtml(p.rationale)}</p>
        </article>`;
      }).join("");
      ui.proposalList.querySelectorAll(".execute-proposal").forEach(button => {
        button.addEventListener("click", () => executeProposal(Number(button.dataset.id)));
      });
    } catch (err) {
      ui.proposalList.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
    }
  }

  async function executeProposal(id) {
    const proposal = `#${id}`;
    if (!window.confirm(`Send proposal ${proposal} to the connected live MT5 account? This can place a real-money order.`)) return;
    try {
      const result = await json(`/engine/proposals/${id}/execute`, {
        method:"POST",
        headers:{"X-Live-Confirm":`PROPOSAL:${id}`},
      });
      ui.engineStatusText.textContent = `Live order accepted: ${result.order_id}`;
      await Promise.all([refreshProposals(), refreshEvents(), checkMt5()]);
    } catch (err) {
      ui.engineStatusText.textContent = err.message;
      await refreshProposals();
    }
  }

  async function refreshEvents() {
    try {
      const data = await json("/engine/events?limit=30");
      const events = data.events || [];
      if (!events.length) {
        ui.eventList.innerHTML = '<div class="empty-state">No engine events yet.</div>';
        return;
      }
      ui.eventList.innerHTML = events.map(e => `<div class="event-row">
        <span class="event-time">${escapeHtml(String(e.created_at).replace("T"," ").slice(0,19))}</span>
        <strong>${escapeHtml(e.event_type)}</strong>
        <span>${escapeHtml(e.symbol || "")}</span>
        <span>${escapeHtml(e.message)}</span>
      </div>`).join("");
    } catch (err) {
      ui.eventList.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
    }
  }

  ui.provider.addEventListener("change", providerChanged);
  ui.fetchModels.addEventListener("click", fetchModels);
  ui.useForEngine.addEventListener("click", configureEngineAI);
  ui.fetchAudio.addEventListener("click", fetchAudio);
  ui.checkMt5.addEventListener("click", checkMt5);
  ui.startEngine.addEventListener("click", () => engineAction("/engine/start"));
  ui.stopEngine.addEventListener("click", () => engineAction("/engine/stop"));
  ui.scanNow.addEventListener("click", () => engineAction("/engine/run-once"));
  ui.emergencyStop.addEventListener("click", () => engineAction("/engine/emergency-stop"));
  ui.resumeEngine.addEventListener("click", resumeKillSwitch);
  ui.refreshProposals.addEventListener("click", refreshProposals);
  ui.refreshEvents.addEventListener("click", refreshEvents);

  ui.chatFab.addEventListener("click", () => {
    ui.chatPanel.classList.add("open");
    ui.chatPanel.setAttribute("aria-hidden", "false");
    ui.chatInput.focus();
  });
  ui.closeChat.addEventListener("click", () => {
    ui.chatPanel.classList.remove("open");
    ui.chatPanel.setAttribute("aria-hidden", "true");
  });
  ui.chatForm.addEventListener("submit", async e => {
    e.preventDefault();
    const text = ui.chatInput.value.trim();
    if (!text) return;
    ui.chatInput.value = "";
    try { await askAI(text); } catch {}
  });
  ui.voiceBtn.addEventListener("click", async () => {
    try {
      if (state.recording) stopRecording();
      else await startRecording();
    } catch (err) {
      addMessage("error", err.message);
      hideOrb();
    }
  });

  loadHealth();
  loadProviders();
  refreshEngine();
  refreshProposals();
  refreshEvents();
  window.setInterval(() => {
    refreshEngine();
    refreshProposals();
  }, 10000);
})();
