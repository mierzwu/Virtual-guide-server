import math

import requests

WIKIPEDIA_API_URL_PL = "https://pl.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_IMAGES_URL_PL = "https://pl.wikipedia.org/w/api.php"
WIKIPEDIA_API_URL_EN = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_IMAGES_URL_EN = "https://en.wikipedia.org/w/api.php"


def get_wikipedia_info(name: str) -> dict:
    """Fetch summary description and images from Wikipedia for a given landmark name.
    Tries Polish Wikipedia first, falls back to English.

    Returns dict with keys: title, description, thumbnail, image, url, images.
    """
    result = _fetch_info(name, WIKIPEDIA_API_URL_PL, WIKIPEDIA_IMAGES_URL_PL)
    if result["description"] is None:
        result = _fetch_info(name, WIKIPEDIA_API_URL_EN, WIKIPEDIA_IMAGES_URL_EN)
    return result


LANDMARK_KEYWORDS = {
    "building", "church", "cathedral", "castle", "palace",
    "monument", "tower", "bridge", "mosque", "temple", "museum", "statue",
    "fountain", "basilica", "chapel", "facade", "dome", "landmark",
    "historic", "heritage", "medieval", "gothic", "baroque", "renaissance",
    "synagogue", "monastery", "abbey", "fortification", "gate", "citadel",
    "shrine", "steeple", "spire", "column", "memorial", "ruins",
    "place of worship", "house", "estate", "mansion",
    "hall", "courthouse", "stately home", "tourist attraction",
    "skyscraper", "hotel", "amphitheatre", "arena", "stadium", "square",
    "plaza", "pier", "lighthouse", "windmill", "aqueduct", "arch",
    "obelisk", "mausoleum", "pyramid",
    "town square",
    "convent", "parish", "holy", "cross", "turret", "finial",
    "religious", "worship", "sacred", "site", "brick", "brickwork",
    "headquarters", "office", "school", "university", "library",
    "theater", "theatre", "opera", "cinema", "gallery",
}

BLACKLISTED_KEYWORDS = {
    "plant", "flower", "houseplant", "flowerpot", "tree", "grass", "leaf",
    "food", "dish", "meal", "fruit", "vegetable", "cuisine", "drink",
    "animal", "dog", "cat", "bird", "fish", "insect", "pet",
    "person", "people", "face", "hair", "smile", "selfie",
    "car", "vehicle", "bicycle", "motorcycle",
    "clothing", "fashion", "shoe", "hat", "shirt",
    "furniture", "table", "chair", "sofa", "bed", "desk",
    "electronics", "laptop", "phone", "computer", "screen",
    "sky", "cloud", "sun", "moon", "star", "night",
    "water", "sea", "ocean", "lake", "river", "beach",
    "mountain", "forest", "nature", "landscape", "garden",
    "book", "toy", "game", "sport", "ball",
    "wood", "metal", "plastic", "glass", "material",
    "art", "painting", "drawing", "photograph", "design",
    "text", "font", "logo", "sign", "poster",
    "interior", "flooring", "floor", "lighting", "curtain", "room",
    "stain", "linens", "hardwood", "window", "tablecloth", "laminate",
    "den", "lamp", "ceiling", "carpet", "rug", "tile", "wall",
    "roof", "door", "shelf", "cabinet", "kitchen", "bathroom",
    "property", "real estate", "construction", "structure",
}

# English → Polish translations for label matching in Polish Wikipedia articles
LABEL_TRANSLATIONS = {
    "building": "budynek",
    "church": "kościół",
    "cathedral": "katedra",
    "castle": "zamek",
    "palace": "pałac",
    "monument": "pomnik",
    "tower": "wieża",
    "bridge": "most",
    "mosque": "meczet",
    "temple": "świątynia",
    "museum": "muzeum",
    "statue": "posąg",
    "fountain": "fontanna",
    "basilica": "bazylika",
    "chapel": "kaplica",
    "dome": "kopuła",
    "landmark": "zabytek",
    "historic": "historyczny",
    "heritage": "dziedzictwo",
    "medieval": "średniowieczny",
    "gothic": "gotycki",
    "baroque": "barokowy",
    "renaissance": "renesansowy",
    "synagogue": "synagoga",
    "monastery": "klasztor",
    "abbey": "opactwo",
    "fortification": "fortyfikacja",
    "gate": "brama",
    "citadel": "cytadela",
    "shrine": "sanktuarium",
    "steeple": "wieżyczka",
    "spire": "iglica",
    "column": "kolumna",
    "memorial": "pomnik",
    "ruins": "ruiny",
    "place of worship": "miejsce kultu",
    "house": "dom",
    "estate": "posiadłość",
    "mansion": "dwór",
    "hall": "hala",
    "courthouse": "sąd",
    "stately home": "rezydencja",
    "tourist attraction": "atrakcja turystyczna",
    "skyscraper": "wieżowiec",
    "hotel": "hotel",
    "amphitheatre": "amfiteatr",
    "arena": "arena",
    "stadium": "stadion",
    "square": "plac",
    "plaza": "plac",
    "town square": "plac",
    "pier": "molo",
    "lighthouse": "latarnia morska",
    "windmill": "wiatrak",
    "aqueduct": "akwedukt",
    "arch": "łuk",
    "obelisk": "obelisk",
    "mausoleum": "mauzoleum",
    "pyramid": "piramida",
    "convent": "klasztor",
    "parish": "parafia",
    "holy": "święty",
    "cross": "krzyż",
    "turret": "wieżyczka",
    "religious": "religijny",
    "sacred": "sakralny",
    "site": "obiekt",
    "brick": "cegła",
    "brickwork": "ceglana",
    "headquarters": "siedziba",
    "office": "biuro",
    "school": "szkoła",
    "university": "uniwersytet",
    "library": "biblioteka",
    "theater": "teatr",
    "theatre": "teatr",
    "opera": "opera",
    "cinema": "kino",
    "gallery": "galeria",
}

def _matches_keywords(desc: str, keywords: set[str]) -> bool:
    """Check if description matches any keyword using word-level matching.

    For single-word keywords: checks if the keyword appears as a whole word in desc.
    For multi-word keywords: checks if the phrase is a substring of desc.
    This prevents 'cat' from matching 'cathedral', 'art' from matching 'turret', etc.
    """
    words = set(desc.split())
    for kw in keywords:
        if " " in kw:
            # Multi-word phrase: substring match
            if kw in desc:
                return True
        else:
            # Single word: must appear as a whole word
            if kw in words:
                return True
    return False


def filter_labels(labels: list[dict]) -> list[dict]:
    """Filter Vision API labels — keep only architecture/landmark/attraction related."""
    sorted_labels = sorted(labels, key=lambda l: l.get("score", 0), reverse=True)
    candidates = []
    for label in sorted_labels:
        desc = label["description"].lower()
        if _matches_keywords(desc, BLACKLISTED_KEYWORDS):
            continue
        if _matches_keywords(desc, LANDMARK_KEYWORDS):
            candidates.append(label)
    print(f"[LABEL FILTER] {len(candidates)}/{len(labels)} labels passed: "
          f"{[c['description'] for c in candidates]}")
    return candidates


def _score_article(title: str, text: str, labels: list[dict],
                   idf_weights: dict[str, float] | None = None) -> tuple[float, list[dict]]:
    """Score an article against filtered labels.

    For each label, searches for both English and Polish versions in:
      - the article TITLE (3x bonus if matched there)
      - the article body text (position bonus: earlier = more points)
    Labels are weighted by IDF — labels matching fewer articles are worth more.

    Returns (total_score, list of matched label details).
    """
    title_lower = title.lower()
    text_lower = text.lower()
    text_len = len(text_lower) or 1
    total = 0.0
    matches = []
    for lb in labels:
        desc = lb["description"].lower()
        pl = LABEL_TRANSLATIONS.get(desc)

        # Check title match (EN or PL)
        in_title = (desc in title_lower) or (pl is not None and pl in title_lower)

        # Search for English version in body
        pos_en = text_lower.find(desc)
        # Search for Polish translation in body
        pos_pl = text_lower.find(pl) if pl else -1

        # Pick the best (earliest) match
        positions = [p for p in (pos_en, pos_pl) if p != -1]
        if not positions and not in_title:
            continue

        base = lb.get("score", 0)

        if positions:
            pos = min(positions)
            position_bonus = (1.0 - pos / text_len) * base
        else:
            pos = 0
            position_bonus = base  # full position bonus for title-only match

        points = base + position_bonus

        # Title match: 3x multiplier
        if in_title:
            points *= 3.0

        # IDF weighting: labels matching fewer articles are worth more
        idf = idf_weights.get(desc, 1.0) if idf_weights else 1.0
        points *= idf

        total += points
        matches.append({
            "label": lb["description"],
            "vision_score": lb.get("score", 0),
            "position": pos,
            "in_title": in_title,
            "idf": round(idf, 2),
            "points": round(points, 4),
        })
    return total, matches


def search_by_labels(labels: list[dict], lat: float, lon: float) -> dict | None:
    """Find the most probable landmark near GPS coordinates using Vision labels.

    Pipeline:
      1. Filter labels — keep only architecture/landmark/attraction related
      2. Geosearch Wikipedia articles within 300m of (lat, lon)
      3. Score each article: label matches + position bonus (earlier = more points)
      4. Return best-scoring article with confidence

    Returns dict with wiki info + scoring, or None.
    """
    candidates = filter_labels(labels)
    if not candidates:
        return None

    # Max possible score = 2 * sum(all label scores)  (base + full position bonus)
    max_possible = 2.0 * sum(lb.get("score", 0) for lb in candidates)

    for api_url, images_url in [
        (WIKIPEDIA_API_URL_PL, WIKIPEDIA_IMAGES_URL_PL),
        (WIKIPEDIA_API_URL_EN, WIKIPEDIA_IMAGES_URL_EN),
    ]:
        # 1. Geosearch — nearby articles within 300m
        resp = requests.get(
            images_url,
            params={
                "action": "query",
                "list": "geosearch",
                "gscoord": f"{lat}|{lon}",
                "gsradius": 300,
                "gslimit": 20,
                "format": "json",
            },
            headers={"User-Agent": "VirtualGuideServer/1.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            continue

        places = resp.json().get("query", {}).get("geosearch", [])
        if not places:
            continue

        # 2. Fetch full extracts + categories for all nearby pages
        page_ids = [str(p["pageid"]) for p in places]
        detail_resp = requests.get(
            images_url,
            params={
                "action": "query",
                "pageids": "|".join(page_ids),
                "prop": "categories|extracts",
                "explaintext": True,
                "exlimit": len(page_ids),
                "exchars": 5000,
                "cllimit": "max",
                "format": "json",
            },
            headers={"User-Agent": "VirtualGuideServer/1.0"},
            timeout=15,
        )
        if detail_resp.status_code != 200:
            continue

        pages_data = detail_resp.json().get("query", {}).get("pages", {})

        # 3. Filter: only keep articles about physical structures/landmarks
        #    Skip parishes, dioceses, administrative units, people, events, etc.
        WIKI_BUILDING_KEYWORDS = {
            # Polish
            "kościół", "kościoły", "bazylika", "katedra", "zamek", "zamki",
            "pałac", "pałace", "pomnik", "pomniki", "most", "mosty",
            "wieża", "wieże", "muzeum", "muzea", "budynek", "budynki",
            "zabytek", "zabytki" "fortyfikacja",
            "brama", "bramy", "ratusz", "ratusze", "dworzec",
            "synagoga", "meczet", "klasztor", "opactwo", "kaplica",
            "stadion", "fontanna", "latarnia", "wiatrak", "amfiteatr",
            "atrakcja", "obiekt", "budowla", "gmach",
            # English
            "church", "cathedral", "castle", "palace", "monument",
            "bridge", "tower", "museum", "building", "landmark",
            "heritage", "historic", "fortification", "basilica",
            "chapel", "mosque", "temple", "synagogue", "monastery",
            "abbey", "stadium", "fountain", "lighthouse",
            "attraction", "structure",
        }
        WIKI_SKIP_KEYWORDS = {
            # Polish
            "parafia", "parafie", "diecezja", "dekanat", "archidiecezja",
            "gmina", "powiat", "województwo", "sołectwo",
            "urodzeni", "zmarli", "biskupi", "duchowni",
            "organizacja", "stowarzyszenie", "partia",
            # English
            "parish", "diocese", "archdiocese", "deanery",
            "municipality", "county", "voivodeship",
            "born in", "deaths in", "bishops", "clergy",
            "organization", "association", "political party",
        }

        # 4. Score each article (only buildings/landmarks)
        # First pass: check which labels match which articles (for IDF)
        article_data = []
        for place in places:
            pid = str(place["pageid"])
            page = pages_data.get(pid, {})
            title = page.get("title", place.get("title", ""))
            cats = " ".join(c.get("title", "").lower() for c in page.get("categories", []))
            extract = page.get("extract") or ""

            # Filter: skip non-building articles
            searchable = f"{title.lower()} {cats}"
            if any(kw in searchable for kw in WIKI_SKIP_KEYWORDS):
                if not any(kw in searchable for kw in WIKI_BUILDING_KEYWORDS):
                    print(f"  [SKIP] {title} — not a building/landmark")
                    continue

            body_text = f"{cats} {extract}"
            article_data.append((place, title, body_text))

        # Compute IDF: labels matching fewer articles are worth more
        num_articles = len(article_data) or 1
        label_match_count: dict[str, int] = {}
        for _place, _title, _body in article_data:
            combined = f"{_title.lower()} {_body.lower()}"
            for lb in candidates:
                desc = lb["description"].lower()
                pl = LABEL_TRANSLATIONS.get(desc)
                if desc in combined or (pl and pl in combined):
                    label_match_count[desc] = label_match_count.get(desc, 0) + 1

        # IDF = log(N / match_count) + 1  (smoothed, min 1.0)
        idf_weights = {}
        for desc, count in label_match_count.items():
            idf_weights[desc] = math.log(num_articles / count) + 1.0
        # Labels not found in any article get weight 1.0 (neutral)

        print(f"  [IDF] {num_articles} articles, label uniqueness:")
        for desc, idf in sorted(idf_weights.items(), key=lambda x: x[1], reverse=True)[:8]:
            cnt = label_match_count.get(desc, 0)
            print(f"    {desc}: matches {cnt}/{num_articles} articles → idf={idf:.2f}")

        # Second pass: score each article with IDF weights
        scored = []
        for place, title, body_text in article_data:
            pid = str(place["pageid"])

            total_score, matched = _score_article(title, body_text, candidates, idf_weights)

            dist = place.get("dist", 0)
            # Exponential distance decay — very strong proximity advantage
            # At 0m → ×6.0, at 63m → ×3.7, at 150m → ×1.7, at 244m → ×1.1, at 300m → ×1.0
            distance_multiplier = 1.0 + 5.0 * math.exp(-dist / 80)

            # Base presence score: every building gets 1.0 point just for being nearby
            # This ensures that when labels don't match any article,
            # the closest building still wins via distance_multiplier
            presence_score = 1.0
            final_score = (total_score + presence_score) * distance_multiplier

            scored.append({
                "title": title,
                "pageid": pid,
                "score": round(final_score, 4),
                "label_score": round(total_score, 4),
                "distance_multiplier": round(distance_multiplier, 2),
                "matched_labels": matched,
                "matched_count": len(matched),
                "distance_m": dist,
            })

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)

        print(f"[SCORING] {len(scored)} articles scored:")
        for s in scored[:5]:
            print(f"  {s['title']}: score={s['score']}, "
                  f"labels={s['matched_count']}, dist={s['distance_m']}m, "
                  f"dist_mult=×{s['distance_multiplier']}")

        # Pick the best
        best = scored[0] if scored else None
        if not best or best["score"] == 0:
            continue

        # Fetch thumbnails + URLs for all scored articles (for nearby list)
        scored_pids = [s["pageid"] for s in scored if s["score"] > 0]
        if scored_pids:
            thumb_resp = requests.get(
                images_url,
                params={
                    "action": "query",
                    "pageids": "|".join(scored_pids),
                    "prop": "pageimages|info",
                    "pithumbsize": 300,
                    "inprop": "url",
                    "format": "json",
                },
                headers={"User-Agent": "VirtualGuideServer/1.0"},
                timeout=15,
            )
            thumbnails = {}
            page_urls = {}
            if thumb_resp.status_code == 200:
                tp = thumb_resp.json().get("query", {}).get("pages", {})
                for pid, page in tp.items():
                    thumbnails[pid] = page.get("thumbnail", {}).get("source")
                    page_urls[pid] = page.get("fullurl")
        else:
            thumbnails = {}
            page_urls = {}

        # Confidence: ratio of best score to second-best (if exists), capped at 1.0
        if len(scored) > 1 and scored[1]["score"] > 0:
            confidence = round(min(best["score"] / (best["score"] + scored[1]["score"]), 1.0), 4)
        else:
            confidence = 1.0 if best["score"] > 0 else 0

        # 4. Fetch full wiki info for the winner
        wiki = _fetch_info(best["title"], api_url, images_url)
        if wiki and wiki.get("description"):
            wiki["confidence"] = confidence
            wiki["match_score"] = best["score"]
            wiki["label_score"] = best["label_score"]
            wiki["distance_multiplier"] = best["distance_multiplier"]
            wiki["matched_labels"] = best["matched_labels"]
            wiki["matched_count"] = best["matched_count"]
            wiki["distance_m"] = best["distance_m"]
            wiki["all_scored"] = [
                {
                    "title": s["title"],
                    "score": s["score"],
                    "label_score": s["label_score"],
                    "distance_multiplier": s["distance_multiplier"],
                    "matched_count": s["matched_count"],
                    "distance_m": s["distance_m"],
                    "thumbnail": thumbnails.get(s["pageid"]),
                    "url": page_urls.get(s["pageid"]),
                }
                for s in scored if s["score"] > 0
            ]
            return wiki

    return None


def _fetch_long_extract(title: str, images_url: str, chars: int = 3000) -> str | None:
    """Fetch a longer extract from Wikipedia action API (up to `chars` characters)."""
    resp = requests.get(
        images_url,
        params={
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "exchars": chars,
            "explaintext": True,
            "format": "json",
        },
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )
    if resp.status_code != 200:
        return None
    pages = resp.json().get("query", {}).get("pages", {})
    for page in pages.values():
        extract = page.get("extract")
        if extract:
            return extract
    return None


def _fetch_info(name: str, api_url: str, images_url: str) -> dict:
    """Fetch summary and images from a specific Wikipedia language edition."""
    # 1. Get page summary (extract + main image)
    resp = requests.get(
        f"{api_url}/{requests.utils.quote(name)}",
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    if resp.status_code == 404:
        return _search_and_fetch(name, api_url, images_url)

    if resp.status_code != 200:
        return {"title": name, "description": None, "thumbnail": None, "image": None, "url": None, "images": []}

    data = resp.json()
    page_title = data.get("title", name)

    # Fetch longer extract via action API
    long_extract = _fetch_long_extract(page_title, images_url)

    result = {
        "title": page_title,
        "description": long_extract or data.get("extract", None),
        "thumbnail": data.get("thumbnail", {}).get("source"),
        "image": data.get("originalimage", {}).get("source"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        "images": [],
    }

    if page_title:
        result["images"] = _fetch_page_images(page_title, images_url)

    return result


def _search_and_fetch(name: str, api_url: str, images_url: str) -> dict:
    """Search Wikipedia for the name and fetch the best match."""
    resp = requests.get(
        images_url,
        params={
            "action": "query",
            "list": "search",
            "srsearch": name,
            "srlimit": 1,
            "format": "json",
        },
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    empty = {"title": name, "description": None, "thumbnail": None, "image": None, "url": None, "images": []}

    if resp.status_code != 200:
        return empty

    results = resp.json().get("query", {}).get("search", [])
    if not results:
        return empty

    found_title = results[0]["title"]

    # Fetch summary for the found page
    summary_resp = requests.get(
        f"{api_url}/{requests.utils.quote(found_title)}",
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    if summary_resp.status_code != 200:
        return empty

    data = summary_resp.json()
    page_title = data.get("title", found_title)
    long_extract = _fetch_long_extract(page_title, images_url)
    return {
        "title": page_title,
        "description": long_extract or data.get("extract", None),
        "thumbnail": data.get("thumbnail", {}).get("source"),
        "image": data.get("originalimage", {}).get("source"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        "images": _fetch_page_images(page_title, images_url),
    }


def _fetch_page_images(title: str, images_url: str) -> list[str]:
    """Fetch image URLs from a Wikipedia page."""
    resp = requests.get(
        images_url,
        params={
            "action": "query",
            "titles": title,
            "prop": "images",
            "imlimit": 20,
            "format": "json",
        },
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    if resp.status_code != 200:
        return []

    pages = resp.json().get("query", {}).get("pages", {})
    image_titles = []
    for page in pages.values():
        for img in page.get("images", []):
            img_title = img.get("title", "")
            # Skip icons, logos, commons metadata files
            if any(skip in img_title.lower() for skip in (".svg", "icon", "logo", "commons-logo", "flag of")):
                continue
            image_titles.append(img_title)

    if not image_titles:
        return []

    # Resolve image titles to actual URLs
    resp = requests.get(
        images_url,
        params={
            "action": "query",
            "titles": "|".join(image_titles[:10]),
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        },
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    if resp.status_code != 200:
        return []

    urls = []
    pages = resp.json().get("query", {}).get("pages", {})
    for page in pages.values():
        for info in page.get("imageinfo", []):
            url = info.get("url")
            if url:
                urls.append(url)

    return urls


def get_nearby_places(lat: float, lon: float, radius_m: int = 300, limit: int = 20) -> list[dict]:
    """Fetch nearby places from Wikipedia geosearch API.
    Tries Polish Wikipedia first, falls back to English.

    Returns list of dicts with keys: title, thumbnail, url, distance_m.
    """
    result = _fetch_nearby(lat, lon, radius_m, limit, WIKIPEDIA_IMAGES_URL_PL)
    if not result:
        result = _fetch_nearby(lat, lon, radius_m, limit, WIKIPEDIA_IMAGES_URL_EN)
    return result


def _fetch_nearby(lat: float, lon: float, radius_m: int, limit: int, images_url: str) -> list[dict]:
    """Fetch nearby landmarks/attractions from a specific Wikipedia language edition.
    Only returns results that have a thumbnail image.
    """
    # 1. Geosearch for nearby articles (landmarks category)
    resp = requests.get(
        images_url,
        params={
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": radius_m,
            "gslimit": limit,
            "format": "json",
        },
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    if resp.status_code != 200:
        return []

    places = resp.json().get("query", {}).get("geosearch", [])
    if not places:
        return []

    # 2. Fetch thumbnails, categories and info for all found pages
    page_ids = [str(p["pageid"]) for p in places]
    thumb_resp = requests.get(
        images_url,
        params={
            "action": "query",
            "pageids": "|".join(page_ids),
            "prop": "pageimages|info|categories",
            "pithumbsize": 300,
            "inprop": "url",
            "cllimit": "max",
            "format": "json",
        },
        headers={"User-Agent": "VirtualGuideServer/1.0"},
        timeout=15,
    )

    thumbnails = {}
    urls = {}
    is_landmark = {}
    if thumb_resp.status_code == 200:
        pages = thumb_resp.json().get("query", {}).get("pages", {})
        for pid, page in pages.items():
            thumbnails[int(pid)] = page.get("thumbnail", {}).get("source")
            urls[int(pid)] = page.get("fullurl")
            # Check if page belongs to landmark/attraction categories
            cats = " ".join(
                c.get("title", "").lower() for c in page.get("categories", [])
            )
            landmark_keywords = (
                "zabyt", "atrakcj", "architektur", "kości", "pałac", "zamek",
                "pomnik", "monument", "landmark", "heritage", "church",
                "castle", "palace", "museum", "cathedral", "temple",
                "bridge", "tower", "fountain", "statue", "budow",
                "most", "wież", "muzeum", "katedra", "świątyni",
                "kaplic", "ratusz", "brama",
            )
            is_landmark[int(pid)] = any(kw in cats for kw in landmark_keywords)

    result = []
    for place in places:
        pid = place["pageid"]
        thumb = thumbnails.get(pid)
        # Only include results with a thumbnail that are landmarks/attractions
        # If no categories found (is_landmark not set), include if has thumbnail
        if not thumb:
            continue
        if pid in is_landmark and not is_landmark[pid]:
            continue
        result.append({
            "title": place["title"],
            "thumbnail": thumb,
            "url": urls.get(pid),
            "distance_m": place.get("dist", 0),
        })

    result.sort(key=lambda p: p["distance_m"])
    return result
