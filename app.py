# app.py
# Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)
# ✅ FIX: ricerca fixture "intelligente" (range ampio + next/last fallback) per evitare "tutto 0".
# ✅ Usa API-FOOTBALL (api-sports) + (opzionale) The Odds API per quote (se vuoi).
# ✅ NEW: Modalità Aggressiva (Corner) con 3 livelli: Prudente / Medio / Aggressivo (separata dal resto)
#
# --- STREAMLIT SECRETS (Settings → Secrets su Streamlit Cloud) ---
# THE_ODDS_API_KEY = "la_tua_key_odds_api"          # opzionale
# API_FOOTBALL_KEY = "la_tua_key_api_football"      # obbligatoria per Analisi PRO
#
# NOTE: Non mettere le API key nel codice/GitHub.

from __future__ import annotations

import re
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

# =============================
# CONFIG
# =============================

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
THE_ODDS_BASE = "https://api.the-odds-api.com/v4"

DEFAULT_LEAGUES = {
    "Serie A (ITA)": 135,
    "Serie B (ITA)": 136,
    "Premier League (ENG)": 39,
    "LaLiga (ESP)": 140,
    "Bundesliga (GER)": 78,
    "Ligue 1 (FRA)": 61,
    "Champions League": 2,
    "Europa League": 3,
}

# =============================
# UTILS
# =============================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def season_for_date(dt: datetime) -> int:
    # Calcio: stagione "anno inizio" tipicamente da luglio.
    # Esempio: Feb 2026 -> season 2025
    return dt.year if dt.month >= 7 else dt.year - 1

def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

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
    # accetta: "Juve-Atalanta", "Juve - Atalanta", "Juve vs Atalanta"
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

def _mean(xs: List[float]) -> float:
    return sum(xs) / max(1, len(xs))

def _std(xs: List[float]) -> float:
    if len(xs) <= 1:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

def _nearest_corner_line(x: float) -> float:
    # linee tipiche: 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5
    # arrotonda alla .5 più vicina, poi clamp
    v = round(x * 2.0) / 2.0
    if v.is_integer():
        v += 0.5
    return float(clamp(v, 6.5, 12.5))

# =============================
# API-FOOTBALL (API-SPORTS)
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
def get_team_next_fixtures(api_key: str, team_id: int, season: int, nxt: int = 20) -> List[Dict[str, Any]]:
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

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_fixture_statistics(api_key: str, fixture_id: int) -> List[Dict[str, Any]]:
    # /fixtures/statistics?fixture=XXXX
    url = f"{API_FOOTBALL_BASE}/fixtures/statistics"
    data = http_get_json(url, api_football_headers(api_key), {"fixture": fixture_id})
    return data.get("response", []) or []

def fixture_match_teams(fx: Dict[str, Any], a_id: int, b_id: int) -> bool:
    teams = fx.get("teams", {}) or {}
    home = (teams.get("home", {}) or {}).get("id")
    away = (teams.get("away", {}) or {}).get("id")
    return (home == a_id and away == b_id) or (home == b_id and away == a_id)

def _extract_corner_kicks(stats_for_team: Dict[str, Any]) -> Optional[int]:
    """
    stats_for_team:
      { "team": {...}, "statistics": [ {"type":"Corner Kicks","value": X}, ... ] }
    """
    arr = stats_for_team.get("statistics", []) or []
    for item in arr:
        if (item.get("type") or "").strip().lower() in ["corner kicks", "corners", "corner kick"]:
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

@st.cache_data(ttl=60 * 30, show_spinner=False)
def compute_team_corner_profile(
    api_key: str,
    team_id: int,
    season: int,
    last_n: int = 10,
) -> Dict[str, Any]:
    """
    Usa le ultime N fixture giocate (last fixtures) e per ciascuna prende /fixtures/statistics
    per ottenere Corner Kicks del team e dell'avversario.
    """
    last_fx = get_team_last_fixtures(api_key, team_id, season, last=last_n)
    corners_for: List[float] = []
    corners_against: List[float] = []
    corners_total: List[float] = []
    used_fixtures: int = 0

    for fx in last_fx:
        fixture_id = (fx.get("fixture", {}) or {}).get("id")
        if not fixture_id:
            continue

        # stats per fixture
        resp = get_fixture_statistics(api_key, int(fixture_id))
        if not resp or len(resp) < 2:
            continue

        # trova record del team e dell'avversario
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
        used_fixtures += 1

    if used_fixtures == 0:
        return {
            "matches_used": 0,
            "for_avg": 0.0,
            "against_avg": 0.0,
            "total_avg": 0.0,
            "total_std": 0.0,
            "last5_total_avg": 0.0,
            "trend": 0.0,
            "raw_totals": [],
        }

    total_avg = _mean(corners_total)
    total_std = _std(corners_total)
    last5 = corners_total[-5:] if len(corners_total) >= 5 else corners_total
    last5_avg = _mean(last5)
    trend = last5_avg - total_avg  # positivo = ultimi 5 più alti della media

    return {
        "matches_used": used_fixtures,
        "for_avg": _mean(corners_for),
        "against_avg": _mean(corners_against),
        "total_avg": total_avg,
        "total_std": total_std,
        "last5_total_avg": last5_avg,
        "trend": trend,
        "raw_totals": corners_total,
    }

def build_corner_recos(
    a_c: Dict[str, Any],
    b_c: Dict[str, Any],
    a_name: str,
    b_name: str,
) -> Dict[str, Any]:
    """
    Costruisce 3 livelli di linee corner + eventuale nota NO BET.
    Basato su:
      - media corner totali attesa (media delle due squadre)
      - varianza (std)
      - trend ultimi 5 vs ultimi 10
    """
    # Se pochi dati, niente aggressivo
    min_used = min(a_c.get("matches_used", 0), b_c.get("matches_used", 0))
    total_avg_expected = (a_c.get("total_avg", 0.0) + b_c.get("total_avg", 0.0)) / 2.0
    total_std_expected = (a_c.get("total_std", 0.0) + b_c.get("total_std", 0.0)) / 2.0
    trend_expected = (a_c.get("trend", 0.0) + b_c.get("trend", 0.0)) / 2.0

    # Regole NO BET (semplici ma efficaci)
    reasons = []
    if min_used < 6:
        reasons.append("pochi dati corner (meno di 6 match con statistiche)")
    if total_avg_expected < 7.2:
        reasons.append("media corner totale bassa")
    if total_std_expected > 3.2:
        reasons.append("corner molto variabili (rischio alto)")
    if abs(trend_expected) < 0.2:
        # non è un blocco totale, ma segnala che non c'è spinta trend
        pass

    no_bet = False
    if len(reasons) >= 2:
        no_bet = True

    # linee (3 livelli)
    # Prudente: leggermente sotto la media
    line_prud = _nearest_corner_line(total_avg_expected - 0.7)
    # Medio: intorno alla media
    line_med = _nearest_corner_line(total_avg_expected)
    # Aggressivo: sopra media
    line_aggr = _nearest_corner_line(total_avg_expected + 1.0)

    # team corners (spunto extra)
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
        "team_pick": team_pick,
    }

def build_aggressive_combo_suggestions(
    a_sum: Dict[str, Any],
    b_sum: Dict[str, Any],
    a_name: str,
    b_name: str,
    corners_reco: Dict[str, Any],
) -> List[str]:
    """
    Piccole combo 'spinte' ma con logica.
    Non sono certezze.
    """
    out: List[str] = []
    if corners_reco.get("no_bet"):
        return out

    avg_goals = (a_sum["avg_total_goals"] + b_sum["avg_total_goals"]) / 2.0
    ppg_diff = a_sum["ppg"] - b_sum["ppg"]

    # Base: corners medio come ancora
    anchor = corners_reco.get("medio", "Over 9.5 Corner")

    if avg_goals >= 2.6:
        out.append(f"Combo (spinta): {anchor} + Over 1.5 Gol")
    elif avg_goals <= 2.1:
        out.append(f"Combo (spinta): {anchor} + Under 3.5 Gol")
    else:
        out.append(f"Combo (spinta): {anchor} + Goal/NoGoal da valutare LIVE")

    # Direzione esito se differenza punti netta
    if abs(ppg_diff) >= 0.8:
        if ppg_diff > 0:
            out.append(f"Combo (spinta): {anchor} + 1X ( {a_name} non perde )")
        else:
            out.append(f"Combo (spinta): {anchor} + X2 ( {b_name} non perde )")

    # Team corners se forte
    if corners_reco.get("team_pick"):
        out.append(f"Alternativa Team Corner: {corners_reco['team_pick']}")

    return out

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
    """
    Strategia:
      1) Range ampio: -30 giorni / +90 giorni (stessa season)
      2) Next fixtures (25) del team A e cerca team B
      3) Next fixtures (25) del team B e cerca team A
      4) Se ancora niente: ritorna None e fai analisi su last fixtures (fallback sensato)
    """
    dt = now_utc()
    season = season_for_date(dt)

    from_dt = dt - timedelta(days=30)
    to_dt = dt + timedelta(days=90)

    # 1) Range ampio su team A
    fx_range = get_fixtures_in_range(api_key, team_a_id, from_dt, to_dt, season, league_id=league_id)
    for fx in fx_range:
        if fixture_match_teams(fx, team_a_id, team_b_id):
            return FixturePick(fixture=fx, message="Fixture trovata nel range (-30/+90 giorni).", season=season)

    # 2) Next su A
    fx_next_a = get_team_next_fixtures(api_key, team_a_id, season, nxt=25)
    for fx in fx_next_a:
        if league_id and (fx.get("league", {}) or {}).get("id") != league_id:
            continue
        if fixture_match_teams(fx, team_a_id, team_b_id):
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT del Team A.", season=season)

    # 3) Next su B
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
# ANALISI (semplice, trasparente)
# =============================

def summarize_form(last_fixtures: List[Dict[str, Any]], team_id: int) -> Dict[str, Any]:
    """
    Calcola:
      - punti tot e PPG
      - gol fatti/subiti
      - media gol totali partita
      - stringa forma (W/D/L)
    """
    if not last_fixtures:
        return {
            "matches": 0,
            "points": 0,
            "ppg": 0.0,
            "gf": 0,
            "ga": 0,
            "avg_total_goals": 0.0,
            "form": "",
        }

    pts = 0
    gf = 0
    ga = 0
    form = []

    for fx in last_fixtures:
        teams = fx.get("teams", {}) or {}
        goals = fx.get("goals", {}) or {}
        home = (teams.get("home", {}) or {}).get("id")
        away = (teams.get("away", {}) or {}).get("id")
        gh = goals.get("home")
        ga_ = goals.get("away")

        # se fixture non giocata, skip
        if gh is None or ga_ is None:
            continue

        if home == team_id:
            gf += int(gh)
            ga += int(ga_)
            if gh > ga_:
                pts += 3
                form.append("W")
            elif gh == ga_:
                pts += 1
                form.append("D")
            else:
                form.append("L")
        elif away == team_id:
            gf += int(ga_)
            ga += int(gh)
            if ga_ > gh:
                pts += 3
                form.append("W")
            elif ga_ == gh:
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
    }

def suggest_markets(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    """
    Suggerimenti "trasparenti" e NON predittivi:
    Usa solo heuristiche basate su media gol e ppg.
    """
    sug = []
    avg_goals = (a["avg_total_goals"] + b["avg_total_goals"]) / 2.0
    ppg_diff = abs(a["ppg"] - b["ppg"])

    if avg_goals >= 3.0:
        sug.append("Tendenza gol alta → valuta Over 2.5 / Over 3.5 (con prudenza).")
    elif avg_goals <= 2.1:
        sug.append("Tendenza gol bassa → valuta Under 2.5 / Under 3.5 (con prudenza).")
    else:
        sug.append("Gol medi → mercato goal/over dipende dal live (non c'è edge automatico).")

    if ppg_diff >= 1.0:
        sug.append("Differenza forma/punti alta → 1X2 o Doppia Chance può essere più coerente.")
    else:
        sug.append("Squadre vicine → attenzione al 1X2; spesso value è su linee gol/live.")

    sug.append("Ricorda: è solo lettura dati recenti, NON una previsione.")
    return sug

# =============================
# TRADING / STOP (manuale)
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
}
.pill {
  display: inline-block;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(255,255,255,0.04);
  margin-right: 8px;
  margin-bottom: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)")
st.caption("Analisi basata su dati recenti e disponibilità API. Non è una previsione certa.")

secrets_keys = dict(st.secrets) if hasattr(st, "secrets") else {}
api_football_key = secrets_keys.get("API_FOOTBALL_KEY", "")
the_odds_key = secrets_keys.get("THE_ODDS_API_KEY", "")

with st.expander("🔧 DEBUG (solo se serve)", expanded=False):
    st.write("keys nei secrets →")
    st.json({k: ("***" if "KEY" in k else v) for k, v in secrets_keys.items()})
    if api_football_key:
        st.write(f"DEBUG: API_FOOTBALL_KEY presente (lunghezza {len(api_football_key)}).")
    else:
        st.warning("API_FOOTBALL_KEY NON trovata nei Secrets. Analisi PRO non funzionerà.")

tabs = st.tabs(["📊 Analisi partita (PRO)", "🧮 Trading / Stop (Manuale)"])

# -----------------------------
# TAB 1: ANALISI PRO
# -----------------------------
with tabs[0]:
    st.subheader("📊 Analisi partita (PRO)")

    colA, colB = st.columns([2, 1], gap="large")
    with colA:
        match_text = st.text_input("Partita", value=st.session_state.get("match_text", ""), placeholder="Es: AC Milan - Como")
    with colB:
        league_label = st.selectbox("Campionato (consigliato)", options=["Auto"] + list(DEFAULT_LEAGUES.keys()), index=0)
        league_id = None if league_label == "Auto" else DEFAULT_LEAGUES[league_label]

    st.session_state["match_text"] = match_text
    btn = st.button("🔎 Analizza", type="primary", use_container_width=True)

    if btn:
        if not api_football_key:
            st.error("Manca API_FOOTBALL_KEY nei Secrets di Streamlit. Vai su Settings → Secrets e aggiungila.")
            st.stop()

        parsed = parse_match_input(match_text)
        if not parsed:
            st.error("Scrivi la partita in formato tipo: 'Juve - Atalanta' oppure 'Juve-Atalanta'.")
            st.stop()

        team_a_name, team_b_name = parsed

        with st.spinner("Cerco squadre su API-FOOTBALL..."):
            a_candidates = search_team(api_football_key, team_a_name)
            b_candidates = search_team(api_football_key, team_b_name)

        if not a_candidates:
            st.error(f"Non trovo la squadra: {team_a_name}")
            st.stop()
        if not b_candidates:
            st.error(f"Non trovo la squadra: {team_b_name}")
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

        a_team = pick_best(a_candidates, team_a_name)
        b_team = pick_best(b_candidates, team_b_name)

        a_id = (a_team.get("team", {}) or {}).get("id")
        b_id = (b_team.get("team", {}) or {}).get("id")
        a_real = (a_team.get("team", {}) or {}).get("name", team_a_name)
        b_real = (b_team.get("team", {}) or {}).get("name", team_b_name)

        if not a_id or not b_id:
            st.error("Errore: ID squadra non disponibile (risposta API inconsistente).")
            st.stop()

        with st.spinner("Cerco fixture (smart) e ultimi match per forma..."):
            pick = find_fixture_smart(api_football_key, int(a_id), int(b_id), league_id)

            a_last = get_team_last_fixtures(api_football_key, int(a_id), pick.season, last=10)
            b_last = get_team_last_fixtures(api_football_key, int(b_id), pick.season, last=10)

            a_sum = summarize_form(a_last, int(a_id))
            b_sum = summarize_form(b_last, int(b_id))

            inj_a = get_injuries(api_football_key, int(a_id), pick.season, league_id if league_id else None)
            inj_b = get_injuries(api_football_key, int(b_id), pick.season, league_id if league_id else None)

            # NEW: corner profile (separato)
            a_corner = compute_team_corner_profile(api_football_key, int(a_id), pick.season, last_n=10)
            b_corner = compute_team_corner_profile(api_football_key, int(b_id), pick.season, last_n=10)
            corner_reco = build_corner_recos(a_corner, b_corner, a_real, b_real)
            corner_combos = build_aggressive_combo_suggestions(a_sum, b_sum, a_real, b_real, corner_reco)

        st.success("✅ Analisi pronta")

        # Header match
        fixture_note = pick.message
        if pick.fixture:
            fx = pick.fixture
            fx_date = ((fx.get("fixture", {}) or {}).get("date")) or ""
            league = fx.get("league", {}) or {}
            st.markdown(
                f"""
<div class="card">
<b>{a_real} vs {b_real}</b><br/>
<span class="small-muted">Fixture trovata: {fx_date} | League: {league.get("name","?")} (ID {league.get("id","?")}) | Stagione: {pick.season}/{pick.season+1}</span><br/>
<span class="small-muted">{fixture_note}</span>
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
<div class="card">
<b>{a_real} vs {b_real}</b><br/>
<span class="small-muted">Stagione stimata: {pick.season}/{pick.season+1} | League: {league_label}</span><br/>
<span class="small-muted">{fixture_note}</span>
</div>
""",
                unsafe_allow_html=True,
            )

        c1, c2 = st.columns(2, gap="large")

        def team_block(title: str, s: Dict[str, Any], inj_count: int):
            stars = "★" * min(5, max(1, int(round(clamp(s["ppg"], 0.0, 3.0) / 0.6))))
            st.markdown(f"### {title}")
            st.write(f"- Forma (ultimi {s['matches']}): **{stars}**  ({s['form']})")
            st.write(f"- Punti: **{s['points']}**  (PPG: **{s['ppg']:.2f}**)")
            st.write(f"- Gol fatti/subiti: **{s['gf']} / {s['ga']}**")
            st.write(f"- Media gol totali: **{s['avg_total_goals']:.2f}**")
            st.write(f"- Infortunati/Squalificati (da API, se disponibili): **{inj_count}**")

        with c1:
            team_block(f"🏠 {a_real}", a_sum, len(inj_a))
        with c2:
            team_block(f"✈️ {b_real}", b_sum, len(inj_b))

        st.markdown("---")
        st.markdown("## 🧠 Suggerimenti (trasparenti, **NON certezze**)")
        for s in suggest_markets(a_sum, b_sum):
            st.write(f"- {s}")

        # =============================
        # NEW: MODALITÀ AGGRESSIVA (CORNER) - SEPARATA
        # =============================
        st.markdown("---")
        st.markdown("## 🎯 Modalità Aggressiva (Corner) — **3 livelli**")
        st.caption("Questa sezione è più “spinta”: stake più piccolo e più rischio. Basata su trend corner reali (ultimi match).")

        if corner_reco.get("no_bet"):
            rs = corner_reco.get("no_bet_reasons", [])
            st.warning("⚠️ Meglio NON forzare i corner su questa partita (NO BET).")
            if rs:
                st.write("Motivi principali:")
                for r in rs:
                    st.write(f"- {r}")
        else:
            # riepilogo numeri
            exp_avg = corner_reco.get("expected_total_avg", 0.0)
            exp_std = corner_reco.get("expected_total_std", 0.0)
            exp_tr = corner_reco.get("expected_trend", 0.0)

            st.markdown(
                f"""
<div class="card">
<b>Corner — stima da trend recenti</b><br/>
<span class="pill">Media corner totali attesa: <b>{exp_avg:.2f}</b></span>
<span class="pill">Variabilità (std): <b>{exp_std:.2f}</b></span>
<span class="pill">Trend ultimi 5 vs 10: <b>{exp_tr:+.2f}</b></span>
</div>
""",
                unsafe_allow_html=True,
            )

            colx1, colx2, colx3 = st.columns(3, gap="large")
            with colx1:
                st.markdown("### 🛡️ Prudente")
                st.write(f"✅ **{corner_reco['prudente']}**")
                st.caption("Linea più bassa: più probabilità, quota più bassa.")
            with colx2:
                st.markdown("### ⚖️ Medio")
                st.write(f"✅ **{corner_reco['medio']}**")
                st.caption("Linea “centrale”: equilibrio tra rischio e quota.")
            with colx3:
                st.markdown("### 🔥 Aggressivo")
                st.write(f"✅ **{corner_reco['aggressivo']}**")
                st.caption("Linea più alta: più quota, più rischio.")

            if corner_reco.get("team_pick"):
                st.info(f"💡 Opzione Team Corner: **{corner_reco['team_pick']}**")

            if corner_combos:
                st.markdown("### 💥 Combo più spinte (stake piccolo)")
                st.caption("Sono solo idee basate sui trend, non previsioni.")
                for c in corner_combos:
                    st.write(f"- {c}")

        with st.expander("📌 Dettagli tecnici (solo se serve)", expanded=False):
            st.write("Ultimi fixtures Team A:", len(a_last))
            st.write("Ultimi fixtures Team B:", len(b_last))
            st.write("Injuries A:", len(inj_a))
            st.write("Injuries B:", len(inj_b))
            st.write("---")
            st.write("Corner profile A:", a_corner)
            st.write("Corner profile B:", b_corner)

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
            options=["Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5", "Under 3.5", "Under 4.5", "Over 5.5", "Under 5.5", "Goal", "No Goal", "Corner Over 8.5", "Corner Over 9.5", "Corner Over 10.5"],
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
<b>📌 Nota importante (Over vs Under)</b><br/>
Il calcolo della bancata è uguale per Over e Under: stai sempre facendo <i>BACK</i> e poi <i>LAY</i> sullo stesso mercato.<br/>
<b>Regola pratica:</b> lo STOP lo usi quando la quota del tuo mercato <b>SALE</b> (ti sta andando contro).
</div>
""",
        unsafe_allow_html=True,
    )

    stop_steps = [25, 35, 50]  # puoi cambiare qui facilmente
    st.markdown("## 🛑 Quote STOP pronte (ti prepari prima)")

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
<b>Liability (rischio se esce il mercato):</b> {liab:.2f} €<br/><br/>
<b>Esiti stimati:</b><br/>
- Se VINCI: <b>{win_p:+.2f} €</b><br/>
- Se PERDI: <b>{lose_p:+.2f} €</b><br/>
<span class="small-muted">Nota: stima semplificata con commissione applicata solo su profitto positivo.</span>
</div>
""",
                unsafe_allow_html=True,
            )
    else:
        st.info("Imposta i valori e premi **CALCOLA**.")

# =============================
# The Odds API (opzionale)
# =============================
# Lasciata fuori dall'analisi per evitare confusione:
# Qui usiamo manuale per quote (come mi hai chiesto).
# Se vuoi reinserire quote automatiche in un secondo momento, lo facciamo in modo “safe”.