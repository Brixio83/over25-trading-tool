import streamlit as st

from live_odds import get_odds_totals, build_event_list, extract_over25



CONFIG

=========================

st.set_page_config(

page_title="Over 2.5 Trading Tool",

layout="centered"

)

st.title("⚽ Over 2.5 Trading Tool")

st.caption("Pre-match ➜ Stop-loss live controllato")

=========================

API KEY

=========================

api_key = st.secrets.get("THE_ODDS_API_KEY", "")

if not api_key:

st.error("❌ API KEY non trovata in secrets.toml")

st.stop()

=========================

PARAMETRI (DEFAULT BUONI)

=========================

quota_min = 1.85

quota_max = 2.10

odds_rise_pct = 25

commission_pct = 5.0

stake = st.number_input(

"Stake BACK (€)",

min_value=10.0,

max_value=500.0,

value=100.0,

step=10.0

)

commission = commission_pct / 100

st.divider()

=========================

PREMATCH

=========================

st.header("📋 Partite Consigliate")

if st.button("🔄 CARICA PARTITE", use_container_width=True):

st.session_state.payload = get_odds_totals(api_key)

payload = st.session_state.get("payload", [])

good_matches = []

for ev in payload:

over = extract_over25(ev)

if over and quota_min <= over["price"] <= quota_max:

    good_matches.append({

        "label": f"{ev['home_team']} vs {ev['away_team']}",

        "price": over["price"],

        "book": over["book"]

    })

if not good_matches:

st.info("Nessuna partita interessante al momento.")

st.stop()

options = [

f"{m['label']} | Over 2.5 @ {m['price']}"

for m in good_matches

]

choice = st.selectbox("Scegli partita", options)

sel = good_matches[options.index(choice)]

B = sel["price"]

st.success(f"Over 2.5 selezionato @ {B}")

st.divider()

=========================

LIVE / MOBILE MODE

=========================

st.header("📱 LIVE – DECISIONE")

current_odds = st.number_input(

"Quota Over 2.5 LIVE (Betflag)",

min_value=1.01,

value=B,

step=0.05

)

odds_trigger = B * (1 + odds_rise_pct / 100)

st.write(f"🛑 Quota STOP: {odds_trigger:.2f}")

def hedge_lay_equal(S, B, L, c):

denom = L - c

if denom <= 0:

    return None

return (S * B) / denom

if current_odds >= odds_trigger:

st.error("🛑 BANCA ORA")



lay_stake = hedge_lay_equal(stake, B, current_odds, commission)

liability = lay_stake * (current_odds - 1)



pl_win = stake * (B - 1) - lay_stake * (current_odds - 1)

pl_lose = -stake + lay_stake * (1 - commission)



st.markdown("### 👉 Azione consigliata")

st.success(f"Banca Over 2.5: **{lay_stake:.2f} €**")



st.markdown("### 📊 Esito")

st.warning(f"❌ Perdita max: **{pl_lose:.2f} €**")

st.info(f"⚠️ Se Over esce: **{pl_win:.2f} €**")

else:

st.success("🟢 Mantieni posizione")

st.caption("La quota non ha ancora raggiunto lo stop.")

