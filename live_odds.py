import requests

BASE_URL = "https://api.the-odds-api.com/v4"


def get_odds_totals(api_key, sport_key, regions="eu"):
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "totals",
        "oddsFormat": "decimal",
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def extract_over25(event_obj):
    for bookmaker in event_obj.get("bookmakers", []):
        book = bookmaker.get("title", "")
        for market in bookmaker.get("markets", []):
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []):
                if (
                    outcome.get("name", "").lower() == "over"
                    and outcome.get("point") == 2.5
                ):
                    return {
                        "price": float(outcome.get("price")),
                        "book": book
                    }
    return None
