const form = document.getElementById("recommend-form");
const submitBtn = document.getElementById("submit-btn");
const results = document.getElementById("results");

const IDEAS = {
  skills: ["python", "sql", "javascript", "react", "html", "css", "git", "figma", "docker", "excel", "pandas", "flask", "statistics", "linux"],
  interests: ["creativity", "problem solving", "ai", "automation", "numbers", "security", "teamwork", "research"],
};

const state = { skills: [], interests: [] };
const inputs = {
  skills: document.getElementById("skills-input"),
  interests: document.getElementById("interests-input"),
};
const boxes = {
  skills: document.getElementById("skills-box"),
  interests: document.getElementById("interests-box"),
};

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/* ---------- Tag inputs ---------- */
function addTerm(type, raw) {
  raw.split(",").forEach((part) => {
    const term = part.trim().toLowerCase();
    if (term && !state[type].includes(term)) state[type].push(term);
  });
  renderTags(type);
}

function removeTerm(type, term) {
  state[type] = state[type].filter((t) => t !== term);
  renderTags(type);
}

function renderTags(type) {
  const box = boxes[type];
  const input = inputs[type];
  box.querySelectorAll(".pill").forEach((p) => p.remove());

  state[type].forEach((term) => {
    const pill = document.createElement("span");
    pill.className = `pill pill-${type}`;
    pill.appendChild(document.createTextNode(term + " "));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "×";
    btn.setAttribute("aria-label", "Remove " + term);
    btn.dataset.type = type;
    btn.dataset.term = term;
    pill.appendChild(btn);
    box.insertBefore(pill, input);
  });

  renderSuggestions(type);
  document.getElementById("stat-skills").textContent = state.skills.length;
}

function renderSuggestions(type) {
  const container = document.getElementById(`${type}-suggest`);
  container.innerHTML = IDEAS[type]
    .map((idea) => {
      const used = state[type].includes(idea);
      return `<button type="button" class="${used ? "used" : ""}" data-term="${idea}">${used ? "✓" : "+"} ${idea}</button>`;
    })
    .join("");
}

["skills", "interests"].forEach((type) => {
  const input = inputs[type];
  const box = boxes[type];

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (input.value.trim()) {
        addTerm(type, input.value);
        input.value = "";
      }
    } else if (e.key === "Backspace" && !input.value && state[type].length) {
      state[type].pop();
      renderTags(type);
    }
  });

  input.addEventListener("blur", () => {
    if (input.value.trim()) {
      addTerm(type, input.value);
      input.value = "";
    }
  });

  box.addEventListener("click", (e) => {
    const btn = e.target.closest(".pill button");
    if (btn) {
      removeTerm(btn.dataset.type, btn.dataset.term);
    } else {
      input.focus();
    }
  });

  document.getElementById(`${type}-suggest`).addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const term = btn.dataset.term;
    if (state[type].includes(term)) removeTerm(type, term);
    else addTerm(type, term);
  });

  renderSuggestions(type);
});

/* ---------- Load saved profile and progress ---------- */
async function loadProfile() {
  try {
    const res = await fetch("/api/profile");
    if (!res.ok) return;
    const data = await res.json();
    if (data.skills) addTerm("skills", data.skills);
    if (data.interests) addTerm("interests", data.interests);
  } catch (e) {
    /* ignore */
  }
}

function renderSide(roles) {
  const el = document.getElementById("side-paths");
  if (!roles.length) {
    el.innerHTML = `<p class="muted small">No paths yet. Get your recommendations and tap "Track this path".</p>`;
    return;
  }
  el.innerHTML = roles
    .map(
      (r) => `
      <div class="mini-path">
        <div class="mini-top"><span>${esc(r.role)}</span><b>${r.percent}%</b></div>
        <div class="bar"><div class="bar-fill" style="width:${r.percent}%"></div></div>
      </div>`
    )
    .join("");
}

async function loadProgress() {
  try {
    const res = await fetch("/api/progress");
    const data = await res.json();
    const roles = data.roles || [];
    const avg = roles.length ? Math.round(roles.reduce((sum, r) => sum + r.percent, 0) / roles.length) : 0;
    document.getElementById("stat-tracked").textContent = roles.length;
    document.getElementById("stat-progress").textContent = avg + "%";
    renderSide(roles);
  } catch (e) {
    document.getElementById("side-paths").innerHTML = `<p class="muted small">Could not load progress.</p>`;
  }
}

loadProfile();
loadProgress();

/* ---------- Results ---------- */
function chips(list, cls) {
  if (!list.length) return `<span class="chip chip-none">none yet</span>`;
  return list.map((s) => `<span class="chip ${cls}">${esc(s)}</span>`).join("");
}

function renderResults(data) {
  let html = "";

  if (data.unrecognized && data.unrecognized.length) {
    html += `<div class="notice">We didn't recognize: <b>${data.unrecognized.map(esc).join(", ")}</b>. Try the suggested terms for better matches.</div>`;
  }

  if (data.advice) {
    html += `<div class="advice fade-up"><h3>💬 Your personal advice</h3><p>${esc(data.advice)}</p></div>`;
  }

  html += `<h2 class="results-title">Your top career matches</h2>`;
  html += `<div class="results-grid">`;
  data.recommendations.forEach((r, index) => {
    html += `
      <article class="card role-card fade-up ${index === 0 ? "top" : ""}" style="animation-delay:${index * 0.1}s">
        ${index === 0 ? '<span class="top-badge">Best match</span>' : ""}
        <div class="role-head">
          <div>
            <h3>${esc(r.role)}</h3>
            <span class="category">${esc(r.category)}</span>
          </div>
          <div class="ring" style="--p:${r.match_score}"><span>${r.match_score}%</span></div>
        </div>
        <p class="role-desc">${esc(r.description)}</p>
        <div>
          <p class="label">Skills you have</p>
          <div class="chips">${chips(r.skills_you_have, "chip-have")}</div>
        </div>
        <div>
          <p class="label">Skills to learn</p>
          <div class="chips">${chips(r.skills_to_learn, "chip-learn")}</div>
        </div>
        <div>
          <p class="label">Learning path</p>
          <ol class="path">${r.learning_path.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
        </div>
        <button class="btn btn-outline track-btn" data-role="${encodeURIComponent(r.role)}">Track this path</button>
      </article>`;
  });
  html += `</div>`;

  results.innerHTML = html;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  ["skills", "interests"].forEach((type) => {
    if (inputs[type].value.trim()) {
      addTerm(type, inputs[type].value);
      inputs[type].value = "";
    }
  });

  if (!state.skills.length && !state.interests.length) {
    showToast("Please add at least one skill or interest.");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Analyzing...";
  results.innerHTML = `<div class="loading"><div class="spinner"></div>Finding your best career matches...</div>`;

  try {
    const res = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skills: state.skills.join(", "),
        interests: state.interests.join(", "),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      results.innerHTML = `<div class="notice">${esc(data.error || "Something went wrong.")}</div>`;
    } else {
      renderResults(data);
    }
  } catch (err) {
    results.innerHTML = `<div class="notice">Could not reach the server. Please try again.</div>`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "✨ Get my recommendations";
  }
});

results.addEventListener("click", async (e) => {
  const btn = e.target.closest(".track-btn");
  if (!btn) return;
  const role = decodeURIComponent(btn.dataset.role);
  btn.disabled = true;
  try {
    const res = await fetch("/api/track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    const data = await res.json();
    if (res.ok) {
      btn.textContent = "✓ Tracking";
      btn.className = "btn btn-success";
      showToast(data.message);
      loadProgress();
    } else {
      btn.disabled = false;
      showToast(data.error || "Could not track this path.");
    }
  } catch (err) {
    btn.disabled = false;
    showToast("Network error. Please try again.");
  }
});