from sqlalchemy import func
from app.extensions import db


class History(db.Model):
    __tablename__ = "history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_path = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Numeric(10, 7), nullable=True)
    longitude = db.Column(db.Numeric(10, 7), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    ai_title = db.Column(db.String(255))
    ai_description = db.Column(db.Text)
    ai_links = db.Column(db.JSON)
