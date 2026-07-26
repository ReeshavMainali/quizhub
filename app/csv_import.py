import csv
import io
from .extensions import db
from .models import Round, Question, ROUND_TYPES

REQUIRED_COLUMNS = {"round_name", "round_type", "question", "answer"}
OPTIONAL_COLUMNS = {"choice_a", "choice_b", "choice_c", "choice_d", "points"}


class CsvImportError(Exception):
    pass


def parse_and_import(game, file_stream):
    """Parses an uploaded CSV file and creates rounds/questions on the given game.

    Expected columns (header row required):
      round_name, round_type (normal|lightning|av), question, answer,
      choice_a, choice_b, choice_c, choice_d (optional, for multiple choice),
      points (optional, defaults to 10)

    Rows are grouped into rounds by round_name. A round is created the first
    time its name is seen; round_type is taken from that first row.
    Media (images/audio) for AV rounds is attached afterwards via the UI.
    """
    raw = file_stream.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))

    if reader.fieldnames is None:
        raise CsvImportError("The CSV file appears to be empty.")

    header = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - header
    if missing:
        raise CsvImportError(
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            f"Required columns are: {', '.join(sorted(REQUIRED_COLUMNS))}."
        )

    rounds_by_name = {r.name.strip().lower(): r for r in game.rounds}
    next_round_order = (max((r.order for r in game.rounds), default=-1)) + 1
    questions_created = 0
    rounds_created = 0

    for line_num, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}

        round_name = row.get("round_name")
        round_type = row.get("round_type", "normal").lower()
        question_text = row.get("question")
        answer_text = row.get("answer")

        if not round_name or not question_text or not answer_text:
            raise CsvImportError(
                f"Row {line_num}: round_name, question, and answer cannot be blank."
            )
        if round_type not in ROUND_TYPES:
            raise CsvImportError(
                f"Row {line_num}: round_type '{round_type}' is invalid. "
                f"Must be one of: {', '.join(ROUND_TYPES)}."
            )

        key = round_name.lower()
        if key not in rounds_by_name:
            new_round = Round(
                game_id=game.id,
                name=round_name,
                type=round_type,
                order=next_round_order,
            )
            next_round_order += 1
            db.session.add(new_round)
            db.session.flush()  # assign id
            rounds_by_name[key] = new_round
            rounds_created += 1

        target_round = rounds_by_name[key]

        choices = [row.get(c) for c in ("choice_a", "choice_b", "choice_c", "choice_d")]
        choices = [c for c in choices if c]
        choices = choices or None

        try:
            points = int(row["points"]) if row.get("points") else 10
        except ValueError:
            raise CsvImportError(f"Row {line_num}: points must be a whole number.")

        next_q_order = len(target_round.questions)
        question = Question(
            round_id=target_round.id,
            text=question_text,
            answer=answer_text,
            choices=choices,
            points=points,
            order=next_q_order,
        )
        target_round.questions.append(question)
        questions_created += 1

    db.session.commit()
    return {"rounds_created": rounds_created, "questions_created": questions_created}
