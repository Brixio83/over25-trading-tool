
import streamlit as st
from live_odds import get_odds_totals, extract_over25

st.set_page_config(page_title="Over 2.5 Trading Tool", layout="centered")

st.title("⚽ Over 2.5 Trading Tool")
st.caption("Pre-match ➜ Stop-loss live controllato")

# =========================
# API KEY
# =========================
api_key = st.secrets.get("THE_ODDS_API_KEY", "")
if not api_key:
    st.error("❌ API KEY non trovata nei Secrets di Streamlit Cloud.")
    st.stop()

# =========================
# PARAMETRI
# =========================
st.subheader("⚙️ Parametri")

quota_min = st.number_input("Quota MIN Over 2.5 (pre-match)", min_value=1.01, value=1.85, step=0.01)
quota_max = st.number_input("Quota MAX Over 2.5 (pre-match)", min_value=1.01, value=2.10, step=0.01)
odds_rise_pct = st.number_input("Stop: quota sale del (%)", min_value=1, value=25, step=1)
commission_pct = st.number_input("Commissione exchange (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)

stake = st.number_input("Stake BACK (€)", min_value=10.0, max_value=500.0, value=100.0, step=10.0)
commission = commission_pct / 100.0

st.divider()

# =========================
# PREMATCH - CARICA PARTITE
# =========================
st.header("📋 Partite Consigliate")

# inizializza session state
if "payload" not in st.session_state:
    st.session_state["payload"] = None

sports = [
    "soccer_italy_serie_a",
    "soccer_italy_serie_b",
    "soccer_epl",
    "soccer_spain_la_liga",
]

if st.button("🔄 CARICA PARTITE", use_container_width=True):
    payload_all = []
    for sport in sports:
        payload_all.extend(get_odds_totals(api_key, sport_key=sport, regions="eu"))
    st.session_state["payload"] = payload_all

payload = st.session_state.get("payload")

if payload is None:
    st.info("Premi 'CARICA PARTITE' per cercare le partite disponibili.")
    st.stop()

good_matches = []
for ev in payload:
    over = extract_over25(ev)
    if over and quota_min <= float(over["price"]) <= quota_max:
        good_matches.append(
            {
                "label": f"{ev.get('home_team', 'Home')} vs {ev.get('away_team', 'Away')}",
                "price": float(over["price"]),
                "book": over.get("book", ""),
            }
        )

if not good_matches:
    st.info("Nessuna partita interessante al momento (prova ad allargare le quote o riprova più tardi).")
    st.stop()

options = [f"{m['label']} | Over 2.5 @ {m['price']:.2f} ({m['book']})" for m in good_matches]
choice = st.selectbox("Scegli partita", options)
sel = good_matches[options.index(choice)]
B = float(sel["price"])

st.success(f"✅ Selezionato: Over 2.5 @ {B:.2f} ({sel['book']})")

st.divider()

# =========================
# LIVE - STOP LOSS
# =========================
st.header("📱 LIVE – Decisione")

current_odds = st.number_input(
    "Quota Over 2.5 LIVE (Betflag)",
    min_value=1.01,
    value=float(B),
    step=0.05
)

odds_trigger = B * (1 + odds_rise_pct / 100.0)
st.write(f"🛑 Quota STOP: **{odds_trigger:.2f}**")

def hedge_lay_equal(S: float, Bk: float, L: float, c: float):
    denom = L - c
    if denom <= 0:
        return None
    return (S * Bk) / denom

def pl_values(S: float, Bk: float, L: float, c: float, lay_stake: float):
    pl_if_over = S * (Bk - 1) - lay_stake * (L - 1)
    pl_if_under = -S + lay_stake * (1 - c)
    liability = lay_stake * (L - 1)
    return pl_if_over, pl_if_under, liability

if current_odds >= odds_trigger:
    st.error("🛑 STOP raggiunto: consigliato coprire ORA (bancando Over 2.5)")

    lay_stake = hedge_lay_equal(stake, B, current_odds, commission)
    if lay_stake is None:
        st.error("Errore nel calcolo della copertura (controlla quota live e commissione).")
        st.stop()

    pl_over, pl_under, liability = pl_values(stake, B, current_odds, commission, lay_stake)

    st.markdown("### 👉 Azione consigliata")
    st.success(f"Banca Over 2.5: **{lay_stake:.2f} €**")
    st.info(f"💣 Liability: **{liability:.2f} €**")

    st.markdown("### 📊 Esiti finali stimati")
    st.warning(f"Se esce Over 2.5: **{pl_over:.2f} €**")
    st.warning(f"Se NON esce Over 2.5: **{pl_under:.2f} €**")
else:
    st.success("🟢 Mantieni posizione")
    st.caption("La quota live non ha ancora raggiunto lo stop.")
