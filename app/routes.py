import os
import uuid
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, jsonify,
    current_app, abort, Response
)
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Game, Team, Round, Question, TEAM_COLORS, ROUND_TYPES
from .csv_import import parse_and_import, CsvImportError
from . import game_logic

bp = Blueprint("main", __name__)

IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a"}


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _save_upload(file_storage, allowed_exts):
    if not file_storage or not file_storage.filename:
        return None
    ext = _ext(file_storage.filename)
    if ext not in allowed_exts:
        raise ValueError(f"Unsupported file type: .{ext}")
    filename = f"{uuid.uuid4().hex}_{secure_filename(file_storage.filename)}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(path)
    return filename


# --------------------------------------------------------------- dashboard

@bp.route("/")
def dashboard():
    games = Game.query.order_by(Game.created_at.desc()).all()
    return render_template("dashboard.html", games=games)


@bp.route("/games", methods=["POST"])
def create_game():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Give the game a name.", "error")
        return redirect(url_for("main.dashboard"))
    try:
        default_timer = int(request.form.get("default_timer", 30))
    except ValueError:
        default_timer = 30
    game = Game(name=name, default_timer=max(5, default_timer))
    db.session.add(game)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game.id))


@bp.route("/games/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    game = Game.query.get_or_404(game_id)
    db.session.delete(game)
    db.session.commit()
    flash(f"Deleted '{game.name}'.", "info")
    return redirect(url_for("main.dashboard"))


# ------------------------------------------------------------------ setup

@bp.route("/games/<int:game_id>/setup")
def game_setup(game_id):
    game = Game.query.get_or_404(game_id)
    return render_template(
        "game_setup.html", game=game, team_colors=TEAM_COLORS, round_types=ROUND_TYPES
    )


@bp.route("/games/<int:game_id>/teams", methods=["POST"])
def add_team(game_id):
    game = Game.query.get_or_404(game_id)
    name = request.form.get("name", "").strip()
    color = request.form.get("color", TEAM_COLORS[0])
    if not name:
        flash("Team name can't be empty.", "error")
        return redirect(url_for("main.game_setup", game_id=game.id))
    team = Team(game_id=game.id, name=name, color=color, order=len(game.teams))
    db.session.add(team)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game.id))


@bp.route("/games/<int:game_id>/teams/<int:team_id>/delete", methods=["POST"])
def delete_team(game_id, team_id):
    team = Team.query.filter_by(id=team_id, game_id=game_id).first_or_404()
    db.session.delete(team)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game_id))


@bp.route("/games/<int:game_id>/rounds", methods=["POST"])
def add_round(game_id):
    game = Game.query.get_or_404(game_id)
    name = request.form.get("name", "").strip()
    rtype = request.form.get("type", "normal")
    timer_raw = request.form.get("timer_seconds", "").strip()
    turn_size = request.form.get("lightning_turn_size", "6").strip()

    if not name:
        flash("Round name can't be empty.", "error")
        return redirect(url_for("main.game_setup", game_id=game.id))
    if rtype not in ROUND_TYPES:
        abort(400)

    round_obj = Round(
        game_id=game.id,
        name=name,
        type=rtype,
        order=len(game.rounds),
        timer_seconds=int(timer_raw) if timer_raw.isdigit() else None,
        lightning_turn_size=int(turn_size) if turn_size.isdigit() else 6,
    )
    db.session.add(round_obj)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game.id))


@bp.route("/games/<int:game_id>/rounds/<int:round_id>/delete", methods=["POST"])
def delete_round(game_id, round_id):
    round_obj = Round.query.filter_by(id=round_id, game_id=game_id).first_or_404()
    db.session.delete(round_obj)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game_id))


@bp.route("/games/<int:game_id>/rounds/<int:round_id>/move", methods=["POST"])
def move_round(game_id, round_id):
    game = Game.query.get_or_404(game_id)
    round_obj = Round.query.filter_by(id=round_id, game_id=game_id).first_or_404()
    direction = request.form.get("direction")
    rounds = sorted(game.rounds, key=lambda r: r.order)
    idx = rounds.index(round_obj)
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(rounds):
        rounds[idx].order, rounds[swap_idx].order = rounds[swap_idx].order, rounds[idx].order
        db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game_id))


@bp.route("/games/<int:game_id>/rounds/<int:round_id>/questions", methods=["POST"])
def add_question(game_id, round_id):
    round_obj = Round.query.filter_by(id=round_id, game_id=game_id).first_or_404()
    text = request.form.get("text", "").strip()
    answer = request.form.get("answer", "").strip()
    points = request.form.get("points", "10").strip()
    choices = [request.form.get(f"choice_{c}", "").strip() for c in ("a", "b", "c", "d")]
    choices = [c for c in choices if c] or None

    if not text or not answer:
        flash("Question and answer are required.", "error")
        return redirect(url_for("main.game_setup", game_id=game_id))

    question = Question(
        round_id=round_obj.id,
        text=text,
        answer=answer,
        choices=choices,
        points=int(points) if points.isdigit() else 10,
        order=len(round_obj.questions),
    )

    try:
        question.image_filename = _save_upload(request.files.get("image"), IMAGE_EXTS)
        question.audio_filename = _save_upload(request.files.get("audio"), AUDIO_EXTS)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("main.game_setup", game_id=game_id))

    db.session.add(question)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game_id))


@bp.route("/games/<int:game_id>/questions/<int:question_id>/delete", methods=["POST"])
def delete_question(game_id, question_id):
    question = Question.query.join(Round).filter(
        Question.id == question_id, Round.game_id == game_id
    ).first_or_404()
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for("main.game_setup", game_id=game_id))


@bp.route("/games/<int:game_id>/import-csv", methods=["POST"])
def import_csv(game_id):
    game = Game.query.get_or_404(game_id)
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Choose a CSV file first.", "error")
        return redirect(url_for("main.game_setup", game_id=game_id))
    try:
        result = parse_and_import(game, file.stream)
        flash(
            f"Imported {result['questions_created']} question(s) across "
            f"{result['rounds_created']} new round(s).",
            "success",
        )
    except CsvImportError as e:
        flash(str(e), "error")
    return redirect(url_for("main.game_setup", game_id=game_id))


@bp.route("/games/<int:game_id>/sample.csv")
def sample_csv(game_id):
    sample = (
        "round_name,round_type,question,answer,choice_a,choice_b,choice_c,choice_d,points\n"
        "General Knowledge,normal,What is the capital of Nepal?,Kathmandu,Kathmandu,"
        "Pokhara,Lalitpur,Biratnagar,10\n"
        "General Knowledge,normal,Who wrote Muna Madan?,Laxmi Prasad Devkota,,,,,10\n"
        "Speed Round,lightning,7 x 8?,56,,,,,10\n"
        "Speed Round,lightning,Capital of France?,Paris,,,,,10\n"
    )
    return Response(
        sample, mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=quizhub_sample.csv"},
    )


@bp.route("/games/<int:game_id>/start", methods=["POST"])
def start_game(game_id):
    game = Game.query.get_or_404(game_id)
    if not game.teams:
        flash("Add at least one team before starting.", "error")
        return redirect(url_for("main.game_setup", game_id=game_id))
    if not game.rounds:
        flash("Add at least one round before starting.", "error")
        return redirect(url_for("main.game_setup", game_id=game_id))
    game.status = "active"
    state = game_logic.get_or_create_state(game)
    first_round = sorted(game.rounds, key=lambda r: r.order)[0]
    game_logic.select_round(game, state, first_round)
    db.session.commit()
    return redirect(url_for("main.control", game_id=game_id))


# ---------------------------------------------------------------- live app

@bp.route("/games/<int:game_id>/control")
def control(game_id):
    game = Game.query.get_or_404(game_id)
    state = game_logic.get_or_create_state(game)
    rounds = sorted(game.rounds, key=lambda r: r.order)
    return render_template("control.html", game=game, state=state, rounds=rounds)


@bp.route("/games/<int:game_id>/display")
def display(game_id):
    game = Game.query.get_or_404(game_id)
    return render_template("display.html", game=game)


@bp.route("/api/games/<int:game_id>/state")
def api_state(game_id):
    game = Game.query.get_or_404(game_id)
    state = game_logic.get_or_create_state(game)
    return jsonify(game_logic.serialize_state(game, state, include_answer=False))


@bp.route("/api/games/<int:game_id>/host-state")
def api_host_state(game_id):
    game = Game.query.get_or_404(game_id)
    state = game_logic.get_or_create_state(game)
    return jsonify(game_logic.serialize_state(game, state, include_answer=True))

