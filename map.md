# QuizHub — Project Map

A live quiz-night app: one **host control panel** (laptop) drives a game while
a **display page** (projector) shows the audience. Host and display stay in
sync over WebSockets. Single-user app, no login, runs locally over SQLite.

Stack: **Flask + Jinja2 + Flask-SocketIO + SQLAlchemy + SQLite + TailwindCSS**.
Pure server-authoritative game state — timers are computed on the server and
clients only animate between updates.

---

## Quick orientation

| Concern | Where it lives |
|---|---|
| Entry point | `run.py` |
| App factory / config | `app/__init__.py` |
| Extensions (db, socketio) | `app/extensions.py` |
| DB models | `app/models.py` |
| Page routes (HTTP) | `app/routes.py` |
| Live game engine (pure logic) | `app/game_logic.py` |
| Real-time event handlers (Socket.IO) | `app/sockets.py` |
| CSV import | `app/csv_import.py` |
| Server-rendered pages | `app/templates/` |
| Client logic | `app/static/js/` |
| Styling (Tailwind) | `app/static/src/input.css`, `tailwind.config.js` |

**Data flow in one sentence:** the host clicks a button in
`app/static/js/control.js` → emits a Socket.IO event handled in
`app/sockets.py` → calls a function in `app/game_logic.py` that mutates the
DB → `broadcast_state()` serializes the new state and pushes `state_update`
to the `game_<id>_host` and `game_<id>_display` rooms → both `control.js` and
`display.js` re-render.

---

## Directory / file inventory

```
run.py                       socketio.run() on 0.0.0.0:5000, debug on
requirements.txt             pinned deps (Flask, SQLAlchemy, SocketIO, engineio, simple-websocket, Werkzeug)
package.json                 tailwind build/watch scripts
tailwind.config.js           design tokens, darkMode class, fonts, animations
sample_quiz.csv              example CSV (also served via /sample.csv route)
app/
  __init__.py                create_app(): config, db/socketio init, create_all, blueprint, sockets
  extensions.py              shared db = SQLAlchemy(), socketio = SocketIO(threading mode)
  models.py                  Game, Team, Round, Question, ScoreEvent, GameState + constants
  routes.py                  HTTP blueprints: dashboard/setup/control/display + CRUD
  sockets.py                 14 Socket.IO event handlers (the live game)
  game_logic.py              game engine: timers, scoring, lightning, undo, serialization
  csv_import.py              CSV → rounds/questions import
  templates/                 8 Jinja templates (see below)
  static/
    src/input.css            Tailwind source with design tokens
    dist/output.css          compiled CSS (checked in)
    js/control.js            host control panel client
    js/display.js            projector/display client
    js/timer-ring.js         shared SVG countdown-ring widget
    js/vendor/socket.io.min.js  bundled Socket.IO client (offline)
    uploads/                 uploaded images/audio (gitignored except .gitkeep)
instance/quizhub.db          SQLite database (created at runtime, gitignored)
```

---

## Models (`app/models.py`)

Constants:
- `TEAM_COLORS` — 8 hex colors for team color pickers
- `ROUND_TYPES = ("normal", "lightning", "av")`
- `QUESTION_STATUSES = ("pending", "active", "resolved")`
- `EVENT_TYPES = ("correct", "incorrect", "pass", "reveal", "lightning_correct", "lightning_incorrect")`

### Game
| column | notes |
|---|---|
| `id`, `name` | |
| `default_timer` | seconds, default 30, per-round override possible |
| `status` | `"setup"` / `"active"` / `"completed"` |
| `created_at` | |

Relationships: `teams` (ordered), `rounds` (ordered), `score_events`,
`state` (one GameState). Methods: `to_summary()` — dict for dashboard cards
(also counts questions across rounds).

### Team
`id`, `game_id`, `name`, `color` (hex, default #8CB0D1), `score` (int, default 0),
`order`. Method: `to_dict()`.

### Round
`id`, `game_id`, `name`, `type` (default `"normal"`), `order`,
`timer_seconds` (nullable — None means "use game default"),
`lightning_turn_size` (default 6, questions per team lightning turn).
Relationships: `questions` (ordered). Methods:
- `effective_timer()` → round override or `game.default_timer`
- `to_dict()`

### Question
`id`, `round_id`, `text`, `answer`, `choices` (JSON list or None, for
multiple choice), `points` (default 10), `order`,
`image_filename` / `audio_filename` (nullable, relative to `/static/uploads/`),
`status`, `used_in_lightning_turn` (int group id that marks a question as
consumed by a particular lightning turn).

Methods:
- `to_public_dict()` — **no answer** (safe for the projector pre-reveal):
  id, text, choices, points, `image_url`, `audio_url`, round_type
- `to_host_dict()` — public + `answer`

### ScoreEvent (audit log that powers Undo)
`id`, `game_id`, `team_id` (nullable — reveal has no team), `question_id`,
`round_id`, `event_type`, `points`, `reversed` (bool — set True when undone),
`created_at`. Relationship: `team`.

### GameState (one row per game, the authoritative live state)
| column | notes |
|---|---|
| `game_id` | unique FK |
| `current_round_id`, `current_question_id`, `current_turn_team_id` | |
| `timer_duration`, `timer_started_at`, `timer_status` | status: stopped/running/paused |
| `timer_remaining_at_pause` | captured when pausing |
| `question_phase` | `idle` / `active` / `revealed` (+ `round_complete`, `lightning_turn_complete` are set ad-hoc in code) |
| `lightning_team_id`, `lightning_correct`, `lightning_total`, `lightning_points_earned`, `lightning_turn_number` | lightning turn counters |

Relationships: `current_round`, `current_question`, `current_turn_team`,
`lightning_team` (each with explicit `foreign_keys`).

---

## Routes (`app/routes.py`)

Blueprint: `main` (url prefix none). Module helpers:
- `_ext(filename)` — extension from filename
- `_save_upload(file_storage, allowed_exts)` — validates ext against
  `IMAGE_EXTS`/`AUDIO_EXTS`, saves as `uuid_orig.ext` in UPLOAD_FOLDER,
  returns filename (or None). Raises `ValueError` on bad type.

### Dashboard
| Method | Route | Function | Purpose |
|---|---|---|---|
| GET | `/` | `dashboard` | lists all games (desc by created_at), renders dashboard.html |
| POST | `/games` | `create_game` | create game (name + default_timer, min 5), redirect to setup |
| POST | `/games/<id>/delete` | `delete_game` | cascade-delete game |
| GET | `/games/<id>/edit` | `edit_game` | render edit form |
| POST | `/games/<id>/edit` | `update_game` | save name + default_timer |

### Setup
| Method | Route | Function | Purpose |
|---|---|---|---|
| GET | `/games/<id>/setup` | `game_setup` | main setup page (teams, rounds, import) |
| POST | `/games/<id>/teams` | `add_team` | add team (name + color) |
| POST | `/games/<id>/teams/<team_id>/delete` | `delete_team` | |
| GET/POST | `/games/<id>/teams/<team_id>/edit` | `edit_team` | rename / recolor |
| POST | `/games/<id>/rounds` | `add_round` | add round (validates type in ROUND_TYPES) |
| POST | `/games/<id>/rounds/<round_id>/delete` | `delete_round` | |
| POST | `/games/<id>/rounds/<round_id>/move` | `move_round` | `direction` = up/down, swaps `order` |
| GET/POST | `/games/<id>/rounds/<round_id>/edit` | `edit_round` | name/type/timer/turn size |
| POST | `/games/<id>/rounds/<round_id>/questions` | `add_question` | text, answer, points, choices a–d, optional image/audio upload |
| POST | `/games/<id>/questions/<q_id>/delete` | `delete_question` | |
| GET/POST | `/games/<id>/questions/<q_id>/edit` | `edit_question` | edit fields; `remove_image`/`remove_audio` checkboxes; replace-upload deletes old file |
| POST | `/games/<id>/import-csv` | `import_csv` | calls `parse_and_import`, flashes result |
| GET | `/games/<id>/sample.csv` | `sample_csv` | serves download template CSV |
| POST | `/games/<id>/start` | `start_game` | requires ≥1 team and ≥1 round; sets active, creates state, selects first round |

### Live app
| Method | Route | Function | Purpose |
|---|---|---|---|
| GET | `/games/<id>/control` | `control` | host panel page |
| GET | `/games/<id>/display` | `display` | projector page |
| GET | `/api/games/<id>/state` | `api_state` | JSON, **no answer** (public) |
| GET | `/api/games/<id>/host-state` | `api_host_state` | JSON **with answer** |

---

## Game engine (`app/game_logic.py`)

Custom exception: `GameLogicError` (caught in sockets and re-emitted as
`action_error`).

### State helpers
- `get_or_create_state(game)` — returns `game.state`, creating a GameState row if missing
- `compute_timer_remaining(state)` — elapsed = now − `timer_started_at`;
  returns seconds left (floored, min 0); respects paused/stopped branches
- `_start_timer(state, duration)` — resets duration, started_at, status=running
- `select_round(game, state, round_obj)` — switch round, clears question/timer/lightning
- `start_question(game, state, question)` — rejects questions already
  `resolved` (raises `GameLogicError`); sets current question, starts its
  round's effective timer, phase=active, question.status=active
- `next_pending_question(round_obj, exclude_lightning=True)` — first
  `pending` question in round (excludes lightning-consumed ones by default)

### Timer controls
- `pause_timer(state)` / `resume_timer(state)` / `restart_timer(state)` —
  restart uses current round's effective timer

### Normal / AV scoring
- `mark_correct(game, state, team)` — add `question.points` to team, resolve
  question, phase=revealed, stop timer, log ScoreEvent(correct)
- `pass_question(game, state, target_team)` — set current_turn_team, restart
  timer, stay active, log ScoreEvent(pass, 0pts)
- `reveal_answer(game, state)` — resolve question, phase=revealed, stop timer,
  log ScoreEvent(reveal, no team, 0pts)

### Lightning
- `start_lightning_turn(game, state, round_obj, team, count)` — takes up to
  `count` unused pending questions from the round, stamps them all with the
  next `used_in_lightning_turn` number, resets turn counters, then starts the
  first question
- `lightning_mark(game, state, correct)` — scores current lightning question
  (correct → team +points, counters up, ScoreEvent lightning_correct; else
  lightning_incorrect, 0pts), then auto-advances to the next unused question
  in the turn; when exhausted returns `{turn_complete: True}` and sets phase
  to `lightning_turn_complete`

### Undo
- `undo_last_action(game, state)` — finds newest unreversed ScoreEvent, marks
  `reversed=True`, subtracts points (clamped ≥0), restores the question to
  `pending`, rewinds lightning counters if it was a lightning mark, re-activates
  the question with a fresh timer. Returns the event or None.

### Serialization
- `serialize_state(game, state, include_answer)` — the single source of truth
  pushed over the socket. Contains: game_id/name/status, `phase`,
  `rounds` (all rounds with `is_current` flag), `round` (current round dict),
  `question` (public dict, or host dict if `include_answer`), `timer`
  (duration/remaining/status), `teams` (sorted by score desc),
  `current_turn_team_id`, `lightning` (team/correct/total/points_earned — only
  for lightning rounds mid-turn), and `board` — the question-number picker grid
  for the current round (id, 1-based `number`, `status`, `is_current`; sent to
  both host and display; **no answer text**, safe for the projector). Plus
  `round_questions` (truncated question list for the host, only when
  `include_answer`).

---

## Socket.IO handlers (`app/sockets.py`)

Rooms: `game_<id>_host` and `game_<id>_display` (see `_rooms(game_id)`).

- `broadcast_state(game)` — emits `state_update` to host room with answer,
  and to display room **with answer only when `phase == "revealed"`** (keeps
  answers secret until revealed)
- `_game_or_error(game_id)` — helper, emits `action_error` if game missing

| Event (client → server) | Handler | Does |
|---|---|---|
| `join` | `on_join` | join room by role (host/display), send initial state |
| `select_round` | `on_select_round` | validate round belongs to game, `select_round` |
| `start_question` | `on_start_question` | validate, `start_question` |
| `pause_timer` | `on_pause_timer` | |
| `resume_timer` | `on_resume_timer` | |
| `restart_timer` | `on_restart_timer` | |
| `mark_correct` | `on_mark_correct` | team must belong to game; catches GameLogicError |
| `pass_question` | `on_pass_question` | target team id |
| `reveal_answer` | `on_reveal_answer` | |
| `next_question` | `on_next_question` | **Lightning:** next pending, else phase=`round_complete`. **Normal/AV:** clears the question and returns to `idle` (back to the question-number board so the room can pick another) |
| `start_lightning_turn` | `on_start_lightning_turn` | round_id, team_id, count |
| `lightning_mark` | `on_lightning_mark` | `correct: bool` |
| `play_audio` | `on_play_audio` | relays `audio_play` to the display room only (host's play button → projector plays clip) |
| `undo` | `on_undo` | `undo_last_action` |
| `end_game` | `on_end_game` | game.status=completed, emits `game_ended` with standings to both rooms |

Every handler ends with `broadcast_state(game)` (except join/play_audio/end_game).

---

## CSV import (`app/csv_import.py`)

- `CsvImportError` — user-facing message, flashed on the setup page
- `parse_and_import(game, file_stream)`:
  - decodes bytes as UTF-8-sig, uses `csv.DictReader`
  - validates header has all of `REQUIRED_COLUMNS` (`round_name`, `round_type`, `question`, `answer`)
  - rows grouped into rounds by `round_name` (case-insensitive); reuses an
    existing round with the same name in this game; round_type taken from the
    first row of that round
  - validates `round_type` ∈ ROUND_TYPES, blank rows, integer `points`
    (default 10)
  - optional `choice_a..d` → `choices` list (None if all empty)
  - returns `{"rounds_created": n, "questions_created": n}`

---

## Templates (`app/templates/`)

| Template | Extends | Purpose / key blocks |
|---|---|---|
| `base.html` | — | Layout: nav bar, theme-toggle (localStorage `quizhub-theme`, no-flash inline script), flash messages with category styling, `{% block head %}`/`content`/`scripts` |
| `dashboard.html` | base | Game cards (summary via `game.to_summary()`), status badge, new-game modal (name + default timer) |
| `game_setup.html` | base | The big setup page: teams list + add form (color radios), CSV import + sample link, add-round form, per-round `<details>` with question table (add/edit/delete/move), add-question form (with image/audio file inputs only for AV rounds) |
| `edit_game.html` | base | name + default timer form |
| `edit_team.html` | base | rename/recolor form |
| `edit_round.html` | base | name/type/timer/turn-size form |
| `edit_question.html` | base | text/answer/points/choices; for AV rounds: current-media view, remove checkboxes, replace uploads |
| `control.html` | base | Host panel: conn-dot, round tabs, `#stage`, `#question-list`, `#scoreboard`, `#toast-area`, undo/end-game buttons, final-overlay. Injects `window.QUIZHUB.gameId`, loads socket.io, timer-ring, control.js |
| `display.html` | — (standalone, no nav) | Projector screen: round stepper, `#stage`, scoreboard strip, fullscreen + theme toggles, click-to-begin overlay (unlocks audio + fullscreen), final-results overlay, hidden `<audio>` element |

---

## Client JS (`app/static/js/`)

### `timer-ring.js` (shared)
`class TimerRing` — animates an SVG stroke-dasharray countdown ring given
`set(duration, remaining, status)`. Uses `requestAnimationFrame` to tick
smoothly between authoritative server updates; turns the ring lightning-color
+ pulsing when ≤5s remain and running. Label shows `ceil(remaining)`. `stop()`
cancels the RAF.

### `control.js` (host)
- connects socket with websocket+polling, joins `host` room on connect,
  turns `#conn-dot` green/red on connect/disconnect
- `esc()` XSS-escapes strings; `showToast()` prepends a toast that fades out
- on `state_update` → re-render round tabs (active styling), stage,
  question list, scoreboard
- **question-number board**: for normal/AV rounds, the idle stage shows a grid
  of numbered cells built from `state.board` (all non-lightning rounds by
  default). Pending cells are clickable and emit `start_question` with the
  question id; resolved cells are grayed out and disabled. The board reappears
  after every question (see `next_question` above), so the room picks the next
  number — this is the default question-selection UI except in lightning
  rounds, which still auto-pull.
- question list (text): pending questions clickable (jump-starts them) — not
  for lightning rounds (which pull automatically); status badges
  (done/current/pool/pending)
- stage renderer branches: no round → "No round selected"; normal/AV →
  `normalStageHtml()` (idle → board grid, else question view); lightning →
  `lightningStageHtml()`
  - normal active view: ring + round badge + points, timer pause/resume/
    restart, question, media (image / play-audio button), choices, host-only
    answer box, "Mark correct" per-team buttons (colored), pass-to-team
    select + button, "Reveal (no score)"
  - normal revealed view: answer box + "Next question →"
  - lightning idle: start-turn form (team select, count input, "Start turn")
  - lightning active: ring, answer box, big "Correct / Incorrect" buttons
- `wireStageEvents()`: maps `data-action` clicks to socket emits
- undo / end-game (confirm dialog) buttons at top
- `game_ended` → fill `#final-standings`, show `#final-overlay`

### `display.js` (projector)
- click-to-begin overlay: on click hides overlay, requests fullscreen, and
  plays/pauses a muted empty audio to unlock programmatic audio later
- fullscreen + theme toggles
- on `state_update`: if question changed, stop/reset current audio; render
- `audio_play` event → sets `#clip-audio.src` to current question's audio_url
  and plays (with visual eq-bar indicator)
- renderer: round stepper pills, scoreboard strip (sorted desc, pulses when a
  team's score grows via `prevScores` tracking), stage:
  - no round → "Get ready…"
  - idle/round_complete → for normal/AV rounds shows the **question-number
    board** (big numbered grid, grayed-out for played questions, "Round
    complete" when all done); for lightning rounds shows the round name
    headline (board is not used for lightning)
  - lightning turn complete → big "correct / total" + points
  - revealed → question + media + answer banner
  - active → big countdown ring (TimerRing, radius 100), optional lightning/
    passed-to banner, question text, media, choices
- `game_ended` → final standings overlay (winner highlighted)

---

## Styling

- `tailwind.config.js`: content scans templates + JS; `darkMode: "class"`;
  custom colors map to CSS vars (`--color-*` as RGB triples so opacity
  modifiers work), fonts (Space Grotesk display / Inter body), shadows
  (`panel`, `lift`), keyframes/animations (`pulse-score`, `fade-up`,
  `ring-urgent`)
- `input.css`: light + dark palettes, base body font, component classes
  (`.btn*`, `.card`, `.input`, `.label`, `.badge`), equalizer-bar animation
  for the audio indicator, prefers-reduced-motion guard
- `output.css` is the committed build artifact (`npm run build:css` to rebuild)

---

## App lifecycle / startup

1. `run.py` → `create_app()` (`app/__init__.py`)
2. Config set: SECRET_KEY from env, SQLite URI pointing at
   `instance/quizhub.db`, UPLOAD_FOLDER, 25MB MAX_CONTENT_LENGTH
3. `instance/` and `app/static/uploads/` dirs ensured; `db.create_all()`
4. `main` blueprint registered; `sockets` module imported (registers handlers)
5. `socketio.run(..., host="0.0.0.0", port=5000, debug=True)`

### Typical game flow (end to end)
1. `/` dashboard → New game → `/games/<id>/setup`
2. Add teams (colored), add rounds (normal/lightning/av, optional timer
   override, lightning turn size) + questions manually or via CSV import;
   attach media on AV rounds
3. **Start game** → `/games/<id>/control` (host) — state row created, first
   round selected; **Open display** → `/games/<id>/display` in another tab
4. Host picks a question from the **number board** (or starts a lightning
   turn) → socket event → engine mutates state → broadcast → display shows
   question + countdown; the played number grays out on the board afterwards
5. Mark correct / pass / reveal; per-question timer; lightning auto-advances
6. Undo available for the single most recent scoring action
7. **End game** → final results overlay on both screens

---

## Notes / gotchas

- **Answer secrecy**: the display room only receives answers when
  `question_phase == "revealed"` (see `broadcast_state` in `sockets.py:16`),
  but anyone who opens `/games/<id>/control` or `/api/games/<id>/host-state`
  can read answers — by design (single trusted host).
- Timer is server-authoritative: a "running" timer is extrapolated from
  `timer_started_at` on every read (`compute_timer_remaining`), so refreshes
  and reconnects stay correct.
- `question_phase` "round_complete" and "lightning_turn_complete" are set
  directly in code but not listed in the model's comment (see
  `game_logic.py` and `sockets.py`).
- `used_in_lightning_turn` prevents a question from being re-used after a
  lightning turn and also distinguishes lightning questions for undo logic.
- Media removal/replacement deletes old files from the uploads folder.
- No auth, no CSRF protection on forms — designed as a trusted localhost tool.
