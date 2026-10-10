const list = document.getElementById("progress-list");

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function updateStats(roles) {
  const totalSteps = roles.reduce((sum, r) => sum + r.total, 0);
  const doneSteps = roles.reduce((sum, r) => sum + r.done, 0);
  const overall = totalSteps ? Math.round((doneSteps / totalSteps) * 100) : 0;
  document.getElementById("p-tracked").textContent = roles.length;
  document.getElementById("p-done").textContent = doneSteps;
  document.getElementById("p-overall").textContent = overall + "%";
}

function motivation(percent) {
  if (percent === 100) return "🏆 Path completed. Amazing work!";
  if (percent >= 60) return "🔥 Almost there, keep going!";
  if (percent > 0) return "🚀 Great start, keep the momentum!";
  return "🌱 Your journey starts with step one.";
}

function render(roles) {
  updateStats(roles);

  if (!roles.length) {
    list.innerHTML = `
      <div class="tp-empty">
        <div class="big">🧭</div>
        <h3>No career path tracked yet</h3>
        <p class="muted">Get your recommendations on the dashboard and click "Track this path" to start your journey.</p>
        <a href="/dashboard" class="btn btn-primary btn-lg">Find my career path</a>
      </div>`;
    return;
  }

  list.innerHTML = roles
    .map(
      (r, index) => `
    <article class="card tp-card ${r.percent === 100 ? "complete" : ""}" style="animation-delay:${index * 0.08}s">
      <div class="tp-head">
        <div class="ring" style="--p:${r.percent}"><span>${r.percent}%</span></div>
        <div class="tp-title">
          <h3>${esc(r.role)}</h3>
          <p class="tp-count">${r.done} of ${r.total} steps completed</p>
          <span class="tp-msg">${motivation(r.percent)}</span>
        </div>
        <button class="tp-remove" data-untrack="${encodeURIComponent(r.role)}">Remove</button>
      </div>
      <div class="bar tp-bar"><div class="bar-fill" style="width:${r.percent}%"></div></div>
      <ul class="tp-steps">
        ${r.steps
          .map(
            (s, i) => `
          <li>
            <label class="tp-step ${s.completed ? "done" : ""}">
              <input type="checkbox" data-step="${s.id}" ${s.completed ? "checked" : ""}>
              <span class="tp-num">${i + 1}</span>
              <span class="tp-text">${esc(s.text)}</span>
              <span class="tp-check"></span>
            </label>
          </li>`
          )
          .join("")}
      </ul>
    </article>`
    )
    .join("");
}

async function load() {
  try {
    const res = await fetch("/api/progress");
    const data = await res.json();
    const roles = data.roles || [];
    render(roles);
    return roles;
  } catch (e) {
    list.innerHTML = `<div class="notice">Could not load your progress. Please refresh.</div>`;
    return [];
  }
}

list.addEventListener("change", async (e) => {
  const box = e.target.closest("input[data-step]");
  if (!box) return;
  const stepId = Number(box.dataset.step);
  try {
    const res = await fetch(`/api/progress/${stepId}`, { method: "POST" });
    const data = await res.json();
    const roles = await load();
    if (data.completed) {
      const role = roles.find((r) => r.steps.some((s) => s.id === stepId));
      showToast(
        role && role.percent === 100
          ? "🏆 Path completed! Congratulations!"
          : "Nice work! 🎉 Step done."
      );
    }
  } catch (err) {
    showToast("Could not save. Please try again.");
  }
});

list.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-untrack]");
  if (!btn) return;
  const role = decodeURIComponent(btn.dataset.untrack);
  if (!confirm(`Stop tracking "${role}"? Your progress on it will be removed.`)) return;
  try {
    await fetch("/api/untrack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    showToast("Removed.");
    await load();
  } catch (err) {
    showToast("Could not remove. Please try again.");
  }
});

load();