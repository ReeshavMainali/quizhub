(() => {
  const gameId = window.QUIZHUB.gameId;
  const socket = io({ transports: ["websocket", "polling"] });

  const stageEl = document.getElementById("stage");
  const stepperEl = document.getElementById("round-stepper");
  const scoreboardEl = document.getElementById("scoreboard-strip");
  const startOverlay = document.getElementById("start-overlay");
  const finalOverlay = document.getElementById("final-overlay");
  const audioEl = document.getElementById("clip-audio");

  let state = null;
  let prevScores = {};
  let ring = null;
  let prevQuestionId = null;

  function esc(str) {
    const d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  // ------------------------------------------------------- unlock overlay

  startOverlay.addEventListener("click", () => {
    startOverlay.classList.add("hidden");
    document.documentElement.requestFullscreen?.().catch(() => {});
    // Prime the audio element inside this user-gesture so later programmatic
    // play() calls (triggered by the host, not a click here) are allowed.
    audioEl.muted = true;
    audioEl.play().catch(() => {}).finally(() => {
      audioEl.pause();
      audioEl.muted = false;
    });
  });

  document.getElementById("fullscreen-toggle").addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      document.documentElement.requestFullscreen?.().catch(() => {});
    }
  });

  document.getElementById("theme-toggle").addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    localStorage.setItem("quizhub-theme", document.documentElement.classList.contains("dark") ? "dark" : "light");
  });

  // -------------------------------------------------------------- socket

  socket.on("connect", () => socket.emit("join", { game_id: gameId, role: "display" }));

  socket.on("state_update", (payload) => {
    const newQId = payload && payload.question ? payload.question.id : null;
    if (prevQuestionId && newQId !== prevQuestionId) {
      try {
        audioEl.pause();
        audioEl.currentTime = 0;
        audioEl.removeAttribute("src");
      } catch (e) {}
    }
    prevQuestionId = newQId;

    state = payload;
    render();
  });

  socket.on("audio_play", () => {
    if (state && state.question && state.question.audio_url) {
      try {
        audioEl.pause();
        audioEl.currentTime = 0;
        audioEl.src = state.question.audio_url;
        audioEl.load();
        audioEl.play().catch(() => {});
      } catch (e) {}
    }
  });

  socket.on("game_ended", (payload) => {
    document.getElementById("final-standings").innerHTML = payload.teams
      .map(
        (t, i) => `
        <div class="flex items-center justify-between rounded-2xl border px-6 py-4 animate-fade-up
          ${i === 0 ? "border-lightning bg-lightning/10" : "border-border bg-surface"}"
          style="animation-delay:${i * 90}ms">
          <span class="flex items-center gap-4">
            <span class="font-display text-2xl w-8 ${i === 0 ? "text-lightning" : "text-muted"}">${i + 1}</span>
            <span class="w-4 h-4 rounded-full" style="background:${t.color}"></span>
            <span class="font-display text-2xl">${esc(t.name)}</span>
          </span>
          <span class="font-display text-3xl font-semibold">${t.score}</span>
        </div>`
      )
      .join("");
    finalOverlay.classList.remove("hidden");
  });

  // -------------------------------------------------------------- render

  function render() {
    if (!state) return;
    renderStepper();
    renderStage();
    renderScoreboard();
  }

  function renderStepper() {
    stepperEl.innerHTML = (state.rounds || [])
      .map(
        (r) => `<span class="px-3 py-1.5 rounded-full text-xs font-medium border ${
          r.is_current
            ? "bg-primary text-surface border-primary"
            : "border-border text-muted"
        }">${esc(r.name)}</span>`
      )
      .join("");
  }

  function renderScoreboard() {
    const sorted = [...state.teams].sort((a, b) => b.score - a.score);
    scoreboardEl.innerHTML = sorted
      .map((t) => {
        const grew = prevScores[t.id] !== undefined && t.score > prevScores[t.id];
        return `
        <div class="flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 ${
          grew ? "animate-pulse-score" : ""
        }">
          <span class="w-3 h-3 rounded-full" style="background:${t.color}"></span>
          <span class="font-medium text-sm">${esc(t.name)}</span>
          <span class="font-display font-semibold text-sm ml-1">${t.score}</span>
        </div>`;
      })
      .join("");
    state.teams.forEach((t) => (prevScores[t.id] = t.score));
  }

  function bigRing(size) {
    const r = size / 2 - 10;
    return `
      <div class="relative mx-auto mb-6" style="width:${size}px;height:${size}px">
        <svg id="ring-main" viewBox="0 0 ${size} ${size}" class="w-full h-full -rotate-90">
          <circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="rgb(var(--color-border))" stroke-width="10"/>
          <circle class="ring-progress stroke-primary" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="10" stroke-linecap="round"/>
        </svg>
        <span id="ring-main-label" class="ring-label absolute inset-0 flex items-center justify-center font-display font-semibold" style="font-size:${size * 0.28}px">–</span>
      </div>`;
  }

  function boardStageHtml() {
    const cells = (state.board || [])
      .map((q) => {
        const cls =
          q.status === "resolved"
            ? "board-cell text-3xl sm:text-4xl bg-border/30 border-border/40 text-muted opacity-40"
            : q.is_current
            ? "board-cell text-3xl sm:text-4xl bg-primary text-surface border-primary"
            : "board-cell text-3xl sm:text-4xl bg-surface text-text border-border";
        return `<div class="${cls}">${q.number}</div>`;
      })
      .join("");
    const allDone = (state.board || []).length > 0 && state.board.every((q) => q.status === "resolved");
    return `
      <div class="w-full">
        <p class="text-sm uppercase tracking-widest text-muted mb-3">${esc(state.round.name)}</p>
        <p class="font-display text-2xl mb-5">${allDone ? "Round complete" : "Pick a number"}</p>
        <div class="board-grid max-w-3xl mx-auto">${cells}</div>
      </div>`;
  }

  function renderStage() {
    if (!state.round) {
      stageEl.innerHTML = `<p class="font-display text-3xl text-muted">Get ready…</p>`;
      return;
    }

    const phase = state.phase;

    if (phase === "idle" || phase === "round_complete") {
      if (state.round.type === "lightning") {
        stageEl.innerHTML = `
          <p class="text-sm uppercase tracking-widest text-muted mb-3">${
            phase === "round_complete" ? "Round complete" : "Up next"
          }</p>
          <p class="font-display text-4xl sm:text-5xl">${esc(state.round.name)}</p>`;
      } else {
        stageEl.innerHTML = boardStageHtml();
      }
      return;
    }

    if (state.round.type === "lightning" && (phase === "lightning_turn_complete")) {
      const l = state.lightning;
      stageEl.innerHTML = l
        ? `
        <p class="text-sm uppercase tracking-widest text-lightning mb-3">⚡ Turn complete</p>
        <p class="font-display text-3xl mb-2" style="color:${l.team.color}">${esc(l.team.name)}</p>
        <p class="font-display text-6xl font-semibold mb-2">${l.correct} / ${l.total}</p>
        <p class="text-muted">+${l.points_earned} points</p>`
        : `<p class="font-display text-3xl text-muted">Ready for the next turn</p>`;
      return;
    }

    const q = state.question;
    if (!q) return;

    const media = `
      ${q.image_url ? `<img src="${q.image_url}" class="max-h-[38vh] rounded-2xl border border-border mx-auto mb-6 shadow-lift" alt="">` : ""}
      ${q.audio_url ? `<div id="audio-indicator" class="flex items-center justify-center gap-1 mb-6 h-6">
          ${[0, 1, 2, 3, 4].map((i) => `<span class="w-1.5 bg-accent rounded-full eq-bar" style="animation-delay:${i * 0.12}s"></span>`).join("")}
        </div>` : ""}
    `;

    const choices = q.choices
      ? `<div class="grid grid-cols-2 gap-3 max-w-2xl mx-auto mb-6 text-lg sm:text-xl">
          ${q.choices
            .map(
              (c, i) =>
                `<div class="rounded-xl border border-border bg-surface px-5 py-3">
                  <span class="text-muted mr-2">${String.fromCharCode(65 + i)}</span>${esc(c)}
                </div>`
            )
            .join("")}
        </div>`
      : "";

    if (phase === "revealed") {
      stageEl.innerHTML = `
        ${state.round.type === "lightning" ? `<p class="text-sm uppercase tracking-widest text-lightning mb-3">⚡ Lightning round</p>` : ""}
        <p class="font-display text-2xl sm:text-3xl mb-6 max-w-4xl">${esc(q.text)}</p>
        ${media}
        ${choices}
        <div class="inline-block rounded-2xl bg-success/10 border border-success/30 px-8 py-5 animate-fade-up">
          <p class="text-xs uppercase tracking-widest text-success mb-1">Answer</p>
          <p class="font-display text-3xl font-semibold">${esc(q.answer)}</p>
        </div>`;
      return;
    }

    // active
    const turnBanner =
      state.round.type === "lightning" && state.lightning
        ? `<p class="text-sm uppercase tracking-widest text-lightning mb-1">⚡ Lightning — <span style="color:${state.lightning.team.color}">${esc(state.lightning.team.name)}</span></p>
           <p class="text-xs text-muted mb-4">${state.lightning.correct} / ${state.lightning.total} so far</p>`
        : state.current_turn_team_id
        ? `<p class="text-sm text-muted mb-4">Passed to <span class="font-medium" style="color:${(state.teams.find((t) => t.id === state.current_turn_team_id) || {}).color}">${esc((state.teams.find((t) => t.id === state.current_turn_team_id) || {}).name || "")}</span></p>`
        : "";

    stageEl.innerHTML = `
      ${bigRing(220)}
      ${turnBanner}
      <p class="font-display text-3xl sm:text-4xl mb-6 max-w-4xl">${esc(q.text)}</p>
      ${media}
      ${choices}
    `;

    ring = new TimerRing(document.getElementById("ring-main"), document.getElementById("ring-main-label"), 100);
    if (state.timer && state.timer.duration) {
      ring.set(state.timer.duration, state.timer.remaining, state.timer.status);
    }
  }
})();
