# QuizHub

A live quiz-night app built for running a game show style event on a projector:
one **host control panel** (your laptop) drives the game, and one **display**
page (the projector) shows the audience-facing screen. They stay in sync in
real time over WebSockets.

## Features

- Import questions from a CSV, or add them one at a time in the UI
- Multiple games, each with its own teams, rounds, and settings
- Any number of teams with a live scoreboard
- Per-question timer (defaults to 30s, overridable per round)
- **Lightning rounds** — put one team "on the clock" for a fast run of
  5–10 questions with a short timer each
- **Audio-visual rounds** — attach an image and/or an audio clip to a question
- **Pass or reveal** — if a team can't answer, pass it to another team or
  reveal the answer to everyone (no points awarded)
- Light and dark mode, using your Soft Slate color palette
- Undo button for the last scoring action, in case of a mis-click
- Works without an internet connection once installed (the only thing that
  needs the internet is the Google Fonts request — if that fails, it falls
  back to your system font and everything else still works)

## How it's meant to be used

1. On your laptop, open `/games/<id>/setup` and build the quiz.
2. Click **Start game** — this takes you to the **control panel**.
3. Click **Open display** — this opens the projector page in a new tab.
   Drag that tab onto the projector/second screen and make it fullscreen
   (there's a fullscreen button in the corner, or use your OS's shortcut).
   The display starts with a "click to begin" screen — click it once to
   unlock audio playback and enter fullscreen.
4. Run the game entirely from the control panel on your own laptop screen.
   The audience only ever sees the display page — they never see answers
   before you reveal them.

There's no login system — this is designed to run as a single trusted host
on one laptop, not as a multiplayer app with team devices, so keep the
control panel tab private and only share the display tab.

## Setup

You'll need **Python 3.10+** and (only if you want to change the CSS) **Node.js 18+**.

```bash
python3 -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt

python3 run.py
```

Then open **http://localhost:5000** on your laptop.

The database (`instance/quizhub.db`) and uploaded media
(`app/static/uploads/`) are created automatically on first run — nothing
else to configure. To reset everything, just delete `instance/quizhub.db`.

### If you want to edit the styling

The compiled CSS is already built and checked in at
`app/static/dist/output.css`, so you don't need Node.js just to run the app.
If you want to change colors, fonts, or any Tailwind classes:

```bash
npm install
npm run build:css     # one-off build
npm run watch:css     # rebuilds automatically while you edit
```

## CSV import format

Required columns: `round_name`, `round_type` (`normal` / `lightning` / `av`),
`question`, `answer`.
Optional columns: `choice_a`, `choice_b`, `choice_c`, `choice_d` (for
multiple choice), `points` (defaults to 10).

Rows that share the same `round_name` are grouped into one round — the
`round_type` is taken from the first row seen for that round. A template is
available for download from the setup page, and it looks like this:

```csv
round_name,round_type,question,answer,choice_a,choice_b,choice_c,choice_d,points
General Knowledge,normal,What is the capital of Nepal?,Kathmandu,Kathmandu,Pokhara,Lalitpur,Biratnagar,10
General Knowledge,normal,Who wrote Muna Madan?,Laxmi Prasad Devkota,,,,,10
Speed Round,lightning,7 x 8?,56,,,,,10
Speed Round,lightning,Capital of France?,Paris,,,,,10
```

For **audio-visual rounds**, the CSV only carries the text — attach the
image/audio file to each question afterwards from the setup page (each
question has its own upload fields once you're editing an AV round).
Supported: images (png/jpg/jpeg/gif/webp), audio (mp3/wav/ogg/m4a), up to
25MB per file.

## How lightning rounds work

1. In the control panel, select the lightning round.
2. Pick a team and how many questions (5–10 is typical), then **Start turn**.
3. The app pulls that many unused questions from the round's pool and walks
   through them one at a time with a short timer, marking each **Correct**
   or **Incorrect** as the team answers.
4. At the end you get a tally (e.g. "4/6 correct, 40 points") — then start
   a turn for the next team, pulling from the remaining pool.

Add enough questions to a lightning round to cover every team's turn (e.g.
4 teams × 6 questions = 24 questions in the pool).

## How passing/revealing works (normal & AV rounds)

While a question is active you can:
- **Mark a team correct** — awards them the points and reveals the answer
  on the display.
- **Pass to team** — hands the question to a specific team (resets the
  timer), without revealing anything.
- **Reveal (no score)** — shows the answer to everyone with no points
  awarded, then move on with **Next question**.

## Project structure

```
run.py                     entry point
app/
  __init__.py               Flask app factory
  models.py                 database models
  extensions.py              db + socketio instances
  routes.py                  page routes (dashboard, setup, control, display)
  sockets.py                  real-time event handlers (the game runs through these)
  game_logic.py               the actual game engine (timers, scoring, lightning turns, undo)
  csv_import.py                CSV parsing
  templates/                   Jinja templates
  static/
    src/input.css               Tailwind source (design tokens live here)
    dist/output.css              built CSS (checked in, ready to run)
    js/                          control.js, display.js, timer-ring.js
    js/vendor/socket.io.min.js    bundled Socket.IO client (works offline)
    uploads/                     question images/audio (created at runtime)
```

## A couple of practical notes

- **Undo** reverses the single most recent scoring action (a correct answer,
  a lightning mark, etc.) — handy for mis-clicks, but it only goes back one
  step.
- The display page's "click to begin" overlay isn't just decoration — most
  browsers block audio autoplay and fullscreen until there's been a real
  click on the page, so that's what unlocks both for the rest of the game.
- Everything runs locally over SQLite — no external services, no accounts,
  nothing to pay for.
