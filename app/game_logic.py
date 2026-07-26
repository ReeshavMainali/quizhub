from datetime import datetime
from .extensions import db
from .models import GameState, Question, ScoreEvent, Round


class GameLogicError(Exception):
    pass


def get_or_create_state(game):
    if game.state:
        return game.state
    state = GameState(game_id=game.id)
    db.session.add(state)
    db.session.commit()
    return state


def compute_timer_remaining(state):
    if not state.timer_duration:
        return None
    if state.timer_status == "running" and state.timer_started_at:
        elapsed = (datetime.utcnow() - state.timer_started_at).total_seconds()
        remaining = state.timer_duration - elapsed
        return max(0, round(remaining))
    if state.timer_status == "paused" and state.timer_remaining_at_pause is not None:
        return state.timer_remaining_at_pause
    return state.timer_duration


def _start_timer(state, duration):
    state.timer_duration = duration
    state.timer_started_at = datetime.utcnow()
    state.timer_status = "running"
    state.timer_remaining_at_pause = None


def select_round(game, state, round_obj):
    if round_obj.game_id != game.id:
        raise GameLogicError("That round does not belong to this game.")
    state.current_round_id = round_obj.id
    state.current_question_id = None
    state.current_turn_team_id = None
    state.question_phase = "idle"
    state.timer_status = "stopped"
    state.timer_started_at = None
    state.timer_duration = None
    state.lightning_team_id = None
    state.lightning_correct = 0
    state.lightning_total = 0
    state.lightning_points_earned = 0
    db.session.commit()


def start_question(game, state, question):
    round_obj = question.round
    _start_timer(state, round_obj.effective_timer())
    state.current_question_id = question.id
    state.current_round_id = round_obj.id
    state.question_phase = "active"
    if round_obj.type != "lightning":
        state.current_turn_team_id = None
    question.status = "active"
    db.session.commit()


def next_pending_question(round_obj, exclude_lightning=True):
    q = (
        Question.query.filter_by(round_id=round_obj.id, status="pending")
        .filter(Question.used_in_lightning_turn.is_(None) if exclude_lightning else True)
        .order_by(Question.order)
        .first()
    )
    return q


def pause_timer(state):
    if state.timer_status == "running":
        state.timer_remaining_at_pause = compute_timer_remaining(state)
        state.timer_status = "paused"
        db.session.commit()


def resume_timer(state):
    if state.timer_status == "paused":
        state.timer_duration = state.timer_remaining_at_pause or state.timer_duration
        state.timer_started_at = datetime.utcnow()
        state.timer_status = "running"
        state.timer_remaining_at_pause = None
        db.session.commit()


def restart_timer(state):
    round_obj = state.current_round
    if round_obj:
        _start_timer(state, round_obj.effective_timer())
        db.session.commit()


def mark_correct(game, state, team):
    question = state.current_question
    if not question:
        raise GameLogicError("No active question to score.")
    team.score += question.points
    question.status = "resolved"
    state.question_phase = "revealed"
    state.timer_status = "stopped"
    event = ScoreEvent(
        game_id=game.id, team_id=team.id, question_id=question.id,
        round_id=question.round_id, event_type="correct", points=question.points,
    )
    db.session.add(event)
    db.session.commit()


def pass_question(game, state, target_team):
    question = state.current_question
    if not question:
        raise GameLogicError("No active question to pass.")
    state.current_turn_team_id = target_team.id
    restart_timer(state)
    state.question_phase = "active"
    event = ScoreEvent(
        game_id=game.id, team_id=target_team.id, question_id=question.id,
        round_id=question.round_id, event_type="pass", points=0,
    )
    db.session.add(event)
    db.session.commit()


def reveal_answer(game, state):
    question = state.current_question
    if not question:
        raise GameLogicError("No active question to reveal.")
    question.status = "resolved"
    state.question_phase = "revealed"
    state.timer_status = "stopped"
    event = ScoreEvent(
        game_id=game.id, team_id=None, question_id=question.id,
        round_id=question.round_id, event_type="reveal", points=0,
    )
    db.session.add(event)
    db.session.commit()


# ---------------------------------------------------------------- lightning

def start_lightning_turn(game, state, round_obj, team, count):
    if round_obj.type != "lightning":
        raise GameLogicError("That round is not a lightning round.")
    pool = (
        Question.query.filter_by(round_id=round_obj.id, status="pending")
        .filter(Question.used_in_lightning_turn.is_(None))
        .order_by(Question.order)
        .limit(count)
        .all()
    )
    if not pool:
        raise GameLogicError("No unused questions left in this round for a lightning turn.")

    turn_number = state.lightning_turn_number + 1
    for q in pool:
        q.used_in_lightning_turn = turn_number

    state.lightning_turn_number = turn_number
    state.lightning_team_id = team.id
    state.current_turn_team_id = team.id
    state.lightning_correct = 0
    state.lightning_total = len(pool)
    state.lightning_points_earned = 0
    state.current_round_id = round_obj.id
    db.session.commit()

    first = pool[0]
    start_question(game, state, first)
    return len(pool)


def lightning_mark(game, state, correct):
    question = state.current_question
    if not question or question.used_in_lightning_turn != state.lightning_turn_number:
        raise GameLogicError("No active lightning question to mark.")
    team = state.lightning_team
    question.status = "resolved"

    if correct:
        team.score += question.points
        state.lightning_correct += 1
        state.lightning_points_earned += question.points
        event_type = "lightning_correct"
        points = question.points
    else:
        event_type = "lightning_incorrect"
        points = 0

    event = ScoreEvent(
        game_id=game.id, team_id=team.id, question_id=question.id,
        round_id=question.round_id, event_type=event_type, points=points,
    )
    db.session.add(event)
    db.session.commit()

    nxt = (
        Question.query.filter_by(
            round_id=question.round_id,
            used_in_lightning_turn=state.lightning_turn_number,
            status="pending",
        )
        .order_by(Question.order)
        .first()
    )
    if nxt:
        start_question(game, state, nxt)
        return {"turn_complete": False}
    else:
        state.current_question_id = None
        state.question_phase = "lightning_turn_complete"
        state.timer_status = "stopped"
        db.session.commit()
        return {"turn_complete": True}


# -------------------------------------------------------------------- undo

def undo_last_action(game, state):
    last = (
        ScoreEvent.query.filter_by(game_id=game.id, reversed=False)
        .order_by(ScoreEvent.id.desc())
        .first()
    )
    if not last:
        return None

    last.reversed = True
    if last.team_id and last.points:
        team = last.team
        team.score = max(0, team.score - last.points)

    if last.question_id:
        q = Question.query.get(last.question_id)
        if q:
            q.status = "pending"
            if last.event_type == "lightning_correct":
                state.lightning_correct = max(0, state.lightning_correct - 1)
                state.lightning_points_earned = max(0, state.lightning_points_earned - last.points)
            if last.event_type in ("lightning_correct", "lightning_incorrect"):
                state.current_round_id = q.round_id
                state.lightning_team_id = last.team_id or state.lightning_team_id
                state.current_turn_team_id = state.lightning_team_id
            state.current_question_id = q.id
            state.question_phase = "active"
            _start_timer(state, q.round.effective_timer())

    db.session.commit()
    return last


# ------------------------------------------------------------- serializing

def serialize_state(game, state, include_answer):
    round_obj = state.current_round
    question = state.current_question
    teams_sorted = sorted(game.teams, key=lambda t: t.score, reverse=True)

    data = {
        "game_id": game.id,
        "game_name": game.name,
        "status": game.status,
        "phase": state.question_phase,
        "rounds": [
            {"id": r.id, "name": r.name, "type": r.type, "is_current": round_obj is not None and r.id == round_obj.id}
            for r in sorted(game.rounds, key=lambda x: x.order)
        ],
        "round": round_obj.to_dict() if round_obj else None,
        "question": (question.to_host_dict() if include_answer else question.to_public_dict())
        if question else None,
        "timer": {
            "duration": state.timer_duration,
            "remaining": compute_timer_remaining(state),
            "status": state.timer_status,
        },
        "teams": [t.to_dict() for t in teams_sorted],
        "current_turn_team_id": state.current_turn_team_id,
        "lightning": None,
    }

    if round_obj and round_obj.type == "lightning" and state.lightning_team_id:
        data["lightning"] = {
            "team": state.lightning_team.to_dict() if state.lightning_team else None,
            "correct": state.lightning_correct,
            "total": state.lightning_total,
            "points_earned": state.lightning_points_earned,
        }

    if include_answer and round_obj:
        data["round_questions"] = [
            {
                "id": q.id,
                "text": q.text[:80] + ("…" if len(q.text) > 80 else ""),
                "points": q.points,
                "status": q.status,
                "is_current": question is not None and q.id == question.id,
            }
            for q in sorted(round_obj.questions, key=lambda x: x.order)
        ]

    return data
