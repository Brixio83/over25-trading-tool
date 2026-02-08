import requests
from typing import Any, Dict, List, Optional, Tuple

BASE_URL = "https://api.the-odds-api.com/v4"


def get_odds_totals_v2(
    api_key: str,
    sport_key: str,
    regions: str = "eu",
    odds_format: str = "decimal",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Scarica quote mercato 'totals' (Over/Under) per sport_key.

    Ritorna SEMPRE:
      - events: lista eventi (anche vuota)
      - meta: debug dict (ok, status_code, message, url, count)
    """
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "totals",
        "oddsFormat": odds_format,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
    except Exception as e:
        return [], {
            "ok": False,
            "status_code": None,
            "message": f"Request error: {e}",
            "url": url,
            "sport_key": sport_key,
            "regions": regions,
            "count": 0,
        }

    try:
        data = r.json()
    except Exception:
        data = None

    if r.status_code != 200:
        msg = ""
        if isinstance(data, dict):
            msg = data.get("message", "")
        if not msg:
            msg = f"HTTP {r.status_code}"
        return [], {
            "ok": False,
            "status_code": r.status_code,
            "message": msg,
            "url": r.url,
            "sport_key": sport_key,
            "regions": regions,
            "count": 0,
        }

    if not isinstance(data, list):
        return [], {
            "ok": False,
            "status_code": r.status_code,
            "message": "Unexpected response format (not a list).",
            "url": r.url,
            "sport_key": sport_key,
            "regions": regions,
            "count": 0,
        }

    return data, {
        "ok": True,
        "status_code": r.status_code,
        "message": "OK",
        "url": r.url,
        "sport_key": sport_key,
        "regions": regions,
        "count": len(data),
    }


def extract_over25(event_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Ritorna Over 2.5 se presente:
    {"price": quota, "book": bookmaker}
    """
    for bookmaker in event_obj.get("bookmakers", []) or []:
        book = bookmaker.get("title", "")
        for market in bookmaker.get("markets", []) or []:
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []) or []:
                name = str(outcome.get("name", "")).lower()
                point = outcome.get("point", None)
                price = outcome.get("price", None)

                if name == "over" and point == 2.5 and price is not None:
                    return {"price": float(price), "book": book}

    return None
