import streamlit as st
from live_odds import get_odds_totals, extract_over25

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="Over 2.5 Trading Tool",
    layout="centered"
)

st.title("⚽ Over 2.5 Trading Tool")
st.caption("Pre-match ➜ Stop-loss live controllato")

# =========================
# API KEY
# =========================
api_key = st.secrets.get("THE_ODDS_API_KEY", "")
if not api_key:
    st.error("❌ API KEY non trovata in secrets.toml / Secrets (Streamlit Cloud).")
    st.stop()

# =========================
# PARAMETRI (DEFAULT)
# =========================
quota_min = 1.85   # rimane in UI per tua comodità, ma NON filtra più
quota_max = 2.10   # rimane in UI per tua comodità, ma NON filtra più
odds_rise_pct = 25
commission_pct = 5.0

stake = st.number_input(
    "Stake BACK (€)",
    min_value=10.0,
    max_value=500.0,
    value=100.0,
    step=10.0
)

commission = commission_pct / 100.0

st.divider()

# =========================
# PREMATCH
# =========================
st.header("📋 Partite (tutte, senza filtri)")

st.caption(
    "Qui NON c'è selezione automatica: il tool ti mostra tutte le partite con Over 2.5 disponibile. "
    "Poi scegli tu in base alle quote."
)

# Inizializza session state
if "payload" not in st.session_state:
    st.session_state["payload"] = None

# Campionati da scaricare (per non rimanere a secco)
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
    st.info("Premi **CARICA PARTITE** per caricare gli eventi disponibili.")
    st.stop()

if not payload:
    st.warning("Nessun evento disponibile al momento (API ha restituito lista vuota). Riprova più tardi.")
    st.stop()

# Costruisci lista partite: TUTTE quelle che hanno Over 2.5 disponibile
matches = []
for ev in payload:
    over = extract_over25(ev)
    if over:
        matches.append({
            "label": f"{ev.get('home_team', 'Home')} vs {ev.get('away_team', 'Away')}",
            "price": float(over["price"]),
            "book": over.get("book", "")
        })

if not matches:
    st.warning("Nessuna partita con quote Over 2.5 disponibile nei dati scaricati. Riprova più tardi.")
    st.stop()

# Ordina per quota (così le vedi meglio)
matches.sort(key=lambda x: x["price"])

options = [
    f"{m['label']} | Over 2.5 @ {m['price']:.2f} ({m['book']})"
    for m in matches
]

choice = st.selectbox("Scegli partita", options)
sel = matches[options.index(choice)]

B = float(sel["price"])

st.success(f"✅ Over 2.5 selezionato @ {B:.2f} ({sel['book']})")

st.divider()

# =========================
# LIVE / MOBILE MODE
# =========================
st.header("📱 LIVE – DECISIONE")

current_odds = st.number_input(
    "Quota Over 2.5 LIVE (Betflag)",
    min_value=1.01,
    value=float(B),
    step=0.05
)

odds_trigger = B * (1 + odds_rise_pct / 100)

st.write(f"🛑 Quota STOP: **{odds_trigger:.2f}**")

def hedge_lay_equal(S, Bk, L, c):
    denom = L - c
    if denom <= 0:
        return None
    return (S * Bk) / denom

def pl_values(S, Bk, L, c, lay_stake):
    # se ESCE Over 2.5: vinci dal back, perdi dalla lay
    pl_over = S * (Bk - 1) - lay_stake * (L - 1)
    # se NON esce Over 2.5: perdi il back, vinci dalla lay (meno commissione)
    pl_no_over = -S + lay_stake * (1 - c)
    liability = lay_stake * (L - 1)
    return pl_over, pl_no_over, liability

if current_odds >= odds_trigger:
    st.error("🛑 BANCA ORA")

    lay_stake = hedge_lay_equal(stake, B, current_odds, commission)
    if lay_stake is None:
        st.error("Errore nel calcolo della copertura. Controlla quota LIVE e commissione.")
        st.stop()

    pl_over, pl_no_over, liability = pl_values(stake, B, current_odds, commission, lay_stake)

    st.markdown("### 👉 Azione consigliata")
    st.success(f"Banca Over 2.5: **{lay_stake:.2f} €**")

    st.markdown("### 📊 Esito")
    st.info(f"💣 Liability (rischio max): **{liability:.2f} €**")
    st.warning(f"⚠️ Se Over esce: **{pl_over:.2f} €**")
    st.warning(f"⚠️ Se Over NON esce: **{pl_no_over:.2f} €**")

else:
    st.success("🟢 Mantieni posizione")
    st.caption("La quota non ha ancora raggiunto lo stop.")
