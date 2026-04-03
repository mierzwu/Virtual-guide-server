import base64
import io
import math
import time

import requests
from PIL import Image

VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"

MAX_VISION_BYTES = 4 * 1024 * 1024  # stay well under 10 MB API limit


def _compress_image(image_bytes: bytes, max_bytes: int = MAX_VISION_BYTES) -> bytes:
    """Resize / re-compress an image so its encoded size stays under *max_bytes*."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")  # drop alpha, ensure JPEG-safe

    quality = 85
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data

        # reduce quality first, then dimensions
        if quality > 30:
            quality -= 10
        else:
            w, h = img.size
            img = img.resize((w * 3 // 4, h * 3 // 4), Image.LANCZOS)
            quality = 85  # reset quality after shrink


def detect_landmarks(image_bytes: bytes, api_key: str) -> dict:
    """Send image to Google Vision Landmark + Label Detection REST API.

    Returns dict with keys:
        landmarks: list of landmark dicts
        labels: list of label dicts (description, score)
    """
    image_bytes = _compress_image(image_bytes)

    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(image_bytes).decode()},
                "features": [
                    {"type": "LANDMARK_DETECTION", "maxResults": 50},
                    {"type": "LABEL_DETECTION", "maxResults": 20},
                ],
            }
        ]
    }

    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.post(
                VISION_API_URL,
                params={"key": api_key},
                json=payload,
                timeout=(60, 120),  # (connect+send, read)
            )
            break
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            wait = 2 ** attempt
            print(f"[VISION] attempt {attempt + 1} failed: {exc}; retrying in {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Vision API unreachable after 3 attempts: {last_exc}")

    if resp.status_code != 200:
        raise RuntimeError(f"Vision API HTTP {resp.status_code}: {resp.text}")

    result = resp.json()
    first_response = result.get("responses", [{}])[0]

    if "error" in first_response:
        err = first_response["error"]
        raise RuntimeError(f"Vision API error {err.get('code')}: {err.get('message')}")

    # --- Landmarks ---
    annotations = first_response.get("landmarkAnnotations", [])
    landmarks = []
    for ann in annotations:
        for loc in ann.get("locations", []):
            lat_lng = loc.get("latLng", {})
            landmarks.append({
                "name": ann.get("description", ""),
                "confidence": ann.get("score", 0),
                "latitude": lat_lng.get("latitude", 0),
                "longitude": lat_lng.get("longitude", 0),
            })

    # --- Labels ---
    label_annotations = first_response.get("labelAnnotations", [])
    labels = [
        {
            "description": la.get("description", ""),
            "score": la.get("score", 0),
        }
        for la in label_annotations
    ]

    return {"landmarks": landmarks, "labels": labels}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in kilometres between two points (haversine formula)."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))