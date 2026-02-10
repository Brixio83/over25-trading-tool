import re
import math
import requests
import streamlit as st
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import streamlit as st

st.write("DEBUG: keys nei secrets →", st.secrets)
st.write("DEBUG: API_FOOTBALL_KEY →", st.secrets.get("API_FOOTBALL_KEY"))
# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Trading Tool PRO (Calcio)", layout="centered")
st.title("⚽ Trading Tool PRO (Calcio) — Analisi + Trading (NO Bot)")
st.caption(
    "Scrivi la partita (es. **Juve - Atalanta**). "
    "L'app prende **forma, gol, infortuni, squalifiche** (se disponibili) e ti dà **consigli trasparenti**. "
    "Poi usi il modulo Trading (stop + uscita adesso)."
)

st.divider()

# =========================
# KEYS
# =========================
API_FOOTBALL_KEY = st.secrets.get("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = st.secrets.get("THE_ODDS_API_KEY", "")  # opzionale

if not API_FOOTBALL_KEY:
    st.error("❌ Manca API_FOOTBALL_KEY in secrets.toml (serve per analisi/infortuni).")
    st.stop()

# =========================
# API SETTINGS
# =========================
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
API_FOOTBALL_HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

SERIE_A_LEAGUE_ID = 135
SERIE_B_LEAGUE_ID = 136

# =========================
# UTILS UI
# =========================
def fmt_euro(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_q(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")

def badge(text: str) -> str:
    return f"<span style='padding:4px 10px;border-radius:999px;border:1px solid #2a2a2a;background:rgba(255,255,255,0.04);font-size:12px;'>{text}</span>"

def season_for_today(today: datetime) -> int:
    # API-Football "season" è l'anno di inizio stagione (es: 2025 per 2025/26)
    return today.year if today.month >= 8 else today.year - 1

def parse_match_input(s: str) -> Tuple[Optional[str], Optional[str]]:
    # accetta "Juve-Atalanta", "Juve vs Atalanta", "Juve – Atalanta", ecc.
    s = (s or "").strip()
    if not s:
        return None, None
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+vs\s+", "-", s, flags=re.IGNORECASE)
    parts = [p.strip() for p in s.split("-") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None

# =========================
# HTTP HELPERS
# =========================
@st.cache_data(ttl=60 * 30)
def api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{API_FOOTBALL_BASE}{path}"
    r = requests.get(url, headers=API_FOOTBALL_HEADERS, params=params, timeout=25)
    try:
        data = r.json()
    except Exception:
        data = {"errors": {"parse": "Invalid JSON"}}

    # Normalizza errore
    if r.status_code != 200:
        return {"errors": {"http": f"HTTP {r.status_code}"}, "raw": data}

    return data

@st.cache_data(ttl=60 * 60)
def oddsapi_get(url: str, params: Dict[str, Any]) -> Any:
    r = requests.get(url, params=params, timeout=25)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None

# =========================
# API-FOOTBALL DATA
# =========================
@st.cache_data(ttl=60 * 60)
def search_team(name: str) -> List[Dict[str, Any]]:
    data = api_get("/teams", {"search": name})
    resp = data.get("response", []) if isinstance(data, dict) else []
    return resp if isinstance(resp, list) else []

def pick_best_team(team_results: List[Dict[str, Any]], league_id: int, season: int) -> Optional[Dict[str, Any]]:
    # prova a scegliere quello in lega/season
    if not team_results:
        return None
    # spesso c'è info su "team" e "venue" ecc.
    # Qui prendiamo il primo, poi in fixtures filtriamo per league.
    return team_results[0]

@st.cache_data(ttl=60 * 30)
def find_fixture_by_teams(league_id: int, season: int, home_team_id: int, away_team_id: int) -> Optional[Dict[str, Any]]:
    # cerchiamo nei prossimi 14 giorni (e nei precedenti 3) per robustezza
    today = datetime.utcnow().date()
    d_from = (today - timedelta(days=3)).isoformat()
    d_to = (today + timedelta(days=14)).isoformat()

    data = api_get("/fixtures", {
        "league": league_id,
        "season": season,
        "from": d_from,
        "to": d_to,
        "team": home_team_id  # prima filtro per team, poi matchiamo away
    })
    fixtures = data.get("response", []) if isinstance(data, dict) else []
    if not fixtures:
        return None

    # trova fixture con coppia team
    for fx in fixtures:
        teams = fx.get("teams", {})
        h = teams.get("home", {}).get("id")
        a = teams.get("away", {}).get("id")
        if h == home_team_id and a == away_team_id:
            return fx
        if h == away_team_id and a == home_team_id:
            return fx
    return None

@st.cache_data(ttl=60 * 60)
def last_matches(team_id: int, league_id: int, season: int, n: int = 10) -> List[Dict[str, Any]]:
    data = api_get("/fixtures", {
        "team": team_id,
        "league": league_id,
        "season": season,
        "last": n
    })
    return data.get("response", []) if isinstance(data, dict) else []

@st.cache_data(ttl=60 * 30)
def injuries_for_team(team_id: int, league_id: int, season: int) -> List[Dict[str, Any]]:
    # Endpoint injuries (se disponibile sul piano)
    data = api_get("/injuries", {
        "team": team_id,
        "league": league_id,
        "season": season
    })
    return data.get("response", []) if isinstance(data, dict) else []

@st.cache_data(ttl=60 * 30)
def standings_for_league(league_id: int, season: int) -> Optional[Dict[str, Any]]:
    data = api_get("/standings", {"league": league_id, "season": season})
    resp = data.get("response", []) if isinstance(data, dict) else []
    return resp[0] if resp else None

# =========================
# STATS / SCORING (trasparente)
# =========================
def fixture_goals(fx: Dict[str, Any]) -> Tuple[int, int]:
    goals = fx.get("goals", {}) or {}
    hg = goals.get("home")
    ag = goals.get("away")
    try:
        return int(hg or 0), int(ag or 0)
    except Exception:
        return 0, 0

def result_letter(fx: Dict[str, Any], team_id: int) -> str:
    teams = fx.get("teams", {}) or {}
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")
    hg, ag = fixture_goals(fx)

    if home_id == team_id:
        if hg > ag: return "W"
        if hg < ag: return "L"
        return "D"
    if away_id == team_id:
        if ag > hg: return "W"
        if ag < hg: return "L"
        return "D"
    return "?"

def compute_team_form(team_matches: List[Dict[str, Any]], team_id: int) -> Dict[str, Any]:
    # ultimi N: punti, GF, GS, media gol totali
    pts = 0
    gf = 0
    ga = 0
    letters = []
    for fx in team_matches:
        teams = fx.get("teams", {}) or {}
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        hg, ag = fixture_goals(fx)

        if home_id == team_id:
            gf += hg; ga += ag
        elif away_id == team_id:
            gf += ag; ga += hg
        else:
            continue

        r = result_letter(fx, team_id)
        letters.append(r)
        if r == "W": pts += 3
        elif r == "D": pts += 1

    n = max(1, len(letters))
    return {
        "matches": len(letters),
        "points": pts,
        "ppg": pts / n,
        "gf": gf,
        "ga": ga,
        "gf_pg": gf / n,
        "ga_pg": ga / n,
        "tot_goals_pg": (gf + ga) / n,
        "form": "".join(letters[:10])
    }

def count_absences(injuries: List[Dict[str, Any]]) -> Dict[str, int]:
    # L’API injuries spesso include "player", "type", "reason"
    # Non sempre distingue "suspended" perfettamente: lo stimiamo da reason/type
    injured = 0
    suspended = 0
    doubtful = 0

    for item in injuries or []:
        reason = str((item.get("player", {}) or {}).get("reason", "")).lower()
        itype = str((item.get("player", {}) or {}).get("type", "")).lower()

        text = f"{reason} {itype}"
        if "suspend" in text or "red card" in text or "yellow" in text:
            suspended += 1
        elif "doubt" in text or "question" in text or "probable" in text:
            doubtful += 1
        else:
            injured += 1

    return {"injured": injured, "suspended": suspended, "doubtful": doubtful}

def suggest_markets(home: Dict[str, Any], away: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Suggerimenti trasparenti (non predizioni):
    - usa medie gol (tot_goals_pg), GF/GA
    - forma PPG
    - assenze (injured/suspended)
    produce 3 suggerimenti: Conservativo / Medio / Aggressivo
    """
    h = home
    a = away

    # indicatori base
    avg_goals = (h["tot_goals_pg"] + a["tot_goals_pg"]) / 2.0
    attack = (h["gf_pg"] + a["gf_pg"]) / 2.0
    defense_leak = (h["ga_pg"] + a["ga_pg"]) / 2.0
    tempo = 0.55 * avg_goals + 0.25 * attack + 0.20 * defense_leak

    # penalità assenze
    abs_pen = 0.0
    abs_pen += 0.10 * (h["abs"]["injured"] + a["abs"]["injured"])
    abs_pen += 0.15 * (h["abs"]["suspended"] + a["abs"]["suspended"])
    tempo_adj = max(0.5, tempo - abs_pen)

    # equilibrio / volatilità
    balance = 1.0 - min(0.6, abs(h["ppg"] - a["ppg"]) / 3.0)  # 1=equilibrio
    volatility = 0.6 * tempo_adj + 0.4 * balance  # più alto => più gol/BTTS probabile

    suggestions: List[Dict[str, Any]] = []

    # Conservativo: under alto se tempo basso, altrimenti under medio
    if tempo_adj < 2.2:
        suggestions.append({
            "level": "Conservativo",
            "market": "Under 4.5",
            "why": f"Ritmo gol stimato basso ({tempo_adj:.2f}). Under alto tende ad essere più stabile.",
        })
    else:
        suggestions.append({
            "level": "Conservativo",
            "market": "Under 3.5",
            "why": f"Ritmo gol medio ({tempo_adj:.2f}). Under 3.5 spesso più gestibile live rispetto a Over 2.5.",
        })

    # Medio: se volatilità medio-alta => Over 2.5 o Goal
    if volatility >= 2.6:
        suggestions.append({
            "level": "Medio",
            "market": "Over 2.5",
            "why": f"Volatilità buona ({volatility:.2f}). Over 2.5 ha senso ma va gestito con stop/uscita adesso.",
        })
    else:
        suggestions.append({
            "level": "Medio",
            "market": "GOAL (BTTS Sì)",
            "why": f"Volatilità non altissima ({volatility:.2f}). Goal può essere più adatto di Over alti.",
        })

    # Aggressivo: over alti se tempo davvero alto
    if tempo_adj >= 3.0:
        suggestions.append({
            "level": "Aggressivo",
            "market": "Over 3.5",
            "why": f"Ritmo gol stimato alto ({tempo_adj:.2f}). Over 3.5 è aggressivo ma ha payoff più alto.",
        })
    else:
        suggestions.append({
            "level": "Aggressivo",
            "market": "Over 1.5",
            "why": f"Ritmo non esplosivo ({tempo_adj:.2f}). Over 1.5 è aggressivo solo se entri live (quota migliore).",
        })

    return suggestions

# =========================
# THE ODDS API (opzionale)
# =========================
def oddsapi_totals_for_match(team_home: str, team_away: str, league_key: str = "soccer_italy_serie_a", regions: str = "eu"):
    if not THE_ODDS_API_KEY:
        return None

    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds"
    params = {
        "apiKey": THE_ODDS_API_KEY,
        "regions": regions,
        "markets": "totals",
        "oddsFormat": "decimal"
    }
    data = oddsapi_get(url, params)
    if not isinstance(data, list):
        return None

    # match per nomi (non perfetto, ma utile)
    def norm(x: str) -> str:
        return re.sub(r"\s+", " ", x.strip().lower())

    h = norm(team_home)
    a = norm(team_away)

    for ev in data:
        eh = norm(ev.get("home_team", ""))
        ea = norm(ev.get("away_team", ""))
        if (eh == h and ea == a) or (eh == a and ea == h):
            return ev
    return None

def extract_totals_lines(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for bookmaker in ev.get("bookmakers", []) or []:
        bname = bookmaker.get("title", "")
        for market in bookmaker.get("markets", []) or []:
            if market.get("key") != "totals":
                continue
            for o in market.get("outcomes", []) or []:
                name = str(o.get("name", "")).lower()
                point = o.get("point", None)
                price = o.get("price", None)
                if point is None or price is None:
                    continue
                out.append({
                    "book": bname,
                    "side": name,  # over/under
                    "line": float(point),
                    "price": float(price)
                })
    # filtra duplicati grossolani
    return out[:200]

# =========================
# TRADING TOOL (stop + uscita adesso)
# =========================
def bounds_bancata(puntata: float, quota_ingresso: float, quota_banca: float, comm: float, perdita_max: float, profitto_min: float):
    denom1 = 1.0 - comm
    denom2 = quota_banca - 1.0
    if denom1 <= 0 or denom2 <= 0:
        return None, None
    x_min = (puntata - perdita_max) / denom1
    x_max = (puntata * (quota_ingresso - 1.0) - profitto_min) / denom2
    return x_min, x_max

def stima_esiti(puntata: float, quota_ingresso: float, quota_banca: float, comm: float, bancata: float):
    vincita_back = puntata * (quota_ingresso - 1.0)
    liability = bancata * (quota_banca - 1.0)
    esito_vinci = vincita_back - liability
    esito_perdi = -puntata + bancata * (1.0 - comm)
    return esito_vinci, esito_perdi, liability

def market_key_to_ui(market: str) -> str:
    return market

def map_suggestion_to_trade_market(m: str) -> Tuple[str, Optional[float]]:
    """
    Converte testo suggerimento in chiave trade:
    - Over/Under 1.5/2.5/3.5/4.5/5.5
    - GOAL/NO GOAL
    """
    m = (m or "").strip().lower()
    if "goal" in m and "no" not in m:
        return ("goal", None)
    if "no goal" in m or "nogoal" in m:
        return ("nogoal", None)

    # over/under + linea
    match = re.search(r"(over|under)\s*([0-9]+(\.[0-9])?)", m)
    if match:
        side = match.group(1)
        line = float(match.group(2))
        return (side, line)
    return ("over", 2.5)

# =========================
# DEFAULTS SESSION (TRADING)
# =========================
if "trade_market_side" not in st.session_state: st.session_state["trade_market_side"] = "over"
if "trade_line" not in st.session_state: st.session_state["trade_line"] = 2.5
if "trade_stake" not in st.session_state: st.session_state["trade_stake"] = 10.0
if "trade_back_odds" not in st.session_state: st.session_state["trade_back_odds"] = 1.70
if "trade_commission_pct" not in st.session_state: st.session_state["trade_commission_pct"] = 5.0
if "trade_loss_max" not in st.session_state: st.session_state["trade_loss_max"] = 4.0
if "trade_profit_min" not in st.session_state: st.session_state["trade_profit_min"] = 0.0
if "trade_stop_pct" not in st.session_state: st.session_state["trade_stop_pct"] = 35
if "trade_live_odds" not in st.session_state: st.session_state["trade_live_odds"] = 2.00
if "trade_cover_now" not in st.session_state: st.session_state["trade_cover_now"] = 100
if "last_selected_match" not in st.session_state: st.session_state["last_selected_match"] = ""

# =========================
# TABS
# =========================
tab1, tab2 = st.tabs(["📊 Analisi partita (PRO)", "🧮 Trading / Stop (Manuale)"])

# =========================
# TAB 1: ANALISI
# =========================
with tab1:
    st.subheader("📌 Inserisci la partita")
    st.write("Esempio: **Juventus - Atalanta** (o **Juve-Atalanta**).")
    colA, colB = st.columns([2, 1])
    with colA:
        match_input = st.text_input("Partita", value=st.session_state.get("last_selected_match", ""), placeholder="Es: Juventus - Atalanta")
    with colB:
        league_choice = st.selectbox("Campionato", ["Serie A", "Serie B"], index=0)

    league_id = SERIE_A_LEAGUE_ID if league_choice == "Serie A" else SERIE_B_LEAGUE_ID
    season = season_for_today(datetime.utcnow())

    st.caption(f"Stagione stimata: **{season}/{season+1}** | League ID: {league_id}")

    do_analyze = st.button("🔍 ANALIZZA PARTITA", use_container_width=True)

    if do_analyze:
        home_name, away_name = parse_match_input(match_input)
        if not home_name or not away_name:
            st.error("Scrivi la partita nel formato: 'Squadra1 - Squadra2'")
        else:
            st.session_state["last_selected_match"] = match_input

            with st.spinner("Cerco squadre e dati (forma, infortuni, squalifiche)..."):
                home_candidates = search_team(home_name)
                away_candidates = search_team(away_name)

                if not home_candidates or not away_candidates:
                    st.error("Non trovo una delle squadre. Prova a scrivere il nome completo (es. Juventus).")
                else:
                    home_team = pick_best_team(home_candidates, league_id, season)
                    away_team = pick_best_team(away_candidates, league_id, season)

                    if not home_team or not away_team:
                        st.error("Errore nel selezionare le squadre.")
                    else:
                        home_id = home_team.get("team", {}).get("id")
                        away_id = away_team.get("team", {}).get("id")
                        home_full = home_team.get("team", {}).get("name", home_name)
                        away_full = away_team.get("team", {}).get("name", away_name)

                        fx = find_fixture_by_teams(league_id, season, home_id, away_id)
                        # Se non troviamo fixture, comunque facciamo analisi generica squadre
                        home_last = last_matches(home_id, league_id, season, n=10)
                        away_last = last_matches(away_id, league_id, season, n=10)

                        home_form = compute_team_form(home_last, home_id)
                        away_form = compute_team_form(away_last, away_id)

                        home_inj = injuries_for_team(home_id, league_id, season)
                        away_inj = injuries_for_team(away_id, league_id, season)

                        home_abs = count_absences(home_inj)
                        away_abs = count_absences(away_inj)

                        home_form["abs"] = home_abs
                        away_form["abs"] = away_abs

                        # UI: Match card
                        st.success("✅ Analisi pronta")
                        if fx:
                            dt = fx.get("fixture", {}).get("date", "")
                            st.markdown(
                                f"""
<div style="padding:14px;border-radius:16px;border:1px solid #2a2a2a;background:rgba(255,255,255,0.03);">
  <div style="font-size:18px;font-weight:800;">{home_full} vs {away_full}</div>
  <div style="margin-top:6px;opacity:0.85;">Fixture trovata (data API): {dt}</div>
</div>
""",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f"""
<div style="padding:14px;border-radius:16px;border:1px solid #2a2a2a;background:rgba(255,255,255,0.03);">
  <div style="font-size:18px;font-weight:800;">{home_full} vs {away_full}</div>
  <div style="margin-top:6px;opacity:0.85;">Fixture non trovata nel range: analisi basata su ultimi match squadre.</div>
</div>
""",
                                unsafe_allow_html=True
                            )

                        # Stats layout
                        c1, c2 = st.columns(2)

                        with c1:
                            st.markdown(f"### 🏠 {home_full}")
                            st.write(f"- Forma (ultimi {home_form['matches']}): **{home_form['form']}**")
                            st.write(f"- Punti: **{home_form['points']}** (PPG: **{home_form['ppg']:.2f}**)")
                            st.write(f"- Gol fatti/subiti: **{home_form['gf']} / {home_form['ga']}**")
                            st.write(f"- Media gol totali: **{home_form['tot_goals_pg']:.2f}**")
                            st.write(f"- Infortunati: **{home_abs['injured']}** | Squalificati (stimati): **{home_abs['suspended']}** | Dubbi: **{home_abs['doubtful']}**")

                        with c2:
                            st.markdown(f"### 🛫 {away_full}")
                            st.write(f"- Forma (ultimi {away_form['matches']}): **{away_form['form']}**")
                            st.write(f"- Punti: **{away_form['points']}** (PPG: **{away_form['ppg']:.2f}**)")
                            st.write(f"- Gol fatti/subiti: **{away_form['gf']} / {away_form['ga']}**")
                            st.write(f"- Media gol totali: **{away_form['tot_goals_pg']:.2f}**")
                            st.write(f"- Infortunati: **{away_abs['injured']}** | Squalificati (stimati): **{away_abs['suspended']}** | Dubbi: **{away_abs['doubtful']}**")

                        st.divider()

                        # Suggestions
                        sug = suggest_markets(home_form, away_form)
                        st.markdown("## 🧠 Suggerimenti (trasparenti, NON certezze)")

                        for i, sgg in enumerate(sug, start=1):
                            st.markdown(
                                f"""
<div style="padding:14px;border-radius:16px;border:1px solid #2a2a2a;background:rgba(255,255,255,0.03); margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div style="font-size:16px;font-weight:800;">{i}) {sgg['market']}</div>
    <div>{badge(sgg['level'])}</div>
  </div>
  <div style="margin-top:8px;opacity:0.9;">{sgg['why']}</div>
</div>
""",
                                unsafe_allow_html=True
                            )

                            # Button: load into trading tab
                            if st.button(f"➡️ Usa suggerimento {i} nel Trading", key=f"use_sug_{i}", use_container_width=True):
                                side, line = map_suggestion_to_trade_market(sgg["market"])
                                st.session_state["trade_market_side"] = side
                                if line is not None:
                                    st.session_state["trade_line"] = line
                                # aggiorna titolo match
                                st.session_state["last_selected_match"] = f"{home_full} - {away_full}"
                                st.success("✅ Suggerimento caricato nel Trading. Vai alla tab 'Trading / Stop'.")

                        st.divider()

                        # Optional: The Odds API totals (reference)
                        st.markdown("## 📡 Quote Totali (opzionali, The Odds API)")
                        if not THE_ODDS_API_KEY:
                            st.info("Se vuoi anche le quote bookmaker: aggiungi THE_ODDS_API_KEY nei secrets.")
                        else:
                            regions = st.selectbox("Regione bookmaker", ["eu", "uk", "us"], index=0, key="odds_regions")
                            league_key = "soccer_italy_serie_a" if league_choice == "Serie A" else "soccer_italy_serie_b"

                            if st.button("📥 Carica quote Totals (The Odds API)", use_container_width=True):
                                ev = oddsapi_totals_for_match(home_full, away_full, league_key=league_key, regions=regions)
                                if not ev:
                                    st.warning("Non trovo quote per questa partita su The Odds API (o nomi non matchano).")
                                else:
                                    totals = extract_totals_lines(ev)
                                    if not totals:
                                        st.warning("Trovato evento ma niente mercato Totals.")
                                    else:
                                        # mostra solo linee principali
                                        show = []
                                        for t in totals:
                                            if t["line"] in [1.5, 2.5, 3.5, 4.5, 5.5]:
                                                show.append(t)
                                        if not show:
                                            show = totals[:30]
                                        st.dataframe(show, use_container_width=True)

# =========================
# TAB 2: TRADING
# =========================
with tab2:
    st.subheader("🧮 Trading / Stop (Manuale, stabile su telefono)")
    st.caption("Qui inserisci i numeri REALI di Betflag. Il tool ti dice quota stop e bancata / uscita adesso.")

    # prefill match
    match_title = st.session_state.get("last_selected_match", "")
    if match_title:
        st.info(f"📌 Partita selezionata: **{match_title}**")

    # FORM input principale (stabilità tasti su mobile)
    with st.form("form_trading", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            trade_stake = st.number_input(
                "Puntata d’ingresso (€)",
                min_value=1.0, max_value=5000.0,
                value=float(st.session_state["trade_stake"]),
                step=1.0
            )
        with col2:
            trade_back_odds = st.number_input(
                "Quota d’ingresso (reale Betflag)",
                min_value=1.01, max_value=200.0,
                value=float(st.session_state["trade_back_odds"]),
                step=0.01
            )

        col3, col4 = st.columns(2)
        with col3:
            trade_comm = st.number_input(
                "Commissione exchange (%)",
                min_value=0.0, max_value=20.0,
                value=float(st.session_state["trade_commission_pct"]),
                step=0.5
            )
        with col4:
            trade_loss_max = st.number_input(
                "Perdita max se PERDI (€)",
                min_value=0.0, max_value=float(trade_stake),
                value=float(st.session_state["trade_loss_max"]),
                step=0.5
            )

        trade_profit_min = st.number_input(
            "Profitto minimo se VINCI (€)",
            min_value=0.0,
            max_value=max(0.0, float(trade_stake * (trade_back_odds - 1.0))),
            value=float(st.session_state["trade_profit_min"]),
            step=0.5
        )

        st.markdown("### 🎯 Mercato")
        market_side = st.selectbox(
            "Tipo",
            options=["over", "under", "goal", "nogoal"],
            index=["over","under","goal","nogoal"].index(st.session_state["trade_market_side"])
        )

        line = None
        if market_side in ["over", "under"]:
            line = st.selectbox(
                "Linea",
                options=[1.5, 2.5, 3.5, 4.5, 5.5],
                index=[1.5,2.5,3.5,4.5,5.5].index(float(st.session_state["trade_line"]))
            )

        trade_stop_pct = st.slider(
            "Stop (%) — quanto può salire la quota prima di bancare",
            min_value=0, max_value=150,
            value=int(st.session_state["trade_stop_pct"]),
            step=1
        )

        go = st.form_submit_button("✅ CALCOLA PIANO STOP", use_container_width=True)

    if go:
        st.session_state["trade_stake"] = float(trade_stake)
        st.session_state["trade_back_odds"] = float(trade_back_odds)
        st.session_state["trade_commission_pct"] = float(trade_comm)
        st.session_state["trade_loss_max"] = float(trade_loss_max)
        st.session_state["trade_profit_min"] = float(trade_profit_min)
        st.session_state["trade_market_side"] = market_side
        if line is not None:
            st.session_state["trade_line"] = float(line)
        st.session_state["trade_stop_pct"] = int(trade_stop_pct)

    # use saved values for stable display
    trade_stake = float(st.session_state["trade_stake"])
    trade_back_odds = float(st.session_state["trade_back_odds"])
    trade_comm = float(st.session_state["trade_commission_pct"])
    trade_loss_max = float(st.session_state["trade_loss_max"])
    trade_profit_min = float(st.session_state["trade_profit_min"])
    market_side = st.session_state["trade_market_side"]
    line = float(st.session_state["trade_line"]) if market_side in ["over", "under"] else None
    trade_stop_pct = int(st.session_state["trade_stop_pct"])

    trade_commission = trade_comm / 100.0
    quota_stop = trade_back_odds * (1.0 + trade_stop_pct / 100.0)

    st.divider()
    st.markdown("## 🛑 Piano Stop (pronto)")

    market_label = "GOAL (BTTS Sì)" if market_side == "goal" else "NO GOAL (BTTS No)" if market_side == "nogoal" else f"{market_side.upper()} {line}"

    st.write(f"**Mercato:** {market_label}")
    st.write(f"**Ingresso:** {fmt_euro(trade_stake)} @ {fmt_q(trade_back_odds)}")
    st.write(f"**Stop scelto:** +{trade_stop_pct}% → **Quota stop:** {fmt_q(quota_stop)}")
    st.write(f"**Perdita max se PERDI:** {fmt_euro(trade_loss_max)} | **Profitto minimo se VINCI:** {fmt_euro(trade_profit_min)}")

    x_min, x_max = bounds_bancata(trade_stake, trade_back_odds, quota_stop, trade_commission, trade_loss_max, trade_profit_min)

    if x_min is None or x_max is None:
        st.error("Parametri non validi (controlla quote/commissione).")
    elif x_min > x_max:
        st.error("❌ Impossibile rispettare sia perdita max che profitto minimo con questo stop/questa quota.")
        st.write("👉 Soluzioni rapide:")
        st.write("- abbassa **Profitto minimo** (anche 0€)")
        st.write("- aumenta **Perdita max**")
        st.write("- stop % più basso")
        st.write("- entra a quota più alta")
    else:
        bancata_stop = min(max(0.0, x_min), x_max)
        ev, ep, liab = stima_esiti(trade_stake, trade_back_odds, quota_stop, trade_commission, bancata_stop)

        st.success(f"👉 Quando la quota LIVE arriva a **{fmt_q(quota_stop)}**, banca: **{fmt_euro(bancata_stop)}**")
        st.info(f"💣 Liability stimata: **{fmt_euro(liab)}**")
        st.warning(f"✅ Se VINCI: **{fmt_euro(ev)}**")
        st.warning(f"❌ Se PERDI: **{fmt_euro(ep)}**")

    st.divider()
    st.markdown("## 🚪 Uscita ADESSO (live)")

    with st.form("form_exit_now", clear_on_submit=False):
        live_odds = st.number_input(
            "Quota LIVE attuale (Betflag)",
            min_value=1.01, max_value=500.0,
            value=float(st.session_state["trade_live_odds"]),
            step=0.01
        )
        cover_now = st.radio(
            "Quanto vuoi coprirti ADESSO?",
            [30, 60, 100],
            index=[30,60,100].index(int(st.session_state["trade_cover_now"])),
            horizontal=True
        )
        go_now = st.form_submit_button("🚪 CALCOLA USCITA ADESSO", use_container_width=True)

    if go_now:
        st.session_state["trade_live_odds"] = float(live_odds)
        st.session_state["trade_cover_now"] = int(cover_now)

        x_min_now, x_max_now = bounds_bancata(trade_stake, trade_back_odds, live_odds, trade_commission, trade_loss_max, trade_profit_min)

        if x_min_now is None or x_max_now is None:
            st.error("Parametri non validi (controlla quota/commissione).")
        elif x_min_now > x_max_now:
            st.error("❌ Impossibile rispettare entrambi i vincoli a questa quota live.")
            st.write("👉 Soluzioni:")
            st.write("- abbassa Profitto minimo")
            st.write("- aumenta Perdita max")
            st.write("- usa copertura 30% o 60%")
        else:
            bancata_now_full = min(max(0.0, x_min_now), x_max_now)
            bancata_now = bancata_now_full * (cover_now / 100.0)
            ev_now, ep_now, liab_now = stima_esiti(trade_stake, trade_back_odds, live_odds, trade_commission, bancata_now)

            st.success(f"👉 BANCA ADESSO: **{fmt_euro(bancata_now)}** @ **{fmt_q(live_odds)}** (copertura {cover_now}%)")
            st.info(f"💣 Liability: **{fmt_euro(liab_now)}**")
            st.warning(f"✅ Se VINCI: **{fmt_euro(ev_now)}**")
            st.warning(f"❌ Se PERDI: **{fmt_euro(ep_now)}**")

    st.info(
        "📌 Nota: per Under/Over la matematica è identica. "
        "Lo stop lo usi quando la quota del tuo mercato **sale** (ti sta andando contro)."
    )
