/* Final proposal screen — Hcode Training identity */

const Proposal = (() => {
  const view = () => document.getElementById("proposal-view");
  const body = () => document.getElementById("proposal-body");
  const images = () => document.getElementById("proposal-images");
  const times = () => document.getElementById("stage-times");
  const title = () => document.getElementById("proposal-title");
  const sub = () => document.getElementById("proposal-sub");

  function show(payload) {
    const company = payload.company || "Cliente";
    title().textContent = "Capacitação que transforma interesse em operação";
    sub().textContent = `Programa de agentes de IA sob medida para ${company}`;
    body().innerHTML = renderMarkdown(payload.proposal_md || "");
    renderImages(payload.images || []);
    renderTimes(payload.stage_times || {}, payload.total_seconds);
    view().classList.remove("hidden");
    document.getElementById("stage-view").style.filter = "blur(2px) brightness(0.55)";
  }

  function hide() {
    view().classList.add("hidden");
    document.getElementById("stage-view").style.filter = "";
  }

  function renderImages(list) {
    const kinds = ["capa", "solucao", "resultado"];
    const labels = { capa: "Capa", solucao: "Solução", resultado: "Resultado" };
    const byKind = {};
    list.forEach((item) => {
      if (typeof item === "string") {
        const kind = kinds.find((k) => item.includes(k)) || "capa";
        byKind[kind] = item;
      } else if (item && item.kind) {
        byKind[item.kind] = item.url || item.path;
      }
    });
    // also pull from last image_ready tracked globally
    if (window.__lastImages) {
      Object.assign(byKind, window.__lastImages);
    }
    images().innerHTML = kinds
      .map((k) => {
        const src = byKind[k] || `/assets/fallback/${k}.svg`;
        return `<figure><img src="${src}" alt="${labels[k]}" /><figcaption>${labels[k]}</figcaption></figure>`;
      })
      .join("");
  }

  function renderTimes(stageTimes, total) {
    const order = ["handoff", "research", "magentic", "group_chat", "images"];
    const parts = order
      .filter((k) => stageTimes[k] != null)
      .map((k) => `${k} ${Number(stageTimes[k]).toFixed(1)}s`);
    if (total != null) parts.push(`total ${Number(total).toFixed(1)}s`);
    times().textContent = parts.join(" · ");
  }

  function renderMarkdown(md) {
    // Minimal markdown → HTML (headings, lists, tables, bold, paragraphs)
    let html = escapeHtml(md);
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // tables
    html = html.replace(/(?:^\|.+\|[ \t]*$\n?)+/gm, (block) => {
      const rows = block.trim().split("\n").filter(Boolean);
      if (rows.length < 2) return block;
      const parse = (row) =>
        row
          .split("|")
          .slice(1, -1)
          .map((c) => c.trim());
      const head = parse(rows[0]);
      const bodyRows = rows.slice(2).map(parse);
      return `<table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${bodyRows
        .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
        .join("")}</tbody></table>`;
    });

    // lists
    html = html.replace(/(?:^[\-\*] .+(?:\n|$))+?/gm, (block) => {
      const items = block
        .trim()
        .split("\n")
        .map((l) => `<li>${l.replace(/^[\-\*] /, "")}</li>`)
        .join("");
      return `<ul>${items}</ul>`;
    });
    html = html.replace(/(?:^\d+\. .+(?:\n|$))+?/gm, (block) => {
      const items = block
        .trim()
        .split("\n")
        .map((l) => `<li>${l.replace(/^\d+\. /, "")}</li>`)
        .join("");
      return `<ol>${items}</ol>`;
    });

    html = html
      .split(/\n{2,}/)
      .map((para) => {
        if (/^<(h\d|ul|ol|table)/.test(para.trim())) return para;
        return `<p>${para.replace(/\n/g, "<br>")}</p>`;
      })
      .join("\n");
    return html;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  return { show, hide };
})();
