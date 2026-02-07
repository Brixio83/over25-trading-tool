import requests


def get_odds_totals(api_key, sport_key="soccer_italy_serie_a", regions="eu"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "totals",
        "oddsFormat": "decimal"
    }

    r = requests.get(url, params=params)
    if r.status_code != 200:
        return []

    return r.json()


def build_event_list(payload):
    labels = []
    obj_map = {}

    for ev in payload:
        label = f"{ev['home_team']} vs {ev['away_team']}"
        labels.append(label)
        obj_map[label] = ev

    return labels, obj_map


def extract_over25(event_obj):
    """
    Ritorna Over 2.5 se presente:
    {
      "price": quota,
      "book": bookmaker
    }
    """
    for bookmaker in event_obj.get("bookmakers", []):
        book = bookmaker.get("title", "")
        for market in bookmaker.get("markets", []):
            if market.get("key") == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome["name"].lower() == "over" and outcome["point"] == 2.5:
                        return {
                            "price": outcome["price"],
                            "book": book
                        }
    return None
