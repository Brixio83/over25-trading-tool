# app.py
# Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)
# ✅ FIX: stagione corretta per LEGA (seasons disponibili) + punti di CLASSIFICA (standings)
# ✅ FIX: scelta fixture più vicina a oggi (evita andata/ritorno sbagliati quando ci sono più match)
#
# --- STREAMLIT SECRETS (Settings → Secrets su Streamlit Cloud) ---
# THE_ODDS_API_KEY = "la_tua_key_odds_api"          # opzionale
# API_FOOTBALL_KEY = "la_tua_key_api_football"      # obbligatoria per Analisi PRO
#
# NOTE: Non mettere le API key nel codice/GitHub.

from __future__ import annotations

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


def parse_fx_datetime(fx: Dict[str, Any]) -> Optional[datetime]:
    # fx["fixture"]["date"] è ISO string (es: 2026-02-13T19:45:00+00:00)
    s = ((fx.get("fixture", {}) or {}).get("date")) or None
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


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
    limit: int = 200,
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


@st.cache_data(ttl=60 * 60, show_spinner=False)
def get_league_seasons(api_key: str, league_id: int) -> List[int]:
    """
    Ritorna lista stagioni disponibili per quella lega, es: [2010,...,2025]
    """
    url = f"{API_FOOTBALL_BASE}/leagues"
    data = http_get_json(url, api_football_headers(api_key), {"id": league_id})
    resp = data.get("response", []) or []
    if not resp:
        return []
    seasons = resp[0].get("seasons", []) or []
    out = []
    for s in seasons:
        y = s.get("year")
        if isinstance(y, int):
            out.append(y)
    return sorted(set(out))


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_standings(api_key: str, league_id: int, season: int) -> Dict[str, Any]:
    """
    /standings?league=135&season=2025
    """
    url = f"{API_FOOTBALL_BASE}/standings"
    data = http_get_json(url, api_football_headers(api_key), {"league": league_id, "season": season})
    return data


def pick_season_for_league(api_key: str, league_id: Optional[int]) -> int:
    """
    Stagione stimata (es. Feb 2026 -> 2025), ma se la LEGA non la supporta
    scelgo l'ultima stagione disponibile (max).
    """
    guessed = season_for_date(now_utc())
    if not league_id:
        return guessed
    seasons = get_league_seasons(api_key, league_id)
    if not seasons:
        return guessed
    if guessed in seasons:
        return guessed
    # fallback: usa la stagione più recente disponibile
    return max(seasons)


def extract_team_from_standings(standings_json: Dict[str, Any], team_id: int) -> Optional[Dict[str, Any]]:
    """
    Cerca il team dentro standings response.
    Struttura tipica:
    response[0].league.standings[0] = [ {team, points, goalsDiff, all:{goals:{for,against}}, rank, form, ...}, ... ]
    """
    try:
        resp = standings_json.get("response", []) or []
        if not resp:
            return None
        league = resp[0].get("league", {}) or {}
        standings = league.get("standings", []) or []
        if not standings:
            return None
        table = standings[0] or []
        for row in table:
            tid = (row.get("team", {}) or {}).get("id")
            if tid == team_id:
                return row
        return None
    except Exception:
        return None


def fixture_match_teams_any_order(fx: Dict[str, Any], a_id: int, b_id: int) -> bool:
    teams = fx.get("teams", {}) or {}
    home = (teams.get("home", {}) or {}).get("id")
    away = (teams.get("away", {}) or {}).get("id")
    return (home == a_id and away == b_id) or (home == b_id and away == a_id)


def fixture_match_teams_ordered(fx: Dict[str, Any], home_id: int, away_id: int) -> bool:
    teams = fx.get("teams", {}) or {}
    home = (teams.get("home", {}) or {}).get("id")
    away = (teams.get("away", {}) or {}).get("id")
    return (home == home_id and away == away_id)


@dataclass
class FixturePick:
    fixture: Optional[Dict[str, Any]]
    message: str
    season: int


def choose_best_fixture(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Se ho più match (andata/ritorno/coppette), prendo quello più vicino a "oggi".
    """
    if not candidates:
        return None
    now = now_utc()
    best = None
    best_delta = None
    for fx in candidates:
        dt = parse_fx_datetime(fx)
        if not dt:
            continue
        delta = abs((dt - now).total_seconds())
        if best is None or (best_delta is not None and delta < best_delta):
            best = fx
            best_delta = delta
    return best or candidates[0]


def find_fixture_smart(
    api_key: str,
    team_home_id: int,
    team_away_id: int,
    league_id: Optional[int],
) -> FixturePick:
    """
    Strategia:
      0) stagione = corretta per LEGA (se disponibili)
      1) Range ampio: -120 / +180 giorni (per evitare limiti strani)
      2) Next fixtures del team HOME e cerca AWAY
      3) Next fixtures del team AWAY e cerca HOME
      4) fallback: None
    Nota: qui diamo priorità all'ordine HOME-AWAY inserito dall'utente.
    Se non trova ordered, allora prova any-order.
    """
    season = pick_season_for_league(api_key, league_id)

    dt = now_utc()
    from_dt = dt - timedelta(days=120)
    to_dt = dt + timedelta(days=180)

    candidates_ordered: List[Dict[str, Any]] = []
    candidates_any: List[Dict[str, Any]] = []

    # 1) Range (team HOME)
    fx_range = get_fixtures_in_range(api_key, team_home_id, from_dt, to_dt, season, league_id=league_id)
    for fx in fx_range:
        if fixture_match_teams_ordered(fx, team_home_id, team_away_id):
            candidates_ordered.append(fx)
        elif fixture_match_teams_any_order(fx, team_home_id, team_away_id):
            candidates_any.append(fx)

    best = choose_best_fixture(candidates_ordered) or choose_best_fixture(candidates_any)
    if best:
        return FixturePick(fixture=best, message="Fixture trovata (range ampio) e scelta la più vicina a oggi.", season=season)

    # 2) Next HOME
    fx_next_h = get_team_next_fixtures(api_key, team_home_id, season, nxt=40)
    for fx in fx_next_h:
        if league_id and (fx.get("league", {}) or {}).get("id") != league_id:
            continue
        if fixture_match_teams_ordered(fx, team_home_id, team_away_id):
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT del Team HOME.", season=season)

    # 3) Next AWAY
    fx_next_a = get_team_next_fixtures(api_key, team_away_id, season, nxt=40)
    for fx in fx_next_a:
        if league_id and (fx.get("league", {}) or {}).get("id") != league_id:
            continue
        if fixture_match_teams_ordered(fx, team_home_id, team_away_id):
            return FixturePick(fixture=fx, message="Fixture trovata tra le NEXT del Team AWAY.", season=season)

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
    Calcola su ultimi N match:
      - punti tot e PPG
      - gol fatti/subiti
      - media gol totali partita
      - stringa forma (W/D/L)
    """
    if not last_fixtures:
        return {"matches": 0, "points": 0, "ppg": 0.0, "gf": 0, "ga": 0, "avg_total_goals": 0.0, "form": ""}

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
        return {"matches": 0, "points": 0, "ppg": 0.0, "gf": 0, "ga": 0, "avg_total_goals": 0.0, "form": ""}

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
    Usa heuristiche basate su media gol e ppg (ultimi match).
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
            plan.append({"Stop": f"+{s}%", "Quota stop": round(quota_stop, 2), "Banca consigliata": "—",
                         "Esito se VINCI": "—", "Esito se PERDI": "—",
                         "Note": "Impossibile (perdita max troppo bassa rispetto alla puntata)."})
            continue

        win_pnl = pnl_if_win(back_stake, back_odds, lay_stake_, quota_stop, comm)
        lose_pnl = pnl_if_lose(back_stake, lay_stake_, comm)

        if win_pnl < min_profit_if_win - 1e-9:
            max_lay = lay_odds_needed_for_min_profit_if_win(back_stake, back_odds, lay_stake_, min_profit_if_win, comm)
            note = "Impossibile (profitto minimo troppo alto o stop troppo aggressivo)."
            if max_lay:
                note += f" Prova quota stop ≤ {max_lay:.2f} oppure abbassa profitto minimo."
            plan.append({"Stop": f"+{s}%", "Quota stop": round(quota_stop, 2), "Banca consigliata": "—",
                         "Esito se VINCI": "—", "Esito se PERDI": "—", "Note": note})
            continue

        if lose_pnl < -max_loss_if_lose - 1e-9:
            plan.append({"Stop": f"+{s}%", "Quota stop": round(quota_stop, 2), "Banca consigliata": "—",
                         "Esito se VINCI": "—", "Esito se PERDI": "—",
                         "Note": "Impossibile (perdita se perdi oltre max)."})
            continue

        plan.append(
            {"Stop": f"+{s}%", "Quota stop": round(quota_stop, 2),
             "Banca consigliata": f"{lay_stake_:.2f} €",
             "Esito se VINCI": f"{win_pnl:+.2f} €",
             "Esito se PERDI": f"{lose_pnl:+.2f} €",
             "Note": "OK"}
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

        team_home_name, team_away_name = parsed

        with st.spinner("Cerco squadre su API-FOOTBALL..."):
            home_candidates = search_team(api_football_key, team_home_name)
            away_candidates = search_team(api_football_key, team_away_name)

        if not home_candidates:
            st.error(f"Non trovo la squadra: {team_home_name}")
            st.stop()
        if not away_candidates:
            st.error(f"Non trovo la squadra: {team_away_name}")
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

        home_team = pick_best(home_candidates, team_home_name)
        away_team = pick_best(away_candidates, team_away_name)

        home_id = (home_team.get("team", {}) or {}).get("id")
        away_id = (away_team.get("team", {}) or {}).get("id")
        home_real = (home_team.get("team", {}) or {}).get("name", team_home_name)
        away_real = (away_team.get("team", {}) or {}).get("name", team_away_name)

        if not home_id or not away_id:
            st.error("Errore: ID squadra non disponibile (risposta API inconsistente).")
            st.stop()

        with st.spinner("Cerco fixture (smart) + forma + classifica stagione..."):
            pick = find_fixture_smart(api_football_key, home_id, away_id, league_id)

            # Se user ha messo "Auto" e troviamo una fixture, usiamo la LEGA della fixture
            used_league_id = league_id
            used_league_name = league_label
            if used_league_id is None and pick.fixture:
                used_league_id = (pick.fixture.get("league", {}) or {}).get("id")
                used_league_name = (pick.fixture.get("league", {}) or {}).get("name", "Auto")

            season = pick.season

            # Forma ultimi 10 (trend)
            home_last = get_team_last_fixtures(api_football_key, home_id, season, last=10)
            away_last = get_team_last_fixtures(api_football_key, away_id, season, last=10)
            home_form = summarize_form(home_last, home_id)
            away_form = summarize_form(away_last, away_id)

            # Injuries
            inj_home = get_injuries(api_football_key, home_id, season, used_league_id if used_league_id else None)
            inj_away = get_injuries(api_football_key, away_id, season, used_league_id if used_league_id else None)

            # CLASSIFICA (punti veri di stagione)
            standings_home = None
            standings_away = None
            standings_json = None
            if used_league_id:
                standings_json = get_standings(api_football_key, used_league_id, season)
                standings_home = extract_team_from_standings(standings_json, home_id)
                standings_away = extract_team_from_standings(standings_json, away_id)

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
<b>{home_real} vs {away_real}</b><br/>
<span class="small-muted">Fixture: {fx_date} | League: {league.get("name","?")} (ID {league.get("id","?")}) | Stagione: {season}/{season+1}</span><br/>
<span class="small-muted">{fixture_note}</span>
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
<div class="card">
<b>{home_real} vs {away_real}</b><br/>
<span class="small-muted">Stagione usata: {season}/{season+1} | League: {used_league_name}</span><br/>
<span class="small-muted">{fixture_note}</span>
</div>
""",
                unsafe_allow_html=True,
            )

        c1, c2 = st.columns(2, gap="large")

        def stars_from_ppg(ppg: float) -> str:
            return "★" * min(5, max(1, int(round(clamp(ppg, 0.0, 3.0) / 0.6))))

        def season_block(row: Optional[Dict[str, Any]]) -> List[str]:
            if not row:
                return ["- Classifica stagione: **non disponibile** (serve lega corretta o endpoint non incluso nel piano)."]
            rank = row.get("rank")
            pts = row.get("points")
            all_ = row.get("all", {}) or {}
            goals = all_.get("goals", {}) or {}
            gf = goals.get("for")
            ga = goals.get("against")
            form = row.get("form", "") or ""
            played = all_.get("played")
            win = all_.get("win")
            draw = all_.get("draw")
            lose = all_.get("lose")
            out = []
            out.append(f"- **Classifica stagione**: Pos **{rank}** | Punti **{pts}** | PG {played} (W{win}-D{draw}-L{lose})")
            if gf is not None and ga is not None:
                out.append(f"- **GF/GS stagione**: {gf} / {ga}")
            if form:
                out.append(f"- **Form (API)**: {form} (ultimi match della lega)")
            return out

        def team_block(title: str, form_sum: Dict[str, Any], inj_count: int, standings_row: Optional[Dict[str, Any]]):
            st.markdown(f"### {title}")

            # CLASSIFICA (stagione intera)
            for line in season_block(standings_row):
                st.write(line)

            st.write("**Trend recente (ultimi 10 match)**")
            stars = stars_from_ppg(form_sum["ppg"])
            st.write(f"- Forma (ultimi {form_sum['matches']}): **{stars}**  ({form_sum['form']})")
            st.write(f"- Punti (ultimi 10): **{form_sum['points']}**  (PPG: **{form_sum['ppg']:.2f}**)")
            st.write(f"- Gol fatti/subiti (ultimi 10): **{form_sum['gf']} / {form_sum['ga']}**")
            st.write(f"- Media gol totali (ultimi 10): **{form_sum['avg_total_goals']:.2f}**")
            st.write(f"- Infortunati/Squalificati (da API, se disponibili): **{inj_count}**")

        with c1:
            team_block(f"🏠 {home_real}", home_form, len(inj_home), standings_home)
        with c2:
            team_block(f"✈️ {away_real}", away_form, len(inj_away), standings_away)

        st.markdown("---")
        st.markdown("## 🧠 Suggerimenti (trasparenti, **NON certezze**)")
        for s in suggest_markets(home_form, away_form):
            st.write(f"- {s}")

        with st.expander("📌 Dettagli tecnici (solo se serve)", expanded=False):
            st.write("League usata:", used_league_id, used_league_name)
            st.write("Season usata:", season)
            st.write("Ultimi fixtures HOME:", len(home_last))
            st.write("Ultimi fixtures AWAY:", len(away_last))
            st.write("Injuries HOME:", len(inj_home))
            st.write("Injuries AWAY:", len(inj_away))
            if used_league_id:
                st.write("Standings status:", (standings_json or {}).get("_http_status"))
                # Non stampo JSON enorme per non impallare, ma puoi abilitarlo se vuoi:
                # st.json(standings_json)

# -----------------------------
# TAB 2: TRADING STOP MANUALE
# -----------------------------
with tabs[1]:
    st.subheader("🧮 Trading / Stop (Manuale)")
    st.caption("Qui inserisci TU quote e importi reali (Exchange). Nessuna API necessaria.")

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
<b>📌 Nota importante (Over vs Under)</b><br/>
Il calcolo della bancata è uguale per Over e Under: stai sempre facendo <i>BACK</i> e poi <i>LAY</i> sullo stesso mercato.<br/>
<b>Regola pratica:</b> lo STOP lo usi quando la quota del tuo mercato <b>SALE</b> (ti sta andando contro).
</div>
""",
        unsafe_allow_html=True,
    )

    stop_steps = [25, 35, 50]
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

