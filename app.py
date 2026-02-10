 # app.py
import re
import math
import requests
import streamlit as st
from datetime import datetime, timezone

# =========================
# CONFIG UI
# =========================
st.set_page_config(page_title="Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)", layout="wide")
st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)")
st.caption("Analisi basata su dati recenti e disponibilità API. Non è una previsione certa. Trading manuale: inserisci TU le quote live.")

# =========================
# SECRETS / KEYS
# =========================
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

API_FOOTBALL_KEY = get_secret("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = get_secret("THE_ODDS_API_KEY", "")

API_FOOTBALL_HOST = "https://v3.football.api-sports.io"

# =========================
# HELPERS
# =========================
def season_for_today(dt: datetime | None = None) -> int:
    """Stagione calcistica tipica: da luglio a giugno. Es: febbraio 2026 -> season 2025."""
    dt = dt or datetime.now(timezone.utc)
    y = dt.year
    if dt.month >= 7:
        return y
    return y - 1

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def fmt2(x: float) -> str:
    return f"{x:.2f}"

def split_match_input(text: str):
    """
    Accetta: 'Inter - Napoli' / 'Inter-Napoli' / 'Inter vs Napoli' / 'Inter Napoli'
    """
    t = text.strip()
    if not t:
        return None, None
    # normalizza separatori
    t = re.sub(r"\s+vs\s+|\s+v\s+", "-", t, flags=re.IGNORECASE)
    t = t.replace("—", "-").replace("–", "-").replace(":", "-")
    if "-" in t:
        parts = [p.strip() for p in t.split("-") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
    # fallback: prova split su doppio spazio
    parts = [p.strip() for p in re.split(r"\s{2,}", t) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None

def api_headers():
    if not API_FOOTBALL_KEY:
        return None
    return {"x-apisports-key": API_FOOTBALL_KEY}

def api_get(path: str, params: dict):
    """
    Wrapper robusto per API-Football.
    """
    headers = api_headers()
    if headers is None:
        return None, {"error": "API_FOOTBALL_KEY mancante nei secrets."}

    url = f"{API_FOOTBALL_HOST}{path}"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
        js = r.json()
        return r, js
    except Exception as e:
        return None, {"error": str(e)}

@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_team_search(search: str, country: str | None, league: int | None, season: int | None):
    """
    Cerca team con API /teams.
    Se league e season sono disponibili, restringe i risultati (molto più preciso).
    """
    params = {"search": search}
    if country:
        params["country"] = country
    if league is not None and season is not None:
        params["league"] = league
        params["season"] = season

    r, js = api_get("/teams", params)
    return js

def pick_team_id(search_name: str, js: dict):
    """
    Sceglie l'id più sensato da una search.
    """
    resp = js.get("response", []) if isinstance(js, dict) else []
    if not resp:
        return None, None

    target = search_name.lower().strip()

    # 1) match "contains" sul nome team
    for item in resp:
        nm = (item.get("team", {}).get("name") or "").lower()
        if target and target in nm:
            team_id = item.get("team", {}).get("id")
            return team_id, item.get("team", {}).get("name")

    # 2) match "contains" su code/alias
    for item in resp:
        code = (item.get("team", {}).get("code") or "").lower()
        nm = (item.get("team", {}).get("name") or "").lower()
        if target and (target == code or code in target or target in code):
            team_id = item.get("team", {}).get("id")
            return team_id, item.get("team", {}).get("name")

    # 3) fallback: primo risultato
    team_id = resp[0].get("team", {}).get("id")
    return team_id, resp[0].get("team", {}).get("name")

def get_team_id(team_name: str, country: str | None, league: int | None, season: int | None):
    js = cached_team_search(team_name, country=country, league=league, season=season)
    if js.get("errors"):
        return None, None, js
    team_id, resolved_name = pick_team_id(team_name, js)
    return team_id, resolved_name, js

@st.cache_data(ttl=60 * 15, show_spinner=False)
def cached_fixtures(params: dict):
    r, js = api_get("/fixtures", params)
    return js

@st.cache_data(ttl=60 * 15, show_spinner=False)
def cached_injuries(params: dict):
    r, js = api_get("/injuries", params)
    return js

def compute_last_matches_stats(fixtures: list):
    """
    fixtures: lista response API /fixtures
    Calcola: punti, gol fatti/subiti, media gol totali.
    """
    pts = 0
    gf = 0
    ga = 0
    played = 0

    for fx in fixtures:
        teams = fx.get("teams", {})
        goals = fx.get("goals", {})
        if not goals:
            continue

        # deve essere finita
        status = fx.get("fixture", {}).get("status", {}).get("short", "")
        if status not in ("FT", "AET", "PEN"):
            continue

        home_winner = teams.get("home", {}).get("winner", None)
        away_winner = teams.get("away", {}).get("winner", None)

        # individua se la squadra analizzata è home o away
        # (lo ricaviamo dai goals presenti e team id non lo abbiamo qui, quindi assumiamo fixture completa)
        # Qui usiamo un trick: se home_winner True/False/None basta per punti "per home/away",
        # ma per la singola squadra il chiamante deve passarci fixtures filtrate per team.
        # Quindi il calcolo punti deve essere fatto dal chiamante sapendo se team è home/away.
        # => Qui calcoliamo solo gol, mentre i punti li calcoliamo fuori.
        played += 1
        gh = goals.get("home")
        ga_ = goals.get("away")
        if gh is None or ga_ is None:
            continue

        # Gol totali (per medie generali)
        # Non sappiamo se il team è home o away: quindi qui non possiamo assegnare gf/ga correttamente.
        # Li calcoliamo fuori con la funzione dedicata.
    return {"played": played}

def compute_team_form_from_fixtures(fixtures: list, team_id: int):
    pts = 0
    gf = 0
    ga = 0
    played = 0
    for fx in fixtures:
        status = fx.get("fixture", {}).get("status", {}).get("short", "")
        if status not in ("FT", "AET", "PEN"):
            continue

        teams = fx.get("teams", {})
        goals = fx.get("goals", {})
        if goals.get("home") is None or goals.get("away") is None:
            continue

        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")

        gh = goals.get("home", 0) or 0
        ga_ = goals.get("away", 0) or 0

        is_home = (home_id == team_id)
        is_away = (away_id == team_id)
        if not (is_home or is_away):
            continue

        played += 1
        if is_home:
            gf += gh
            ga += ga_
            winner = teams.get("home", {}).get("winner")
        else:
            gf += ga_
            ga += gh
            winner = teams.get("away", {}).get("winner")

        if winner is True:
            pts += 3
        elif winner is None:
            pts += 1
        else:
            pts += 0

    avg_total_goals = (gf + ga) / played if played else 0.0
    ppg = pts / played if played else 0.0
    return {
        "played": played,
        "points": pts,
        "ppg": ppg,
        "gf": gf,
        "ga": ga,
        "avg_total_goals": avg_total_goals,
    }

def stars_from_ppg(ppg: float) -> str:
    # scala semplice 0..3 => 0..5 stelle
    # 0.0 => 1 stella, 3.0 => 5 stelle
    x = max(0.0, min(3.0, ppg))
    stars = 1 + int(round((x / 3.0) * 4))
    return "★" * stars + "☆" * (5 - stars)

def build_suggestions(avg_total: float, home_ppg: float, away_ppg: float):
    suggestions = []

    # linee goal
    if avg_total <= 2.10:
        suggestions.append("Tendenza gol bassa → valuta Under 2.5 / Under 3.5 (con prudenza).")
    elif avg_total <= 2.60:
        suggestions.append("Gol moderati → spesso la zona 'Under 3.5' è la più stabile; occhio al live.")
    elif avg_total <= 3.20:
        suggestions.append("Gol abbastanza alti → valuta Over 2.5, ma gestisci con stop (quota sale se non segnano).")
    else:
        suggestions.append("Tendenza gol alta → possibili spot su Over 2.5/3.5; attenzione ai rossi e al ritmo partita.")

    # equilibrio 1X2
    diff = abs(home_ppg - away_ppg)
    if diff < 0.35:
        suggestions.append("Squadre vicine → attenzione al 1X2; spesso value su linee goal / gestione live.")
    else:
        suggestions.append("Squadra più forte sui numeri recenti → se giochi 1X2 valuta copertura live su momenti chiave.")

    suggestions.append("Ricorda: è solo lettura dati recenti, NON una previsione certa.")
    return suggestions

# =========================
# TRADING CALCULATIONS
# =========================
def lay_stake_for_max_loss_if_lose(back_stake: float, max_loss_if_lose: float, commission: float):
    """
    Impone che:
    - Se PERDI (selezione NON esce): risultato = -max_loss_if_lose
      risultato_lose = L*(1-c) - S
      => L = (S - max_loss)/ (1-c)
    """
    c = commission
    denom = (1.0 - c)
    if denom <= 0:
        return None
    if back_stake <= max_loss_if_lose:
        return None
    L = (back_stake - max_loss_if_lose) / denom
    return L

def max_lay_odds_allowed(back_stake: float, back_odds: float, lay_stake: float, min_profit_if_win: float):
    """
    Impone che:
    risultato_win = S*(Ob-1) - L*(Ol-1) >= min_profit
    => Ol <= 1 + (S*(Ob-1) - min_profit)/L
    """
    if lay_stake <= 0:
        return None
    numerator = back_stake * (back_odds - 1.0) - min_profit_if_win
    return 1.0 + (numerator / lay_stake)

def greenup_lay_stake(back_stake: float, back_odds: float, lay_odds_now: float, commission: float):
    """
    Green-up (tipo cashout): scegli L tale che profitto sia uguale in entrambi gli esiti.
    Derivazione:
    S*Ob = L*(Ol - c)
    => L = S*Ob / (Ol - c)
    """
    c = commission
    denom = (lay_odds_now - c)
    if denom <= 0:
        return None
    return (back_stake * back_odds) / denom

def outcomes(back_stake: float, back_odds: float, lay_stake: float, lay_odds: float, commission: float):
    c = commission
    win = back_stake * (back_odds - 1.0) - lay_stake * (lay_odds - 1.0)
    lose = lay_stake * (1.0 - c) - back_stake
    return win, lose

# =========================
# UI TABS
# =========================
tab1, tab2 = st.tabs(["📊 Analisi partita (PRO)", "📈 Trading / Stop (Manuale)"])

# =========================
# TAB 1 — ANALISI PRO
# =========================
with tab1:
    st.subheader("📊 Analisi partita (PRO) — dati reali da API-Football (API-Sports)")

    colA, colB = st.columns([2, 1])

    with colA:
        match_text = st.text_input("Partita", value="Inter - Napoli", help="Esempio: Inter - Napoli (oppure Milan-Como, Juventus - Atalanta)")
    with colB:
        league_map = {
            "Auto (Italia)": None,
            "Serie A (ID 135)": 135,
            "Serie B (ID 136)": 136,
            "Coppa Italia (ID 137)": 137,
        }
        league_label = st.selectbox("Campionato (consigliato)", list(league_map.keys()), index=0)
        league_id = league_map[league_label]

    season = season_for_today(datetime.now(timezone.utc))
    st.caption(f"Stagione stimata: {season}/{season+1} | League ID: {league_id if league_id else 'Auto'}")

    analyze = st.button("🔎 Analizza", use_container_width=True)

    with st.expander("🔧 DEBUG (solo se serve)"):
        st.write("API_FOOTBALL_KEY presente:", bool(API_FOOTBALL_KEY))
        st.write("THE_ODDS_API_KEY presente:", bool(THE_ODDS_API_KEY))
        if API_FOOTBALL_KEY:
            r, js = api_get("/status", {})
            st.write("DEBUG /status code:", getattr(r, "status_code", None))
            st.json(js)

    if analyze:
        home_raw, away_raw = split_match_input(match_text)
        if not home_raw or not away_raw:
            st.error("Inserisci la partita in formato tipo: Inter - Napoli")
            st.stop()

        country = "Italy"
        # 1) risolvi team ids in modo robusto
        home_id, home_name, home_js = get_team_id(home_raw, country=country, league=league_id, season=season)
        away_id, away_name, away_js = get_team_id(away_raw, country=country, league=league_id, season=season)

        if not home_id or not away_id:
            st.error("Non riesco a trovare le squadre. Prova a scrivere il nome più completo (es. 'AC Milan' invece di 'Milan').")
            with st.expander("Dettagli tecnici (search)"):
                st.write("HOME search response:")
                st.json(home_js)
                st.write("AWAY search response:")
                st.json(away_js)
            st.stop()

        # 2) prendi ultimi match (fallback forte)
        last_n = 8
        home_fx = cached_fixtures({"team": home_id, "season": season, "last": last_n}).get("response", [])
        away_fx = cached_fixtures({"team": away_id, "season": season, "last": last_n}).get("response", [])

        # se stagione stimata è "vuota" (inizio stagione), prova anche season-1
        if len(home_fx) < 3:
            home_fx2 = cached_fixtures({"team": home_id, "season": season - 1, "last": last_n}).get("response", [])
            home_fx = home_fx or home_fx2
        if len(away_fx) < 3:
            away_fx2 = cached_fixtures({"team": away_id, "season": season - 1, "last": last_n}).get("response", [])
            away_fx = away_fx or away_fx2

        home_stats = compute_team_form_from_fixtures(home_fx, home_id)
        away_stats = compute_team_form_from_fixtures(away_fx, away_id)

        # 3) infortuni/squalifiche (API: injuries)
        inj_params_home = {"team": home_id, "season": season}
        inj_params_away = {"team": away_id, "season": season}
        if league_id:
            inj_params_home["league"] = league_id
            inj_params_away["league"] = league_id

        home_inj = cached_injuries(inj_params_home).get("response", [])
        away_inj = cached_injuries(inj_params_away).get("response", [])

        # 4) build UI
        st.success("✅ Analisi pronta")

        st.markdown(f"### {home_name} vs {away_name}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"## 🏠 {home_name}")
            st.write(f"• Forma (ultimi {home_stats['played']}): **{stars_from_ppg(home_stats['ppg'])}**")
            st.write(f"• Punti: **{home_stats['points']}** (PPG: **{home_stats['ppg']:.2f}**)")
            st.write(f"• Gol fatti/subiti: **{home_stats['gf']} / {home_stats['ga']}**")
            st.write(f"• Media gol totali (match team): **{home_stats['avg_total_goals']:.2f}**")
            st.write(f"• Infortunati/Squalificati (da API, se disponibili): **{len(home_inj)}**")

        with c2:
            st.markdown(f"## ✈️ {away_name}")
            st.write(f"• Forma (ultimi {away_stats['played']}): **{stars_from_ppg(away_stats['ppg'])}**")
            st.write(f"• Punti: **{away_stats['points']}** (PPG: **{away_stats['ppg']:.2f}**)")
            st.write(f"• Gol fatti/subiti: **{away_stats['gf']} / {away_stats['ga']}**")
            st.write(f"• Media gol totali (match team): **{away_stats['avg_total_goals']:.2f}**")
            st.write(f"• Infortunati/Squalificati (da API, se disponibili): **{len(away_inj)}**")

        # media combinata semplice
        combined_avg = (home_stats["avg_total_goals"] + away_stats["avg_total_goals"]) / 2.0
        st.divider()

        st.markdown("## 🧠 Suggerimenti (trasparenti, NON certezze)")
        suggestions = build_suggestions(combined_avg, home_stats["ppg"], away_stats["ppg"])
        for s in suggestions:
            st.write(f"• {s}")

        with st.expander("📌 Dettagli tecnici (solo se serve)"):
            st.write("Team IDs risolti:")
            st.code(f"{home_name} -> {home_id}\n{away_name} -> {away_id}")
            st.write("Ultimi fixtures HOME (count):", len(home_fx))
            st.write("Ultimi fixtures AWAY (count):", len(away_fx))
            st.write("Injuries HOME (count):", len(home_inj))
            st.write("Injuries AWAY (count):", len(away_inj))

# =========================
# TAB 2 — TRADING / STOP
# =========================
with tab2:
    st.subheader("📈 Trading / Stop (Manuale) — tu inserisci le quote live")

    st.info(
        "✅ Logica corretta: tu scegli **Perdita max se PERDI** e **Profitto minimo se VINCI**.\n"
        "L’app ti calcola: **quanto bancare** e **fino a che quota stop puoi aspettare**.\n"
        "In più: puoi calcolare l’**uscita adesso** (green-up tipo cashout) inserendo la quota live."
    )

    market = st.selectbox(
        "Che cosa stai giocando?",
        [
            "Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5", "Over 5.5",
            "Under 2.5", "Under 3.5", "Under 4.5", "Under 5.5",
            "Goal (GG)", "No Goal (NG)"
        ],
        index=1
    )

    col1, col2 = st.columns(2)
    with col1:
        back_stake = st.number_input("Puntata d’ingresso (€)", min_value=1.0, value=10.0, step=1.0, format="%.2f")
        commission_pct = st.number_input("Commissione exchange (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5, format="%.2f")
    with col2:
        back_odds = st.number_input("Quota d’ingresso (reale)", min_value=1.01, value=1.70, step=0.01, format="%.2f")
        max_loss_if_lose = st.number_input("Perdita max se PERDI (€)", min_value=0.0, value=4.0, step=0.5, format="%.2f")

    min_profit_if_win = st.number_input("Profitto minimo se VINCI (€)", min_value=0.0, value=1.0, step=0.5, format="%.2f")

    commission = commission_pct / 100.0

    st.divider()
    st.markdown("## 🛑 Piano STOP (ti prepari prima)")

    lay_stake = lay_stake_for_max_loss_if_lose(back_stake, max_loss_if_lose, commission)

    if lay_stake is None:
        st.error(
            "Impossibile con questi vincoli.\n\n"
            "👉 Tipicamente succede se:\n"
            "• Perdita max è troppo bassa rispetto alla puntata (es. vuoi perdere 2€ su 10€ e commissione alta)\n"
            "• Oppure vuoi un profitto minimo troppo alto.\n\n"
            "Prova: aumenta puntata, aumenta perdita max, oppure abbassa profitto minimo."
        )
    else:
        # stop odds massimo accettabile per mantenere profitto minimo
        stop_odds_max = max_lay_odds_allowed(back_stake, back_odds, lay_stake, min_profit_if_win)

        if stop_odds_max is None or stop_odds_max <= 1.01:
            st.error("Impossibile rispettare il profitto minimo con questi numeri.")
        else:
            st.success("✅ Piano STOP calcolato")

            st.write(f"**Mercato:** {market}")
            st.write(f"**Banca consigliata (stake lay):** **{fmt2(lay_stake)} €**")
            st.write(f"**Quota STOP massima (lay):** **{fmt2(stop_odds_max)}**")
            st.caption("Regola pratica: usi lo STOP quando la quota del tuo mercato **SALE** (ti sta andando contro).")

            # Mostra outcome per alcuni stop (percentuali)
            stop_pcts = [0.15, 0.25, 0.35, 0.50, 0.75]
            rows = []
            for p in stop_pcts:
                q = back_odds * (1 + p)
                if q > stop_odds_max:
                    note = "❌ Oltre la tua quota STOP max"
                    rows.append([f"+{int(p*100)}%", fmt2(q), "—", "—", "—", note])
                    continue

                win, lose = outcomes(back_stake, back_odds, lay_stake, q, commission)
                rows.append([f"+{int(p*100)}%", fmt2(q), fmt2(lay_stake), fmt2(win), fmt2(lose), "OK"])

            st.markdown("### Quote STOP pronte (esempi)")
            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
                column_config={
                    0: "Stop",
                    1: "Quota stop (lay)",
                    2: "Banca consigliata (€)",
                    3: "Esito se VINCI (€)",
                    4: "Esito se PERDI (€)",
                    5: "Note",
                }
            )

    st.divider()
    st.markdown("## 🚪 Uscita ADESSO (green-up tipo cashout)")

    lay_odds_now = st.number_input("Quota LIVE attuale per bancare (lay)", min_value=1.01, value=2.00, step=0.01, format="%.2f")
    calc_exit = st.button("✅ Calcola uscita adesso", use_container_width=True)

    if calc_exit:
        Lg = greenup_lay_stake(back_stake, back_odds, lay_odds_now, commission)
        if Lg is None or Lg <= 0:
            st.error("Impossibile calcolare green-up con questi valori (quota troppo bassa o commissione troppo alta).")
        else:
            win_g, lose_g = outcomes(back_stake, back_odds, Lg, lay_odds_now, commission)
            st.success("✅ Uscita calcolata (profitto simile in entrambi gli esiti)")
            st.write(f"**Banca (stake lay) per uscire adesso:** **{fmt2(Lg)} €** @ **{fmt2(lay_odds_now)}**")
            st.write(f"**Esito se VINCI:** {fmt2(win_g)} €")
            st.write(f"**Esito se PERDI:** {fmt2(lose_g)} €")
            st.caption("Nota: è una 'stima' matematica. In reale contano liquidità/abbinamento e scostamenti quota.")

    st.divider()
    st.markdown("### ✅ Nota importante (Over vs Under)")
    st.write("Il calcolo della bancata è **uguale** per Over e Under: stai sempre coprendo **lo stesso mercato** con una bancata.")
    st.write("Regola pratica: lo STOP lo usi quando la quota del tuo mercato **SALE** (ti va contro).")

# Footer
st.caption("© Tool educativo. Nessun consiglio di scommessa certo. Usalo con responsabilità.")