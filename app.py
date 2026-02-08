
import streamlit as st
from live_odds import get_odds_totals, extract_over25

st.set_page_config(page_title="Over 2.5 Trading Tool", layout="centered")

st.title("⚽ Over 2.5 Trading Tool")
st.caption("Serie A + Serie B — nessun filtro, scegli tu")

api_key = st.secrets.get("THE_ODDS_API_KEY", "")
if not api_key:
    st.error("API KEY mancante")
    st.stop()

stake = st.number_input("Stake BACK (€)", 10.0, 500.0, 100.0, 10.0)
commission_pct = st.number_input("Commissione (%)", 0.0, 20.0, 5.0, 0.5)
odds_rise_pct = st.number_input("Stop (% aumento quota)", 1.0, 300.0, 25.0, 1.0)
commission = commission_pct / 100

st.divider()

regions = st.selectbox("Regione bookmaker", ["eu", "uk", "us"])

if st.button("🔄 CARICA PARTITE", use_container_width=True):
    events = []
    events += get_odds_totals(api_key, "soccer_italy_serie_a", regions)
    events += get_odds_totals(api_key, "soccer_italy_serie_b", regions)
    st.session_state["events"] = events

events = st.session_state.get("events")

if not events:
    st.warning("Nessun evento disponibile al momento.")
    st.stop()

matches = []
for ev in events:
    over = extract_over25(ev)
    if over:
        matches.append({
            "label": f"{ev.get('home_team')} vs {ev.get('away_team')}",
            "price": over["price"],
            "book": over["book"]
        })

if not matches:
    st.warning("Eventi trovati, ma Over 2.5 non disponibile.")
    st.stop()

matches.sort(key=lambda x: x["price"])

choice = st.selectbox(
    "Scegli partita",
    [f"{m['label']} | Over 2.5 @ {m['price']}" for m in matches]
)

sel = matches[[f"{m['label']} | Over 2.5 @ {m['price']}" for m in matches].index(choice)]
B = sel["price"]

st.success(f"Over 2.5 selezionato @ {B}")

st.divider()

current_odds = st.number_input("Quota LIVE (Betflag)", 1.01, 20.0, B, 0.05)
stop_odds = B * (1 + odds_rise_pct / 100)

st.write(f"Quota STOP: {stop_odds:.2f}")

def hedge_lay(S, B, L, c):
    return (S * B) / (L - c)

if current_odds >= stop_odds:
    lay = hedge_lay(stake, B, current_odds, commission)
    liability = lay * (current_odds - 1)

    st.error("🛑 BANCA ORA")
    st.success(f"Banca Over 2.5: {lay:.2f} €")
    st.info(f"Liability: {liability:.2f} €")
else:
    st.success("🟢 Mantieni posizione")