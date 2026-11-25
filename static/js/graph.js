/* Canvas graph: 5 orchestration zones + agent nodes + message particles */

const Graph = (() => {
  const STAGES = [
    { id: "handoff", pattern: "Handoff", talk: "Roteamento", agents: ["triagem", "esp_treinamento", "esp_automacao"] },
    { id: "research", pattern: "Concorrente", talk: "Swarm", agents: ["pesq_empresa", "pesq_noticias", "pesq_maturidade"] },
    { id: "magentic", pattern: "Magentic", talk: "Hierárquico", agents: ["gerente", "analista", "sintetizador"] },
    { id: "group_chat", pattern: "Group Chat", talk: "Time", agents: ["redator", "revisor"] },
    { id: "images", pattern: "Concorrente", talk: "Swarm", agents: ["img_capa", "img_solucao", "img_resultado"] },
  ];

  const LABELS = {
    triagem: "Triagem",
    esp_treinamento: "Treinamento",
    esp_automacao: "Automação",
    pesq_empresa: "Empresa",
    pesq_noticias: "Notícias",
    pesq_maturidade: "Maturidade",
    gerente: "Gerente",
    analista: "Analista",
    sintetizador: "Sintetizador",
    redator: "Redator",
    revisor: "Revisor",
    img_capa: "Capa",
    img_solucao: "Solução",
    img_resultado: "Resultado",
  };

  let canvas, ctx, w, h, dpr;
  let activeStage = null;
  let activeAgents = new Set();
  let finishedStages = new Set();
  let particles = [];
  let pulse = 0;
  let raf = 0;

  const nodes = {};

  function init(canvasEl) {
    canvas = canvasEl;
    ctx = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
    layout();
    raf = requestAnimationFrame(tick);
    renderLegend();
  }

  function resize() {
    if (!canvas) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = Math.max(640, rect.width);
    h = Math.max(360, rect.height);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    layout();
  }

  function layout() {
    const padX = 36;
    const zoneW = (w - padX * 2) / STAGES.length;
    STAGES.forEach((stage, si) => {
      const zx = padX + si * zoneW;
      stage._x = zx;
      stage._w = zoneW - 12;
      stage._y = 56;
      stage._h = h - 100;
      const n = stage.agents.length;
      stage.agents.forEach((id, ai) => {
        const cy = stage._y + 70 + (ai + 0.5) * ((stage._h - 90) / n);
        nodes[id] = {
          id,
          stage: stage.id,
          x: zx + stage._w / 2,
          y: cy,
          r: 28,
        };
      });
    });
  }

  function reset() {
    activeStage = null;
    activeAgents.clear();
    finishedStages.clear();
    particles = [];
    renderLegend();
  }

  function setStage(stageId) {
    activeStage = stageId;
    renderLegend();
  }

  function finishStage(stageId) {
    finishedStages.add(stageId);
    renderLegend();
  }

  function setAgentActive(id, on = true) {
    if (on) activeAgents.add(id);
    else activeAgents.delete(id);
  }

  function sendMessage(fromId, toId) {
    const a = nodes[fromId];
    const b = nodes[toId];
    if (!a || !b) return;
    particles.push({
      x: a.x,
      y: a.y,
      tx: b.x,
      ty: b.y,
      t: 0,
      life: 0.85,
    });
  }

  function renderLegend() {
    const el = document.getElementById("pipeline-legend");
    if (!el) return;
    el.innerHTML = STAGES.map((s) => {
      const cls = s.id === activeStage ? "active" : finishedStages.has(s.id) ? "done" : "";
      return `<span class="${cls}" data-stage="${s.id}">${s.pattern} · ${s.talk}</span>`;
    }).join("");
  }

  function tick(ts) {
    pulse = (Math.sin(ts / 220) + 1) / 2;
    draw();
    // particles
    particles = particles.filter((p) => {
      p.t += 0.028;
      return p.t < 1;
    });
    raf = requestAnimationFrame(tick);
  }

  function draw() {
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);

    // sequential pipeline line
    const midY = 40;
    const first = STAGES[0];
    const last = STAGES[STAGES.length - 1];
    const x0 = first._x + 8;
    const x1 = last._x + last._w - 8;
    ctx.strokeStyle = "rgba(54,68,89,0.9)";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x0, midY);
    ctx.lineTo(x1, midY);
    ctx.stroke();

    const progress = (finishedStages.size + (activeStage ? 0.45 : 0)) / STAGES.length;
    ctx.strokeStyle = "#008EFF";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x0, midY);
    ctx.lineTo(x0 + (x1 - x0) * Math.min(1, progress), midY);
    ctx.stroke();

    STAGES.forEach((stage) => {
      const isActive = stage.id === activeStage;
      const done = finishedStages.has(stage.id);
      const alpha = !activeStage || isActive || done ? 1 : 0.28;

      ctx.save();
      ctx.globalAlpha = alpha;

      // zone
      roundRect(stage._x, stage._y, stage._w, stage._h, 14);
      ctx.fillStyle = isActive ? "rgba(0,142,255,0.12)" : "rgba(54,68,89,0.22)";
      ctx.fill();
      ctx.strokeStyle = isActive ? "#008EFF" : "rgba(255,255,255,0.08)";
      ctx.lineWidth = isActive ? 2 : 1;
      ctx.stroke();

      // titles
      ctx.fillStyle = "#008EFF";
      ctx.font = "700 14px 'Maven Pro', sans-serif";
      ctx.fillText(stage.pattern, stage._x + 14, stage._y + 24);
      ctx.fillStyle = "rgba(255,255,255,0.75)";
      ctx.font = "400 13px 'Maven Pro', sans-serif";
      ctx.fillText(stage.talk, stage._x + 14, stage._y + 44);

      // edges inside zone
      const ids = stage.agents;
      for (let i = 0; i < ids.length - 1; i++) {
        const a = nodes[ids[i]];
        const b = nodes[ids[i + 1]];
        ctx.strokeStyle = "rgba(0,142,255,0.25)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y + a.r);
        ctx.lineTo(b.x, b.y - b.r);
        ctx.stroke();
      }

      ids.forEach((id) => drawNode(nodes[id]));
      ctx.restore();
    });

    // particles on top
    particles.forEach((p) => {
      const x = p.x + (p.tx - p.x) * ease(p.t);
      const y = p.y + (p.ty - p.y) * ease(p.t);
      ctx.beginPath();
      ctx.fillStyle = "#008EFF";
      ctx.shadowColor = "#008EFF";
      ctx.shadowBlur = 12;
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    });
  }

  function drawNode(n) {
    const active = activeAgents.has(n.id);
    const r = n.r + (active ? pulse * 5 : 0);
    ctx.beginPath();
    ctx.fillStyle = active ? "#008EFF" : "#364459";
    ctx.strokeStyle = active ? "#FFFFFF" : "rgba(255,255,255,0.25)";
    ctx.lineWidth = active ? 2.5 : 1.5;
    if (active) {
      ctx.shadowColor = "rgba(0,142,255,0.8)";
      ctx.shadowBlur = 18 + pulse * 10;
    }
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.fillStyle = "#FFFFFF";
    ctx.font = "700 12px 'Maven Pro', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(LABELS[n.id] || n.id, n.x, n.y + r + 18);
    ctx.textAlign = "left";

    // simple icon mark
    ctx.beginPath();
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.arc(n.x, n.y, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  function roundRect(x, y, rw, rh, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + rw, y, x + rw, y + rh, r);
    ctx.arcTo(x + rw, y + rh, x, y + rh, r);
    ctx.arcTo(x, y + rh, x, y, r);
    ctx.arcTo(x, y, x + rw, y, r);
    ctx.closePath();
  }

  function ease(t) {
    return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  }

  return { init, reset, setStage, finishStage, setAgentActive, sendMessage, STAGES, LABELS };
})();
