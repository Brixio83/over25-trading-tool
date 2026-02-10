# app.py
# ✅ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)
# Versione "pulita e corretta" con:
# - API-Football (API-Sports) integrata bene
# - Ricerca fixture robusta (H2H -> range -> next fixtures team)
# - Season corretta (anno di inizio stagione)
# - Range ampio (±30 giorni) per evitare falsi "non trovata"
# - Debug opzionale (toggle) senza sporcare l'app
#
# REQUISITI:
#   pip install streamlit requests pandas
#
# STREAMLIT SECRETS (Streamlit Cloud -> Settings -> Secrets):
#   API_FOOTBALL_KEY = "xxxx"
#   THE_ODDS_API_KEY = "xxxx"   # opzionale (se vuoi quote)
#
# NOTE: non inserire chiavi nel codice.

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st


# ----------------------------
# Config
# ----------------------------
st.set_page_config(
    page_title="Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)",
    layout="wide",
    initial_sidebar_state="collapsed",
)

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
THE_ODDS_BASE = "https://api.the-odds-api.com/v4"

DEFAULT_TTL = 60 * 10  # 10 min cache


# ----------------------------
# Helpers: Secrets / Keys
# ----------------------------
def get_secret(name: str) -> Optional[str]:
    # Streamlit Cloud: st.secrets
    if name in st.secrets:
        val = st.secrets.get(name)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Local: env var
    val = os.getenv(name)
    if val and val.strip():
        return val.strip()
    return None


def mask_key(k: Optional[str]) -> str:
    if not k:
        return "MISSING"
    if len(k) <= 8:
        return "***"
    return f"{k[:4]}...{k[-4:]}"


API_FOOTBALL_KEY = get_secret("API_FOOTBALL_KEY")
THE_ODDS_API_KEY = get_secret("THE_ODDS_API_KEY")


# ----------------------------
# UI: Header
# ----------------------------
st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)")
st.caption(
    "Analisi basata su dati recenti e disponibilità API. Non è una previsione certa. "
    "Trading manuale: inserisci TU le quote live."
)

tabs = st.tabs(["📊 Analisi partita (PRO)", "📈 Trading / Stop (Manuale)"])


# ----------------------------
# API Client (con debug e retry)
# ----------------------------
class ApiDebug:
    def __init__(self) -> None:
        self.items: List[Tuple[str, Any]] = []

    def add(self, title: str, payload: Any) -> None:
        self.items.append((title, payload))


def _requests_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
    retries: int = 2,
    backoff: float = 1.2,
    dbg: Optional[ApiDebug] = None,
    dbg_title: str = "HTTP GET",
) -> requests.Response:
    last_exc = None
    for i in range(retries + 1):
        try:
            if dbg is not None:
                dbg.add(f"DEBUG — {dbg_title} request", {"url": url, "headers": headers, "params": params})
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if dbg is not None:
                # Non stampiamo tutto se è enorme: ma lasciamo raw per capire il bug.
                dbg.add(f"DEBUG — {dbg_title} response (raw)", {"status_code": r.status_code, "text": r.text[:5000]})
            return r
        except Exception as e:
            last_exc = e
            time.sleep(backoff * (i + 1))
    raise RuntimeError(f"HTTP GET failed: {last_exc}")


@st.cache_data(ttl=DEFAULT_TTL, show_spinner=False)
def api_football_get_cached(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # Questa funzione è cache-data. Non può ricevere dbg, quindi la usiamo per chiamate stabili.
    if not API_FOOTBALL_KEY:
        return {"errors": {"missing_key": "API_FOOTBALL_KEY missing"}, "response": []}

    url = f"{API_FOOTBALL_BASE}{endpoint}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    r = _requests_get(url, headers=headers, params=params, timeout=25, retries=2)
    try:
        return r.json()
    except Exception:
        return {"errors": {"json": "Invalid JSON"}, "raw": r.text}


def api_football_get(endpoint: str, params: Dict[str, Any], dbg: Optional[ApiDebug] = None) -> Dict[str, Any]:
    if not API_FOOTBALL_KEY:
        if dbg is not None:
            dbg.add("DEBUG — API_FOOTBALL_KEY", "MISSING")
        return {"errors": {"missing_key": "API_FOOTBALL_KEY missing"}, "response": []}

    url = f"{API_FOOTBALL_BASE}{endpoint}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    r = _requests_get(url, headers=headers, params=params, timeout=25, retries=2, dbg=dbg, dbg_title=f"API {endpoint}")
    try:
        return r.json()
    except Exception:
        return {"errors": {"json": "Invalid JSON"}, "raw": r.text}


def api_football_status(dbg: Optional[ApiDebug] = None) -> Tuple[int, Dict[str, Any]]:
    js = api_football_get("/status", {}, dbg=dbg)
    # /status normalmente ha "errors": [] se ok.
    # Non facciamo assunzioni: restituiamo un "code" fittizio se non è presente.
    return 200 if "errors" in js else 0, js


# ----------------------------
# Parsing Match Input
# ----------------------------
def parse_match_input(s: str) -> Optional[Tuple[str, str]]:
    if not s:
        return None
    s = s.strip()

    # accetta: "Milan - Como", "Milan vs Como", "Milan v Como"
    s = re.sub(r"\s+", " ", s)
    m = re.split(r"\s*-\s*|\s+vs\s+|\s+v\s+", s, flags=re.IGNORECASE)
    if len(m) != 2:
        return None
    home = m[0].strip()
    away = m[1].strip()
    if not home or not away:
        return None
    return home, away


# ----------------------------
# Season logic (CORRETTA per API-Football)
# API-Football vuole season=anno di INIZIO stagione (es: 2025 per 2025/26).
# ----------------------------
def season_start_year_for_date(dt: datetime) -> int:
    # Regola comune calcio europeo: stagione nuova da luglio/agosto.
    # Usare luglio come cut-off robusto.
    # Feb 2026 -> season = 2025.
    if dt.month >= 7:
        return dt.year
    return dt.year - 1


# ----------------------------
# Leagues (semplici)
# ----------------------------
LEAGUES = [
    ("Auto", None),
    ("Serie A (ID 135)", 135),
    ("Premier League (ID 39)", 39),
    ("LaLiga (ID 140)", 140),
    ("Bundesliga (ID 78)", 78),
    ("Ligue 1 (ID 61)", 61),
    ("Champions League (ID 2)", 2),
    ("Europa League (ID 3)", 3),
]

LEAGUE_LABEL_TO_ID = {lab: lid for lab, lid in LEAGUES}


# ----------------------------
# Team Search
# ----------------------------
def normalize_team_query(name: str) -> str:
    return name.strip()


def search_team(name: str, dbg: Optional[ApiDebug] = None) -> List[Dict[str, Any]]:
    q = normalize_team_query(name)
    js = api_football_get("/teams", {"search": q}, dbg=dbg)
    return js.get("response", []) or []


def pick_best_team_result(name: str, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # Se c'è un match esatto per nome o per "AC Milan" ecc., prendiamo il migliore.
    if not results:
        return None
    target = name.strip().lower()

    def score(item: Dict[str, Any]) -> int:
        team = (item.get("team") or {})
        nm = (team.get("name") or "").lower()
        code = (team.get("code") or "").lower()
        if nm == target:
            return 100
        if target in nm:
            return 90
        if code and target == code:
            return 95
        return 10

    results_sorted = sorted(results, key=score, reverse=True)
    return results_sorted[0]


# ----------------------------
# Fixtures Finder (ROBUSTO)
# - H2H (se league nota)
# - Range largo (±30 giorni)
# - Next fixtures di home (next=50) e filtro away
# ----------------------------
def find_fixture(
    home_id: int,
    away_id: int,
    season_start: int,
    league_id: Optional[int],
    dbg: Optional[ApiDebug] = None,
) -> Optional[Dict[str, Any]]:
    # 1) H2H (se league presente o anche senza, ma meglio con league)
    h2h_params = {"h2h": f"{home_id}-{away_id}", "season": season_start}
    if league_id:
        h2h_params["league"] = league_id
    js_h2h = api_football_get("/fixtures", h2h_params, dbg=dbg)
    resp = js_h2h.get("response", []) or []
    if resp:
        # prendiamo la prossima futura (o la più vicina)
        fixture = pick_closest_future_fixture(resp)
        if fixture:
            return fixture

    if dbg is not None:
        dbg.add("DEBUG — Fixture h2h FAIL", {"params": h2h_params, "result_count": len(resp)})

    # 2) Range ampio: oggi-30 / oggi+30
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=30)).isoformat()
    date_to = (today + timedelta(days=30)).isoformat()
    range_params: Dict[str, Any] = {
        "season": season_start,
        "from": date_from,
        "to": date_to,
    }
    if league_id:
        range_params["league"] = league_id

    js_range = api_football_get("/fixtures", range_params, dbg=dbg)
    resp2 = js_range.get("response", []) or []
    if resp2:
        # filtriamo partite con home/away id matchati
        filtered = []
        for it in resp2:
            teams = it.get("teams", {})
            h = (teams.get("home") or {}).get("id")
            a = (teams.get("away") or {}).get("id")
            if {h, a} == {home_id, away_id}:
                filtered.append(it)
        fixture = pick_closest_future_fixture(filtered) if filtered else pick_closest_future_fixture(resp2)
        if fixture and is_fixture_between(fixture, home_id, away_id):
            return fixture

    if dbg is not None:
        dbg.add("DEBUG — Fixture range FAIL", {"params": range_params, "result_count": len(resp2)})

    # 3) Next fixtures di HOME (next=50) e filtro vs away
    js_next = api_football_get(
        "/fixtures",
        {"team": home_id, "season": season_start, "next": 50},
        dbg=dbg,
    )
    resp3 = js_next.get("response", []) or []
    filtered3 = [it for it in resp3 if is_fixture_between(it, home_id, away_id)]
    fixture = pick_closest_future_fixture(filtered3) if filtered3 else None
    if fixture:
        return fixture

    if dbg is not None:
        dbg.add("DEBUG — Fixture next FAIL", {"params": {"team": home_id, "season": season_start, "next": 50}, "result_count": len(resp3)})

    return None


def is_fixture_between(fx: Dict[str, Any], home_id: int, away_id: int) -> bool:
    teams = fx.get("teams", {})
    h = (teams.get("home") or {}).get("id")
    a = (teams.get("away") or {}).get("id")
    return {h, a} == {home_id, away_id}


def parse_fixture_datetime_utc(fx: Dict[str, Any]) -> Optional[datetime]:
    dt_str = ((fx.get("fixture") or {}).get("date"))  # ISO
    if not dt_str:
        return None
    try:
        # es: "2026-02-08T19:45:00+00:00"
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def pick_closest_future_fixture(fixtures: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not fixtures:
        return None
    now = datetime.now(timezone.utc)
    scored = []
    for fx in fixtures:
        dt = parse_fixture_datetime_utc(fx)
        if not dt:
            continue
        delta = (dt - now).total_seconds()
        # prefer future, ma se tutto passato prendi il più vicino
        scored.append((abs(delta) if delta < 0 else delta, delta, fx))
    if not scored:
        return fixtures[0]
    # prima preferisci future (delta>=0) con delta minimo, altrimenti passato più vicino
    future = [x for x in scored if x[1] >= 0]
    if future:
        return sorted(future, key=lambda x: x[0])[0][2]
    return sorted(scored, key=lambda x: x[0])[0][2]


# ----------------------------
# Stats: ultimi match squadra
# ----------------------------
def get_last_fixtures(team_id: int, season_start: int, league_id: Optional[int], last_n: int = 10, dbg: Optional[ApiDebug] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"team": team_id, "season": season_start, "last": last_n}
    if league_id:
        params["league"] = league_id
    js = api_football_get("/fixtures", params, dbg=dbg)
    return js.get("response", []) or []


def compute_team_form(fixtures: List[Dict[str, Any]], team_id: int) -> Dict[str, Any]:
    pts = 0
    gf = 0
    ga = 0
    played = 0
    form_seq = []

    for fx in fixtures:
        teams = fx.get("teams", {})
        goals = fx.get("goals", {})
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        h_id = home.get("id")
        a_id = away.get("id")

        hg = goals.get("home")
        ag = goals.get("away")
        if hg is None or ag is None:
            continue

        played += 1
        if team_id == h_id:
            gf += int(hg)
            ga += int(ag)
            if hg > ag:
                pts += 3
                form_seq.append("W")
            elif hg == ag:
                pts += 1
                form_seq.append("D")
            else:
                form_seq.append("L")
        elif team_id == a_id:
            gf += int(ag)
            ga += int(hg)
            if ag > hg:
                pts += 3
                form_seq.append("W")
            elif ag == hg:
                pts += 1
                form_seq.append("D")
            else:
                form_seq.append("L")

    ppg = pts / played if played else 0.0
    avg_total_goals = (gf + ga) / played if played else 0.0

    # stelline semplici: 0..5 in base a ppg
    stars = 0
    if played:
        if ppg >= 2.3:
            stars = 5
        elif ppg >= 2.0:
            stars = 4
        elif ppg >= 1.6:
            stars = 3
        elif ppg >= 1.2:
            stars = 2
        elif ppg >= 0.8:
            stars = 1

    return {
        "played": played,
        "points": pts,
        "ppg": ppg,
        "gf": gf,
        "ga": ga,
        "avg_total_goals": avg_total_goals,
        "form_seq": form_seq,
        "stars": stars,
    }


# ----------------------------
# Injuries (se disponibili)
# ----------------------------
def get_injuries(team_id: int, season_start: int, league_id: Optional[int], dbg: Optional[ApiDebug] = None) -> int:
    # API-Football endpoint /injuries supporta filtri team, season e league
    params: Dict[str, Any] = {"team": team_id, "season": season_start}
    if league_id:
        params["league"] = league_id
    js = api_football_get("/injuries", params, dbg=dbg)
    resp = js.get("response", []) or []
    return len(resp)


# ----------------------------
# Suggestions (trasparenti)
# ----------------------------
def make_suggestions(home_stats: Dict[str, Any], away_stats: Dict[str, Any]) -> List[str]:
    tips = []

    # tendenza goal: media totale bassa
    avg_goals = (home_stats["avg_total_goals"] + away_stats["avg_total_goals"]) / 2 if (home_stats["played"] and away_stats["played"]) else 0
    if avg_goals and avg_goals <= 2.4:
        tips.append("Tendenza gol bassa → valuta Under 2.5 / Under 3.5 (con prudenza).")
    elif avg_goals and avg_goals >= 3.2:
        tips.append("Tendenza gol alta → valuta Over 2.5 / Over 3.5 (con prudenza).")
    else:
        tips.append("Tendenza gol media → spesso value su linee live dopo 15–25' guardando ritmo/occasioni.")

    # equilibrio squadre
    diff_ppg = abs(home_stats["ppg"] - away_stats["ppg"])
    if diff_ppg <= 0.25:
        tips.append("Squadre vicine → attenzione all'1X2; spesso value è su linee gol/live.")
    else:
        tips.append("Squadre non equivalenti → evita over-esposizione su 1X2; cerca conferme live (ritmo, tiri, xG se li hai).")

    tips.append("Ricorda: è solo lettura dati recenti, NON una previsione certa.")
    return tips


# ----------------------------
# Odds (opzionale, molto semplice)
# ----------------------------
def odds_available() -> bool:
    return bool(THE_ODDS_API_KEY)


# ----------------------------
# Sidebar / Debug Toggle
# ----------------------------
with st.sidebar:
    st.subheader("⚙️ Impostazioni")
    show_debug = st.toggle("Mostra DEBUG", value=False)
    st.markdown("---")
    st.caption(f"API_FOOTBALL_KEY: `{mask_key(API_FOOTBALL_KEY)}`")
    st.caption(f"THE_ODDS_API_KEY: `{mask_key(THE_ODDS_API_KEY)}`")


# ----------------------------
# TAB 1: Analisi
# ----------------------------
with tabs[0]:
    st.header("📊 Analisi partita (PRO) — dati reali da API-Football (API-Sports)")

    colA, colB = st.columns([2, 1])

    with colA:
        match_str = st.text_input("Partita", value="Milan - Como", help="Esempio: Juventus - Atalanta (o Juve-Atalanta).")

    with colB:
        league_label = st.selectbox("Campionato (consigliato)", [x[0] for x in LEAGUES], index=1)
        league_id = LEAGUE_LABEL_TO_ID.get(league_label)

    now_utc = datetime.now(timezone.utc)
    season_start = season_start_year_for_date(now_utc)

    st.caption(f"Stagione stimata: **{season_start}/{season_start+1}** | League ID: **{league_id if league_id else 'Auto'}**")

    run = st.button("🔎 Analizza", use_container_width=True)

    dbg = ApiDebug()

    # Debug status sempre utile (solo quando premi Analizza)
    if run:
        if not API_FOOTBALL_KEY:
            st.error("Manca API_FOOTBALL_KEY nei Secrets. Vai su Streamlit → App settings → Secrets e inseriscila.")
            st.stop()

        # 1) parse input
        parsed = parse_match_input(match_str)
        if not parsed:
            st.error("Formato non valido. Scrivi tipo: `Milan - Como` oppure `Milan vs Como`.")
            st.stop()
        home_name, away_name = parsed

        # 2) status
        code, status_js = api_football_status(dbg=dbg)
        # non forziamo 200: se l'endpoint risponde bene vedrai in debug.
        # Comunque: se errors contiene token -> problema key
        errors = status_js.get("errors")
        if isinstance(errors, dict) and errors:
            st.warning("API status segnala errori. Guarda DEBUG.")
        st.success("✅ Analisi in corso…")

        # 3) team search
        home_results = search_team(home_name, dbg=dbg)
        away_results = search_team(away_name, dbg=dbg)

        home_pick = pick_best_team_result(home_name, home_results)
        away_pick = pick_best_team_result(away_name, away_results)

        if dbg is not None:
            dbg.add("DEBUG — Team home (search result)", home_results[:10])
            dbg.add("DEBUG — Team away (search result)", away_results[:10])

        if not home_pick or not away_pick:
            st.error("Non riesco a trovare le squadre. Prova a scrivere il nome più completo (es. 'AC Milan' invece di 'Milan').")
            with st.expander("🧰 Dettagli tecnici (search)"):
                st.write({"home_query": home_name, "away_query": away_name})
                st.write({"home_found": len(home_results), "away_found": len(away_results)})
            st.stop()

        home_team = home_pick["team"]
        away_team = away_pick["team"]
        home_id = int(home_team["id"])
        away_id = int(away_team["id"])

        # 4) fixture finder robusto
        fixture = find_fixture(home_id, away_id, season_start, league_id, dbg=dbg)
        if not fixture:
            st.error("❌ Fixture non trovata con h2h, né con range, né con next fixtures. Quindi o LEGA/SEASON è sbagliata, o i team ID non sono quelli giusti.")
            st.info("Guarda i DEBUG per vedere: season calcolata, league_id, risultati fixtures ed eventuali errori API.")
            if show_debug:
                with st.expander("🧪 DEBUG (completo)", expanded=True):
                    for title, payload in dbg.items:
                        st.markdown(f"**{title}**")
                        st.write(payload)
            st.stop()

        fx_info = fixture.get("fixture", {})
        fx_teams = fixture.get("teams", {})
        fx_league = fixture.get("league", {})
        fx_dt = parse_fixture_datetime_utc(fixture)
        fx_date_str = fx_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if fx_dt else "N/D"

        st.markdown("---")
        st.subheader(f"{(fx_teams.get('home') or {}).get('name', home_name)} vs {(fx_teams.get('away') or {}).get('name', away_name)}")
        st.caption(f"Fixture ID: {fx_info.get('id')} | Data: {fx_date_str} | Competizione: {fx_league.get('name')} (ID {fx_league.get('id')})")

        # 5) ultimi match + stats
        with st.spinner("Scarico ultimi match e calcolo forma..."):
            home_last = get_last_fixtures(home_id, season_start, league_id, last_n=10, dbg=dbg)
            away_last = get_last_fixtures(away_id, season_start, league_id, last_n=10, dbg=dbg)
            home_stats = compute_team_form(home_last, home_id)
            away_stats = compute_team_form(away_last, away_id)

        # 6) injuries (se disponibili)
        with st.spinner("Scarico infortuni (se disponibili)..."):
            home_inj = get_injuries(home_id, season_start, league_id, dbg=dbg)
            away_inj = get_injuries(away_id, season_start, league_id, dbg=dbg)

        # 7) UI output
        left, right = st.columns(2)

        def star_bar(n: int) -> str:
            return "★" * n + "☆" * (5 - n)

        with left:
            st.markdown(f"### 🏠 {home_team.get('name')}")
            st.write(f"• Forma (ultimi {home_stats['played']}): **{star_bar(home_stats['stars'])}** ({''.join(home_stats['form_seq'][-10:])})")
            st.write(f"• Punti: **{home_stats['points']}** (PPG: **{home_stats['ppg']:.2f}**)")
            st.write(f"• Gol fatti/subiti: **{home_stats['gf']} / {home_stats['ga']}**")
            st.write(f"• Media gol totali: **{home_stats['avg_total_goals']:.2f}**")
            st.write(f"• Infortunati/Squalificati (da API, se disponibili): **{home_inj}**")

        with right:
            st.markdown(f"### ✈️ {away_team.get('name')}")
            st.write(f"• Forma (ultimi {away_stats['played']}): **{star_bar(away_stats['stars'])}** ({''.join(away_stats['form_seq'][-10:])})")
            st.write(f"• Punti: **{away_stats['points']}** (PPG: **{away_stats['ppg']:.2f}**)")
            st.write(f"• Gol fatti/subiti: **{away_stats['gf']} / {away_stats['ga']}**")
            st.write(f"• Media gol totali: **{away_stats['avg_total_goals']:.2f}**")
            st.write(f"• Infortunati/Squalificati (da API, se disponibili): **{away_inj}**")

        st.markdown("---")
        st.markdown("## 🧠 Suggerimenti (trasparenti, NON certezze)")
        for tip in make_suggestions(home_stats, away_stats):
            st.write(f"• {tip}")

        # 8) Dettagli tecnici
        with st.expander("📌 Dettagli tecnici (solo se serve)"):
            st.write(
                {
                    "season_start": season_start,
                    "league_id": league_id,
                    "home_id": home_id,
                    "away_id": away_id,
                    "fixture_id": (fx_info.get("id")),
                    "fixture_date_utc": fx_date_str,
                }
            )

        # 9) DEBUG completo (opzionale)
        if show_debug:
            with st.expander("🧪 DEBUG (completo)", expanded=False):
                for title, payload in dbg.items:
                    st.markdown(f"**{title}**")
                    st.write(payload)


# ----------------------------
# TAB 2: Trading / Stop Manuale
# ----------------------------
with tabs[1]:
    st.header("📈 Trading / Stop (Manuale)")
    st.caption("Qui non usiamo bot: inserisci TU le quote live e calcoliamo coperture / stop / profitto stimato.")

    c1, c2, c3 = st.columns(3)
    with c1:
        stake = st.number_input("Stake iniziale (€)", min_value=1.0, value=20.0, step=1.0)
        odd_entry = st.number_input("Quota entrata", min_value=1.01, value=1.50, step=0.01, format="%.2f")
    with c2:
        odd_exit = st.number_input("Quota uscita/copertura", min_value=1.01, value=3.50, step=0.01, format="%.2f")
        mode = st.selectbox("Tipo operazione", ["Cashout (stima)", "Copertura Opposta (stima)"])
    with c3:
        fee_pct = st.number_input("Commissioni / slippage (%)", min_value=0.0, value=0.0, step=0.1, format="%.1f")
        st.caption("Se vuoi simulare bookmaker/cambio quota, metti 1–3%.")

    st.markdown("---")

    # Formule semplici (approssimazioni):
    # - Profitto potenziale se vince la prima bet: stake*(odd_entry-1)
    # - Per coprire con bet opposta a quota odd_exit, scegli stake2 per pareggiare i profitti:
    #   stake2 = (stake*odd_entry) / odd_exit  (approccio grezzo, dipende dal mercato reale)
    # Nota: qui è volutamente semplice.

    gross_win = stake * (odd_entry - 1.0)
    st.write(f"📌 Vincita potenziale (se la giocata iniziale passa): **€ {gross_win:.2f}**")

    if mode == "Copertura Opposta (stima)":
        stake2 = (stake * odd_entry) / odd_exit
        # Profitto se passa prima: stake*odd_entry - stake2
        # Profitto se passa seconda: stake2*odd_exit - stake
        profit_if_first = (stake * odd_entry - stake2)
        profit_if_second = (stake2 * odd_exit - stake)

        fee = fee_pct / 100.0
        profit_if_first *= (1 - fee)
        profit_if_second *= (1 - fee)

        st.write(f"🎯 Stake copertura stimato: **€ {stake2:.2f}**")
        st.write(f"✅ Profitto stimato se passa la prima: **€ {profit_if_first:.2f}**")
        st.write(f"✅ Profitto stimato se passa la copertura: **€ {profit_if_second:.2f}**")
        st.info("È una stima semplificata: nei mercati goal/linee (under/over) la copertura reale dipende dal mercato specifico.")
    else:
        # Cashout (stima): valore = stake * (odd_entry / odd_exit) (euristica)
        cashout_est = stake * (odd_entry / odd_exit)
        cashout_est *= (1 - (fee_pct / 100.0))
        pnl = cashout_est - stake
        st.write(f"💸 Cashout stimato: **€ {cashout_est:.2f}**")
        st.write(f"📉 P&L stimato: **€ {pnl:.2f}**")
        st.info("Cashout reale dipende dal bookmaker e dal mercato. Qui è una stima euristica.")


# ----------------------------
# Footer
# ----------------------------
st.markdown("---")
st.caption(
    "Nota: se una partita non viene trovata, quasi sempre è per: season sbagliata (serve anno di inizio), "
    "league errata, range troppo stretto, oppure nomi squadra che non matchano i record dell'API."
)
