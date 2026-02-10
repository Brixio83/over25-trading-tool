import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
import re

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(page_title="Trading Tool PRO (Calcio)", layout="wide")

API_BASE = "https://v3.football.api-sports.io"
DEFAULT_LEAGUES = {
    "Serie A (ID 135)": 135,
    "Premier League (ID 39)": 39,
    "LaLiga (ID 140)": 140,
    "Bundesliga (ID 78)": 78,
    "Ligue 1 (ID 61)": 61,
}

# ----------------------------
# SECRETS
# ----------------------------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

API_FOOTBALL_KEY = get_secret("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = get_secret("THE_ODDS_API_KEY", "")

# ----------------------------
# HELPERS
# ----------------------------
def season_for_today_utc() -> int:
    """
    API-Football usa 'season' = anno di INIZIO stagione.
    Esempio: 2025/26 -> season=2025
    """
    now = datetime.now(timezone.utc)
    # stagione calcio europea: parte circa ad agosto
    return now.year if now.month >= 8 else now.year - 1


def api_get(path: str, params: dict | None = None) -> tuple[dict, int]:
    headers = {"x-apisports-key": API_FOOTBALL_KEY} if API_FOOTBALL_KEY else {}
    url = f"{API_BASE}{path}"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        return r.json(), r.status_code
    except Exception as e:
        return {"errors": {"exception": str(e)}, "response": []}, 0


def clean_team_name(s: str) -> str:
    s = s.strip()
    # normalizza separatori tipo "Milan vs Como", "Milan - Como"
    s = re.sub(r"\s+vs\s+", " - ", s, flags=re.I)
    s = re.sub(r"\s*-\s*", " - ", s)
    return s


def parse_match_input(s: str) -> tuple[str, str] | None:
    s = clean_team_name(s)
    if " - " not in s:
        return None
    a, b = s.split(" - ", 1)
    return a.strip(), b.strip()


def pick_best_team(team_response: list, wanted: str) -> dict | None:
    """
    team_response: lista di oggetti API-Football /teams.
    Prova a prendere il match più sensato per nome.
    """
    if not team_response:
        return None
    w = wanted.lower().strip()

    # 1) match esatto
    for item in team_response:
        name = (item.get("team", {}).get("name") or "").lower()
        if name == w:
            return item

    # 2) contiene
    for item in team_response:
        name = (item.get("team", {}).get("name") or "").lower()
        if w in name or name in w:
            return item

    # 3) fallback: primo
    return team_response[0]


def last_n_form(fixtures: list, team_id: int, n: int = 5) -> str:
    """
    Restituisce stringa tipo 'WDLWW' sugli ultimi n match.
    fixtures: lista response /fixtures
    """
    res = []
    for fx in fixtures[:n]:
        teams = fx.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        goals = fx.get("goals", {})
        gh = goals.get("home")
        ga = goals.get("away")
        if gh is None or ga is None:
            continue

        if home.get("id") == team_id:
            if gh > ga:
                res.append("W")
            elif gh < ga:
                res.append("L")
            else:
                res.append("D")
        elif away.get("id") == team_id:
            if ga > gh:
                res.append("W")
            elif ga < gh:
                res.append("L")
            else:
                res.append("D")
    return "".join(res) if res else "—"


def compute_basic_stats(fixtures: list, team_id: int, n: int = 5) -> dict:
    """
    Calcola punti, gol fatti/subiti e media gol totale sugli ultimi n match.
    """
    points = 0
    gf = 0
    ga = 0
    counted = 0

    for fx in fixtures[:n]:
        teams = fx.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        goals = fx.get("goals", {})
        gh = goals.get("home")
        ga_ = goals.get("away")
        if gh is None or ga_ is None:
            continue

        if home.get("id") == team_id:
            gf += gh
            ga += ga_
            if gh > ga_:
                points += 3
            elif gh == ga_:
                points += 1
            counted += 1

        elif away.get("id") == team_id:
            gf += ga_
            ga += gh
            if ga_ > gh:
                points += 3
            elif ga_ == gh:
                points += 1
            counted += 1

        if counted >= n:
            break

    ppg = (points / counted) if counted else 0.0
    avg_total_goals = ((gf + ga) / counted) if counted else 0.0

    return {
        "counted": counted,
        "points": points,
        "ppg": ppg,
        "gf": gf,
        "ga": ga,
        "avg_total_goals": avg_total_goals,
    }


# ----------------------------
# UI
# ----------------------------
st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)")
st.caption("Analisi basata su dati recenti e disponibilità API. Non è una previsione certa. Trading manuale: inserisci TU le quote live.")

tab1, tab2 = st.tabs(["📊 Analisi partita (PRO)", "📈 Trading / Stop (Manuale)"])

with tab1:
    if not API_FOOTBALL_KEY:
        st.error("Manca API_FOOTBALL_KEY nei Secrets. Aggiungila in Streamlit → Settings → Secrets.")
        st.stop()

    colA, colB = st.columns([2, 1])
    with colA:
        match_input = st.text_input("Partita", value="AC Milan - Como", help="Esempio: Juventus - Atalanta (anche 'vs').")
    with colB:
        league_label = st.selectbox("Campionato (consigliato)", ["Auto"] + list(DEFAULT_LEAGUES.keys()), index=0)

    season = season_for_today_utc()

    st.markdown(f"**Stagione stimata:** {season}/{season+1}")

    analyze = st.button("🔎 Analizza", type="primary")

    if analyze:
        parsed = parse_match_input(match_input)
        if not parsed:
            st.error("Formato non valido. Usa: 'Squadra A - Squadra B' (oppure 'vs').")
            st.stop()

        team_a_name, team_b_name = parsed

        with st.spinner("Cerco squadre..."):
            # 1) Cerca team A e B
            a_json, a_code = api_get("/teams", {"search": team_a_name})
            b_json, b_code = api_get("/teams", {"search": team_b_name})

        a_resp = a_json.get("response", []) if isinstance(a_json, dict) else []
        b_resp = b_json.get("response", []) if isinstance(b_json, dict) else []

        a_team = pick_best_team(a_resp, team_a_name)
        b_team = pick_best_team(b_resp, team_b_name)

        if not a_team or not b_team:
            st.error("Non riesco a trovare le squadre. Prova a scrivere il nome più completo (es. 'AC Milan' invece di 'Milan').")
            st.stop()

        a_id = a_team["team"]["id"]
        b_id = b_team["team"]["id"]
        a_name = a_team["team"]["name"]
        b_name = b_team["team"]["name"]

        # League id (se scelto)
        league_id = None
        if league_label != "Auto":
            league_id = DEFAULT_LEAGUES.get(league_label)

        st.success("✅ Squadre trovate")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"🏠 {a_name} (id {a_id})")
        with c2:
            st.subheader(f"✈️ {b_name} (id {b_id})")

        # 2) Trova fixture (tre tentativi: h2h, range, next)
        fixture = None
        fixture_note = ""

        # a) h2h
        params_h2h = {"h2h": f"{a_id}-{b_id}", "season": season}
        if league_id:
            params_h2h["league"] = league_id

        with st.spinner("Cerco fixture (h2h)..."):
            h2h_json, _ = api_get("/fixtures", params_h2h)

        h2h_list = h2h_json.get("response", []) if isinstance(h2h_json, dict) else []
        if h2h_list:
            fixture = h2h_list[0]
            fixture_note = "Fixture trovata via h2h."

        # b) range date (da ieri a +10 giorni) se non trovata
        if not fixture:
            from_dt = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            to_dt = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
            params_range = {"season": season, "from": from_dt, "to": to_dt}
            if league_id:
                params_range["league"] = league_id
            # Per range, l'API filtra per team singolo, quindi facciamo due chiamate e incrociamo
            with st.spinner("Cerco fixture (range date)..."):
                a_rng, _ = api_get("/fixtures", {**params_range, "team": a_id})
                b_rng, _ = api_get("/fixtures", {**params_range, "team": b_id})

            a_list = a_rng.get("response", []) if isinstance(a_rng, dict) else []
            b_list = b_rng.get("response", []) if isinstance(b_rng, dict) else []

            # incrocio per fixture.id
            b_ids = {fx.get("fixture", {}).get("id") for fx in b_list}
            for fx in a_list:
                fid = fx.get("fixture", {}).get("id")
                if fid in b_ids and fid is not None:
                    fixture = fx
                    fixture_note = "Fixture trovata via range date."
                    break

        # c) next fixtures (senza range) se non trovata
        if not fixture:
            params_next_a = {"team": a_id, "next": 10, "season": season}
            params_next_b = {"team": b_id, "next": 10, "season": season}
            if league_id:
                params_next_a["league"] = league_id
                params_next_b["league"] = league_id

            with st.spinner("Cerco fixture (next fixtures)..."):
                a_next, _ = api_get("/fixtures", params_next_a)
                b_next, _ = api_get("/fixtures", params_next_b)

            a_list = a_next.get("response", []) if isinstance(a_next, dict) else []
            b_list = b_next.get("response", []) if isinstance(b_next, dict) else []

            b_ids = {fx.get("fixture", {}).get("id") for fx in b_list}
            for fx in a_list:
                fid = fx.get("fixture", {}).get("id")
                if fid in b_ids and fid is not None:
                    fixture = fx
                    fixture_note = "Fixture trovata via next fixtures."
                    break

        # 3) Se fixture non trovata -> fallback: analisi ultimi match squadra
        if not fixture:
            st.warning("Fixture non trovata nel range: analisi basata su ultimi match squadra (fallback).")

        # 4) Recupera ultimi match per forma e stats
        # ultimi 5 match per ogni team (senza league per essere più robusto)
        with st.spinner("Recupero ultimi match..."):
            a_last_json, _ = api_get("/fixtures", {"team": a_id, "last": 5, "season": season})
            b_last_json, _ = api_get("/fixtures", {"team": b_id, "last": 5, "season": season})

        a_last = a_last_json.get("response", []) if isinstance(a_last_json, dict) else []
        b_last = b_last_json.get("response", []) if isinstance(b_last_json, dict) else []

        a_form = last_n_form(a_last, a_id, n=5)
        b_form = last_n_form(b_last, b_id, n=5)

        a_stats = compute_basic_stats(a_last, a_id, n=5)
        b_stats = compute_basic_stats(b_last, b_id, n=5)

        # 5) Infortuni/squalifiche (se disponibili) -> spesso limitato nel free
        injuries_a = 0
        injuries_b = 0
        susp_a = 0
        susp_b = 0

        # Se abbiamo fixture, proviamo /injuries per fixture
        if fixture:
            fid = fixture.get("fixture", {}).get("id")
            if fid:
                with st.spinner("Recupero infortuni (se disponibili)..."):
                    inj_json, _ = api_get("/injuries", {"fixture": fid})
                inj_list = inj_json.get("response", []) if isinstance(inj_json, dict) else []
                for it in inj_list:
                    team = (it.get("team", {}) or {}).get("id")
                    if team == a_id:
                        injuries_a += 1
                    elif team == b_id:
                        injuries_b += 1

        # 6) UI output
        st.success("✅ Analisi pronta")

        info_box = st.container()
        with info_box:
            title = f"{a_name} vs {b_name}"
            st.subheader(title)
            if fixture_note:
                st.caption(fixture_note)

            if fixture:
                dt_str = fixture.get("fixture", {}).get("date")
                league_name = fixture.get("league", {}).get("name")
                round_name = fixture.get("league", {}).get("round")
                if dt_str:
                    st.write(f"📅 Data (UTC): **{dt_str}**")
                if league_name:
                    st.write(f"🏟️ Competizione: **{league_name}**")
                if round_name:
                    st.write(f"🔁 Round: **{round_name}**")

        c1, c2 = st.columns(2)

        with c1:
            st.markdown(f"## 🏠 {a_name}")
            st.write(f"• Forma (ultimi 5): **{a_form}**")
            st.write(f"• Punti: **{a_stats['points']}** (PPG: **{a_stats['ppg']:.2f}**)")
            st.write(f"• Gol fatti/subiti: **{a_stats['gf']} / {a_stats['ga']}**")
            st.write(f"• Media gol totali: **{a_stats['avg_total_goals']:.2f}**")
            st.write(f"• Infortunati (da API, se disponibili): **{injuries_a}** | Squalificati (stimati): **{susp_a}** | Dubbi: **0**")

        with c2:
            st.markdown(f"## ✈️ {b_name}")
            st.write(f"• Forma (ultimi 5): **{b_form}**")
            st.write(f"• Punti: **{b_stats['points']}** (PPG: **{b_stats['ppg']:.2f}**)")
            st.write(f"• Gol fatti/subiti: **{b_stats['gf']} / {b_stats['ga']}**")
            st.write(f"• Media gol totali: **{b_stats['avg_total_goals']:.2f}**")
            st.write(f"• Infortunati (da API, se disponibili): **{injuries_b}** | Squalificati (stimati): **{susp_b}** | Dubbi: **0**")

        # 7) Suggerimenti (semplici, trasparenti)
        st.markdown("---")
        st.markdown("## 🧠 Suggerimenti (trasparenti, NON certezze)")

        # euristica semplice basata su media gol
        avg_total = (a_stats["avg_total_goals"] + b_stats["avg_total_goals"]) / 2 if (a_stats["counted"] and b_stats["counted"]) else 0.0

        tips = []
        if avg_total and avg_total < 2.2:
            tips.append("Tendenza gol bassa → valuta **Under 2.5 / Under 3.5** (con prudenza).")
        elif avg_total and avg_total > 3.0:
            tips.append("Tendenza gol alta → valuta **Over 2.5** o linee gol live (solo se quote ok).")
        else:
            tips.append("Squadre vicine → attenzione al **1X2**; spesso value è su linee gol/live.")

        tips.append("Ricorda: è solo lettura dati recenti, **NON** una previsione.")

        for t in tips:
            st.write(f"• {t}")

with tab2:
    st.subheader("📈 Trading / Stop (Manuale)")
    st.write("Qui puoi inserire le quote live manualmente e gestire stop/uscita. (Modulo base, personalizzabile)")

    col1, col2, col3 = st.columns(3)
    with col1:
        stake = st.number_input("Stake (€)", min_value=1.0, value=20.0, step=1.0)
    with col2:
        odd_in = st.number_input("Quota entrata", min_value=1.01, value=1.80, step=0.01)
    with col3:
        odd_out = st.number_input("Quota uscita (target)", min_value=1.01, value=1.60, step=0.01)

    # Calcoli base
    implied_in = 1.0 / odd_in
    implied_out = 1.0 / odd_out
    st.write(f"Prob. implicita entrata: **{implied_in*100:.2f}%**")
    st.write(f"Prob. implicita uscita: **{implied_out*100:.2f}%**")

    st.info("Se vuoi, qui possiamo aggiungere calcolo hedge / cashout / stop-loss in base al tuo book.")

