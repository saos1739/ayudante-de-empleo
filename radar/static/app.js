// Estado de la búsqueda en vivo, acciones rápidas y copiar al portapapeles.
(function () {
  const runBox = document.getElementById("runBox");
  const runStatus = document.getElementById("runStatus");
  const runBtn = document.getElementById("runBtn");
  const logPanel = document.getElementById("logPanel");
  const logText = document.getElementById("logText");
  let wasRunning = runBox && runBox.dataset.running === "1";

  async function poll() {
    try {
      const r = await fetch("/api/estado");
      const s = await r.json();
      if (s.running) {
        runBox.dataset.running = "1";
        runBtn.disabled = true;
        runStatus.textContent = `Buscando en ${s.source || "…"} · ${s.found} vistas · ${s.new} nuevas · ${s.relevant} relevantes`;
        logPanel.hidden = false;
        logText.textContent = s.log.join("\n");
        logPanel.scrollTop = logPanel.scrollHeight;
        wasRunning = true;
      } else {
        runBox.dataset.running = "0";
        runBtn.disabled = false;
        if (wasRunning) {
          // Terminó una búsqueda: recargar para ver las ofertas nuevas.
          wasRunning = false;
          window.location.reload();
          return;
        }
      }
    } catch (e) { /* panel cerrado o reiniciando */ }
    setTimeout(poll, wasRunning ? 2000 : 8000);
  }
  if (runBox) poll();

  // Botones rápidos "Me interesa" / "Descartar" en el listado.
  document.querySelectorAll(".js-status").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const card = btn.closest(".job-card");
      const body = new FormData();
      body.append("estado", btn.dataset.status);
      btn.disabled = true;
      const r = await fetch(`/oferta/${card.dataset.id}/estado`, {
        method: "POST", body, headers: { "X-Requested-With": "fetch" },
      });
      if (r.ok) {
        card.classList.add("fade");
        setTimeout(() => card.remove(), 300);
      } else {
        btn.disabled = false;
      }
    });
  });

  // Copiar textos de la postulación.
  document.querySelectorAll(".js-copy").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = document.getElementById(btn.dataset.target);
      await navigator.clipboard.writeText(el.value);
      const old = btn.textContent;
      btn.textContent = "¡Copiado!";
      setTimeout(() => (btn.textContent = old), 1500);
    });
  });

  // Indicador de carga para acciones con IA (tardan unos segundos).
  document.querySelectorAll("form.js-loading").forEach((f) => {
    f.addEventListener("submit", () => setTimeout(() => f.classList.add("loading"), 0));
  });
})();
