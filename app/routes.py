import os
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import History

api_bp = Blueprint("api", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


@api_bp.before_request
def require_api_key():
    if request.endpoint == "api.health":
        return
    print(f"[AUTH] Headers: {dict(request.headers)}")
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != current_app.config["SECRET_KEY"]:
        print(f"[AUTH] REJECTED - got key: '{api_key}', expected: '{current_app.config['SECRET_KEY']}'")
        return jsonify({"error": "Brak lub nieprawidłowy klucz API."}), 401


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.post("/guide")
def guide():
    image = request.files.get("image")
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")

    if not image or image.filename == "":
        return jsonify({"error": "Pole 'image' jest wymagane."}), 400
    if not _allowed_file(image.filename):
        return jsonify({"error": "Dozwolone rozszerzenia: png, jpg, jpeg, webp."}), 400
    if latitude is None or longitude is None:
        return jsonify({"error": "Pola 'latitude' i 'longitude' są wymagane."}), 400

    safe_name = f"{uuid4().hex}_{secure_filename(image.filename)}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], safe_name)
    image.save(save_path)

    entry = History(
        file_path=save_path,
        latitude=latitude,
        longitude=longitude,
        ai_title=request.form.get("ai_title"),
        ai_description=request.form.get("ai_description"),
        ai_links=request.form.getlist("ai_links") or None,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({"message": "Zapisano", "id": entry.id}), 201


@api_bp.get("/history")
def history():
    rows = History.query.order_by(History.created_at.desc()).all()
    return jsonify([
        {
            "id": r.id,
            "file_path": r.file_path,
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
            "created_at": r.created_at.isoformat(),
            "ai_title": r.ai_title,
            "ai_description": r.ai_description,
            "ai_links": r.ai_links,
        }
        for r in rows
    ])
