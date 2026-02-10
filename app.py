import os
import re
import json
import requests
import streamlit as st
from datetime import datetime, timezone

# =========================
# CONFIG
# =========================
API_BASE = "https://v3.football.api-sports.io"

def get_api_key() -> str:
    # Streamlit Cloud: st.secrets
    if "API_FOOTBALL_KEY" in st.secrets:
        return str(st.secrets["API_FOOTBALL_KEY"]).strip()
    # Fallback locale
    return os.getenv("API_FOOTBALL_KEY", "").strip()

API_KEY = get_api_key()

def api_get(path: str, params: dict | None = None, debug_store: dict | None = None):
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_KEY non trovata. Mettila in Streamlit Secrets.")

    url = f"{API_BASE}{path}"
    headers = {
        "x-apisports-key": API_KEY,   # header corretto per API-Sports
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
        if debug_store is not None:
            debug_store.setdefault("requests", []).append({
                "url": url,
                "params": params,
                "status": r.status_code,
                "text": r.text[:4000],  # non infinito
            })
        r.raise_for_status()
        return r.json(), r.status_code
    except requests.RequestException as e:
        if debug_store is not None:
            debug_store.setdefault("errors", []).append({
                "url": url,
                "params": params,
                "error": str(e),
            })
        raise

def normalize_team_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    return name

def split_match_input(s: str):
    # accetta: "AC Milan - Como" / "Milan-Como" / "Inter vs Napoli"
    s = s.strip()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+vs\s+", "-", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*-\s*", "-", s)
    parts = s.split("-")
    if len(parts) != 2:
        return None, None
    return normalize_team_name(parts[0]), normalize_team_name(parts[1])

def season_guess_yyyy():
    # stagione europea: se siamo tra luglio-dicembre => season = anno corrente
    # se siamo tra gennaio-giugno => season = anno precedente
    now = datetime.now(timezone.utc)
    if now.month >= 7:
        return now.year
    return now.year - 1

def pick_league_id(country: str, league_name: str, debug: dict):
    data, _ = api_get("/leagues", {"country": country, "name": league_name}, debug)
    resp = data.get("response", [])
    if not resp:
        return None, []
    # Prendiamo il primo match più “ufficiale”
    league_id = resp[0]["league"]["id"]
    seasons = [x.get("year") for x in resp[0].get("seasons", []) if "year" in x]
    return league_id, seasons

def find_team_id(team_name: str, league_id: int, season: int, debug: dict):
    # Prova prima con teams + league + season (più preciso)
    data, _ = api_get("/teams", {"search": team_name, "league": league_id, "season": season}, debug)
    resp = data.get("response", [])
    if resp:
        return resp[0]["team"]["id"], resp[0]["team"]["name"]

    # Fallback: search globale
    data2, _ = api_get("/teams", {"search": team_name}, debug)
    resp2 = data2.get("response", [])
    if resp2:
        return resp2[0]["team"]["id"], resp2[0]["team"]["name"]

    return None, None

def find_match_from_next_fixtures(team_a_id: int, team_b_id: int, league_id: int, season: int, debug: dict, next_n: int = 20):
    # Prendo le prossime partite del team A nella lega/season, e cerco se l’avversario è team B
    data, _ = api_get("/fixtures", {"league": league_id, "season": season, "team": team_a_id, "next": next_n}, debug)
    fixtures = data.get("response", [])

    for fx in fixtures:
        home_id = fx["teams"]["home"]["id"]
        away_id = fx["teams"]["away"]["id"]
        if (home_id == team_a_id and away_id == team_b_id) or (home_id == team_b_id and away_id == team_a_id):
            return fx

    return None

# =========================
# UI
# =========================
st.set_page_config(page_title="Analisi Partita (API-Football)", layout="wide")
st.title("⚽ Analisi partita (PRO) — dati reali da API-Football (API-Sports)")

with st.sidebar:
    st.markdown("### Impostazioni")
    debug_on = st.checkbox("Mostra DEBUG", value=True)
    country = st.selectbox("Paese", ["Italy", "England", "Spain", "Germany", "France"], index=0)
    league_name = st.text_input("Nome lega", value="Serie A")
    season_mode = st.selectbox("Stagione", ["Auto", "Manuale"], index=0)
    if season_mode == "Manuale":
        season = st.number_input("Season (YYYY)", min_value=2000, max_value=2100, value=season_guess_yyyy(), step=1)
    else:
        season = season_guess_yyyy()
    next_n = st.slider("Quante prossime partite controllare (next)", 5, 50, 20)

st.caption("Inserisci: `AC Milan - Como` oppure `Inter - Napoli` (anche `vs`).")

match_input = st.text_input("Partita", value="AC Milan - Como")
btn = st.button("🔎 Analizza", type="primary")

debug = {"requests": [], "errors": []} if debug_on else None

# =========================
# RUN
# =========================
if btn:
    try:
        if not API_KEY:
            st.error("❌ Manca API_FOOTBALL_KEY nei Secrets.")
            st.stop()

        # 1) Status (verifica key OK)
        status_data, status_code = api_get("/status", None, debug)
        st.success("✅ API key OK (status 200)")

        # 2) League id + seasons disponibili
        league_id, available_seasons = pick_league_id(country, league_name, debug if debug_on else {})
        if not league_id:
            st.error("❌ Non trovo la lega. Cambia Paese/Nome lega.")
            st.stop()

        st.write(f"**League ID:** {league_id} — **Season stimata:** {season}")

        # 3) Parse input squadra A/B
        a, b = split_match_input(match_input)
        if not a or not b:
            st.error("❌ Formato partita non valido. Esempio: `AC Milan - Como`")
            st.stop()

        # 4) Team IDs
        a_id, a_name_api = find_team_id(a, league_id, season, debug if debug_on else {})
        b_id, b_name_api = find_team_id(b, league_id, season, debug if debug_on else {})

        if not a_id or not b_id:
            st.error("❌ Non riesco a trovare le squadre. Prova a scrivere il nome più completo (es. 'AC Milan').")
            st.stop()

        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"🏠 {a_name_api} (id {a_id})")
        with col2:
            st.subheader(f"✈️ {b_name_api} (id {b_id})")

        # 5) Cerco partita dalle prossime del Team A
        fx = find_match_from_next_fixtures(a_id, b_id, league_id, season, debug if debug_on else {}, next_n=next_n)

        if not fx:
            st.error("❌ Fixture non trovata nelle 'next fixtures' del team. Probabile: season non disponibile nel Free, oppure season/league errate.")

            # Diagnosi: mostro seasons disponibili per questa lega (se API le ritorna)
            if available_seasons:
                st.info(f"Stagioni che l'API dichiara per **{league_name}**: {available_seasons[:30]}{' ...' if len(available_seasons) > 30 else ''}")
                if season not in available_seasons:
                    st.warning(
                        f"La season **{season}** NON è nella lista stagioni della lega: questo è compatibile con limitazione del piano Free."
                    )

            st.stop()

        # 6) Se trovata: mostra info base
        fixture_date = fx["fixture"]["date"]
        venue = fx["fixture"]["venue"]["name"] if fx["fixture"].get("venue") else "N/D"
        st.success("✅ Fixture trovata!")
        st.write(f"**Data:** {fixture_date}")
        st.write(f"**Stadio:** {venue}")

        # risultato/live
        status = fx["fixture"]["status"]["long"]
        st.write(f"**Status:** {status}")

        # Score se esiste
        goals = fx.get("goals", {})
        if goals:
            st.write(f"**Gol:** {goals.get('home')} - {goals.get('away')}")

    except Exception as e:
        st.error(f"Errore: {e}")

# =========================
# DEBUG VIEW
# =========================
if debug_on and debug is not None:
    st.divider()
    st.subheader("🛠 DEBUG (richieste e risposte)")

    with st.expander("DEBUG — Ultime richieste API (url/params/status)"):
        st.json(debug.get("requests", []), expanded=False)

    with st.expander("DEBUG — Errori"):
        st.json(debug.get("errors", []), expanded=False)

