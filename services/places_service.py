"""
Google Places API を用いた医療機関検索サービス
柏駅の緯度経度を Text Search で取得し、Nearby Search で病院・クリニックを検索
"""
import googlemaps


def get_kashiwa_station_coords(api_key: str) -> tuple[float, float]:
    """
    柏駅の緯度・経度を Text Search で取得
    Returns: (latitude, longitude)
    """
    gmaps = googlemaps.Client(key=api_key)
    result = gmaps.places(query="柏駅", language="ja", region="jp")
    if result.get("status") != "OK" or not result.get("results"):
        raise ValueError("柏駅の位置を取得できませんでした")
    location = result["results"][0]["geometry"]["location"]
    return (location["lat"], location["lng"])


def search_nearby_medical_facilities(
    api_key: str,
    lat: float,
    lng: float,
    radius_m: int = 3000,
    max_results: int = 10,
) -> list[dict]:
    """
    指定座標周辺の病院・クリニックを Nearby Search で取得
    doctor と hospital の両方を検索し、重複を除いて結合
    """
    gmaps = googlemaps.Client(key=api_key)
    location = f"{lat},{lng}"
    seen_place_ids: set[str] = set()
    facilities: list[dict] = []

    for place_type in ["doctor", "hospital"]:
        result = gmaps.places_nearby(
            location=location,
            radius=radius_m,
            type=place_type,
            language="ja",
        )
        if result.get("status") != "OK":
            continue
        for place in result.get("results", []):
            pid = place.get("place_id")
            if pid and pid not in seen_place_ids:
                seen_place_ids.add(pid)
                facility = _extract_facility_info(place, gmaps, api_key)
                if facility:
                    facilities.append(facility)
                if len(facilities) >= max_results:
                    break
        if len(facilities) >= max_results:
            break

    return facilities[:max_results]


def _extract_facility_info(
    place: dict,
    gmaps: googlemaps.Client,
    api_key: str,
) -> dict | None:
    """
    施設情報を抽出。Place Details で website, opening_hours を取得
    """
    place_id = place.get("place_id")
    if not place_id:
        return None

    # Place Details で website, opening_hours を取得（なければ nearby の基本情報を使用）
    result = dict(place)
    try:
        details = gmaps.place(
            place_id,
            fields="name,formatted_address,place_id,opening_hours,website",
            language="ja",
        )
        if details.get("result"):
            result.update(details["result"])
    except Exception:
        pass

    opening = result.get("opening_hours") or {}
    open_now = opening.get("open_now") if isinstance(opening, dict) else None

    return {
        "name": result.get("name", "名称不明"),
        "address": result.get("formatted_address") or result.get("vicinity", ""),
        "place_id": place_id,
        "open_now": open_now,
        "opening_hours": (
            opening.get("weekday_text", []) if isinstance(opening, dict) else []
        ),
        "website": result.get("website", ""),
    }


def get_medical_facilities_near_kashiwa(
    api_key: str,
    max_results: int = 10,
) -> list[dict]:
    """
    柏駅周辺の医療機関を取得（メインエントリ）
    """
    lat, lng = get_kashiwa_station_coords(api_key)
    return search_nearby_medical_facilities(
        api_key=api_key,
        lat=lat,
        lng=lng,
        radius_m=3000,
        max_results=max_results,
    )
