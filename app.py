# app.py
# Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)
# ✅ FIX: ricerca fixture "intelligente" (range ampio + next/last fallback) per evitare "tutto 0".
# ✅ Usa API-FOOTBALL (api-sports) + (opzionale) The Odds API per quote (se vuoi).
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


# =============================
# CONSIGLI (più chiari + specifici)
# =============================

def suggest_markets_structured(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Ritorna 2 liste:
      - goals: over/under specifici
      - result: 1X2 / doppia chance con spiegazione semplice
    """
    goals: List[str] = []
    result: List[str] = []

    avg_goals = (a["avg_total_goals"] + b["avg_total_goals"]) / 2.0
    ppg_diff = abs(a["ppg"] - b["ppg"])

    # --- GOALS: consigli specifici ---
    if avg_goals >= 3.6:
        goals.append("📈 Media gol **molto alta** → più coerente: **Over 3.5**.")
        goals.append("🛡️ Se vuoi più prudenza: **Under 4.5** (copre partite da 4 gol).")
    elif avg_goals >= 3.0:
        goals.append("📈 Media gol **alta** → consiglio principale: **Over 2.5**.")
        goals.append("🛡️ Alternativa prudente: **Under 4.5**.")
    elif avg_goals >= 2.4:
        goals.append("📊 Media gol **media** → linea prudente: **Over 1.5**.")
        goals.append("🛡️ Se vuoi coprire gli eccessi: **Under 4.5**.")
    elif avg_goals >= 2.0:
        goals.append("📉 Media gol **bassa** → più sensato: **Under 3.5**.")
        goals.append("✅ Linea prudente alternativa: **Over 1.5** solo se quota buona.")
    else:
        goals.append("📉 Media gol **molto bassa** → più coerente: **Under 2.5**.")
        goals.append("🛡️ Alternativa ancora più safe: **Under 3.5**.")

    goals.append("ℹ️ Nota pratica: queste sono linee “da guardare”, poi decidi con le **quote live**.")

    # --- RESULT: 1X2 / doppia chance con spiegazione ---
    if ppg_diff >= 1.2:
        result.append("🏆 Differenza punti/forma **netta** → puoi valutare esito a favore della squadra più forte.")
        result.append("👉 Opzioni tipiche: **1 fisso** (se gioca in casa) oppure **X2** (se la forte è in trasferta).")
    elif ppg_diff >= 0.6:
        result.append("⚖️ Differenza **moderata** → meglio **Doppia Chance** rispetto al secco 1X2.")
        result.append("👉 Esempi: **1X** (casa non perde) oppure **X2** (trasferta non perde).")
    else:
        result.append("⚠️ Squadre **equilibrate** → il 1X2 è più “casino”. Meglio mercati gol o gestione live.")
        result.append("👉 In questi casi spesso è più pulito lavorare con **Over/Under** o ingresso live.")

    result.append("📌 Mini guida: **1X2** = scegli il risultato secco (1=Casa, X=Pareggio, 2=Trasferta).")
    result.append("📌 **Doppia Chance** = prendi 2 risultati su 3 (1X, X2, 12) → più copertura, quota più bassa.")
    result.append("ℹ️ Ricorda: sono letture su trend recenti, **NON** previsioni.")

    return {"goals": goals, "result": result}


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
            pick = find_fixture_smart(api_football_key, a_id, b_id, league_id)

            a_last = get_team_last_fixtures(api_football_key, a_id, pick.season, last=10)
            b_last = get_team_last_fixtures(api_football_key, b_id, pick.season, last=10)

            a_sum = summarize_form(a_last, a_id)
            b_sum = summarize_form(b_last, b_id)

            inj_a = get_injuries(api_football_key, a_id, pick.season, league_id if league_id else None)
            inj_b = get_injuries(api_football_key, b_id, pick.season, league_id if league_id else None)

        st.success("✅ Analisi pronta")

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

        tips = suggest_markets_structured(a_sum, b_sum)

        st.markdown("## 🧠 Consigli (chiari, **NON certezze**)")

        colG, colR = st.columns(2, gap="large")
        with colG:
            st.markdown("### ⚽ Mercati Goal / Over / Under")
            for s in tips["goals"]:
                st.write(f"- {s}")

        with colR:
            st.markdown("### 🏁 Mercati Esito (1X2 / Doppia Chance)")
            for s in tips["result"]:
                st.write(f"- {s}")

        with st.expander("📌 Dettagli tecnici (solo se serve)", expanded=False):
            st.write("Ultimi fixtures Team A:", len(a_last))
            st.write("Ultimi fixtures Team B:", len(b_last))
            st.write("Injuries A:", len(inj_a))
            st.write("Injuries B:", len(inj_b))

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