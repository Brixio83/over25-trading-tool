from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

# =========================================================
# CONFIG
# =========================================================

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"

DEFAULT_LEAGUES: Dict[str, int] = {
    "Serie A (ITA)": 135,
    "Serie B (ITA)": 136,
    "Premier League (ENG)": 39,
    "LaLiga (ESP)": 140,
    "Bundesliga (GER)": 78,
    "Ligue 1 (FRA)": 61,
    "Eredivisie (NED)": 88,
    "Primeira Liga (POR)": 94,
    "Champions League": 2,
    "Europa League": 3,
    "Conference League": 848,
}

ODDS_SPORT_KEYS: Dict[int, str] = {
    135: "soccer_italy_serie_a",
    136: "soccer_italy_serie_b",
    39: "soccer_epl",
    140: "soccer_spain_la_liga",
    78: "soccer_germany_bundesliga",
    61: "soccer_france_ligue_one",
    88: "soccer_netherlands_eredivisie",
    94: "soccer_portugal_primeira_liga",
    2: "soccer_uefa_champs_league",
    3: "soccer_uefa_europa_league",
    848: "soccer_uefa_europa_conference_league",
}

PREFERRED_BOOKMAKERS = [
    "netbet",
    "bet365",
    "bwin",
    "unibet",
    "william hill",
    "pinnacle",
    "betfair",
    "1xbet",
    "marathonbet",
]

# =========================================================
# UTILS
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def season_for_date(dt: datetime) -> int:
    return dt.year if dt.month >= 7 else dt.year - 1


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("’", "'")
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = re.sub(r"\b(fc|cf|ac|afc|calcio|club|football club|sv|sc|ss|ssc)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    aliases = {
        "inter milan": "inter",
        "ac milan": "milan",
        "man city": "manchester city",
        "man utd": "manchester united",
        "st pauli": "fc st pauli",
        "bayern munich": "bayern munchen",
        "psg": "paris saint germain",
    }
    return aliases.get(s, s)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def parse_match_input(text: str) -> Optional[Tuple[str, str]]:
    if not text or not text.strip():
        return None
    t = text.strip()
    t = re.sub(r"\s+vs\s+", " - ", t, flags=re.IGNORECASE)
    if "-" in t:
        parts = [p.strip() for p in t.split("-") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None


def api_football_headers(api_key: str) -> Dict[str, str]:
    return {"x-apisports-key": api_key}


def safe_json_get(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"errors": {"json": "Invalid JSON"}, "raw": r.text}
    data["_http_status"] = r.status_code
    data["_url"] = r.url
    return data


# =========================================================
# API-FOOTBALL
# =========================================================

@st.cache_data(ttl=60 * 30, show_spinner=False)
def search_team(api_key: str, query: str) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/teams"
    data = safe_json_get(url, api_football_headers(api_key), {"search": query})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_team_last_fixtures(api_key: str, team_id: int, season: int, last: int = 10) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures"
    data = safe_json_get(url, api_football_headers(api_key), {"team": team_id, "season": season, "last": last})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_team_next_fixtures(api_key: str, team_id: int, season: int, nxt: int = 25) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures"
    data = safe_json_get(url, api_football_headers(api_key), {"team": team_id, "season": season, "next": nxt})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_fixtures_in_range(
    api_key: str,
    team_id: int,
    from_date: datetime,
    to_date: datetime,
    season: int,
    league_id: Optional[int] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures"
    params: Dict[str, Any] = {
        "team": team_id,
        "season": season,
        "from": from_date.date().isoformat(),
        "to": to_date.date().isoformat(),
    }
    if league_id:
        params["league"] = league_id
    data = safe_json_get(url, api_football_headers(api_key), params)
    return (data.get("response", []) or [])[:limit]


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_injuries(api_key: str, team_id: int, season: int, league_id: Optional[int]) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/injuries"
    params: Dict[str, Any] = {"team": team_id, "season": season}
    if league_id:
        params["league"] = league_id
    data = safe_json_get(url, api_football_headers(api_key), params)
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 10, show_spinner=False)
def get_fixtures_by_date_and_league(api_key: str, day: str, league_id: int) -> List[Dict[str, Any]]:
    try:
        dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        season = season_for_date(dt)
    except Exception:
        season = season_for_date(now_utc())

    url = f"{API_FOOTBALL_BASE}/fixtures"
    params = {"date": day, "league": league_id, "season": season}
    data = safe_json_get(url, api_football_headers(api_key), params)
    return data.get("response", []) or []


def fixture_match_teams(fx: Dict[str, Any], a_id: int, b_id: int) -> bool:
    teams = fx.get("teams", {}) or {}
    home = (teams.get("home", {}) or {}).get("id")
    away = (teams.get("away", {}) or {}).get("id")
    return (home == a_id and away == b_id) or (home == b_id and away == a_id)


@dataclass
class FixturePick:
    fixture: Optional[Dict[str, Any]]
    message: str
    season: int


def find_fixture_smart(
    api_key: str,
    team_a_id: int,
    team_b_id: int,
    league_id: Optional[int],
) -> FixturePick:
    dt = now_utc()
    season = season_for_date(dt)

    from_dt = dt - timedelta(days=30)
    to_dt = dt + timedelta(days=90)

    fx_range = get_fixtures_in_range(api_key, team_a_id, from_dt, to_dt, season, league_id=league_id)
    for fx in fx_range:
        if fixture_match_teams(fx, team_a_id, team_b_id):
            return FixturePick(fixture=fx, message="Fixture trovata nel range (-30/+90 giorni).", season=season)

    fx_next_a = get_team_next_fixtures(api_key, team_a_id, season, nxt=25)
    for fx in fx_next_a:
        if league_id and (fx.get("league", {}) or {}).get("id") != league_id:
            continue
        if fixture_match_teams(fx, team_a_id, team_b_id):
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT Team A.", season=season)

    fx_next_b = get_team_next_fixtures(api_key, team_b_id, season, nxt=25)
    for fx in fx_next_b:
        if league_id and (fx.get("league", {}) or {}).get("id") != league_id:
            continue
        if fixture_match_teams(fx, team_a_id, team_b_id):
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT Team B.", season=season)

    return FixturePick(
        fixture=None,
        message="Fixture non trovata. Analisi in fallback sugli ultimi match.",
        season=season,
    )


# =========================================================
# THE ODDS API
# =========================================================

@st.cache_data(ttl=60 * 5, show_spinner=False)
def get_the_odds_api_events(
    odds_api_key: str,
    sport_key: str,
    regions: str = "eu,uk",
    markets: str = "h2h",
    odds_format: str = "decimal",
    date_format: str = "iso",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    url = f"{THE_ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": odds_api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
        "dateFormat": date_format,
    }

    debug = {
        "url": url,
        "params": params.copy(),
        "status_code": None,
        "text_preview": "",
        "count": 0,
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        debug["status_code"] = r.status_code
        debug["text_preview"] = r.text[:500]

        if r.status_code != 200:
            return [], debug

        data = r.json()
        if not isinstance(data, list):
            return [], debug

        debug["count"] = len(data)
        return data, debug
    except Exception as e:
        debug["text_preview"] = str(e)
        return [], debug


def pick_preferred_bookmaker(bookmakers: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not bookmakers:
        return None, "Nessun bookmaker"

    for pref in PREFERRED_BOOKMAKERS:
        for b in bookmakers:
            title = (b.get("title") or "").strip().lower()
            key = (b.get("key") or "").strip().lower()
            if pref in title or pref in key:
                return b, b.get("title") or b.get("key") or "Bookmaker"

    b = bookmakers[0]
    return b, b.get("title") or b.get("key") or "Bookmaker"


def extract_odds_from_the_odds_event(event: Dict[str, Any]) -> Tuple[Dict[str, float], str]:
    bookmakers = event.get("bookmakers", []) or []
    bookmaker, bookmaker_name = pick_preferred_bookmaker(bookmakers)
    if not bookmaker:
        return {}, "Nessun bookmaker"

    odds_map: Dict[str, float] = {}

    for market in bookmaker.get("markets", []) or []:
        mkey = (market.get("key") or "").strip().lower()

        if mkey == "h2h":
            for o in market.get("outcomes", []) or []:
                name = norm_text(o.get("name", ""))
                price = o.get("price")
                try:
                    price = float(price)
                except Exception:
                    continue

                if name == "draw":
                    odds_map["X"] = price
                else:
                    odds_map[o.get("name", "")] = price

        elif mkey in {"double_chance", "double chance"}:
            for o in market.get("outcomes", []) or []:
                name = norm_text(o.get("name", ""))
                price = o.get("price")
                try:
                    price = float(price)
                except Exception:
                    continue

                if name in {"1x", "home or draw", "home/draw"}:
                    odds_map["1X"] = price
                elif name in {"x2", "draw or away", "draw/away"}:
                    odds_map["X2"] = price
                elif name in {"12", "home or away", "home/away"}:
                    odds_map["12"] = price

        elif mkey == "totals":
            for o in market.get("outcomes", []) or []:
                name = norm_text(o.get("name", ""))
                point = o.get("point")
                price = o.get("price")
                try:
                    price = float(price)
                except Exception:
                    continue

                if point is None:
                    continue

                point_str = str(point)
                if point_str in {"1.5", "2.5", "3.5", "4.5", "5.5"}:
                    if name == "over":
                        odds_map[f"Over {point_str}"] = price
                    elif name == "under":
                        odds_map[f"Under {point_str}"] = price

        elif mkey == "btts":
            for o in market.get("outcomes", []) or []:
                name = norm_text(o.get("name", ""))
                price = o.get("price")
                try:
                    price = float(price)
                except Exception:
                    continue

                if name == "yes":
                    odds_map["Goal (BTTS Sì)"] = price
                elif name == "no":
                    odds_map["No Goal (BTTS No)"] = price

    return odds_map, bookmaker_name


def normalize_named_odds_map(raw_odds: Dict[str, float], home_name: str, away_name: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    home_norm = norm_text(home_name)
    away_norm = norm_text(away_name)

    for k, v in raw_odds.items():
        nk = norm_text(k)

        if nk == home_norm:
            out["1"] = v
        elif nk == away_norm:
            out["2"] = v
        elif k == "X":
            out["X"] = v
        else:
            out[k] = v

    return out


def find_odds_for_match(
    odds_api_key: str,
    league_id: Optional[int],
    match_date: Optional[str],
    home_name: str,
    away_name: str,
) -> Tuple[Dict[str, float], str, Dict[str, Any]]:
    debug = {
        "sport_key": None,
        "events_found_h2h": 0,
        "events_found_totals": 0,
        "events_found_btts": 0,
        "matched_event_h2h": None,
        "matched_event_totals": None,
        "matched_event_btts": None,
        "http_h2h": {},
        "http_totals": {},
        "http_btts": {},
    }

    if not odds_api_key or not league_id:
        return {}, "ODDS API non configurata", debug

    sport_key = ODDS_SPORT_KEYS.get(league_id)
    debug["sport_key"] = sport_key

    if not sport_key:
        return {}, "Sport key non mappata", debug

    events_h2h, dbg_h2h = get_the_odds_api_events(
        odds_api_key=odds_api_key,
        sport_key=sport_key,
        regions="eu,uk",
        markets="h2h",
        odds_format="decimal",
        date_format="iso",
    )
    events_totals, dbg_totals = get_the_odds_api_events(
        odds_api_key=odds_api_key,
        sport_key=sport_key,
        regions="eu,uk",
        markets="totals",
        odds_format="decimal",
        date_format="iso",
    )
    events_btts, dbg_btts = get_the_odds_api_events(
        odds_api_key=odds_api_key,
        sport_key=sport_key,
        regions="eu,uk",
        markets="btts",
        odds_format="decimal",
        date_format="iso",
    )

    debug["http_h2h"] = dbg_h2h
    debug["http_totals"] = dbg_totals
    debug["http_btts"] = dbg_btts
    debug["events_found_h2h"] = len(events_h2h)
    debug["events_found_totals"] = len(events_totals)
    debug["events_found_btts"] = len(events_btts)

    def pick_best_event(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not events:
            return None

        best_event = None
        best_score = -9999.0

        target_dt = None
        if match_date:
            try:
                target_dt = datetime.strptime(match_date, "%Y-%m-%d").date()
            except Exception:
                target_dt = None

        for ev in events:
            home_ev = ev.get("home_team", "") or ""
            away_ev = ev.get("away_team", "") or ""

            s_direct = (similarity(home_name, home_ev) + similarity(away_name, away_ev)) / 2.0
            s_swapped = (similarity(home_name, away_ev) + similarity(away_name, home_ev)) / 2.0
            team_score = max(s_direct, s_swapped)

            date_bonus = 0.0
            ev_date_str = (ev.get("commence_time") or "")[:10]
            if target_dt and ev_date_str:
                try:
                    ev_dt = datetime.strptime(ev_date_str, "%Y-%m-%d").date()
                    diff_days = abs((ev_dt - target_dt).days)
                    if diff_days == 0:
                        date_bonus = 0.20
                    elif diff_days == 1:
                        date_bonus = 0.08
                    elif diff_days == 2:
                        date_bonus = -0.05
                    else:
                        date_bonus = -0.20
                except Exception:
                    pass

            score = team_score + date_bonus
            if score > best_score:
                best_score = score
                best_event = ev

        if best_score < 0.62:
            return None
        return best_event

    best_h2h = pick_best_event(events_h2h)
    best_totals = pick_best_event(events_totals)
    best_btts = pick_best_event(events_btts)

    if best_h2h:
        debug["matched_event_h2h"] = {
            "home_team": best_h2h.get("home_team"),
            "away_team": best_h2h.get("away_team"),
            "commence_time": best_h2h.get("commence_time"),
        }
    if best_totals:
        debug["matched_event_totals"] = {
            "home_team": best_totals.get("home_team"),
            "away_team": best_totals.get("away_team"),
            "commence_time": best_totals.get("commence_time"),
        }
    if best_btts:
        debug["matched_event_btts"] = {
            "home_team": best_btts.get("home_team"),
            "away_team": best_btts.get("away_team"),
            "commence_time": best_btts.get("commence_time"),
        }

    odds_map: Dict[str, float] = {}
    bookmaker_name = "Nessun evento The Odds API"

    for best_event in [best_h2h, best_totals, best_btts]:
        if not best_event:
            continue
        partial_map, partial_bookmaker = extract_odds_from_the_odds_event(best_event)
        partial_map = normalize_named_odds_map(partial_map, home_name, away_name)
        if partial_map:
            odds_map.update(partial_map)
            if bookmaker_name == "Nessun evento The Odds API":
                bookmaker_name = partial_bookmaker

    if not odds_map:
        return {}, "Nessun evento The Odds API", debug

    return odds_map, bookmaker_name, debug


# =========================================================
# CORNER
# =========================================================

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_fixture_statistics(api_key: str, fixture_id: int) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures/statistics"
    data = safe_json_get(url, api_football_headers(api_key), {"fixture": fixture_id})
    return data.get("response", []) or []


def _extract_corner_kicks(stats_for_team: Dict[str, Any]) -> Optional[int]:
    arr = stats_for_team.get("statistics", []) or []
    for item in arr:
        t = (item.get("type") or "").strip().lower()
        if t in {"corner kicks", "corners", "corner kick"}:
            v = item.get("value")
            if v is None:
                return None
            try:
                return int(v)
            except Exception:
                try:
                    return int(float(v))
                except Exception:
                    return None
    return None


def _mean(xs: List[float]) -> float:
    return sum(xs) / max(1, len(xs))


def _std(xs: List[float]) -> float:
    if len(xs) <= 1:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _nearest_corner_line(x: float, lo: float = 3.5, hi: float = 12.5) -> float:
    v = round(x * 2.0) / 2.0
    if float(v).is_integer():
        v += 0.5
    return float(max(lo, min(hi, v)))


@st.cache_data(ttl=60 * 30, show_spinner=False)
def compute_team_corner_profile(api_key: str, team_id: int, season: int, last_n: int = 10) -> Dict[str, Any]:
    last_fx = get_team_last_fixtures(api_key, team_id, season, last=last_n)

    corners_total: List[float] = []

    for fx in last_fx:
        fixture_id = (fx.get("fixture", {}) or {}).get("id")
        if not fixture_id:
            continue

        resp = get_fixture_statistics(api_key, int(fixture_id))
        if not resp or len(resp) < 2:
            continue

        team_rec = None
        opp_rec = None
        for r in resp:
            tid = (r.get("team", {}) or {}).get("id")
            if tid == team_id:
                team_rec = r
            else:
                opp_rec = r

        if not team_rec or not opp_rec:
            continue

        cf = _extract_corner_kicks(team_rec)
        ca = _extract_corner_kicks(opp_rec)
        if cf is None or ca is None:
            continue

        corners_total.append(float(cf + ca))

    if len(corners_total) == 0:
        return {
            "matches_used": 0,
            "total_avg": 0.0,
            "total_std": 0.0,
            "trend": 0.0,
        }

    total_avg = _mean(corners_total)
    total_std = _std(corners_total)
    last5 = corners_total[-5:] if len(corners_total) >= 5 else corners_total
    trend = _mean(last5) - total_avg

    return {
        "matches_used": len(corners_total),
        "total_avg": total_avg,
        "total_std": total_std,
        "trend": trend,
    }


def build_corner_recos(a_c: Dict[str, Any], b_c: Dict[str, Any]) -> Dict[str, Any]:
    min_used = min(a_c.get("matches_used", 0), b_c.get("matches_used", 0))
    total_avg_expected = (a_c.get("total_avg", 0.0) + b_c.get("total_avg", 0.0)) / 2.0
    total_std_expected = (a_c.get("total_std", 0.0) + b_c.get("total_std", 0.0)) / 2.0

    reasons = []
    if min_used < 6:
        reasons.append("pochi dati corner")
    if total_avg_expected < 7.0:
        reasons.append("media corner bassa")
    if total_std_expected > 3.2:
        reasons.append("corner molto variabili")

    no_bet = len(reasons) >= 2

    line_prud = _nearest_corner_line(total_avg_expected - 1.2)
    line_med = _nearest_corner_line(total_avg_expected - 0.3)
    line_aggr = _nearest_corner_line(total_avg_expected + 0.9)

    return {
        "no_bet": no_bet,
        "no_bet_reasons": reasons,
        "prudente": f"Over {line_prud:.1f} Corner",
        "medio": f"Over {line_med:.1f} Corner",
        "aggressivo": f"Over {line_aggr:.1f} Corner",
    }


# =========================================================
# ANALISI
# =========================================================

def summarize_form(last_fixtures: List[Dict[str, Any]], team_id: int) -> Dict[str, Any]:
    pts = 0
    gf = 0
    ga = 0
    form: List[str] = []
    totals: List[int] = []
    btts: List[bool] = []

    for fx in last_fixtures:
        teams = fx.get("teams", {}) or {}
        goals = fx.get("goals", {}) or {}
        home = (teams.get("home", {}) or {}).get("id")
        away = (teams.get("away", {}) or {}).get("id")
        gh = goals.get("home")
        ga_ = goals.get("away")

        if gh is None or ga_ is None:
            continue

        gh_i = int(gh)
        ga_i = int(ga_)
        totals.append(gh_i + ga_i)
        btts.append(gh_i > 0 and ga_i > 0)

        if home == team_id:
            gf += gh_i
            ga += ga_i
            if gh_i > ga_i:
                pts += 3
                form.append("W")
            elif gh_i == ga_i:
                pts += 1
                form.append("D")
            else:
                form.append("L")
        elif away == team_id:
            gf += ga_i
            ga += gh_i
            if ga_i > gh_i:
                pts += 3
                form.append("W")
            elif ga_i == gh_i:
                pts += 1
                form.append("D")
            else:
                form.append("L")

    played = len(form)
    if played == 0:
        return {
            "matches": 0,
            "points": 0,
            "ppg": 0.0,
            "gf": 0,
            "ga": 0,
            "avg_total_goals": 0.0,
            "form": "",
            "totals": [],
            "btts": [],
        }

    avg_total_goals = (gf + ga) / played
    return {
        "matches": played,
        "points": pts,
        "ppg": pts / played,
        "gf": gf,
        "ga": ga,
        "avg_total_goals": avg_total_goals,
        "form": "".join(form[-5:]),
        "totals": totals,
        "btts": btts,
    }


def market_rates_from_summary(s: Dict[str, Any]) -> Dict[str, float]:
    totals = s.get("totals", []) or []
    btts = s.get("btts", []) or []
    n = len(totals)

    if n == 0:
        return {
            "o15": 0.0,
            "o25": 0.0,
            "o35": 0.0,
            "o45": 0.0,
            "o55": 0.0,
            "u35": 0.0,
            "u45": 0.0,
            "u55": 0.0,
            "btts_yes": 0.0,
        }

    return {
        "o15": sum(1 for t in totals if t >= 2) / n,
        "o25": sum(1 for t in totals if t >= 3) / n,
        "o35": sum(1 for t in totals if t >= 4) / n,
        "o45": sum(1 for t in totals if t >= 5) / n,
        "o55": sum(1 for t in totals if t >= 6) / n,
        "u35": sum(1 for t in totals if t <= 3) / n,
        "u45": sum(1 for t in totals if t <= 4) / n,
        "u55": sum(1 for t in totals if t <= 5) / n,
        "btts_yes": sum(1 for x in btts if x) / n,
    }


def combine_rates(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    keys = set(a.keys()) | set(b.keys())
    return {k: (a.get(k, 0.0) + b.get(k, 0.0)) / 2.0 for k in keys}


def label_risk(market: str) -> str:
    safe = {"Over 1.5", "Under 4.5", "Under 5.5", "1X", "X2"}
    medium = {"Under 3.5", "Over 2.5", "Goal (BTTS Sì)", "No Goal (BTTS No)", "1", "2", "12"}
    agg = {"X", "Over 3.5", "Over 4.5", "Over 5.5"}
    if market in safe:
        return "🟩 Prudente"
    if market in medium:
        return "🟨 Medio"
    if market in agg:
        return "🟥 Aggressivo"
    return "🟦 Neutro"


def recommend_outright_1x2(home_sum: Dict[str, Any], away_sum: Dict[str, Any]) -> Dict[str, Any]:
    h_m = max(1, int(home_sum.get("matches", 0) or 1))
    a_m = max(1, int(away_sum.get("matches", 0) or 1))

    h_ppg = float(home_sum.get("ppg", 0.0))
    a_ppg = float(away_sum.get("ppg", 0.0))

    h_gf_pg = float(home_sum.get("gf", 0.0)) / h_m
    h_ga_pg = float(home_sum.get("ga", 0.0)) / h_m
    a_gf_pg = float(away_sum.get("gf", 0.0)) / a_m
    a_ga_pg = float(away_sum.get("ga", 0.0)) / a_m

    avg_goals = (float(home_sum.get("avg_total_goals", 0.0)) + float(away_sum.get("avg_total_goals", 0.0))) / 2.0

    home_idx = h_ppg + 0.35 * (h_gf_pg - h_ga_pg)
    away_idx = a_ppg + 0.35 * (a_gf_pg - a_ga_pg)
    diff = home_idx - away_idx

    draw_base = 0.24 + max(0.0, 0.10 - abs(diff) * 0.05) + max(0.0, (2.6 - avg_goals) * 0.05)
    draw_base = clamp(draw_base, 0.18, 0.38)

    home_raw = math.exp(diff * 0.9)
    away_raw = math.exp(-diff * 0.9)

    rest = max(0.02, 1.0 - draw_base)
    p1 = rest * home_raw / (home_raw + away_raw)
    p2 = rest * away_raw / (home_raw + away_raw)
    px = draw_base

    probs = {"1": p1, "X": px, "2": p2}
    best_market = max(probs, key=probs.get)

    if best_market == "1":
        why = f"Casa favorita: indice forma migliore ({home_idx:.2f} vs {away_idx:.2f})."
    elif best_market == "2":
        why = f"Trasferta favorita: indice forma migliore ({away_idx:.2f} vs {home_idx:.2f})."
    else:
        why = f"Match equilibrato: differenza forma ridotta e media gol ≈ {avg_goals:.2f}."

    return {
        "market": best_market,
        "prob": probs[best_market],
        "probs": probs,
        "why": why,
        "risk": label_risk(best_market),
    }


def recommend_for_match(home_sum: Dict[str, Any], away_sum: Dict[str, Any]) -> Dict[str, Any]:
    h_rates = market_rates_from_summary(home_sum)
    a_rates = market_rates_from_summary(away_sum)
    r = combine_rates(h_rates, a_rates)
    avg_goals = (home_sum.get("avg_total_goals", 0.0) + away_sum.get("avg_total_goals", 0.0)) / 2.0

    if r["o25"] >= 0.62 and avg_goals >= 2.7:
        primary = ("Over 2.5", f"Trend gol alto: Over 2.5 ≈ {r['o25']*100:.0f}%.")
        alt = [
            ("Under 4.5", f"Under 4.5 ≈ {r['u45']*100:.0f}%."),
            ("Over 3.5", f"Over 3.5 ≈ {r['o35']*100:.0f}%."),
        ]
    elif r["u35"] >= 0.70 and avg_goals <= 2.4:
        primary = ("Under 3.5", f"Trend gol basso: Under 3.5 ≈ {r['u35']*100:.0f}%.")
        alt = [
            ("Over 1.5", f"Over 1.5 ≈ {r['o15']*100:.0f}%."),
            ("Under 4.5", f"Under 4.5 ≈ {r['u45']*100:.0f}%."),
        ]
    else:
        primary = ("Over 1.5", f"Zona centrale: Over 1.5 ≈ {r['o15']*100:.0f}%.")
        alt = [
            ("Over 2.5", f"Over 2.5 ≈ {r['o25']*100:.0f}%."),
            ("Under 4.5", f"Under 4.5 ≈ {r['u45']*100:.0f}%."),
        ]

    btts_yes = r["btts_yes"]
    if btts_yes >= 0.62:
        alt.append(("Goal (BTTS Sì)", f"BTTS Sì ≈ {btts_yes*100:.0f}%."))
    elif btts_yes <= 0.40:
        alt.append(("No Goal (BTTS No)", "No Goal più coerente."))
    else:
        alt.append(("Goal/NoGoal", "Zona media, da leggere con attenzione."))

    ppg_h = home_sum.get("ppg", 0.0)
    ppg_a = away_sum.get("ppg", 0.0)
    diff = ppg_h - ppg_a

    if diff >= 0.55:
        outcome = ("1X", f"Casa più in forma: PPG {ppg_h:.2f} vs {ppg_a:.2f}.")
    elif diff <= -0.55:
        outcome = ("X2", f"Trasferta più in forma: PPG {ppg_a:.2f} vs {ppg_h:.2f}.")
    else:
        outcome = ("12", f"PPG simili ({ppg_h:.2f} vs {ppg_a:.2f}).")

    outright = recommend_outright_1x2(home_sum, away_sum)

    primary_market, primary_why = primary
    primary_obj = {"market": primary_market, "why": primary_why, "risk": label_risk(primary_market)}

    alternatives: List[Dict[str, Any]] = []
    seen = {primary_market}
    for m, why in alt:
        if m in seen:
            continue
        seen.add(m)
        alternatives.append({"market": m, "why": why, "risk": label_risk(m)})

    return {
        "primary": primary_obj,
        "alternatives": alternatives[:4],
        "outcome": {"market": outcome[0], "why": outcome[1], "risk": label_risk(outcome[0])},
        "outright": outright,
        "meta": {"avg_goals": avg_goals, "rates": r},
    }


# =========================================================
# VALUE ENGINE
# =========================================================

def market_probability_map(rec: Dict[str, Any]) -> Dict[str, float]:
    probs_1x2 = rec["outright"]["probs"]
    rates = rec["meta"]["rates"]

    out = {
        "1": probs_1x2.get("1", 0.0),
        "X": probs_1x2.get("X", 0.0),
        "2": probs_1x2.get("2", 0.0),

        "Over 1.5": rates.get("o15", 0.0),
        "Over 2.5": rates.get("o25", 0.0),
        "Over 3.5": rates.get("o35", 0.0),
        "Over 4.5": rates.get("o45", 0.0),
        "Over 5.5": rates.get("o55", 0.0),

        "Under 3.5": rates.get("u35", 0.0),
        "Under 4.5": rates.get("u45", 0.0),
        "Under 5.5": rates.get("u55", 0.0),

        "Goal (BTTS Sì)": rates.get("btts_yes", 0.0),
        "No Goal (BTTS No)": 1.0 - rates.get("btts_yes", 0.0),
    }

    out["1X"] = clamp(out["1"] + out["X"], 0.0, 1.0)
    out["X2"] = clamp(out["X"] + out["2"], 0.0, 1.0)
    out["12"] = clamp(out["1"] + out["2"], 0.0, 1.0)

    return out


MARKET_PROFILES = {
    "1": {"min_prob": 0.52, "min_odd": 1.35, "max_odd": 3.10, "target_odd": 1.85, "stability": 0.78},
    "X": {"min_prob": 0.28, "min_odd": 2.90, "max_odd": 4.60, "target_odd": 3.40, "stability": 0.40},
    "2": {"min_prob": 0.52, "min_odd": 1.35, "max_odd": 3.10, "target_odd": 1.85, "stability": 0.78},

    "1X": {"min_prob": 0.72, "min_odd": 1.18, "max_odd": 1.95, "target_odd": 1.42, "stability": 0.95},
    "X2": {"min_prob": 0.72, "min_odd": 1.18, "max_odd": 1.95, "target_odd": 1.42, "stability": 0.95},
    "12": {"min_prob": 0.68, "min_odd": 1.20, "max_odd": 1.95, "target_odd": 1.38, "stability": 0.70},

    "Over 1.5": {"min_prob": 0.72, "min_odd": 1.18, "max_odd": 1.90, "target_odd": 1.42, "stability": 1.00},
    "Over 2.5": {"min_prob": 0.56, "min_odd": 1.45, "max_odd": 2.35, "target_odd": 1.82, "stability": 0.86},
    "Over 3.5": {"min_prob": 0.42, "min_odd": 1.85, "max_odd": 3.20, "target_odd": 2.35, "stability": 0.62},
    "Over 4.5": {"min_prob": 0.28, "min_odd": 2.40, "max_odd": 5.00, "target_odd": 3.50, "stability": 0.35},
    "Over 5.5": {"min_prob": 0.18, "min_odd": 3.40, "max_odd": 7.00, "target_odd": 4.60, "stability": 0.18},

    "Under 3.5": {"min_prob": 0.62, "min_odd": 1.28, "max_odd": 2.30, "target_odd": 1.68, "stability": 0.92},
    "Under 4.5": {"min_prob": 0.76, "min_odd": 1.15, "max_odd": 1.85, "target_odd": 1.38, "stability": 1.00},
    "Under 5.5": {"min_prob": 0.84, "min_odd": 1.08, "max_odd": 1.55, "target_odd": 1.22, "stability": 0.96},

    "Goal (BTTS Sì)": {"min_prob": 0.56, "min_odd": 1.45, "max_odd": 2.30, "target_odd": 1.78, "stability": 0.78},
    "No Goal (BTTS No)": {"min_prob": 0.56, "min_odd": 1.45, "max_odd": 2.30, "target_odd": 1.78, "stability": 0.78},
}


def get_match_context(prob_map: Dict[str, float]) -> Dict[str, Any]:
    p1 = prob_map.get("1", 0.0)
    px = prob_map.get("X", 0.0)
    p2 = prob_map.get("2", 0.0)

    if p1 - p2 >= 0.14:
        side = "home"
    elif p2 - p1 >= 0.14:
        side = "away"
    else:
        side = "balanced"

    if prob_map.get("Over 2.5", 0.0) >= 0.62:
        goals_profile = "high"
    elif prob_map.get("Under 4.5", 0.0) >= 0.82 and prob_map.get("Under 3.5", 0.0) >= 0.58:
        goals_profile = "low"
    else:
        goals_profile = "mid"

    return {
        "side": side,
        "goals_profile": goals_profile,
        "p1": p1,
        "px": px,
        "p2": p2,
    }


def context_bonus_for_market(market: str, ctx: Dict[str, Any]) -> float:
    bonus = 0.0
    side = ctx["side"]
    goals_profile = ctx["goals_profile"]

    if side == "home":
        if market in {"1", "1X"}:
            bonus += 10.0
        if market in {"2", "X2"}:
            bonus -= 10.0
        if market == "X":
            bonus -= 4.0
    elif side == "away":
        if market in {"2", "X2"}:
            bonus += 10.0
        if market in {"1", "1X"}:
            bonus -= 10.0
        if market == "X":
            bonus -= 4.0
    else:
        if market in {"X", "12", "Under 3.5"}:
            bonus += 6.0

    if goals_profile == "high":
        if market in {"Over 1.5", "Over 2.5", "Goal (BTTS Sì)"}:
            bonus += 8.0
        if market in {"Under 3.5", "Under 4.5", "No Goal (BTTS No)"}:
            bonus -= 6.0
    elif goals_profile == "low":
        if market in {"Under 3.5", "Under 4.5", "Under 5.5", "No Goal (BTTS No)"}:
            bonus += 8.0
        if market in {"Over 3.5", "Over 4.5", "Over 5.5"}:
            bonus -= 10.0

    return bonus


def score_market_candidate(market: str, prob: float, odd: float, prob_map: Dict[str, float], relaxed: bool = False) -> Optional[float]:
    profile = MARKET_PROFILES.get(market)
    if not profile:
        return None

    min_prob = profile["min_prob"] - (0.05 if relaxed else 0.0)
    max_odd = profile["max_odd"] + (0.50 if relaxed else 0.0)
    min_odd = profile["min_odd"]
    target_odd = profile["target_odd"]
    stability = profile["stability"]

    if prob < min_prob:
        return None
    if odd < min_odd or odd > max_odd:
        return None

    edge = prob * odd
    min_edge = 0.88 if relaxed else 0.93
    if edge < min_edge:
        return None

    prob_score = prob * 100.0 * stability
    edge_bonus = max(0.0, edge - 1.0) * 32.0

    odds_span = max_odd - min_odd
    if odds_span <= 0:
        target_bonus = 0.0
    else:
        target_bonus = max(0.0, 1.0 - abs(odd - target_odd) / odds_span) * 10.0

    ctx = get_match_context(prob_map)
    ctx_bonus = context_bonus_for_market(market, ctx)

    longshot_penalty = 0.0
    if odd >= 5.5:
        longshot_penalty += 18.0
    elif odd >= 4.2:
        longshot_penalty += 10.0
    elif odd >= 3.4:
        longshot_penalty += 4.0

    if market == "X":
        longshot_penalty += 5.0

    final_score = prob_score + edge_bonus + target_bonus + ctx_bonus - longshot_penalty
    return final_score


def build_value_table(prob_map: Dict[str, float], odds_map: Dict[str, float]) -> List[Dict[str, Any]]:
    rows = []

    allowed_markets = {
        "1", "X", "2",
        "1X", "X2", "12",
        "Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5", "Over 5.5",
        "Under 3.5", "Under 4.5", "Under 5.5",
        "Goal (BTTS Sì)", "No Goal (BTTS No)"
    }

    for market, prob in prob_map.items():
        if market not in allowed_markets:
            continue

        odd = odds_map.get(market)
        if odd is None:
            continue

        score = score_market_candidate(market, prob, odd, prob_map, relaxed=False)
        if score is None:
            continue

        rows.append(
            {
                "market": market,
                "prob": prob,
                "odd": odd,
                "value_idx": score,
                "risk": label_risk(market),
                "source": "quota",
            }
        )

    if not rows:
        for market, prob in prob_map.items():
            if market not in allowed_markets:
                continue

            odd = odds_map.get(market)
            if odd is None:
                continue

            score = score_market_candidate(market, prob, odd, prob_map, relaxed=True)
            if score is None:
                continue

            rows.append(
                {
                    "market": market,
                    "prob": prob,
                    "odd": odd,
                    "value_idx": score,
                    "risk": label_risk(market),
                    "source": "quota",
                }
            )

    rows.sort(key=lambda x: x["value_idx"], reverse=True)
    return rows


def build_model_only_table(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    prob_map = market_probability_map(rec)

    rows = []
    for market, prob in prob_map.items():
        bonus = 0.0
        if market in {"Over 1.5", "Under 4.5", "Under 5.5", "1X", "X2"}:
            bonus += 8.0
        elif market in {"Under 3.5", "Over 2.5", "Goal (BTTS Sì)", "No Goal (BTTS No)", "1", "2"}:
            bonus += 4.0

        value_idx = prob * 100.0 + bonus

        rows.append(
            {
                "market": market,
                "prob": prob,
                "odd": None,
                "value_idx": value_idx,
                "risk": label_risk(market),
                "source": "modello",
            }
        )

    rows.sort(key=lambda x: x["value_idx"], reverse=True)
    return rows


def pick_best_single(table: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not table:
        return None
    return table[0]


def signal_badge(x: float, source: str) -> str:
    if source == "quota":
        if x >= 78:
            return "🔵 Molto buona"
        if x >= 68:
            return "🟣 Buona"
        return "🟠 Da valutare"
    else:
        if x >= 72:
            return "🔵 Forte dal modello"
        if x >= 60:
            return "🟣 Buona dal modello"
        return "🟠 Debole dal modello"


# =========================================================
# PIPELINE MATCH
# =========================================================

def fixture_label(fx: Dict[str, Any]) -> str:
    teams = fx.get("teams", {}) or {}
    league = fx.get("league", {}) or {}
    home = (teams.get("home", {}) or {}).get("name", "Home")
    away = (teams.get("away", {}) or {}).get("name", "Away")
    l_name = league.get("name", "League")
    dt = (fx.get("fixture", {}) or {}).get("date", "")
    hhmm = ""
    if dt:
        try:
            ddt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            hhmm = ddt.astimezone().strftime("%H:%M")
        except Exception:
            hhmm = ""
    return f"{hhmm}  {home} - {away}  •  {l_name}"


def analyze_by_team_ids(
    api_football_key: str,
    odds_api_key: str,
    home_id: int,
    away_id: int,
    league_id: Optional[int],
    home_name: str,
    away_name: str,
) -> Dict[str, Any]:
    pick = find_fixture_smart(api_football_key, home_id, away_id, league_id)
    season = pick.season

    home_last = get_team_last_fixtures(api_football_key, home_id, season, last=10)
    away_last = get_team_last_fixtures(api_football_key, away_id, season, last=10)

    home_sum = summarize_form(home_last, home_id)
    away_sum = summarize_form(away_last, away_id)

    inj_home = get_injuries(api_football_key, home_id, season, league_id if league_id else None)
    inj_away = get_injuries(api_football_key, away_id, season, league_id if league_id else None)

    rec = recommend_for_match(home_sum, away_sum)

    a_corner = compute_team_corner_profile(api_football_key, home_id, season, last_n=10)
    b_corner = compute_team_corner_profile(api_football_key, away_id, season, last_n=10)
    corner_reco = build_corner_recos(a_corner, b_corner)

    odds_map: Dict[str, float] = {}
    bookmaker_used = "Nessuna quota"
    odds_debug: Dict[str, Any] = {}

    match_date = None
    if pick.fixture:
        match_date = ((pick.fixture.get("fixture", {}) or {}).get("date") or "")[:10]

    odds_map, bookmaker_used, odds_debug = find_odds_for_match(
        odds_api_key=odds_api_key,
        league_id=league_id,
        match_date=match_date,
        home_name=home_name,
        away_name=away_name,
    )

    if odds_map:
        value_table = build_value_table(market_probability_map(rec), odds_map)
        if not value_table:
            value_table = build_model_only_table(rec)
    else:
        value_table = build_model_only_table(rec)

    best_single = pick_best_single(value_table)

    return {
        "pick": pick,
        "home_sum": home_sum,
        "away_sum": away_sum,
        "inj_home": inj_home,
        "inj_away": inj_away,
        "rec": rec,
        "home_name": home_name,
        "away_name": away_name,
        "league_id": league_id,
        "corner_reco": corner_reco,
        "odds_map": odds_map,
        "bookmaker_used": bookmaker_used,
        "value_table": value_table,
        "best_single": best_single,
        "odds_debug": odds_debug,
    }


# =========================================================
# TRADING / STOP
# =========================================================

def lay_liability(lay_stake: float, lay_odds: float) -> float:
    return lay_stake * (lay_odds - 1.0)


def pnl_if_win(back_stake: float, back_odds: float, lay_stake_: float, lay_odds_: float, comm: float) -> float:
    gross = back_stake * (back_odds - 1.0) - lay_liability(lay_stake_, lay_odds_)
    if gross > 0:
        gross = gross * (1.0 - comm)
    return gross


def pnl_if_lose(back_stake: float, lay_stake_: float, comm: float) -> float:
    gross = -back_stake + lay_stake_
    if gross > 0:
        gross = gross * (1.0 - comm)
    return gross


def lay_stake_for_target_loss_when_lose(back_stake: float, target_loss: float) -> float:
    return max(0.0, back_stake - target_loss)


def lay_odds_needed_for_min_profit_if_win(back_stake: float, back_odds: float, lay_stake_: float, min_profit_win: float, comm: float) -> Optional[float]:
    if lay_stake_ <= 0:
        return None
    gross_target = min_profit_win / max(1e-9, (1.0 - comm))
    numerator = back_stake * (back_odds - 1.0) - gross_target
    max_lay_odds = 1.0 + (numerator / lay_stake_)
    if max_lay_odds <= 1.01:
        return None
    return max_lay_odds


def make_stop_plan(back_stake: float, back_odds: float, comm_pct: float, max_loss_if_lose: float, min_profit_if_win: float, stop_steps: List[int]) -> List[Dict[str, Any]]:
    comm = comm_pct / 100.0
    plan = []

    for s in stop_steps:
        quota_stop = back_odds * (1.0 + s / 100.0)
        lay_stake_ = lay_stake_for_target_loss_when_lose(back_stake, max_loss_if_lose)

        if lay_stake_ <= 0:
            plan.append({"Stop": f"+{s}%", "Quota stop": round(quota_stop, 2), "Banca consigliata": "—", "Esito se VINCI": "—", "Esito se PERDI": "—", "Note": "Impossibile"})
            continue

        win_pnl = pnl_if_win(back_stake, back_odds, lay_stake_, quota_stop, comm)
        lose_pnl = pnl_if_lose(back_stake, lay_stake_, comm)

        if win_pnl < min_profit_if_win - 1e-9:
            max_lay = lay_odds_needed_for_min_profit_if_win(back_stake, back_odds, lay_stake_, min_profit_if_win, comm)
            note = "Profitto minimo troppo alto."
            if max_lay:
                note += f" Prova quota stop ≤ {max_lay:.2f}"
            plan.append({"Stop": f"+{s}%", "Quota stop": round(quota_stop, 2), "Banca consigliata": "—", "Esito se VINCI": "—", "Esito se PERDI": "—", "Note": note})
            continue

        plan.append(
            {
                "Stop": f"+{s}%",
                "Quota stop": round(quota_stop, 2),
                "Banca consigliata": f"{lay_stake_:.2f} €",
                "Esito se VINCI": f"{win_pnl:+.2f} €",
                "Esito se PERDI": f"{lose_pnl:+.2f} €",
                "Note": "OK",
            }
        )

    return plan


# =========================================================
# UI
# =========================================================

st.set_page_config(page_title="Trading Tool PRO (Calcio) — Analisi + Quote + Value", layout="wide")

st.markdown(
    """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.small-muted { opacity: 0.75; font-size: 0.92rem; }
.card {
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03);
  border-radius: 16px;
  padding: 16px;
  margin-bottom: 12px;
}
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(255,255,255,0.05);
  font-size: 0.85rem;
  margin-left: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Quote + Value")
st.caption("Analisi su dati recenti, forma e quote disponibili. Non è una previsione certa.")

secrets_keys = dict(st.secrets) if hasattr(st, "secrets") else {}
api_football_key = secrets_keys.get("API_FOOTBALL_KEY", "")
odds_api_key = secrets_keys.get("ODDS_API_KEY", "")

with st.expander("🔧 DEBUG (solo se serve)", expanded=False):
    st.json({k: ("***" if "KEY" in k else v) for k, v in secrets_keys.items()})

    if api_football_key:
        st.write(f"API_FOOTBALL_KEY presente (lunghezza {len(api_football_key)}).")
    else:
        st.warning("API_FOOTBALL_KEY NON trovata nei Secrets.")

    if odds_api_key:
        st.write(f"ODDS_API_KEY presente (lunghezza {len(odds_api_key)}).")
    else:
        st.warning("ODDS_API_KEY NON trovata nei Secrets.")

if not api_football_key:
    st.error("Manca API_FOOTBALL_KEY nei Secrets.")
    st.stop()

if not odds_api_key:
    st.warning("ODDS_API_KEY non trovata. L'app funzionerà, ma le quote useranno il fallback del modello.")

tabs = st.tabs(["📊 Analisi partita (PRO)", "🧮 Trading / Stop (Manuale)"])


def render_analysis(res: Dict[str, Any]):
    pick = res["pick"]
    home_sum = res["home_sum"]
    away_sum = res["away_sum"]
    inj_home = res["inj_home"]
    inj_away = res["inj_away"]
    rec = res["rec"]
    hn = res["home_name"]
    an = res["away_name"]
    corner_reco = res.get("corner_reco")
    best_single = res.get("best_single")
    value_table = res.get("value_table", [])
    bookmaker_used = res.get("bookmaker_used", "N/D")
    odds_map = res.get("odds_map", {})
    odds_debug = res.get("odds_debug", {})

    st.success("✅ Analisi pronta")

    st.markdown(
        f"""
<div class="card">
<b>{hn} vs {an}</b><br/>
<span class="small-muted">{pick.message}</span><br/>
<span class="small-muted"><b>Bookmaker quote:</b> {bookmaker_used}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.expander("DEBUG QUOTE MATCH", expanded=False):
        st.write(odds_debug)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"### 🏠 {hn}")
        st.write(f"- Forma: **{home_sum['form']}**")
        st.write(f"- PPG: **{home_sum['ppg']:.2f}**")
        st.write(f"- Gol fatti/subiti: **{home_sum['gf']} / {home_sum['ga']}**")
        st.write(f"- Infortuni/Squalifiche: **{len(inj_home)}**")

    with c2:
        st.markdown(f"### ✈️ {an}")
        st.write(f"- Forma: **{away_sum['form']}**")
        st.write(f"- PPG: **{away_sum['ppg']:.2f}**")
        st.write(f"- Gol fatti/subiti: **{away_sum['gf']} / {away_sum['ga']}**")
        st.write(f"- Infortuni/Squalifiche: **{len(inj_away)}**")

    st.markdown("---")
    st.markdown("## 🎯 Miglior giocata della partita")

    if best_single:
        source = best_single.get("source", "modello")
        idx_label = "Indice valore" if source == "quota" else "Forza modello"
        odd_text = f" @ {best_single['odd']:.2f}" if best_single.get("odd") else ""
        st.markdown(
            f"""
<div class="card">
<b>✅ Miglior giocata:</b> <span class="badge">{best_single['risk']}</span><br/>
<h3>{best_single['market']}{odd_text}</h3>
<span class="small-muted"><b>Probabilità:</b> {best_single['prob']*100:.0f}% · <b>{idx_label}:</b> {best_single['value_idx']:.2f} · {signal_badge(float(best_single['value_idx']), source)}</span><br/>
<span class="small-muted"><b>Origine:</b> {source}</span>
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("## 1️⃣X️⃣2️⃣")
    probs_1x2 = rec["outright"]["probs"]
    k1, kx, k2 = st.columns(3)
    with k1:
        st.metric("1", f"{probs_1x2['1']*100:.0f}%")
    with kx:
        st.metric("X", f"{probs_1x2['X']*100:.0f}%")
    with k2:
        st.metric("2", f"{probs_1x2['2']*100:.0f}%")

    if odds_map:
        st.markdown("## 💰 Quote trovate")
        st.dataframe([{"Mercato": k, "Quota": v} for k, v in odds_map.items()], use_container_width=True)
    else:
        st.info("Quote non trovate per questo match. Uso il fallback del modello.")

    st.markdown("## 📈 Classifica mercati")
    if value_table:
        rows = []
        for r in value_table[:15]:
            rows.append(
                {
                    "Mercato": r["market"],
                    "Probabilità": f"{r['prob']*100:.0f}%",
                    "Quota": "-" if r.get("odd") is None else f"{r['odd']:.2f}",
                    "Indice": f"{r['value_idx']:.2f}",
                    "Origine": r["source"],
                    "Rischio": r["risk"],
                }
            )
        st.dataframe(rows, use_container_width=True)

    st.markdown("## 🎯 Corner")
    if not corner_reco or corner_reco.get("prudente") is None:
        st.info("Corner non disponibili.")
    else:
        if corner_reco.get("no_bet"):
            st.warning("Corner: meglio non forzare.")
            for rr in corner_reco.get("no_bet_reasons", []):
                st.write(f"- {rr}")
        else:
            st.write(f"Prudente: **{corner_reco['prudente']}**")
            st.write(f"Medio: **{corner_reco['medio']}**")
            st.write(f"Aggressivo: **{corner_reco['aggressivo']}**")


with tabs[0]:
    st.subheader("📊 Analisi partita (PRO)")

    mode_tabs = st.tabs(["🗓️ Partite del giorno", "✍️ Inserisci partita manualmente"])

    with mode_tabs[0]:
        st.markdown("### 🗓️ Partite del giorno")

        cA, cB, cC = st.columns([2, 1, 1])
        with cA:
            selected_leagues = st.multiselect(
                "Campionati da includere",
                options=list(DEFAULT_LEAGUES.keys()),
                default=[],
            )
        with cB:
            day_pick = st.date_input("Giorno", value=datetime.now().date())
        with cC:
            max_out = st.number_input("Max partite", min_value=3, max_value=20, value=10, step=1)

        if st.button("🔄 Trova partite", type="primary", use_container_width=True):
            if not selected_leagues:
                st.warning("Seleziona almeno un campionato.")
            else:
                with st.spinner("Cerco partite..."):
                    day_str = day_pick.isoformat()
                    all_fx: List[Dict[str, Any]] = []
                    debug_counts = []

                    for lname in selected_leagues:
                        lid = DEFAULT_LEAGUES[lname]
                        fx = get_fixtures_by_date_and_league(api_football_key, day_str, lid)
                        debug_counts.append(
                            {
                                "lega": lname,
                                "league_id": lid,
                                "trovate_api": len(fx),
                            }
                        )
                        for f in fx:
                            status = (((f.get("fixture", {}) or {}).get("status", {}) or {}).get("short")) or ""
                            if status in {"FT", "AET", "PEN", "CANC", "PST", "ABD"}:
                                continue
                            all_fx.append(f)

                    st.session_state["debug_counts"] = debug_counts

                    ranked: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []

                    for fx in all_fx[:60]:
                        teams = fx.get("teams", {}) or {}
                        league = fx.get("league", {}) or {}
                        home = teams.get("home", {}) or {}
                        away = teams.get("away", {}) or {}

                        home_id = home.get("id")
                        away_id = away.get("id")
                        if not home_id or not away_id:
                            continue

                        result = analyze_by_team_ids(
                            api_football_key=api_football_key,
                            odds_api_key=odds_api_key,
                            home_id=int(home_id),
                            away_id=int(away_id),
                            league_id=int(league.get("id", 0) or 0) or None,
                            home_name=home.get("name", "Home"),
                            away_name=away.get("name", "Away"),
                        )

                        best_single = result.get("best_single")
                        if not best_single:
                            continue

                        ranked.append((float(best_single["value_idx"]), fx, result))

                    ranked.sort(key=lambda x: x[0], reverse=True)
                    st.session_state["day_ranked"] = ranked[: int(max_out)]

        dbg = st.session_state.get("debug_counts", [])
        if dbg:
            st.write("Debug leghe:")
            st.dataframe(dbg, use_container_width=True)

        ranked = st.session_state.get("day_ranked", [])

        if ranked:
            st.markdown("## ⭐ Migliori giocate del giorno")
            rows_rank = []
            for _, fx, result in ranked:
                teams = fx.get("teams", {}) or {}
                home = (teams.get("home", {}) or {}).get("name", "Home")
                away = (teams.get("away", {}) or {}).get("name", "Away")
                best = result.get("best_single", {})
                rows_rank.append(
                    {
                        "Partita": f"{home} - {away}",
                        "Giocata": best.get("market", "-"),
                        "Quota": "-" if best.get("odd") is None else f"{best.get('odd'):.2f}",
                        "Prob.": f"{best.get('prob', 0.0)*100:.0f}%",
                        "Indice": f"{best.get('value_idx', 0.0):.2f}",
                        "Origine": best.get("source", "-"),
                        "Bookmaker": result.get("bookmaker_used", "N/D"),
                    }
                )
            st.dataframe(rows_rank, use_container_width=True)

            labels = [fixture_label(fx) for _, fx, _ in ranked]
            selected_label = st.selectbox("Apri dettaglio partita", labels)
            idx = labels.index(selected_label)
            _, _, res_selected = ranked[idx]
            render_analysis(res_selected)
        else:
            st.info("Seleziona campionati e premi Trova partite.")

    with mode_tabs[1]:
        st.markdown("### ✍️ Inserisci partita manualmente")

        colA, colB = st.columns([2, 1])
        with colA:
            match_text = st.text_input("Partita", placeholder="Es: AC Milan - Como")
        with colB:
            league_label = st.selectbox("Campionato (consigliato)", options=["Auto"] + list(DEFAULT_LEAGUES.keys()), index=0)
            league_id = None if league_label == "Auto" else DEFAULT_LEAGUES[league_label]

        if st.button("🔎 Analizza (manuale)", type="primary", use_container_width=True):
            parsed = parse_match_input(match_text)
            if not parsed:
                st.error("Scrivi la partita tipo: Juve - Atalanta")
                st.stop()

            home_name_in, away_name_in = parsed

            with st.spinner("Cerco squadre..."):
                home_candidates = search_team(api_football_key, home_name_in)
                away_candidates = search_team(api_football_key, away_name_in)

            if not home_candidates:
                st.error(f"Non trovo la squadra: {home_name_in}")
                st.stop()
            if not away_candidates:
                st.error(f"Non trovo la squadra: {away_name_in}")
                st.stop()

            def pick_best(cands: List[Dict[str, Any]], q: str) -> Dict[str, Any]:
                qn = norm_text(q)
                best = cands[0]
                best_score = -1.0
                for c in cands:
                    name = (c.get("team", {}) or {}).get("name", "") or ""
                    nn = norm_text(name)
                    score = 0.0
                    if nn == qn:
                        score += 100
                    if qn in nn:
                        score += 40
                    score += max(0, 20 - abs(len(nn) - len(qn)))
                    if score > best_score:
                        best_score = score
                        best = c
                return best

            home_team = pick_best(home_candidates, home_name_in)
            away_team = pick_best(away_candidates, away_name_in)

            home_id = (home_team.get("team", {}) or {}).get("id")
            away_id = (away_team.get("team", {}) or {}).get("id")
            home_real = (home_team.get("team", {}) or {}).get("name", home_name_in)
            away_real = (away_team.get("team", {}) or {}).get("name", away_name_in)

            if not home_id or not away_id:
                st.error("Errore: ID squadra non disponibile.")
                st.stop()

            with st.spinner("Analizzo..."):
                result = analyze_by_team_ids(
                    api_football_key=api_football_key,
                    odds_api_key=odds_api_key,
                    home_id=int(home_id),
                    away_id=int(away_id),
                    league_id=league_id,
                    home_name=home_real,
                    away_name=away_real,
                )

            render_analysis(result)


with tabs[1]:
    st.subheader("🧮 Trading / Stop (Manuale)")
    st.caption("Qui inserisci tu quote e importi reali.")

    col1, col2 = st.columns(2)
    with col1:
        back_stake = st.number_input("Puntata d’ingresso (€)", min_value=1.0, value=10.0, step=1.0)
        comm_pct = st.number_input("Commissione exchange (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)
    with col2:
        back_odds = st.number_input("Quota d’ingresso", min_value=1.01, value=1.80, step=0.01, format="%.2f")
        market_label = st.selectbox(
            "Mercato",
            options=["Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5", "Under 3.5", "Under 4.5", "Over 5.5", "Under 5.5", "Goal", "No Goal"],
            index=0,
        )

    max_loss_if_lose = st.number_input("Perdita max se perdi (€)", min_value=0.0, value=5.0, step=0.5)
    min_profit_if_win = st.number_input("Profitto minimo se vinci (€)", min_value=0.0, value=1.0, step=0.5)

    stop_steps = [25, 35, 50]

    if st.button("✅ CALCOLA", type="primary", use_container_width=True):
        plan = make_stop_plan(
            back_stake=back_stake,
            back_odds=back_odds,
            comm_pct=comm_pct,
            max_loss_if_lose=max_loss_if_lose,
            min_profit_if_win=min_profit_if_win,
            stop_steps=stop_steps,
        )
        st.dataframe(plan, use_container_width=True)

        live_odds = st.number_input("Quota LIVE attuale (LAY)", min_value=1.01, value=back_odds, step=0.01, format="%.2f")

        comm = comm_pct / 100.0
        lay_stake_ = lay_stake_for_target_loss_when_lose(back_stake, max_loss_if_lose)

        if lay_stake_ <= 0:
            st.warning("Perdita max troppo bassa rispetto alla puntata.")
        else:
            win_p = pnl_if_win(back_stake, back_odds, lay_stake_, live_odds, comm)
            lose_p = pnl_if_lose(back_stake, lay_stake_, comm)
            liab = lay_liability(lay_stake_, live_odds)

            st.markdown(
                f"""
<div class="card">
<b>{market_label}</b><br/>
<b>Banca consigliata adesso:</b> {lay_stake_:.2f} € @ {live_odds:.2f}<br/>
<b>Liability:</b> {liab:.2f} €<br/><br/>
<b>Esiti stimati:</b><br/>
- Se VINCI: <b>{win_p:+.2f} €</b><br/>
- Se PERDI: <b>{lose_p:+.2f} €</b>
</div>
""",
                unsafe_allow_html=True,
            )
    else:
        st.info("Imposta i valori e premi CALCOLA.")