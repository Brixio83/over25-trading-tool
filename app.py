# app.py
# Streamlit app con DEBUG "aggressivo" per capire perché API-Football non trova squadre/partite.
# Incolla tutto in app.py su GitHub e fai deploy su Streamlit Cloud.

import os
import re
import json
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st


# =========================
# CONFIG UI
# =========================
st.set_page_config(
    page_title="Trading Tool PRO (Calcio) — Analisi + Trading (DEBUG)",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (DEBUG)")
st.caption("Questa versione ha DEBUG dettagliati per capire DOVE si rompe: stagione, lega, nomi squadre, fixture, ecc.")


# =========================
# SECRETS / KEYS
# =========================
def get_secret(name: str, default: str = "") -> str:
    # Streamlit Cloud: st.secrets
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    # Fallback: env var
    return os.getenv(name, default)


API_FOOTBALL_KEY = get_secret("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = get_secret("THE_ODDS_API_KEY", "")  # magari ti serve per odds, qui non è obbligatoria

API_BASE = "https://v3.football.api-sports.io"

# =========================
# DEBUG TOGGLE
# =========================
with st.sidebar:
    st.header("⚙️ Impostazioni")
    DEBUG = st.toggle("DEBUG ON", value=True)
    st.caption("Se DEBUG ON: vedi chiamate API, parametri e risultati (senza mostrare la key).")

    st.divider()
    st.subheader("🔑 Stato chiavi (solo info)")
    st.write("API_FOOTBALL_KEY presente:", bool(API_FOOTBALL_KEY))
    if API_FOOTBALL_KEY:
        st.write("Lunghezza key:", len(API_FOOTBALL_KEY))
        st.write("Prime 4:", API_FOOTBALL_KEY[:4] + "…")
    st.write("THE_ODDS_API_KEY presente:", bool(THE_ODDS_API_KEY))
    if THE_ODDS_API_KEY:
        st.write("Lunghezza key:", len(THE_ODDS_API_KEY))
        st.write("Prime 4:", THE_ODDS_API_KEY[:4] + "…")


# =========================
# HELPERS
# =========================
def dbg(title: str, payload):
    """Stampa debug solo se DEBUG attivo."""
    if not DEBUG:
        return
    with st.expander(f"🧪 DEBUG — {title}", expanded=False):
        if isinstance(payload, (dict, list)):
            st.code(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            st.write(payload)


def api_get(endpoint: str, params: dict | None = None, timeout: int = 20):
    """
    GET verso API-Football (API-Sports).
    Ritorna (ok: bool, data: dict, meta: dict)
    """
    url = f"{API_BASE}{endpoint}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY} if API_FOOTBALL_KEY else {}

    meta = {"url": url, "params": params or {}, "status_code": None}

    if not API_FOOTBALL_KEY:
        return False, {"errors": {"token": "Missing API_FOOTBALL_KEY (secrets)"}}, meta

    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        meta["status_code"] = r.status_code
        try:
            data = r.json()
        except Exception:
            data = {"_raw_text": r.text}

        # debug chiamata
        dbg("API GET request", {"url": url, "params": params, "status_code": r.status_code})
        dbg("API GET response (raw)", data)

        if r.status_code != 200:
            return False, data, meta

        # API-Sports spesso mette errori in data["errors"]
        if isinstance(data, dict) and data.get("errors"):
            return False, data, meta

        return True, data, meta

    except Exception as e:
        return False, {"errors": {"exception": str(e)}}, meta


def normalize_team_name(name: str) -> str:
    """Normalizza input utente: toglie spazi extra, uniforma trattini, ecc."""
    name = (name or "").strip()
    # sostituisci vari tipi di trattino con '-'
    name = re.sub(r"[–—−]", "-", name)
    name = re.sub(r"\s+", " ", name)
    return name


def parse_match_input(s: str):
    """
    Accetta input tipo:
    - "Inter - Napoli"
    - "Inter-Napoli"
    - "Inter vs Napoli"
    - "Inter v Napoli"
    """
    raw = s
    s = normalize_team_name(s)
    # prova separatori comuni
    for sep in [" vs ", " v ", " - ", "-", " vs", "v "]:
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) >= 2:
                home = parts[0]
                away = parts[1]
                dbg("Parse partita", {"raw": raw, "normalized": s, "home": home, "away": away, "sep_used": sep})
                return home, away

    dbg("Parse partita (FAIL)", {"raw": raw, "normalized": s})
    return None, None


def season_auto_guess():
    """
    Stima stagione:
    - se siamo da luglio in poi: season = anno corrente
    - altrimenti: season = anno precedente
    Esempio: Feb 2026 -> season 2025 (stagione 2025/26)
    """
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month
    season = year if month >= 7 else year - 1
    dbg("Season auto guess", {"utc_now": now.isoformat(), "month": month, "season": season})
    return season


def find_team_id_by_search(name: str):
    """
    /teams?search=NAME
    Ritorna: (team_id, team_name, raw_team_obj)
    """
    ok, data, meta = api_get("/teams", params={"search": name})
    if not ok:
        dbg("Team search FAIL", {"name": name, "meta": meta, "data": data})
        return None, None, None

    resp = data.get("response", [])
    dbg("Team search results count", {"name": name, "count": len(resp)})

    if not resp:
        return None, None, None

    # prendi il primo risultato
    team_obj = resp[0]
    team_id = team_obj.get("team", {}).get("id")
    team_name = team_obj.get("team", {}).get("name")
    return team_id, team_name, team_obj


def api_status_check():
    ok, data, meta = api_get("/status")
    return ok, data, meta


def find_fixture_h2h(league_id: int, season: int, home_id: int, away_id: int):
    """
    Metodo migliore: h2h (se funziona).
    /fixtures?h2h=home-away&league=&season=&next=1
    """
    params = {
        "h2h": f"{home_id}-{away_id}",
        "league": league_id,
        "season": season,
        "next": 1,
    }
    ok, data, meta = api_get("/fixtures", params=params)
    if not ok:
        dbg("Fixture h2h FAIL", {"params": params, "meta": meta, "data": data})
        return None

    resp = data.get("response", [])
    dbg("Fixture h2h results", {"count": len(resp), "params": params})

    if not resp:
        return None

    return resp[0]


def find_fixture_range(league_id: int, season: int, home_id: int, away_id: int, days_back=30, days_fwd=365):
    """
    Fallback: cerca fixtures della squadra home (o entrambe) in range date e filtra per avversario.
    /fixtures?league=&season=&team=&from=&to=
    """
    now = datetime.now(timezone.utc).date()
    date_from = (now - timedelta(days=days_back)).isoformat()
    date_to = (now + timedelta(days=days_fwd)).isoformat()

    params = {
        "league": league_id,
        "season": season,
        "team": home_id,
        "from": date_from,
        "to": date_to,
    }
    ok, data, meta = api_get("/fixtures", params=params)
    if not ok:
        dbg("Fixture range FAIL", {"params": params, "meta": meta, "data": data})
        return None

    resp = data.get("response", [])
    dbg("Fixture range count", {"count": len(resp), "params": params})

    if not resp:
        return None

    # filtra per avversario
    for fx in resp:
        teams = fx.get("teams", {})
        hid = teams.get("home", {}).get("id")
        aid = teams.get("away", {}).get("id")
        if (hid == home_id and aid == away_id) or (hid == away_id and aid == home_id):
            dbg("Fixture range MATCH FOUND", {"fixture_id": fx.get("fixture", {}).get("id")})
            return fx

    dbg("Fixture range NO MATCH", {"searched_team": home_id, "target_opp": away_id})
    return None


def short_fixture_view(fx: dict):
    if not fx:
        return None
    fixture = fx.get("fixture", {})
    league = fx.get("league", {})
    teams = fx.get("teams", {})
    goals = fx.get("goals", {})
    dt = fixture.get("date")

    return {
        "fixture_id": fixture.get("id"),
        "date": dt,
        "league": f"{league.get('name')} (ID {league.get('id')})",
        "season": league.get("season"),
        "home": teams.get("home", {}).get("name"),
        "away": teams.get("away", {}).get("name"),
        "status": fx.get("fixture", {}).get("status", {}).get("long"),
        "goals_home": goals.get("home"),
        "goals_away": goals.get("away"),
    }


# =========================
# UI: TABS
# =========================
tab1, tab2 = st.tabs(["📊 Analisi partita (DEBUG)", "📉 Trading / Stop (Manuale)"])

# =========================
# TAB 1 — ANALISI (DEBUG)
# =========================
with tab1:
    st.subheader("📊 Analisi partita (DEBUG) — API-Football (API-Sports)")

    colA, colB = st.columns([2, 1])

    with colA:
        match_input = st.text_input("Partita (es. Inter - Napoli)", value="Inter - Napoli")

    with colB:
        # League selector (consigliato Serie A ID 135)
        league_options = {
            "Auto (ti faccio scegliere dopo)": 0,
            "Serie A (ID 135)": 135,
            "Serie B (ID 136)": 136,
            "Premier League (ID 39)": 39,
            "La Liga (ID 140)": 140,
            "Bundesliga (ID 78)": 78,
            "Ligue 1 (ID 61)": 61,
        }
        league_label = st.selectbox("Campionato", list(league_options.keys()), index=1)
        league_id = league_options[league_label]

    st.write("Stagione (auto consigliata):")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        use_auto_season = st.checkbox("Auto", value=True)
    with c2:
        season_manual = st.number_input("Season (anno)", value=2025, step=1)
    with c3:
        st.caption("Esempio: stagione 2025/26 => season = 2025. Se Auto è ON, la calcolo in base alla data attuale.")

    season = season_auto_guess() if use_auto_season else int(season_manual)

    # Debug base input
    dbg("Input base", {"match_input": match_input, "league_id": league_id, "season": season, "use_auto_season": use_auto_season})

    # Pulsanti test
    bcol1, bcol2 = st.columns(2)
    with bcol1:
        if st.button("🧪 Test API /status", use_container_width=True):
            ok, data, meta = api_status_check()
            if ok:
                st.success("✅ /status OK (la key funziona)")
            else:
                st.error("❌ /status FAIL (key/rate limit/problema rete)")
            dbg("Status meta", meta)
            dbg("Status data", data)

    with bcol2:
        st.caption("Suggerimento: prima fai /status. Se è OK, allora il problema è NOME SQUADRE / LEGA / STAGIONE / FIXTURE.")

    st.divider()

    if st.button("🔎 Analizza (DEBUG completo)", type="primary", use_container_width=True):
        home_name, away_name = parse_match_input(match_input)

        if not home_name or not away_name:
            st.error("Non riesco a capire le squadre. Scrivi tipo: 'Inter - Napoli' oppure 'Inter vs Napoli'.")
            st.stop()

        # 1) trova team id
        home_id, home_api_name, home_obj = find_team_id_by_search(home_name)
        away_id, away_api_name, away_obj = find_team_id_by_search(away_name)

        dbg("Team home (search result)", {"input": home_name, "team_id": home_id, "api_name": home_api_name})
        dbg("Team away (search result)", {"input": away_name, "team_id": away_id, "api_name": away_api_name})

        if not home_id or not away_id:
            st.error("❌ Non trovo una o entrambe le squadre con /teams?search=. Questo è un problema di NOMI.")
            st.info("Prova nomi più completi (es. 'Inter' -> 'Inter Milan', 'Milan' -> 'AC Milan').")
            st.stop()

        # 2) se league_id = 0 (Auto) chiedi all’utente
        if league_id == 0:
            st.warning("Hai scelto Campionato=Auto. Seleziona una lega dal menu e riprova.")
            st.stop()

        # 3) prova fixture con h2h
        fx = find_fixture_h2h(league_id=league_id, season=season, home_id=home_id, away_id=away_id)

        # 4) fallback range
        if fx is None:
            fx = find_fixture_range(league_id=league_id, season=season, home_id=home_id, away_id=away_id)

        if fx is None:
            st.error("❌ Fixture non trovata con h2h né con range. Quindi: o LEGA/SEASON è sbagliata, o i team ID non sono quelli giusti.")
            st.info("Guarda i DEBUG per vedere: season calcolata, league_id, risultati fixtures e eventuali errori API.")
            st.stop()

        # 5) Mostra fixture trovata
        view = short_fixture_view(fx)
        st.success("✅ Fixture trovata!")
        st.json(view)

        # 6) Esempio mini-statistiche (semplici) — ultimi match squadra
        st.subheader("📌 Mini-check (ultimi match squadra) — per capire se API risponde")
        col1, col2 = st.columns(2)

        def last_matches(team_id: int, label: str):
            params = {
                "team": team_id,
                "league": league_id,
                "season": season,
                "last": 5,
            }
            ok, data, meta = api_get("/fixtures", params=params)
            dbg(f"Last fixtures {label} meta", meta)
            if not ok:
                st.error(f"{label}: ❌ non riesco a prendere gli ultimi match")
                return

            resp = data.get("response", [])
            st.write(f"**{label}** — ultimi {min(len(resp),5)} match trovati: {len(resp)}")
            rows = []
            for fx0 in resp[:5]:
                rows.append(short_fixture_view(fx0))
            st.dataframe(rows, use_container_width=True)

        with col1:
            last_matches(home_id, f"{home_api_name} (home)")
        with col2:
            last_matches(away_id, f"{away_api_name} (away)")

        st.subheader("🧠 Suggerimenti (trasparenti, NON certezze)")
        st.write(
            "- Se fixture trovata: allora il problema di prima era **stagione/lega/nome**.\n"
            "- Se fixture NON trovata: guarda i debug di **/fixtures** (params, season, league, h2h).\n"
            "- Se /teams trova ma /fixtures no: spesso è **season sbagliata** (deve essere 2025 per 2025/26).\n"
        )

        st.divider()
        st.caption("Quando hai finito i test, spegni DEBUG (sidebar) e poi possiamo pulire il codice togliendo i debug.")


# =========================
# TAB 2 — TRADING (placeholder, qui non tocchiamo)
# =========================
with tab2:
    st.subheader("📉 Trading / Stop (Manuale)")
    st.info("Qui non ho cambiato la logica trading. Questo file è focalizzato sul DEBUG API-Football.")
    st.write("Se vuoi, dopo che risolviamo l’API, reintegriamo la parte trading completa nel tuo app.py.")


# =========================
# NOTE FINALI (per te)
# =========================
if DEBUG:
    st.caption("DEBUG è ON: vedi expander con request/response. Non condividere screenshot con chiavi visibili.")