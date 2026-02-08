import streamlit as st
from live_odds import get_odds_totals_v2, extract_over25

st.set_page_config(page_title="Over 2.5 Trading Tool", layout="centered")

st.title("⚽ Over 2.5 Trading Tool")
st.caption("Serie A + Serie B — Nessun filtro: scegli tu la partita. Live stop-loss controllato.")

# =========================
# API KEY
# =========================
api_key = st.secrets.get("THE_ODDS_API_KEY", "")
if not api_key:
    st.error("❌ API KEY non trovata nei Secrets di Streamlit Cloud.")
    st.stop()

# =========================
# PARAMETRI LIVE
# =========================
st.subheader("⚙️ Parametri live")

odds_rise_pct = st.number_input("Stop: quota sale del (%)", min_value=1.0, max_value=300.0, value=25.0, step=1.0)
commission_pct = st.number_input("Commissione exchange (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)
stake = st.number_input("Stake BACK (€)", min_value=10.0, max_value=500.0, value=100.0, step=10.0)

commission = commission_pct / 100.0

st.divider()

# =========================
# PREMATCH
# =========================
st.header("📋 Partite (tutte, senza filtri)")

regions = st.selectbox("Regione bookmaker", ["eu", "uk", "us"], index=0)

if "payload" not in st.session_state:
    st.session_state["payload"] = None
if "meta" not in st.session_state:
    st.session_state["meta"] = []

sports = [
    ("Serie A", "soccer_italy_serie_a"),
    ("Serie B", "soccer_italy_serie_b"),
]

if st.button("🔄 CARICA PARTITE", use_container_width=True):
    payload_all = []
    metas = []

    for name, key in sports:
        events, meta = get_odds_totals_v2(api_key, sport_key=key, regions=regions)
        payload_all.extend(events)
        meta["league"] = name
        metas.append(meta)

    st.session_state["payload"] = payload_all
    st.session_state["meta"] = metas

payload = st.session_state.get("payload")
metas = st.session_state.get("meta", [])

if payload is None:
    st.info("Premi **CARICA PARTITE** per caricare gli eventi di Serie A e Serie B.")
    st.stop()

with st.expander("🛠️ Debug API (apri se non vedi partite)", expanded=False):
    for m in metas:
        st.write(
            f"**{m.get('league','')}** | ok={m.get('ok')} | status={m.get('status_code')} | eventi={m.get('count')} | region={m.get('regions')} | msg={m.get('message')}"
        )

if not payload:
    st.warning("Nessun evento disponibile (API ha restituito lista vuota). Prova a cambiare regione (uk/us) o riprova più tardi.")
    st.stop()

# Lista partite: tutte quelle con Over 2.5 disponibile (nessun filtro quota)
matches = []
for ev in payload:
    over = extract_over25(ev)
    if over:
        label = f"{ev.get('home_team','Home')} vs {ev.get('away_team','Away')}"
        matches.append({
            "label": label,
            "price": float(over["price"]),
            "book": over.get("book", "")
        })

if not matches:
    st.warning("Ci sono eventi, ma nessuno ha il mercato Over 2.5 disponibile nei dati (totals). Riprova più tardi o cambia regione.")
    st.stop()

matches.sort(key=lambda x: x["price"])

options = [f"{m['label']} | Over 2.5 @ {m['price']:.2f} ({m['book']})" for m in matches]
choice = st.selectbox("Scegli partita", options)
sel = matches[options.index(choice)]

B = float(sel["price"])
st.success(f"✅ Selezionato: Over 2.5 @ {B:.2f} ({sel['book']})")

st.divider()

# =========================
# LIVE / STOP-LOSS
# =========================
st.header("📱 LIVE – DECISIONE")

current_odds = st.number_input(
    "Quota Over 2.5 LIVE (Betflag)",
    min_value=1.01,
    value=float(B),
    step=0.05
)

odds_trigger = B * (1 + odds_rise_pct / 100.0)
st.write(f"🛑 Quota STOP: **{odds_trigger:.2f}**")

def hedge_lay_equal(S, Bk, L, c):
    denom = L - c
    if denom <= 0:
        return None
    return (S * Bk) / denom

def pl_values(S, Bk, L, c, lay_stake):
    pl_over = S * (Bk - 1) - lay_stake * (L - 1)
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
    st.info(f"💣 Liability: **{liability:.2f} €**")

    st.markdown("### 📊 Esiti finali stimati")
    st.warning(f"Se esce Over 2.5: **{pl_over:.2f} €**")
    st.warning(f"Se NON esce Over 2.5: **{pl_no_over:.2f} €**")
else:
    st.success("🟢 Mantieni posizione")
    st.caption("La quota non ha ancora raggiunto lo stop.")
