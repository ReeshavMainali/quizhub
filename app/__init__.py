import os
from flask import Flask
from .extensions import db, socketio


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)
    upload_dir = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    app.config.update(
        SECRET_KEY=os.environ.get("QUIZHUB_SECRET_KEY", "dev-key-change-me"),
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(app.instance_path, 'quizhub.db')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=upload_dir,
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,  # 25MB cap on uploads (images/audio for AV rounds)
    )

    db.init_app(app)
    socketio.init_app(app)

    from . import models  # noqa: F401  (ensure models are registered before create_all)

    with app.app_context():
        db.create_all()

    from .routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    from . import sockets  # noqa: F401  (registers socketio event handlers)

    return app
