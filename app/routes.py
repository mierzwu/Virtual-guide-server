import json
import os
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import History
from app.vision import detect_landmarks, haversine_km
from app.wiki import get_wikipedia_info, get_nearby_places, search_by_labels, filter_labels

api_bp = Blueprint("api", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


@api_bp.before_request
def require_api_key():
    if request.endpoint == "api.health":
        return
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != current_app.config["SECRET_KEY"]:
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

    # Accept comma as decimal separator (e.g. "52,2297" → "52.2297")
    if latitude:
        latitude = latitude.replace(",", ".")
    if longitude:
        longitude = longitude.replace(",", ".")

    if not image or image.filename == "":
        return jsonify({"error": "Pole 'image' jest wymagane."}), 400
    if not _allowed_file(image.filename):
        return jsonify({"error": "Dozwolone rozszerzenia: png, jpg, jpeg, webp."}), 400

    safe_name = f"{uuid4().hex}_{secure_filename(image.filename)}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], safe_name)
    image.save(save_path)

    # --- Google Vision Landmark Detection ---
    with open(save_path, "rb") as f:
        image_bytes = f.read()

    try:
        vision_result = detect_landmarks(image_bytes, current_app.config["GOOGLE_VISION_API_KEY"])
    except (RuntimeError, Exception) as exc:
        print(f"[ERROR] Vision API: {exc}")
        return jsonify({"error": f"Vision API: {exc}"}), 502

    landmarks = vision_result["landmarks"]
    labels = vision_result["labels"]

    print(f"[VISION] {len(landmarks)} landmark(s): {[lm['name'] for lm in landmarks]}")
    print(f"[VISION] {len(labels)} label(s): {[lb['description'] for lb in labels]}")

    has_coords = latitude is not None and longitude is not None

    # Build debug log for frontend
    filtered = filter_labels(labels)
    debug_log = {
        "gps": {
            "latitude": float(latitude) if latitude else None,
            "longitude": float(longitude) if longitude else None,
            "available": has_coords,
        },
        "vision_labels": [lb["description"] for lb in labels],
        "filtered_labels": [lb["description"] for lb in filtered],
        "vision_landmarks": [lm["name"] for lm in landmarks],
    }

    if has_coords:
        user_lat = float(latitude)
        user_lon = float(longitude)

        for lm in landmarks:
            lm["distance_km"] = round(
                haversine_km(user_lat, user_lon, lm["latitude"], lm["longitude"]),
                3,
            )

        landmarks.sort(key=lambda lm: lm["distance_km"])

    # --- No landmarks found – try label-based fallback ---
    if not landmarks:
        wiki_from_labels = None
        if has_coords and labels:
            wiki_from_labels = search_by_labels(labels, float(latitude), float(longitude))
            if wiki_from_labels:
                print(f"[LABEL FALLBACK] confidence={wiki_from_labels.get('confidence')} "
                      f"matched={wiki_from_labels.get('matched_count')} labels "
                      f"-> {wiki_from_labels.get('title')}")

        entry = History(
            file_path=save_path,
            latitude=latitude,
            longitude=longitude,
            ai_title=wiki_from_labels["title"] if wiki_from_labels else None,
            ai_description=wiki_from_labels["description"] if wiki_from_labels else None,
            ai_links=wiki_from_labels["url"] if wiki_from_labels else None,
        )
        db.session.add(entry)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[DB ERROR] {e}")

        if wiki_from_labels:
            # Build nearby list from scored articles (excluding the winner), sorted by score
            nearby_scored = [
                s for s in wiki_from_labels.get("all_scored", [])
                if s["title"] != wiki_from_labels.get("title") and s["score"] > 0
            ]
            debug_log["matched_labels"] = wiki_from_labels.get("matched_labels", [])
            debug_log["scoring"] = wiki_from_labels.get("all_scored", [])
            debug_log["confidence"] = wiki_from_labels.get("confidence", 0)
            debug_log["winner"] = {
                "title": wiki_from_labels.get("title"),
                "score": wiki_from_labels.get("match_score"),
                "distance_m": wiki_from_labels.get("distance_m"),
                "distance_multiplier": wiki_from_labels.get("distance_multiplier"),
            }
            response_data = {
                "message": f"Dopasowano na podstawie etykiet i GPS (pewność: {wiki_from_labels.get('confidence', 0):.0%}).",
                "id": entry.id,
                "landmarks": [],
                "labels": labels,
                "wiki": wiki_from_labels,
                "nearby": nearby_scored,
                "debug_log": debug_log,
            }
            print(f"[RESPONSE] {json.dumps(response_data, indent=2, ensure_ascii=False, default=str)}")
            return jsonify(response_data), 200

        response_data = {
            "message": "Nie znaleziono obiektu, spróbuj zrobić lepsze zdjęcie.",
            "id": entry.id,
            "landmarks": [],
            "labels": labels,
            "wiki": None,
            "nearby": get_nearby_places(float(latitude), float(longitude)) if has_coords else [],
            "debug_log": debug_log,
        }
        print(f"[RESPONSE] {json.dumps(response_data, indent=2, ensure_ascii=False, default=str)}")
        return jsonify(response_data), 200

    best = landmarks[0]

    # --- Distance warning (> 300m) ---
    warning = None
    if has_coords and best.get("distance_km", 0) > 0.3:
        warning = "Ze względu twoją odległość do obiektu wynik wygląda podejrzanie."

    # --- Wikipedia info for the best landmark ---
    wiki_info = get_wikipedia_info(best["name"])
    print(f"[WIKI] {wiki_info.get('title')} -> {wiki_info.get('url')}")

    entry = History(
        file_path=save_path,
        latitude=latitude,
        longitude=longitude,
        ai_title=best["name"],
        ai_description=wiki_info["description"] if wiki_info else None,
        ai_links=wiki_info["url"] if wiki_info else None,
    )
    db.session.add(entry)
    db.session.commit()

    debug_log["matched_landmark"] = best["name"]

    response_data = {
        "message": "Zapisano",
        "id": entry.id,
        "landmarks": landmarks,
        "labels": labels,
        "wiki": wiki_info,
        "debug_log": debug_log,
    }

    if warning:
        response_data["warning"] = warning
        response_data["nearby"] = get_nearby_places(float(latitude), float(longitude)) if has_coords else []

    print(f"[RESPONSE] {json.dumps(response_data, indent=2, ensure_ascii=False, default=str)}")

    return jsonify(response_data), 201


@api_bp.get("/history")
def history():
    rows = History.query.order_by(History.created_at.desc()).all()
    return jsonify([
        {
            "id": r.id,
            "file_path": r.file_path,
            "latitude": float(r.latitude) if r.latitude is not None else None,
            "longitude": float(r.longitude) if r.longitude is not None else None,
            "created_at": r.created_at.isoformat(),
            "ai_title": r.ai_title,
            "ai_description": r.ai_description,
            "ai_links": r.ai_links,
        }
        for r in rows
    ])
