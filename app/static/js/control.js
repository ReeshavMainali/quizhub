(() => {
  const gameId = window.QUIZHUB.gameId;
  const socket = io({ transports: ["websocket", "polling"] });

  const stageEl = document.getElementById("stage");
  const listEl = document.getElementById("question-list");
  const scoreboardEl = document.getElementById("scoreboard");
  const toastArea = document.getElementById("toast-area");
  const connDot = document.getElementById("conn-dot");
  const finalOverlay = document.getElementById("final-overlay");

  let state = null;
  let ring = null;

  // ------------------------------------------------------------- helpers

  function esc(str) {
    const d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  function showToast(message, kind = "error") {
    const el = document.createElement("div");
    el.className =
      "rounded-lg px-4 py-2.5 text-sm border animate-fade-up " +
      (kind === "error"
        ? "bg-danger/10 border-danger/30 text-danger"
        : "bg-success/10 border-success/30 text-success");
    el.textContent = message;
    toastArea.prepend(el);
    setTimeout(() => el.remove(), 4500);
  }

  function teamPassOptions(teams) {
    return teams
      .map((t) => `<option value="${t.id}">${esc(t.name)}</option>`)
      .join("");
  }

  // -------------------------------------------------------------- socket

  socket.on("connect", () => {
    connDot.classList.remove("bg-muted", "bg-danger");
    connDot.classList.add("bg-success");
    socket.emit("join", { game_id: gameId, role: "host" });
  });

  socket.on("disconnect", () => {
    connDot.classList.remove("bg-success");
    connDot.classList.add("bg-danger");
  });

  socket.on("state_update", (payload) => {
    state = payload;
    render();
  });

  socket.on("action_error", (payload) => showToast(payload.message, "error"));

  socket.on("game_ended", (payload) => {
    const standings = document.getElementById("final-standings");
    standings.innerHTML = payload.teams
      .map(
        (t, i) => `
        <li class="flex items-center justify-between rounded-lg border border-border px-3 py-2">
          <span class="flex items-center gap-2">
            <span class="text-muted text-xs w-4">${i + 1}</span>
            <span class="w-3 h-3 rounded-full" style="background:${t.color}"></span>
            <span class="font-medium">${esc(t.name)}</span>
          </span>
          <span class="font-display font-semibold">${t.score}</span>
        </li>`
      )
      .join("");
    finalOverlay.classList.remove("hidden");
  });

  // ------------------------------------------------------------- actions

  document.getElementById("undo-btn").addEventListener("click", () => {
    socket.emit("undo", { game_id: gameId });
  });

  document.getElementById("end-game-btn").addEventListener("click", () => {
    if (confirm("End the game and show final results on the display?")) {
      socket.emit("end_game", { game_id: gameId });
    }
  });

  document.querySelectorAll(".round-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      socket.emit("select_round", { game_id: gameId, round_id: Number(btn.dataset.roundId) });
    });
  });

  // -------------------------------------------------------------- render

  function render() {
    if (!state) return;
    renderRoundTabs();
    renderStage();
    renderQuestionList();
    renderScoreboard();
  }

  function renderRoundTabs() {
    document.querySelectorAll(".round-tab").forEach((btn) => {
      const active = state.round && Number(btn.dataset.roundId) === state.round.id;
      btn.classList.toggle("btn-primary", !!active);
      btn.classList.toggle("btn-secondary", !active);
    });
  }

  function renderScoreboard() {
    scoreboardEl.innerHTML = state.teams
      .map(
        (t) => `
        <li class="flex items-center justify-between rounded-lg border px-3 py-2 ${
          state.current_turn_team_id === t.id ? "border-primary" : "border-border"
        }">
          <span class="flex items-center gap-2 text-sm font-medium">
            <span class="w-2.5 h-2.5 rounded-full" style="background:${t.color}"></span>
            ${esc(t.name)}
          </span>
          <span class="font-display font-semibold">${t.score}</span>
        </li>`
      )
      .join("");
  }

  function renderQuestionList() {
    if (!state.round) {
      listEl.innerHTML = "";
      return;
    }
    const rows = (state.round_questions || [])
      .map((q) => {
        const clickable = q.status === "pending" && state.round.type !== "lightning";
        const statusBadge =
          q.status === "resolved"
            ? '<span class="badge bg-muted/10 border-border text-muted">done</span>'
            : q.is_current
            ? '<span class="badge bg-primary/10 border-primary/30 text-primary">current</span>'
            : q.status === "pending" && q.id && state.round.type === "lightning" && !q.is_current
            ? '<span class="badge bg-lightning/10 border-lightning/30 text-lightning">pool</span>'
            : '<span class="badge bg-border/40 border-border text-muted">pending</span>';
        return `
        <li class="flex items-center justify-between gap-3 py-2 border-b border-border last:border-0 ${
          clickable ? "cursor-pointer hover:bg-surface2 -mx-2 px-2 rounded-lg" : ""
        }" ${clickable ? `data-question-id="${q.id}"` : ""}>
          <span class="text-sm truncate">${esc(q.text)}</span>
          <span class="flex items-center gap-2 shrink-0">
            <span class="text-xs text-muted">${q.points} pt</span>
            ${statusBadge}
          </span>
        </li>`;
      })
      .join("");

    listEl.innerHTML = `
      <h2 class="font-display font-semibold mb-2">Questions in this round</h2>
      ${
        state.round.type === "lightning"
          ? '<p class="text-xs text-muted mb-3">Lightning rounds pull questions automatically when a team\'s turn starts.</p>'
          : '<p class="text-xs text-muted mb-3">Click a pending question to jump straight to it.</p>'
      }
      <ul>${rows || '<li class="text-sm text-muted py-2">No questions in this round.</li>'}</ul>
    `;

    listEl.querySelectorAll("[data-question-id]").forEach((li) => {
      li.addEventListener("click", () => {
        socket.emit("start_question", { game_id: gameId, question_id: Number(li.dataset.questionId) });
      });
    });
  }

  function renderStage() {
    if (!state.round) {
      stageEl.innerHTML = `<div class="m-auto text-center text-muted py-10">
        <p class="font-display text-lg mb-1">No round selected</p>
        <p class="text-sm">Choose a round above to begin.</p>
      </div>`;
      return;
    }
    stageEl.innerHTML =
      state.round.type === "lightning" ? lightningStageHtml() : normalStageHtml();
    wireStageEvents();
  }

  function ringSvg(id, size) {
    const r = size / 2 - 6;
    return `
      <div class="relative shrink-0" style="width:${size}px;height:${size}px">
        <svg id="${id}" viewBox="0 0 ${size} ${size}" class="w-full h-full -rotate-90">
          <circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="rgb(var(--color-border))" stroke-width="6"/>
          <circle class="ring-progress stroke-primary" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="6" stroke-linecap="round"/>
        </svg>
        <span id="${id}-label" class="ring-label absolute inset-0 flex items-center justify-center font-display font-semibold text-xl">–</span>
      </div>`;
  }

  function timerControls() {
    return `
      <div class="flex items-center gap-1.5">
        <button data-action="pause_timer" class="btn-secondary !px-2.5 !py-1.5 text-xs">Pause</button>
        <button data-action="resume_timer" class="btn-secondary !px-2.5 !py-1.5 text-xs">Resume</button>
        <button data-action="restart_timer" class="btn-secondary !px-2.5 !py-1.5 text-xs">Restart</button>
      </div>`;
  }

  function normalStageHtml() {
    const phase = state.phase;
    if (phase === "idle" || phase === "round_complete") {
      return `<div class="m-auto text-center text-muted py-10">
        <p class="font-display text-lg mb-1">${
          phase === "round_complete" ? "Round complete" : "Ready when you are"
        }</p>
        <p class="text-sm">${
          phase === "round_complete"
            ? "Every question here has been used — pick another round above."
            : "Pick a question from the list below to start the timer."
        }</p>
      </div>`;
    }

    const q = state.question;
    if (!q) return "";
    const media = `
      ${q.image_url ? `<img src="${q.image_url}" class="max-h-48 rounded-lg border border-border mx-auto mb-4" alt="">` : ""}
      ${q.audio_url ? `<button data-action="play_audio" class="btn-secondary mx-auto mb-4">▶ Play audio clip</button>` : ""}
    `;
    const choices = q.choices
      ? `<div class="grid grid-cols-2 gap-2 max-w-md mx-auto mb-4 text-sm">
          ${q.choices.map((c, i) => `<div class="rounded-lg border border-border px-3 py-2">${String.fromCharCode(65 + i)}. ${esc(c)}</div>`).join("")}
        </div>`
      : "";

    if (phase === "revealed") {
      return `
        <div class="flex items-start justify-between gap-4 mb-4">
          <span class="badge bg-primary/10 border-primary/30 text-primary">${esc(state.round.name)}</span>
          <span class="text-xs text-muted">${q.points} pts</span>
        </div>
        <p class="font-display text-xl mb-4">${esc(q.text)}</p>
        ${media}
        ${choices}
        <div class="rounded-lg bg-success/10 border border-success/30 px-4 py-3 mb-5">
          <p class="text-xs uppercase tracking-wide text-success mb-1">Answer</p>
          <p class="font-medium">${esc(q.answer)}</p>
        </div>
        <button data-action="next_question" class="btn-primary mt-auto">Next question →</button>
      `;
    }

    // active
    return `
      <div class="flex items-start justify-between gap-4 mb-4">
        <div class="flex items-center gap-4">
          ${ringSvg("ring-main", 64)}
          <div>
            <span class="badge bg-primary/10 border-primary/30 text-primary">${esc(state.round.name)}</span>
            <p class="text-xs text-muted mt-1">${q.points} pts</p>
          </div>
        </div>
        ${timerControls()}
      </div>
      <p class="font-display text-xl mb-3">${esc(q.text)}</p>
      ${media}
      ${choices}
      <div class="rounded-lg bg-surface2 border border-border px-4 py-3 mb-5">
        <p class="text-xs uppercase tracking-wide text-muted mb-1">Answer (host only)</p>
        <p class="font-medium">${esc(q.answer)}</p>
      </div>
      <div class="mt-auto space-y-3">
        <div>
          <p class="label mb-2">Mark correct</p>
          <div class="flex flex-wrap gap-2">
            ${state.teams
              .map(
                (t) => `<button data-action="mark_correct" data-team-id="${t.id}"
                  class="btn-secondary border-2" style="border-color:${t.color}">${esc(t.name)}</button>`
              )
              .join("")}
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <select id="pass-target" class="input !w-auto">${teamPassOptions(state.teams)}</select>
          <button data-action="pass_question" class="btn-secondary">Pass to team</button>
          <button data-action="reveal_answer" class="btn-danger ml-auto">Reveal (no score)</button>
        </div>
      </div>
    `;
  }

  function lightningStageHtml() {
    const phase = state.phase;
    const lightning = state.lightning;
    const turnSize = state.round.lightning_turn_size;

    const summary = lightning
      ? `<div class="rounded-lg bg-lightning/10 border border-lightning/30 px-4 py-3 mb-4 flex items-center justify-between">
          <span class="text-sm">
            <span class="font-medium" style="color:${lightning.team.color}">${esc(lightning.team.name)}</span>
            — ${lightning.correct}/${lightning.total} correct, ${lightning.points_earned} pts this turn
          </span>
        </div>`
      : "";

    if (phase === "idle" || phase === "lightning_turn_complete" || phase === "round_complete") {
      return `
        ${summary}
        <div class="m-auto text-center py-6 w-full max-w-sm mx-auto">
          <p class="font-display text-lg mb-4">Start a lightning turn</p>
          <div class="space-y-3 text-left">
            <div>
              <label class="label">Team</label>
              <select id="lightning-team" class="input">${teamPassOptions(state.teams)}</select>
            </div>
            <div>
              <label class="label">Questions this turn</label>
              <input id="lightning-count" type="number" class="input" min="1" max="20" value="${turnSize}">
            </div>
            <button data-action="start_lightning_turn" class="btn-lightning w-full">Start turn ⚡</button>
          </div>
        </div>
      `;
    }

    const q = state.question;
    return `
      ${summary}
      <div class="flex items-center gap-4 mb-4">
        ${ringSvg("ring-main", 64)}
        <div>
          <span class="badge bg-lightning/10 border-lightning/30 text-lightning">Lightning</span>
          <p class="text-xs text-muted mt-1">${q ? q.points : ""} pts</p>
        </div>
      </div>
      <p class="font-display text-xl mb-4">${q ? esc(q.text) : ""}</p>
      <div class="rounded-lg bg-surface2 border border-border px-4 py-3 mb-5">
        <p class="text-xs uppercase tracking-wide text-muted mb-1">Answer (host only)</p>
        <p class="font-medium">${q ? esc(q.answer) : ""}</p>
      </div>
      <div class="mt-auto grid grid-cols-2 gap-3">
        <button data-action="lightning_correct" class="btn-success !py-4 text-base">✓ Correct</button>
        <button data-action="lightning_incorrect" class="btn-danger !py-4 text-base">✗ Incorrect</button>
      </div>
    `;
  }

  function wireStageEvents() {
    if (document.getElementById("ring-main")) {
      ring = new TimerRing(
        document.getElementById("ring-main"),
        document.getElementById("ring-main-label"),
        26
      );
      if (state.timer && state.timer.duration) {
        ring.set(state.timer.duration, state.timer.remaining, state.timer.status);
      }
    }

    stageEl.querySelectorAll("[data-action]").forEach((el) => {
      el.addEventListener("click", () => {
        const action = el.dataset.action;
        if (action === "mark_correct") {
          socket.emit("mark_correct", { game_id: gameId, team_id: Number(el.dataset.teamId) });
        } else if (action === "pass_question") {
          const teamId = Number(document.getElementById("pass-target").value);
          socket.emit("pass_question", { game_id: gameId, team_id: teamId });
        } else if (action === "reveal_answer") {
          socket.emit("reveal_answer", { game_id: gameId });
        } else if (action === "next_question") {
          socket.emit("next_question", { game_id: gameId });
        } else if (action === "play_audio") {
          socket.emit("play_audio", { game_id: gameId });
        } else if (action === "pause_timer") {
          socket.emit("pause_timer", { game_id: gameId });
        } else if (action === "resume_timer") {
          socket.emit("resume_timer", { game_id: gameId });
        } else if (action === "restart_timer") {
          socket.emit("restart_timer", { game_id: gameId });
        } else if (action === "start_lightning_turn") {
          socket.emit("start_lightning_turn", {
            game_id: gameId,
            round_id: state.round.id,
            team_id: Number(document.getElementById("lightning-team").value),
            count: Number(document.getElementById("lightning-count").value),
          });
        } else if (action === "lightning_correct") {
          socket.emit("lightning_mark", { game_id: gameId, correct: true });
        } else if (action === "lightning_incorrect") {
          socket.emit("lightning_mark", { game_id: gameId, correct: false });
        }
      });
    });
  }
})();
