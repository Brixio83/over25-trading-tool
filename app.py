# app.py
# Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)
# ✅ Modalità 1: "Partite del giorno" (max 10) + ranking migliori giocate
# ✅ Modalità 2: Inserimento manuale partita
# ✅ Trading / Stop manuale
# ✅ Champions League + Europa League (+ Conference opzionale)
# ✅ Corner
# ✅ NUOVO:
#    - Mercati 1 / X / 2
#    - Quote automatiche da API-Football
#    - Preferenza NetBet, fallback automatico se non disponibile
#    - Miglior giocata partita
#    - Migliori giocate del giorno
#
# --- STREAMLIT SECRETS ---
# API_FOOTBALL_KEY = "la_tua_key_api_football"

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

# =============================
# CONFIG
# =============================

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

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

FALLBACK_BOOKMAKERS = [
    "Netbet",
    "Bet365",
    "1xBet",
    "Bwin",
    "William Hill",
    "Pinnacle",
    "Unibet",
    "Marathonbet",
    "Betfair",
]

# =============================
# UTILS
# =============================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def season_for_date(dt: datetime) -> int:
    return dt.year if dt.month >= 7 else dt.year - 1


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def norm_team_name(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


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


def http_get_json(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"errors": {"json": "Invalid JSON"}, "raw": r.text}
    data["_http_status"] = r.status_code
    data["_url"] = r.url
    return data


# =============================
# API-FOOTBALL
# =============================

@st.cache_data(ttl=60 * 30, show_spinner=False)
def search_team(api_key: str, query: str) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/teams"
    data = http_get_json(url, api_football_headers(api_key), {"search": query})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_team_last_fixtures(api_key: str, team_id: int, season: int, last: int = 10) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures"
    data = http_get_json(url, api_football_headers(api_key), {"team": team_id, "season": season, "last": last})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_team_next_fixtures(api_key: str, team_id: int, season: int, nxt: int = 25) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures"
    data = http_get_json(url, api_football_headers(api_key), {"team": team_id, "season": season, "next": nxt})
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
    data = http_get_json(url, api_football_headers(api_key), params)
    resp = data.get("response", []) or []
    return resp[:limit]


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_injuries(api_key: str, team_id: int, season: int, league_id: Optional[int]) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/injuries"
    params: Dict[str, Any] = {"team": team_id, "season": season}
    if league_id:
        params["league"] = league_id
    data = http_get_json(url, api_football_headers(api_key), params)
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 10, show_spinner=False)
def get_fixtures_by_date_and_league(api_key: str, day: str, league_id: int) -> List[Dict[str, Any]]:
    """
    day: YYYY-MM-DD
    Usa la stagione calcolata dalla data scelta, non da now_utc()
    """
    try:
        dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        season = season_for_date(dt)
    except Exception:
        season = season_for_date(now_utc())

    url = f"{API_FOOTBALL_BASE}/fixtures"
    params = {"date": day, "league": league_id, "season": season}
    data = http_get_json(url, api_football_headers(api_key), params)
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_odds_bookmakers(api_key: str) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/odds/bookmakers"
    data = http_get_json(url, api_football_headers(api_key), {})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 10, show_spinner=False)
def get_fixture_odds(api_key: str, fixture_id: int) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/odds"
    data = http_get_json(url, api_football_headers(api_key), {"fixture": fixture_id})
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
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT del Team A.", season=season)

    fx_next_b = get_team_next_fixtures(api_key, team_b_id, season, nxt=25)
    for fx in fx_next_b:
        if league_id and (fx.get("league", {}) or {}).get("id") != league_id:
            continue
        if fixture_match_teams(fx, team_a_id, team_b_id):
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT del Team B.", season=season)

    return FixturePick(
        fixture=None,
        message="Fixture non trovata (range + next). Analisi basata su ultimi match squadra (fallback).",
        season=season,
    )


# =============================
# ODDS PARSING
# =============================

def normalize_bookmaker_name(name: str) -> str:
    return (name or "").strip().lower()


def normalize_bet_label(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def normalize_value_label(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def choose_bookmaker_from_odds(odds_response: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    candidates = []
    for item in odds_response:
        book = item.get("bookmaker", {}) or {}
        name = book.get("name", "")
        if name:
            candidates.append(item)

    if not candidates:
        return None, "Nessun bookmaker disponibile"

    for item in candidates:
        name = normalize_bookmaker_name((item.get("bookmaker", {}) or {}).get("name", ""))
        if "netbet" in name:
            return item, (item.get("bookmaker", {}) or {}).get("name", "NetBet")

    for pref in FALLBACK_BOOKMAKERS:
        pref_n = pref.lower()
        for item in candidates:
            name = normalize_bookmaker_name((item.get("bookmaker", {}) or {}).get("name", ""))
            if pref_n in name:
                return item, (item.get("bookmaker", {}) or {}).get("name", pref)

    first = candidates[0]
    return first, (first.get("bookmaker", {}) or {}).get("name", "Bookmaker")


def extract_market_odds_from_bookmaker(bookmaker_item: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    bets = bookmaker_item.get("bets", []) or []

    for bet in bets:
        bet_name = normalize_bet_label(bet.get("name", ""))
        values = bet.get("values", []) or []

        if bet_name in {"match winner", "winner", "match result"}:
            for v in values:
                label = normalize_value_label(v.get("value", ""))
                odd = v.get("odd")
                try:
                    odd_f = float(odd)
                except Exception:
                    continue

                if label in {"home", "1"}:
                    out["1"] = odd_f
                elif label in {"draw", "x"}:
                    out["X"] = odd_f
                elif label in {"away", "2"}:
                    out["2"] = odd_f

        elif bet_name in {"double chance"}:
            for v in values:
                label = normalize_value_label(v.get("value", ""))
                odd = v.get("odd")
                try:
                    odd_f = float(odd)
                except Exception:
                    continue

                if label in {"home/draw", "1x"}:
                    out["1X"] = odd_f
                elif label in {"draw/away", "x2"}:
                    out["X2"] = odd_f
                elif label in {"home/away", "12"}:
                    out["12"] = odd_f

        elif "goals over/under" in bet_name or "over/under" in bet_name:
            for v in values:
                label = normalize_value_label(v.get("value", ""))
                odd = v.get("odd")
                try:
                    odd_f = float(odd)
                except Exception:
                    continue

                if label.startswith("over "):
                    raw = label.replace("over ", "").strip()
                    if raw in {"1.5", "2.5", "3.5", "4.5", "5.5"}:
                        out[f"Over {raw}"] = odd_f
                elif label.startswith("under "):
                    raw = label.replace("under ", "").strip()
                    if raw in {"1.5", "2.5", "3.5", "4.5", "5.5"}:
                        out[f"Under {raw}"] = odd_f

        elif bet_name in {"both teams score", "both teams to score"}:
            for v in values:
                label = normalize_value_label(v.get("value", ""))
                odd = v.get("odd")
                try:
                    odd_f = float(odd)
                except Exception:
                    continue

                if label in {"yes", "y"}:
                    out["Goal (BTTS Sì)"] = odd_f
                elif label in {"no", "n"}:
                    out["No Goal (BTTS No)"] = odd_f

    return out


# =============================
# CORNER
# =============================

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_fixture_statistics(api_key: str, fixture_id: int) -> List[Dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE}/fixtures/statistics"
    data = http_get_json(url, api_football_headers(api_key), {"fixture": fixture_id})
    return data.get("response", []) or []


def _extract_corner_kicks(stats_for_team: Dict[str, Any]) -> Optional[int]:
    arr = stats_for_team.get("statistics", []) or []
    for item in arr:
        t = (item.get("type") or "").strip().lower()
        if t in ["corner kicks", "corners", "corner kick"]:
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

    corners_for: List[float] = []
    corners_against: List[float] = []
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

        corners_for.append(float(cf))
        corners_against.append(float(ca))
        corners_total.append(float(cf + ca))

    if len(corners_total) == 0:
        return {
            "matches_used": 0,
            "for_avg": 0.0,
            "against_avg": 0.0,
            "total_avg": 0.0,
            "total_std": 0.0,
            "last5_total_avg": 0.0,
            "trend": 0.0,
        }

    total_avg = _mean(corners_total)
    total_std = _std(corners_total)
    last5 = corners_total[-5:] if len(corners_total) >= 5 else corners_total
    last5_avg = _mean(last5)
    trend = last5_avg - total_avg

    return {
        "matches_used": len(corners_total),
        "for_avg": _mean(corners_for),
        "against_avg": _mean(corners_against),
        "total_avg": total_avg,
        "total_std": total_std,
        "last5_total_avg": last5_avg,
        "trend": trend,
    }


def build_corner_recos(a_c: Dict[str, Any], b_c: Dict[str, Any], a_name: str, b_name: str) -> Dict[str, Any]:
    min_used = min(a_c.get("matches_used", 0), b_c.get("matches_used", 0))
    total_avg_expected = (a_c.get("total_avg", 0.0) + b_c.get("total_avg", 0.0)) / 2.0
    total_std_expected = (a_c.get("total_std", 0.0) + b_c.get("total_std", 0.0)) / 2.0
    trend_expected = (a_c.get("trend", 0.0) + b_c.get("trend", 0.0)) / 2.0

    reasons = []
    if min_used < 6:
        reasons.append("pochi dati corner (meno di 6 match con statistiche)")
    if total_avg_expected < 7.0:
        reasons.append("media corner totale bassa")
    if total_std_expected > 3.2:
        reasons.append("corner molto variabili (rischio alto)")

    no_bet = len(reasons) >= 2

    line_prud = _nearest_corner_line(total_avg_expected - 1.2, lo=3.5, hi=12.5)
    line_med = _nearest_corner_line(total_avg_expected - 0.3, lo=3.5, hi=12.5)
    line_aggr = _nearest_corner_line(total_avg_expected + 0.9, lo=3.5, hi=12.5)

    low1 = _nearest_corner_line(total_avg_expected - 2.2, lo=3.5, hi=12.5)
    low2 = _nearest_corner_line(total_avg_expected - 1.7, lo=3.5, hi=12.5)
    low3 = _nearest_corner_line(total_avg_expected - 1.2, lo=3.5, hi=12.5)

    lows = sorted(list({low1, low2, low3, line_prud}), key=lambda x: x)

    a_for = a_c.get("for_avg", 0.0)
    b_for = b_c.get("for_avg", 0.0)
    team_pick = None
    if a_for >= 5.2 and a_for > b_for + 0.6:
        team_pick = f"{a_name} Team Corners Over 4.5"
    elif b_for >= 5.2 and b_for > a_for + 0.6:
        team_pick = f"{b_name} Team Corners Over 4.5"

    return {
        "no_bet": no_bet,
        "no_bet_reasons": reasons,
        "expected_total_avg": total_avg_expected,
        "expected_total_std": total_std_expected,
        "expected_trend": trend_expected,
        "prudente": f"Over {line_prud:.1f} Corner",
        "medio": f"Over {line_med:.1f} Corner",
        "aggressivo": f"Over {line_aggr:.1f} Corner",
        "low_lines": [f"Over {x:.1f} Corner" for x in lows],
        "team_pick": team_pick,
    }


def parse_corner_line_value(label: str) -> Optional[float]:
    try:
        m = re.search(r"over\s+([0-9]+(?:\.[0-9])?)", label.strip().lower())
        if not m:
            return None
        return float(m.group(1))
    except Exception:
        return None


# =============================
# ANALISI / FORMA
# =============================

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
        return {"matches": 0, "points": 0, "ppg": 0.0, "gf": 0, "ga": 0, "avg_total_goals": 0.0, "form": "", "totals": [], "btts": []}

    avg_total_goals = (gf + ga) / played
    return {
        "matches": played,
        "points": pts,
        "ppg": pts / played,
        "gf": gf,
        "ga": ga,
        "avg_total_goals": avg_total_goals,
        "form": "".join(form[-5:]),
        "totals": totals[-played:],
        "btts": btts[-played:],
    }


def market_rates_from_summary(s: Dict[str, Any]) -> Dict[str, float]:
    totals = s.get("totals", []) or []
    btts = s.get("btts", []) or []
    n = len(totals)
    if n == 0:
        return {"o15": 0.0, "o25": 0.0, "o35": 0.0, "u35": 0.0, "u45": 0.0, "btts_yes": 0.0}
    o15 = sum(1 for t in totals if t >= 2) / n
    o25 = sum(1 for t in totals if t >= 3) / n
    o35 = sum(1 for t in totals if t >= 4) / n
    u35 = sum(1 for t in totals if t <= 3) / n
    u45 = sum(1 for t in totals if t <= 4) / n
    btts_yes = sum(1 for x in btts if x) / n
    return {"o15": o15, "o25": o25, "o35": o35, "u35": u35, "u45": u45, "btts_yes": btts_yes}


def combine_rates(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    keys = set(a.keys()) | set(b.keys())
    return {k: (a.get(k, 0.0) + b.get(k, 0.0)) / 2.0 for k in keys}


def label_risk(market: str) -> str:
    safe = {"Over 1.5", "Under 4.5", "Under 3.5", "1X", "X2", "12"}
    medium = {"Over 2.5", "Goal (BTTS Sì)", "No Goal (BTTS No)", "1", "2"}
    agg = {"Over 3.5", "X"}
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
    best_prob = probs[best_market]

    if best_market == "1":
        why = f"Casa leggermente favorita: indice forma migliore ({home_idx:.2f} vs {away_idx:.2f})."
    elif best_market == "2":
        why = f"Trasferta leggermente favorita: indice forma migliore ({away_idx:.2f} vs {home_idx:.2f})."
    else:
        why = f"Match equilibrato e abbastanza da pareggio: differenza forma ridotta ({abs(diff):.2f}) e media gol ≈ {avg_goals:.2f}."

    return {
        "market": best_market,
        "prob": best_prob,
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
        primary = ("Over 2.5", f"Trend gol alto: Over 2.5 medio ≈ {r['o25']*100:.0f}% (ultimi match). Media gol ≈ {avg_goals:.2f}.")
        alt = [
            ("Under 4.5", f"Linea prudente: Under 4.5 ≈ {r['u45']*100:.0f}%."),
            ("Over 3.5", f"Più aggressivo: Over 3.5 ≈ {r['o35']*100:.0f}%."),
        ]
    elif r["u35"] >= 0.70 and avg_goals <= 2.4:
        primary = ("Under 3.5", f"Trend gol basso: Under 3.5 medio ≈ {r['u35']*100:.0f}%. Media gol ≈ {avg_goals:.2f}.")
        alt = [
            ("Over 1.5", f"Alternativa prudente: Over 1.5 ≈ {r['o15']*100:.0f}%."),
            ("Under 4.5", f"Ancora più coperto: Under 4.5 ≈ {r['u45']*100:.0f}%."),
        ]
    else:
        primary = ("Over 1.5", f"Zona centrale: Over 1.5 ≈ {r['o15']*100:.0f}%. Media gol ≈ {avg_goals:.2f}.")
        alt = [
            ("Over 2.5", f"Se vuoi più quota: Over 2.5 ≈ {r['o25']*100:.0f}%."),
            ("Under 4.5", f"Se vuoi più copertura: Under 4.5 ≈ {r['u45']*100:.0f}%."),
        ]

    btts_yes = r["btts_yes"]
    if btts_yes >= 0.62:
        alt.append(("Goal (BTTS Sì)", f"BTTS Sì alto: ≈ {btts_yes*100:.0f}%."))
    elif btts_yes <= 0.40:
        alt.append(("No Goal (BTTS No)", f"BTTS basso: BTTS Sì ≈ {btts_yes*100:.0f}% → più coerente No Goal."))
    else:
        alt.append(("Goal/NoGoal", f"BTTS medio ≈ {btts_yes*100:.0f}% → decide meglio col LIVE."))

    ppg_h = home_sum.get("ppg", 0.0)
    ppg_a = away_sum.get("ppg", 0.0)
    diff = ppg_h - ppg_a

    if diff >= 0.55:
        outcome = ("1X", f"Casa più in forma nei recenti: PPG {ppg_h:.2f} vs {ppg_a:.2f}.")
    elif diff <= -0.55:
        outcome = ("X2", f"Trasferta più in forma nei recenti: PPG {ppg_a:.2f} vs {ppg_h:.2f}.")
    else:
        outcome = ("12", f"PPG simili ({ppg_h:.2f} vs {ppg_a:.2f}): match aperto (no pareggio).")

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


# =============================
# VALUE ENGINE
# =============================

def market_probability_map(rec: Dict[str, Any]) -> Dict[str, float]:
    rates = rec["meta"]["rates"]
    outright = rec.get("outright", {})
    probs_1x2 = outright.get("probs", {"1": 0.0, "X": 0.0, "2": 0.0})

    return {
        "1": probs_1x2.get("1", 0.0),
        "X": probs_1x2.get("X", 0.0),
        "2": probs_1x2.get("2", 0.0),
        "1X": clamp(probs_1x2.get("1", 0.0) + probs_1x2.get("X", 0.0), 0.0, 1.0),
        "X2": clamp(probs_1x2.get("X", 0.0) + probs_1x2.get("2", 0.0), 0.0, 1.0),
        "12": clamp(probs_1x2.get("1", 0.0) + probs_1x2.get("2", 0.0), 0.0, 1.0),
        "Over 1.5": rates.get("o15", 0.0),
        "Over 2.5": rates.get("o25", 0.0),
        "Over 3.5": rates.get("o35", 0.0),
        "Under 3.5": rates.get("u35", 0.0),
        "Under 4.5": rates.get("u45", 0.0),
        "Goal (BTTS Sì)": rates.get("btts_yes", 0.0),
        "No Goal (BTTS No)": 1.0 - rates.get("btts_yes", 0.0),
    }


def build_value_table(prob_map: Dict[str, float], odds_map: Dict[str, float]) -> List[Dict[str, Any]]:
    rows = []
    for market, prob in prob_map.items():
        odd = odds_map.get(market)
        if odd is None or odd <= 1.0:
            continue
        value_idx = prob * odd
        rows.append({
            "market": market,
            "prob": prob,
            "odd": odd,
            "value_idx": value_idx,
            "risk": label_risk(market),
        })
    rows.sort(key=lambda x: x["value_idx"], reverse=True)
    return rows


def pick_best_single_from_value_table(value_table: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not value_table:
        return None
    return value_table[0]


def pick_combo_suggestion(best_single: Optional[Dict[str, Any]], corner_reco: Dict[str, Any]) -> Dict[str, Any]:
    if not best_single:
        return {
            "ok": False,
            "legs": [],
            "why": ["Nessuna singola disponibile con quote bookmaker."],
            "corner_lines": [],
        }

    if not corner_reco or corner_reco.get("expected_total_avg", 0.0) <= 0:
        return {
            "ok": False,
            "legs": [],
            "why": ["Corner non disponibili per questo match."],
            "corner_lines": [],
        }

    if corner_reco.get("no_bet"):
        return {
            "ok": False,
            "legs": [],
            "why": ["Corner: meglio NON forzare (dati pochi o troppo variabili)."] + corner_reco.get("no_bet_reasons", []),
            "corner_lines": corner_reco.get("low_lines", []),
        }

    lows = corner_reco.get("low_lines", []) or []
    if not lows:
        lows = [corner_reco.get("prudente", "Over 6.5 Corner")]

    best_line = None
    best_val = None
    for lab in lows:
        v = parse_corner_line_value(lab)
        if v is None:
            continue
        if best_val is None or v < best_val:
            best_val = v
            best_line = lab
    best_line = best_line or lows[0]

    why = []
    why.append(f"Base: **{best_single['market']}** (miglior valore quota/probabilità).")
    why.append("Corner: uso una linea bassa per tenere la combinata più prudente.")

    return {
        "ok": True,
        "legs": [best_single["market"], best_line],
        "why": why,
        "corner_lines": lows,
    }


def signal_badge(x: float) -> str:
    if x >= 1.18:
        return "🔵 Valore molto alto"
    if x >= 1.05:
        return "🟣 Valore buono"
    return "🟠 Valore basso"


# =============================
# HELPERS UI
# =============================

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


def analyze_by_team_ids(api_key: str, home_id: int, away_id: int, league_id: Optional[int], home_name: str, away_name: str) -> Dict[str, Any]:
    pick = find_fixture_smart(api_key, home_id, away_id, league_id)
    season = pick.season

    home_last = get_team_last_fixtures(api_key, home_id, season, last=10)
    away_last = get_team_last_fixtures(api_key, away_id, season, last=10)

    home_sum = summarize_form(home_last, home_id)
    away_sum = summarize_form(away_last, away_id)

    inj_home = get_injuries(api_key, home_id, season, league_id if league_id else None)
    inj_away = get_injuries(api_key, away_id, season, league_id if league_id else None)

    rec = recommend_for_match(home_sum, away_sum)

    a_corner = compute_team_corner_profile(api_key, int(home_id), season, last_n=10)
    b_corner = compute_team_corner_profile(api_key, int(away_id), season, last_n=10)
    corner_reco = build_corner_recos(a_corner, b_corner, home_name, away_name)

    odds_map = {}
    bookmaker_used = "N/D"
    if pick.fixture:
        fixture_id = (pick.fixture.get("fixture", {}) or {}).get("id")
        if fixture_id:
            odds_resp = get_fixture_odds(api_key, int(fixture_id))
            bookmaker_item, bookmaker_used = choose_bookmaker_from_odds(odds_resp)
            if bookmaker_item:
                odds_map = extract_market_odds_from_bookmaker(bookmaker_item)

    prob_map = market_probability_map(rec)
    value_table = build_value_table(prob_map, odds_map)
    best_single = pick_best_single_from_value_table(value_table)
    combo_pick = pick_combo_suggestion(best_single, corner_reco)

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
        "corner_a": a_corner,
        "corner_b": b_corner,
        "corner_reco": corner_reco,
        "odds_map": odds_map,
        "bookmaker_used": bookmaker_used,
        "value_table": value_table,
        "best_single": best_single,
        "combo_pick": combo_pick,
    }


# =============================
# TRADING / STOP
# =============================

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


def lay_odds_needed_for_min_profit_if_win(
    back_stake: float,
    back_odds: float,
    lay_stake_: float,
    min_profit_win: float,
    comm: float,
) -> Optional[float]:
    if lay_stake_ <= 0:
        return None
    gross_target = min_profit_win / max(1e-9, (1.0 - comm))
    numerator = back_stake * (back_odds - 1.0) - gross_target
    max_lay_odds = 1.0 + (numerator / lay_stake_)
    if max_lay_odds <= 1.01:
        return None
    return max_lay_odds


def make_stop_plan(
    back_stake: float,
    back_odds: float,
    comm_pct: float,
    max_loss_if_lose: float,
    min_profit_if_win: float,
    stop_steps: List[int],
) -> List[Dict[str, Any]]:
    comm = comm_pct / 100.0
    plan = []

    for s in stop_steps:
        quota_stop = back_odds * (1.0 + s / 100.0)

        lay_stake_ = lay_stake_for_target_loss_when_lose(back_stake, max_loss_if_lose)
        if lay_stake_ <= 0:
            plan.append(
                {
                    "Stop": f"+{s}%",
                    "Quota stop": round(quota_stop, 2),
                    "Banca consigliata": "—",
                    "Esito se VINCI": "—",
                    "Esito se PERDI": "—",
                    "Note": "Impossibile (perdita max troppo bassa rispetto alla puntata).",
                }
            )
            continue

        win_pnl = pnl_if_win(back_stake, back_odds, lay_stake_, quota_stop, comm)
        lose_pnl = pnl_if_lose(back_stake, lay_stake_, comm)

        if win_pnl < min_profit_if_win - 1e-9:
            max_lay = lay_odds_needed_for_min_profit_if_win(back_stake, back_odds, lay_stake_, min_profit_if_win, comm)
            note = "Impossibile (profitto minimo troppo alto o stop troppo aggressivo)."
            if max_lay:
                note += f" Prova quota stop ≤ {max_lay:.2f} oppure abbassa profitto minimo."
            plan.append(
                {
                    "Stop": f"+{s}%",
                    "Quota stop": round(quota_stop, 2),
                    "Banca consigliata": "—",
                    "Esito se VINCI": "—",
                    "Esito se PERDI": "—",
                    "Note": note,
                }
            )
            continue

        if lose_pnl < -max_loss_if_lose - 1e-9:
            plan.append(
                {
                    "Stop": f"+{s}%",
                    "Quota stop": round(quota_stop, 2),
                    "Banca consigliata": "—",
                    "Esito se VINCI": "—",
                    "Esito se PERDI": "—",
                    "Note": "Impossibile (perdita se perdi oltre max).",
                }
            )
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


# =============================
# UI
# =============================

st.set_page_config(page_title="Trading Tool PRO (Calcio)", layout="wide")

st.markdown(
    """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
h1, h2, h3 { letter-spacing: -0.02em; }
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
st.caption("Analisi basata su dati recenti + quote bookmaker. Non è una previsione certa.")

secrets_keys = dict(st.secrets) if hasattr(st, "secrets") else {}
api_football_key = secrets_keys.get("API_FOOTBALL_KEY", "")

with st.expander("🔧 DEBUG (solo se serve)", expanded=False):
    st.json({k: ("***" if "KEY" in k else v) for k, v in secrets_keys.items()})
    if api_football_key:
        st.write(f"API_FOOTBALL_KEY presente (lunghezza {len(api_football_key)}).")
    else:
        st.warning("API_FOOTBALL_KEY NON trovata nei Secrets.")

if not api_football_key:
    st.error("Manca API_FOOTBALL_KEY nei Secrets (Streamlit → Settings → Secrets).")
    st.stop()

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
    combo_pick = res.get("combo_pick")
    value_table = res.get("value_table", [])
    bookmaker_used = res.get("bookmaker_used", "N/D")
    odds_map = res.get("odds_map", {})

    st.success("✅ Analisi pronta")

    if pick.fixture:
        fx = pick.fixture
        fx_date = ((fx.get("fixture", {}) or {}).get("date")) or ""
        league = fx.get("league", {}) or {}
        st.markdown(
            f"""
<div class="card">
<b>{hn} vs {an}</b><br/>
<span class="small-muted">Fixture: {fx_date} | League: {league.get("name","?")} (ID {league.get("id","?")}) | Stagione: {pick.season}/{pick.season+1}</span><br/>
<span class="small-muted">{pick.message}</span><br/>
<span class="small-muted"><b>Bookmaker quote usato:</b> {bookmaker_used}</span>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
<div class="card">
<b>{hn} vs {an}</b><br/>
<span class="small-muted">Stagione stimata: {pick.season}/{pick.season+1}</span><br/>
<span class="small-muted">{pick.message}</span><br/>
<span class="small-muted"><b>Bookmaker quote usato:</b> {bookmaker_used}</span>
</div>
""",
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2, gap="large")

    def team_block(title: str, s: Dict[str, Any], inj_count: int):
        stars = "★" * min(5, max(1, int(round(clamp(s["ppg"], 0.0, 3.0) / 0.6))))
        st.markdown(f"### {title}")
        st.write(f"- Forma (ultimi {s['matches']}): **{stars}**  ({s['form']})")
        st.write(f"- PPG: **{s['ppg']:.2f}**  |  Punti: **{s['points']}**")
        st.write(f"- Gol fatti/subiti: **{s['gf']} / {s['ga']}**")
        st.write(f"- Media gol totali: **{s['avg_total_goals']:.2f}**")
        st.write(f"- Infortuni/Squalifiche (eventi API): **{inj_count}**")

    with c1:
        team_block(f"🏠 {hn}", home_sum, len(inj_home))
    with c2:
        team_block(f"✈️ {an}", away_sum, len(inj_away))

    st.markdown("---")
    st.markdown("## 🎯 Miglior giocata della partita")

    if best_single:
        st.markdown(
            f"""
<div class="card">
<b>✅ Miglior giocata:</b> <span class="badge">{best_single['risk']}</span><br/>
<h3 style="margin-top:8px;margin-bottom:8px;">{best_single['market']} @ {best_single['odd']:.2f}</h3>
<span class="small-muted"><b>Probabilità stimata:</b> {best_single['prob']*100:.0f}% · <b>Indice valore:</b> {best_single['value_idx']:.2f} · {signal_badge(float(best_single['value_idx']))}</span>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.warning("Nessuna quota utile trovata per costruire la miglior giocata automatica.")

    st.markdown("## 1️⃣X️⃣2️⃣ Esito secco")
    outright = rec.get("outright", {})
    probs_1x2 = outright.get("probs", {"1": 0.0, "X": 0.0, "2": 0.0})

    c_1x2a, c_1x2b, c_1x2c = st.columns(3)
    with c_1x2a:
        st.metric("1", f"{probs_1x2.get('1', 0.0)*100:.0f}%")
    with c_1x2b:
        st.metric("X", f"{probs_1x2.get('X', 0.0)*100:.0f}%")
    with c_1x2c:
        st.metric("2", f"{probs_1x2.get('2', 0.0)*100:.0f}%")

    st.caption(f"Scelta 1X2 del modello: {outright.get('market', '-')} — {outright.get('why', '')}")

    st.markdown("---")
    st.markdown("## 💰 Quote bookmaker trovate")
    if odds_map:
        odds_rows = [{"Mercato": k, "Quota": v} for k, v in odds_map.items()]
        st.dataframe(odds_rows, use_container_width=True)
    else:
        st.info("Nessuna quota disponibile da API per questo match.")

    st.markdown("## 📈 Classifica mercati della partita")
    if value_table:
        rows = []
        for r in value_table[:10]:
            rows.append({
                "Mercato": r["market"],
                "Probabilità": f"{r['prob']*100:.0f}%",
                "Quota": f"{r['odd']:.2f}",
                "Indice valore": f"{r['value_idx']:.2f}",
                "Rischio": r["risk"],
            })
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("Nessun mercato quotato disponibile per costruire la classifica value.")

    if combo_pick:
        st.markdown("## ➕ Combinata opzionale")
        if combo_pick.get("ok"):
            legs = combo_pick["legs"]
            st.markdown(
                f"""
<div class="card">
<h3 style="margin-top:8px;margin-bottom:8px;">{legs[0]} + {legs[1]}</h3>
</div>
""",
                unsafe_allow_html=True,
            )
            for r in combo_pick.get("why", []):
                st.write(f"- {r}")
        else:
            for r in combo_pick.get("why", []):
                st.write(f"- {r}")

    st.markdown("---")
    st.markdown("## 🎯 Corner")
    st.caption("Sezione separata: più rischio. Se l’API non dà corner, lo diciamo chiaramente.")

    if not corner_reco or corner_reco.get("expected_total_avg", 0.0) <= 0:
        st.info("Corner: dati non disponibili su questi match (dipende dall’API/piano).")
    else:
        if corner_reco.get("no_bet"):
            st.warning("⚠️ Corner: meglio NON forzare (NO BET).")
            for r in corner_reco.get("no_bet_reasons", []):
                st.write(f"- {r}")
        else:
            st.markdown(
                f"""
<div class="card">
<b>Corner — numeri stimati</b><br/>
<span class="small-muted">Media corner attesa: <b>{corner_reco['expected_total_avg']:.2f}</b> · Variabilità: <b>{corner_reco['expected_total_std']:.2f}</b> · Trend ultimi 5 vs 10: <b>{corner_reco['expected_trend']:+.2f}</b></span>
</div>
""",
                unsafe_allow_html=True,
            )
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.markdown("### 🛡️ Prudente")
                st.write(f"✅ **{corner_reco['prudente']}**")
            with cc2:
                st.markdown("### ⚖️ Medio")
                st.write(f"✅ **{corner_reco['medio']}**")
            with cc3:
                st.markdown("### 🔥 Aggressivo")
                st.write(f"✅ **{corner_reco['aggressivo']}**")

            lows = corner_reco.get("low_lines", []) or []
            if lows:
                st.markdown("**Linee corner più basse (più facili):**")
                st.write(" · ".join(lows[:6]))

            if corner_reco.get("team_pick"):
                st.info(f"💡 Opzione Team Corner: **{corner_reco['team_pick']}**")


# -----------------------------
# TAB 1: ANALISI PRO
# -----------------------------
with tabs[0]:
    st.subheader("📊 Analisi partita (PRO)")

    mode_tabs = st.tabs(["🗓️ Partite del giorno (max 10)", "✍️ Inserisci partita manualmente"])

    with mode_tabs[0]:
        st.markdown("### 🗓️ Partite del giorno")
        st.caption("Include anche Champions League ed Europa League (se ci sono match quel giorno).")

        cA, cB, cC = st.columns([2, 1, 1], gap="large")
        with cA:
            selected_leagues = st.multiselect(
                "Campionati da includere",
                options=list(DEFAULT_LEAGUES.keys()),
                default=st.session_state.get(
                    "selected_leagues",
                    ["Premier League (ENG)", "Serie A (ITA)", "Bundesliga (GER)", "LaLiga (ESP)", "Ligue 1 (FRA)", "Champions League", "Europa League"],
                ),
            )
        with cB:
            d_today = datetime.now().date()
            day_pick = st.date_input("Giorno", value=st.session_state.get("day_pick", d_today))
        with cC:
            max_out = st.number_input("Max partite", min_value=3, max_value=20, value=int(st.session_state.get("max_out", 10)), step=1)

        st.session_state["selected_leagues"] = selected_leagues
        st.session_state["day_pick"] = day_pick
        st.session_state["max_out"] = int(max_out)

        if st.button("🔄 Trova partite", type="primary", use_container_width=True):
            if not selected_leagues:
                st.warning("Seleziona almeno un campionato.")
            else:
                with st.spinner("Carico le partite e preparo la short-list..."):
                    day_str = day_pick.isoformat()

                    all_fx: List[Dict[str, Any]] = []
                    debug_counts = []

                    for lname in selected_leagues:
                        lid = DEFAULT_LEAGUES[lname]
                        fx = get_fixtures_by_date_and_league(api_football_key, day_str, lid)

                        debug_counts.append({
                            "lega": lname,
                            "league_id": lid,
                            "trovate_api": len(fx),
                        })

                        for f in fx:
                            status = (((f.get("fixture", {}) or {}).get("status", {}) or {}).get("short")) or ""
                            if status in {"FT", "AET", "PEN", "CANC", "PST", "ABD"}:
                                continue
                            all_fx.append(f)

                    st.session_state["debug_counts"] = debug_counts

                    all_fx = all_fx[:40]
                    ranked: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []

                    for fx in all_fx:
                        teams = fx.get("teams", {}) or {}
                        league = fx.get("league", {}) or {}

                        home = teams.get("home", {}) or {}
                        away = teams.get("away", {}) or {}
                        home_id = home.get("id")
                        away_id = away.get("id")
                        if not home_id or not away_id:
                            continue

                        result = analyze_by_team_ids(
                            api_football_key,
                            int(home_id),
                            int(away_id),
                            int(league.get("id", 0) or 0) or None,
                            home.get("name", "Home"),
                            away.get("name", "Away"),
                        )

                        best_single = result.get("best_single")
                        if not best_single:
                            continue

                        score = float(best_single["value_idx"])
                        ranked.append((score, fx, result))

                    ranked.sort(key=lambda x: x[0], reverse=True)

                    st.session_state["day_ranked"] = ranked[: int(max_out)]
                    st.session_state["day_choice_idx"] = 0
                    st.session_state["last_analysis_result"] = None
                    st.session_state["last_analysis_source"] = None

        dbg = st.session_state.get("debug_counts", [])
        if dbg:
            st.write("Debug leghe:")
            st.dataframe(dbg, use_container_width=True)

        ranked = st.session_state.get("day_ranked", [])

        if not ranked:
            st.info("Seleziona campionati e premi **Trova partite**.")
        else:
            st.markdown("## ⭐ Migliori giocate del giorno")
            rows_rank = []
            for score, fx, result in ranked[: int(max_out)]:
                teams = fx.get("teams", {}) or {}
                home = (teams.get("home", {}) or {}).get("name", "Home")
                away = (teams.get("away", {}) or {}).get("name", "Away")
                best_single = result.get("best_single", {})
                rows_rank.append({
                    "Partita": f"{home} - {away}",
                    "Giocata consigliata": best_single.get("market", "-"),
                    "Quota": f"{best_single.get('odd', 0.0):.2f}" if best_single else "-",
                    "Probabilità": f"{best_single.get('prob', 0.0)*100:.0f}%" if best_single else "-",
                    "Indice valore": f"{score:.2f}",
                    "Bookmaker": result.get("bookmaker_used", "N/D"),
                    "Rischio": best_single.get("risk", "-"),
                })
            st.dataframe(rows_rank, use_container_width=True)

            labels = [fixture_label(fx) for _, fx, _ in ranked]
            idx = int(st.session_state.get("day_choice_idx", 0))
            idx = max(0, min(idx, len(labels) - 1))
            choice = st.selectbox("Seleziona una partita per vedere il dettaglio", labels, index=idx)
            st.session_state["day_choice_idx"] = labels.index(choice)

            _, _, res_selected = ranked[st.session_state["day_choice_idx"]]

            if st.button("🔎 Apri dettaglio partita", use_container_width=True):
                st.session_state["last_analysis_result"] = res_selected
                st.session_state["last_analysis_source"] = "day"

            res = st.session_state.get("last_analysis_result")
            if res and st.session_state.get("last_analysis_source") == "day":
                render_analysis(res)

    with mode_tabs[1]:
        st.markdown("### ✍️ Inserisci partita manualmente")

        colA, colB = st.columns([2, 1], gap="large")
        with colA:
            match_text = st.text_input("Partita", value=st.session_state.get("match_text", ""), placeholder="Es: AC Milan - Como")
        with colB:
            league_label = st.selectbox("Campionato (consigliato)", options=["Auto"] + list(DEFAULT_LEAGUES.keys()), index=0)
            league_id = None if league_label == "Auto" else DEFAULT_LEAGUES[league_label]

        st.session_state["match_text"] = match_text

        if st.button("🔎 Analizza (manuale)", type="primary", use_container_width=True):
            parsed = parse_match_input(match_text)
            if not parsed:
                st.error("Scrivi la partita tipo: 'Juve - Atalanta' oppure 'Juve-Atalanta'.")
                st.stop()

            home_name_in, away_name_in = parsed

            with st.spinner("Cerco squadre su API-FOOTBALL..."):
                home_candidates = search_team(api_football_key, home_name_in)
                away_candidates = search_team(api_football_key, away_name_in)

            if not home_candidates:
                st.error(f"Non trovo la squadra: {home_name_in}")
                st.stop()
            if not away_candidates:
                st.error(f"Non trovo la squadra: {away_name_in}")
                st.stop()

            def pick_best(cands: List[Dict[str, Any]], q: str) -> Dict[str, Any]:
                qn = norm_team_name(q)
                best = cands[0]
                best_score = -1
                for c in cands:
                    name = (c.get("team", {}) or {}).get("name", "") or ""
                    nn = norm_team_name(name)
                    score = 0
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
                result = analyze_by_team_ids(api_football_key, int(home_id), int(away_id), league_id, home_real, away_real)

            st.session_state["last_analysis_result"] = result
            st.session_state["last_analysis_source"] = "manual"

        res = st.session_state.get("last_analysis_result")
        if res and st.session_state.get("last_analysis_source") == "manual":
            render_analysis(res)


# -----------------------------
# TAB 2: TRADING STOP MANUALE
# -----------------------------
with tabs[1]:
    st.subheader("🧮 Trading / Stop (Manuale)")
    st.caption("Qui inserisci TU quote e importi reali (Betflag/Exchange). Nessuna API necessaria.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        back_stake = st.number_input("Puntata d’ingresso (€)", min_value=1.0, value=float(st.session_state.get("back_stake", 10.0)), step=1.0)
        comm_pct = st.number_input("Commissione exchange (%)", min_value=0.0, max_value=20.0, value=float(st.session_state.get("comm_pct", 5.0)), step=0.5)
    with col2:
        back_odds = st.number_input("Quota d’ingresso (reale)", min_value=1.01, value=float(st.session_state.get("back_odds", 1.80)), step=0.01, format="%.2f")
        market_label = st.selectbox(
            "Che cosa stai giocando?",
            options=["Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5", "Under 3.5", "Under 4.5", "Over 5.5", "Under 5.5", "Goal", "No Goal"],
            index=0,
        )

    st.session_state["back_stake"] = back_stake
    st.session_state["back_odds"] = back_odds
    st.session_state["comm_pct"] = comm_pct

    max_loss_if_lose = st.number_input("Perdita max se PERDI (€)", min_value=0.0, value=float(st.session_state.get("max_loss", 5.0)), step=0.5)
    min_profit_if_win = st.number_input("Profitto minimo se VINCI (€)", min_value=0.0, value=float(st.session_state.get("min_profit", 1.0)), step=0.5)

    st.session_state["max_loss"] = max_loss_if_lose
    st.session_state["min_profit"] = min_profit_if_win

    st.markdown(
        """
<div class="card">
<b>📌 Nota importante</b><br/>
Il calcolo della bancata è uguale per Over e Under: stai facendo <i>BACK</i> e poi <i>LAY</i> sullo stesso mercato.<br/>
<b>STOP:</b> lo usi quando la quota <b>SALE</b> (ti va contro).
</div>
""",
        unsafe_allow_html=True,
    )

    stop_steps = [25, 35, 50]
    st.markdown("## 🛑 Quote STOP pronte")

    if st.button("✅ CALCOLA (aggiorna risultati)", type="primary", use_container_width=True):
        plan = make_stop_plan(
            back_stake=back_stake,
            back_odds=back_odds,
            comm_pct=comm_pct,
            max_loss_if_lose=max_loss_if_lose,
            min_profit_if_win=min_profit_if_win,
            stop_steps=stop_steps,
        )
        st.dataframe(plan, use_container_width=True)

        st.markdown("## 🚪 Uscita adesso (se sei già LIVE)")
        live_odds = st.number_input("Quota LIVE attuale (LAY odds)", min_value=1.01, value=float(st.session_state.get("live_odds", back_odds)), step=0.01, format="%.2f")
        st.session_state["live_odds"] = live_odds

        comm = comm_pct / 100.0
        lay_stake_ = lay_stake_for_target_loss_when_lose(back_stake, max_loss_if_lose)

        if lay_stake_ <= 0:
            st.warning("Perdita max troppo bassa rispetto alla puntata: non c’è una bancata che limiti la perdita come vuoi.")
        else:
            win_p = pnl_if_win(back_stake, back_odds, lay_stake_, live_odds, comm)
            lose_p = pnl_if_lose(back_stake, lay_stake_, comm)
            liab = lay_liability(lay_stake_, live_odds)

            st.markdown(
                f"""
<div class="card">
<b>{market_label}</b><br/>
<b>BANCA consigliata adesso:</b> {lay_stake_:.2f} € @ {live_odds:.2f}<br/>
<b>Liability (rischio):</b> {liab:.2f} €<br/><br/>
<b>Esiti stimati:</b><br/>
- Se VINCI: <b>{win_p:+.2f} €</b><br/>
- Se PERDI: <b>{lose_p:+.2f} €</b><br/>
<span class="small-muted">Stima semplificata: commissione applicata solo su profitto positivo.</span>
</div>
""",
                unsafe_allow_html=True,
            )
    else:
        st.info("Imposta i valori e premi **CALCOLA**.")