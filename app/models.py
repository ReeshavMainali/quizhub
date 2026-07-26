from datetime import datetime
from .extensions import db


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    default_timer = db.Column(db.Integer, nullable=False, default=30)
    status = db.Column(db.String(20), nullable=False, default="setup")  # setup, active, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teams = db.relationship("Team", backref="game", cascade="all, delete-orphan", order_by="Team.order")
    rounds = db.relationship("Round", backref="game", cascade="all, delete-orphan", order_by="Round.order")
    score_events = db.relationship("ScoreEvent", backref="game", cascade="all, delete-orphan")
    state = db.relationship("GameState", backref="game", uselist=False, cascade="all, delete-orphan")

    def to_summary(self):
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "team_count": len(self.teams),
            "round_count": len(self.rounds),
            "question_count": sum(len(r.questions) for r in self.rounds),
            "created_at": self.created_at.strftime("%d %b %Y"),
        }


TEAM_COLORS = [
    "#8CB0D1",  # slate blue (primary)
    "#D9B36C",  # amber
    "#8FBC9C",  # sage
    "#C97B7B",  # rose
    "#A797C9",  # muted violet
    "#7FBFB0",  # teal
    "#D19A8C",  # clay
    "#94A3B8",  # cool grey
]


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#8CB0D1")
    score = db.Column(db.Integer, nullable=False, default=0)
    order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "color": self.color, "score": self.score}


ROUND_TYPES = ("normal", "lightning", "av")


class Round(db.Model):
    __tablename__ = "rounds"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="normal")
    order = db.Column(db.Integer, nullable=False, default=0)
    timer_seconds = db.Column(db.Integer, nullable=True)  # None = use game default
    lightning_turn_size = db.Column(db.Integer, nullable=False, default=6)  # 5-10 questions per team turn

    questions = db.relationship(
        "Question", backref="round", cascade="all, delete-orphan", order_by="Question.order"
    )

    def effective_timer(self):
        if self.timer_seconds:
            return self.timer_seconds
        return self.game.default_timer

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "order": self.order,
            "timer_seconds": self.effective_timer(),
            "lightning_turn_size": self.lightning_turn_size,
            "question_count": len(self.questions),
        }


QUESTION_STATUSES = ("pending", "active", "resolved")


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    choices = db.Column(db.JSON, nullable=True)  # optional list of strings for multiple choice
    points = db.Column(db.Integer, nullable=False, default=10)
    order = db.Column(db.Integer, nullable=False, default=0)
    image_filename = db.Column(db.String(255), nullable=True)
    audio_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    used_in_lightning_turn = db.Column(db.Integer, nullable=True)  # groups lightning turns

    def to_public_dict(self):
        """Fields safe to send to the projector display before resolution (no answer)."""
        return {
            "id": self.id,
            "text": self.text,
            "choices": self.choices,
            "points": self.points,
            "image_url": f"/static/uploads/{self.image_filename}" if self.image_filename else None,
            "audio_url": f"/static/uploads/{self.audio_filename}" if self.audio_filename else None,
            "round_type": self.round.type,
        }

    def to_host_dict(self):
        d = self.to_public_dict()
        d["answer"] = self.answer
        return d


EVENT_TYPES = ("correct", "incorrect", "pass", "reveal", "lightning_correct", "lightning_incorrect")


class ScoreEvent(db.Model):
    __tablename__ = "score_events"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=True)
    event_type = db.Column(db.String(30), nullable=False)
    points = db.Column(db.Integer, nullable=False, default=0)
    reversed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    team = db.relationship("Team")


class GameState(db.Model):
    """Authoritative live state for a game's control/display sync. One row per game."""

    __tablename__ = "game_states"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, unique=True)

    current_round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=True)
    current_question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=True)
    current_turn_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)

    timer_duration = db.Column(db.Integer, nullable=True)
    timer_started_at = db.Column(db.DateTime, nullable=True)
    timer_status = db.Column(db.String(20), nullable=False, default="stopped")  # stopped, running, paused
    timer_remaining_at_pause = db.Column(db.Integer, nullable=True)

    question_phase = db.Column(db.String(20), nullable=False, default="idle")
    # idle, active, revealed

    lightning_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    lightning_correct = db.Column(db.Integer, nullable=False, default=0)
    lightning_total = db.Column(db.Integer, nullable=False, default=0)
    lightning_points_earned = db.Column(db.Integer, nullable=False, default=0)
    lightning_turn_number = db.Column(db.Integer, nullable=False, default=0)

    current_round = db.relationship("Round", foreign_keys=[current_round_id])
    current_question = db.relationship("Question", foreign_keys=[current_question_id])
    current_turn_team = db.relationship("Team", foreign_keys=[current_turn_team_id])
    lightning_team = db.relationship("Team", foreign_keys=[lightning_team_id])
