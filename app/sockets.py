from flask_socketio import join_room, emit
from .extensions import socketio, db
from .models import Game, Team, Round, Question
from . import game_logic


def _rooms(game_id):
    return f"game_{game_id}_host", f"game_{game_id}_display"


def broadcast_state(game):
    state = game_logic.get_or_create_state(game)
    host_room, display_room = _rooms(game.id)

    host_payload = game_logic.serialize_state(game, state, include_answer=True)
    display_show_answer = state.question_phase in ("revealed",)
    display_payload = game_logic.serialize_state(game, state, include_answer=display_show_answer)

    socketio.emit("state_update", host_payload, room=host_room)
    socketio.emit("state_update", display_payload, room=display_room)


def _game_or_error(game_id):
    game = Game.query.get(game_id)
    if not game:
        emit("action_error", {"message": "Game not found."})
        return None
    return game


@socketio.on("join")
def on_join(data):
    game_id = data.get("game_id")
    role = data.get("role")
    if role not in ("host", "display"):
        return
    room = f"game_{game_id}_{role}"
    join_room(room)
    game = Game.query.get(game_id)
    if game:
        state = game_logic.get_or_create_state(game)
        include_answer = role == "host" or state.question_phase == "revealed"
        emit("state_update", game_logic.serialize_state(game, state, include_answer=include_answer))


@socketio.on("select_round")
def on_select_round(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    round_obj = Round.query.filter_by(id=data.get("round_id"), game_id=game.id).first()
    if not round_obj:
        emit("action_error", {"message": "Round not found."})
        return
    state = game_logic.get_or_create_state(game)
    game_logic.select_round(game, state, round_obj)
    broadcast_state(game)


@socketio.on("start_question")
def on_start_question(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    question = Question.query.join(Round).filter(
        Question.id == data.get("question_id"), Round.game_id == game.id
    ).first()
    if not question:
        emit("action_error", {"message": "Question not found."})
        return
    state = game_logic.get_or_create_state(game)
    try:
        game_logic.start_question(game, state, question)
    except game_logic.GameLogicError as e:
        emit("action_error", {"message": str(e)})
        return
    broadcast_state(game)


@socketio.on("pause_timer")
def on_pause_timer(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    game_logic.pause_timer(state)
    broadcast_state(game)


@socketio.on("resume_timer")
def on_resume_timer(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    game_logic.resume_timer(state)
    broadcast_state(game)


@socketio.on("restart_timer")
def on_restart_timer(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    game_logic.restart_timer(state)
    broadcast_state(game)


@socketio.on("mark_correct")
def on_mark_correct(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    team = Team.query.filter_by(id=data.get("team_id"), game_id=game.id).first()
    if not team:
        emit("action_error", {"message": "Team not found."})
        return
    state = game_logic.get_or_create_state(game)
    try:
        game_logic.mark_correct(game, state, team)
    except game_logic.GameLogicError as e:
        emit("action_error", {"message": str(e)})
        return
    broadcast_state(game)


@socketio.on("pass_question")
def on_pass_question(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    team = Team.query.filter_by(id=data.get("team_id"), game_id=game.id).first()
    if not team:
        emit("action_error", {"message": "Team not found."})
        return
    state = game_logic.get_or_create_state(game)
    try:
        game_logic.pass_question(game, state, team)
    except game_logic.GameLogicError as e:
        emit("action_error", {"message": str(e)})
        return
    broadcast_state(game)


@socketio.on("reveal_answer")
def on_reveal_answer(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    try:
        game_logic.reveal_answer(game, state)
    except game_logic.GameLogicError as e:
        emit("action_error", {"message": str(e)})
        return
    broadcast_state(game)


@socketio.on("next_question")
def on_next_question(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    round_obj = state.current_round
    if not round_obj:
        emit("action_error", {"message": "Select a round first."})
        return
    if round_obj.type == "lightning":
        nxt = game_logic.next_pending_question(round_obj)
        if not nxt:
            state.question_phase = "round_complete"
            state.current_question_id = None
            db.session.commit()
        else:
            game_logic.start_question(game, state, nxt)
    else:
        state.current_question_id = None
        state.current_turn_team_id = None
        state.question_phase = "idle"
        state.timer_status = "stopped"
        state.timer_duration = None
        state.timer_started_at = None
        state.timer_remaining_at_pause = None
        db.session.commit()
    broadcast_state(game)


@socketio.on("start_lightning_turn")
def on_start_lightning_turn(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    round_obj = Round.query.filter_by(id=data.get("round_id"), game_id=game.id).first()
    team = Team.query.filter_by(id=data.get("team_id"), game_id=game.id).first()
    count = data.get("count") or (round_obj.lightning_turn_size if round_obj else 6)
    if not round_obj or not team:
        emit("action_error", {"message": "Round or team not found."})
        return
    state = game_logic.get_or_create_state(game)
    try:
        game_logic.start_lightning_turn(game, state, round_obj, team, int(count))
    except game_logic.GameLogicError as e:
        emit("action_error", {"message": str(e)})
        return
    broadcast_state(game)


@socketio.on("lightning_mark")
def on_lightning_mark(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    try:
        game_logic.lightning_mark(game, state, bool(data.get("correct")))
    except game_logic.GameLogicError as e:
        emit("action_error", {"message": str(e)})
        return
    broadcast_state(game)


@socketio.on("play_audio")
def on_play_audio(data):
    game_id = data.get("game_id")
    _, display_room = _rooms(game_id)
    emit("audio_play", {}, room=display_room)


@socketio.on("undo")
def on_undo(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    state = game_logic.get_or_create_state(game)
    event = game_logic.undo_last_action(game, state)
    if not event:
        emit("action_error", {"message": "Nothing to undo."})
        return
    broadcast_state(game)


@socketio.on("end_game")
def on_end_game(data):
    game = _game_or_error(data.get("game_id"))
    if not game:
        return
    game.status = "completed"
    db.session.commit()
    host_room, display_room = _rooms(game.id)
    teams_sorted = sorted(game.teams, key=lambda t: t.score, reverse=True)
    payload = {"teams": [t.to_dict() for t in teams_sorted]}
    socketio.emit("game_ended", payload, room=host_room)
    socketio.emit("game_ended", payload, room=display_room)
