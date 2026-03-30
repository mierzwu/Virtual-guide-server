import os

from flask import Flask
from app.extensions import db
from config import Config


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)

    from app.routes import api_bp
    app.register_blueprint(api_bp)

    return app
