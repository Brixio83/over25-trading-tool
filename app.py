# app.py
# Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)
# ✅ Modalità 1: "Partite del giorno" (max 10) + click per analisi
# ✅ Modalità 2: Inserimento manuale partita (come prima)
# ✅ Trading / Stop manuale (come prima)
# ✅ AGGIUNTO: Champions League + Europa League (e Conference League opzionale)
#
# --- STREAMLIT SECRETS (Settings → Secrets su Streamlit Cloud) ---
# API_FOOTBALL_KEY = "la_tua_key_api_football"      # obbligatoria
# THE_ODDS_API_KEY = "la_tua_key_odds_api"          # opzionale (non usata qui)
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

DEFAULT_LEAGUES: Dict[str, int] = {
    "Serie A (ITA)": 135,
    "Serie B (ITA)": 136,
    "Premier League (ENG)": 39,
    "LaLiga (ESP)": 140,
    "Bundesliga (GER)": 78,
    "Ligue 1 (FRA)": 61,
    "Eredivisie (NED)": 88,
    "Primeira Liga (POR)": 94,
    # ✅ Coppe Europee
    "Champions League": 2,
    "Europa League": 3,
    "Conference League": 848,  # opzionale ma utile
}

# =============================
# UTILS
# =============================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def season_for_date(dt: datetime) -> int:
    # Stagione = anno di inizio (es. Feb 2026 -> 2025)
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
# API-FOOTBALL (API-Sports)
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
    day: 'YYYY-MM-DD'
    ✅ Per Champions/Europa: la season è comunque "anno inizio" (es. 2025 per 2025/26)
    """
    season = season_for_date(now_utc())
    url = f"{API_FOOTBALL_BASE}/fixtures"
    params = {"date": day, "league": league_id, "season": season}
    data = http_get_json(url, api_football_headers(api_key), params)
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
    medium = {"Over 2.5", "Goal (BTTS Sì)", "No Goal (BTTS No)"}
    agg = {"Over 3.5"}
    if market in safe:
        return "🟩 Prudente"
    if market in medium:
        return "🟨 Medio"
    if market in agg:
        return "🟥 Aggressivo"
    return "🟦 Neutro"


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
        outcome = ("12", f"PPG simili ({ppg_h:.2f} vs {ppg_a:.2f}): match “aperto” (no pareggio).")

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
        "meta": {"avg_goals": avg_goals, "rates": r},
    }


# =============================
# "TOP 10 DEL GIORNO"
# =============================

def clarity_score(home_sum: Dict[str, Any], away_sum: Dict[str, Any]) -> float:
    hr = market_rates_from_summary(home_sum)
    ar = market_rates_from_summary(away_sum)
    r = combine_rates(hr, ar)

    avg_goals = (home_sum.get("avg_total_goals", 0.0) + away_sum.get("avg_total_goals", 0.0)) / 2.0
    ppg_diff = abs(home_sum.get("ppg", 0.0) - away_sum.get("ppg", 0.0))
    btts = r.get("btts_yes", 0.0)

    gol_extreme = abs(avg_goals - 2.5)
    btts_extreme = abs(btts - 0.5) * 1.2
    ppg_component = clamp(ppg_diff, 0.0, 1.5) * 0.7

    return gol_extreme + btts_extreme + ppg_component


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
    }


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

st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)")
st.caption("Analisi basata su dati recenti. Non è una previsione certa.")

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

# -----------------------------
# TAB 1: ANALISI PRO
# -----------------------------
with tabs[0]:
    st.subheader("📊 Analisi partita (PRO)")

    mode_tabs = st.tabs(["🗓️ Partite del giorno (max 10)", "✍️ Inserisci partita manualmente"])

    # ====== MODE 1: Partite del giorno ======
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
                    season = season_for_date(now_utc())

                    all_fx: List[Dict[str, Any]] = []
                    for lname in selected_leagues:
                        lid = DEFAULT_LEAGUES[lname]
                        fx = get_fixtures_by_date_and_league(api_football_key, day_str, lid)
                        for f in fx:
                            status = (((f.get("fixture", {}) or {}).get("status", {}) or {}).get("short")) or ""
                            if status in {"FT", "AET", "PEN", "CANC", "PST", "ABD"}:
                                continue
                            all_fx.append(f)

                    all_fx = all_fx[:40]

                    scored: List[Tuple[float, Dict[str, Any]]] = []
                    for fx in all_fx:
                        teams = fx.get("teams", {}) or {}
                        home = teams.get("home", {}) or {}
                        away = teams.get("away", {}) or {}
                        home_id = home.get("id")
                        away_id = away.get("id")
                        if not home_id or not away_id:
                            continue

                        home_last = get_team_last_fixtures(api_football_key, int(home_id), season, last=10)
                        away_last = get_team_last_fixtures(api_football_key, int(away_id), season, last=10)

                        home_sum = summarize_form(home_last, int(home_id))
                        away_sum = summarize_form(away_last, int(away_id))

                        sc = clarity_score(home_sum, away_sum)
                        scored.append((sc, fx))

                    scored.sort(key=lambda x: x[0], reverse=True)
                    top_fx = [fx for _, fx in scored[: int(max_out)]]

                    st.session_state["day_candidates"] = top_fx
                    st.session_state["day_choice_idx"] = 0
                    st.session_state["last_analysis_result"] = None
                    st.session_state["last_analysis_source"] = None

        candidates = st.session_state.get("day_candidates", [])
        if not candidates:
            st.info("Seleziona campionati e premi **Trova partite**.")
        else:
            labels = [fixture_label(fx) for fx in candidates]
            idx = int(st.session_state.get("day_choice_idx", 0))
            idx = max(0, min(idx, len(labels) - 1))
            choice = st.selectbox("Seleziona una partita", labels, index=idx)
            st.session_state["day_choice_idx"] = labels.index(choice)

            fx_sel = candidates[st.session_state["day_choice_idx"]]
            t = fx_sel.get("teams", {}) or {}
            l = fx_sel.get("league", {}) or {}
            home = t.get("home", {}) or {}
            away = t.get("away", {}) or {}

            home_id = int(home.get("id", 0) or 0)
            away_id = int(away.get("id", 0) or 0)
            home_name = home.get("name", "Home")
            away_name = away.get("name", "Away")
            league_id = int(l.get("id", 0) or 0) or None

            if st.button("🔎 Analizza questa partita", use_container_width=True):
                st.session_state["match_text"] = f"{home_name} - {away_name}"
                with st.spinner("Analizzo..."):
                    result = analyze_by_team_ids(api_football_key, home_id, away_id, league_id, home_name, away_name)
                st.session_state["last_analysis_result"] = result
                st.session_state["last_analysis_source"] = "day"

            res = st.session_state.get("last_analysis_result")
            if res and st.session_state.get("last_analysis_source") == "day":
                pick = res["pick"]
                home_sum = res["home_sum"]
                away_sum = res["away_sum"]
                inj_home = res["inj_home"]
                inj_away = res["inj_away"]
                rec = res["rec"]
                hn = res["home_name"]
                an = res["away_name"]

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
<span class="small-muted">{pick.message}</span>
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
<span class="small-muted">{pick.message}</span>
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
                st.markdown("## 🧠 Consigli (chiari, NON certezze)")

                primary = rec["primary"]
                outcome = rec["outcome"]
                alts = rec["alternatives"]
                rates = rec["meta"]["rates"]

                left, right = st.columns(2, gap="large")
                with left:
                    st.markdown("### ⚽ Goal / Over / Under")
                    st.markdown(
                        f"""
<div class="card">
<b>🎯 Scelta consigliata:</b> <span class="badge">{primary['risk']}</span><br/>
<h3 style="margin-top:8px;margin-bottom:8px;">{primary['market']}</h3>
<span class="small-muted">{primary['why']}</span><br/><br/>
<span class="small-muted">Indicatori: Over1.5 ≈ {rates['o15']*100:.0f}% · Over2.5 ≈ {rates['o25']*100:.0f}% · Over3.5 ≈ {rates['o35']*100:.0f}% · Under4.5 ≈ {rates['u45']*100:.0f}% · BTTS ≈ {rates['btts_yes']*100:.0f}%</span>
</div>
""",
                        unsafe_allow_html=True,
                    )
                    for a in alts:
                        if a["market"] in {"1X", "X2", "12"}:
                            continue
                        st.markdown(
                            f"""
<div class="card">
<b>Alternativa:</b> <span class="badge">{a['risk']}</span><br/>
<b style="font-size:1.1rem;">{a['market']}</b><br/>
<span class="small-muted">{a['why']}</span>
</div>
""",
                            unsafe_allow_html=True,
                        )

                with right:
                    st.markdown("### 🏁 Esito (Doppia Chance)")
                    st.markdown(
                        f"""
<div class="card">
<b>🎯 Scelta consigliata (prudente):</b> <span class="badge">{outcome['risk']}</span><br/>
<h3 style="margin-top:8px;margin-bottom:8px;">{outcome['market']}</h3>
<span class="small-muted">{outcome['why']}</span><br/><br/>
<span class="small-muted"><b>Mini guida:</b> 1X = casa o pareggio · X2 = trasferta o pareggio · 12 = una delle due vince (no pareggio).</span>
</div>
""",
                        unsafe_allow_html=True,
                    )

    # ====== MODE 2: Inserimento manuale ======
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
            pick = res["pick"]
            home_sum = res["home_sum"]
            away_sum = res["away_sum"]
            inj_home = res["inj_home"]
            inj_away = res["inj_away"]
            rec = res["rec"]
            hn = res["home_name"]
            an = res["away_name"]

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
<span class="small-muted">{pick.message}</span>
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
<span class="small-muted">{pick.message}</span>
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
            st.markdown("## 🧠 Consigli (chiari, NON certezze)")

            primary = rec["primary"]
            outcome = rec["outcome"]
            alts = rec["alternatives"]
            rates = rec["meta"]["rates"]

            left, right = st.columns(2, gap="large")
            with left:
                st.markdown("### ⚽ Goal / Over / Under")
                st.markdown(
                    f"""
<div class="card">
<b>🎯 Scelta consigliata:</b> <span class="badge">{primary['risk']}</span><br/>
<h3 style="margin-top:8px;margin-bottom:8px;">{primary['market']}</h3>
<span class="small-muted">{primary['why']}</span><br/><br/>
<span class="small-muted">Indicatori: Over1.5 ≈ {rates['o15']*100:.0f}% · Over2.5 ≈ {rates['o25']*100:.0f}% · Over3.5 ≈ {rates['o35']*100:.0f}% · Under4.5 ≈ {rates['u45']*100:.0f}% · BTTS ≈ {rates['btts_yes']*100:.0f}%</span>
</div>
""",
                    unsafe_allow_html=True,
                )
                for a in alts:
                    if a["market"] in {"1X", "X2", "12"}:
                        continue
                    st.markdown(
                        f"""
<div class="card">
<b>Alternativa:</b> <span class="badge">{a['risk']}</span><br/>
<b style="font-size:1.1rem;">{a['market']}</b><br/>
<span class="small-muted">{a['why']}</span>
</div>
""",
                        unsafe_allow_html=True,
                    )

            with right:
                st.markdown("### 🏁 Esito (Doppia Chance)")
                st.markdown(
                    f"""
<div class="card">
<b>🎯 Scelta consigliata (prudente):</b> <span class="badge">{outcome['risk']}</span><br/>
<h3 style="margin-top:8px;margin-bottom:8px;">{outcome['market']}</h3>
<span class="small-muted">{outcome['why']}</span><br/><br/>
<span class="small-muted"><b>Mini guida:</b> 1X = casa o pareggio · X2 = trasferta o pareggio · 12 = una delle due vince (no pareggio).</span>
</div>
""",
                    unsafe_allow_html=True,
                )

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
```0