import streamlit as st

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Over 2.5 Trading Tool (Manual)", layout="centered")

st.title("⚽ Over 2.5 Trading Tool — Manuale (NO API)")
st.caption("Inserisci tu partita, quota di ingresso e quota live (Betflag). Calcolo stop e copertura.")

st.divider()

# =========================
# INPUT MANUALI
# =========================
st.header("📝 Dati partita e ingresso (manuale)")

match_name = st.text_input("Partita (es. Juventus–Lazio)", value=st.session_state.get("match_name", ""))
st.session_state["match_name"] = match_name

colA, colB = st.columns(2)

with colA:
    stake_back = st.number_input("Stake BACK (€)", min_value=1.0, max_value=5000.0, value=float(st.session_state.get("stake_back", 10.0)), step=1.0)
with colB:
    back_odds = st.number_input("Quota BACK reale (ingresso su Betflag)", min_value=1.01, max_value=100.0, value=float(st.session_state.get("back_odds", 2.12)), step=0.01)

st.session_state["stake_back"] = float(stake_back)
st.session_state["back_odds"] = float(back_odds)

colC, colD = st.columns(2)

with colC:
    commission_pct = st.number_input("Commissione Exchange (%)", min_value=0.0, max_value=20.0, value=float(st.session_state.get("commission_pct", 5.0)), step=0.5)
with colD:
    stop_pct = st.number_input("Stop (%) aumento quota", min_value=1.0, max_value=300.0, value=float(st.session_state.get("stop_pct", 25.0)), step=1.0)

st.session_state["commission_pct"] = float(commission_pct)
st.session_state["stop_pct"] = float(stop_pct)

c = commission_pct / 100.0
stop_odds = back_odds * (1.0 + stop_pct / 100.0)

st.info(f"📌 Stop quota (solo riferimento): **{stop_odds:.2f}**  (da quota ingresso {back_odds:.2f} con stop {stop_pct:.0f}%)")

st.divider()

# =========================
# LIVE INPUT
# =========================
st.header("📱 LIVE (manuale)")

lay_odds = st.number_input(
    "Quota LIVE attuale (su Betflag) — Over 2.5",
    min_value=1.01,
    max_value=200.0,
    value=float(st.session_state.get("lay_odds", stop_odds)),
    step=0.01
)
st.session_state["lay_odds"] = float(lay_odds)

col1, col2 = st.columns(2)
with col1:
    cover_percent = st.radio("Copertura", [30, 60, 100], horizontal=True, index=2)
with col2:
    mode = st.radio("Modalità calcolo", ["Stop-loss (perdita max)", "Pareggio (chiudi tutto)"], index=0)

st.divider()

# =========================
# FUNZIONI
# =========================
def hedge_equal_profit(stake: float, back: float, lay: float, comm: float) -> float | None:
    # lay_stake = (stake * back) / (lay - comm)
    denom = lay - comm
    if denom <= 0:
        return None
    return (stake * back) / denom

def hedge_stoploss_maxloss(stake: float, comm: float, max_loss: float) -> float | None:
    # Se vuoi che nello scenario "NO OVER" (cioè perdi il back) la perdita massima sia max_loss:
    # pl_no_over = -stake + lay_stake*(1-comm) = -max_loss
    # lay_stake*(1-comm) = stake - max_loss
    denom = 1 - comm
    if denom <= 0:
        return None
    x = (stake - max_loss) / denom
    return max(x, 0.0)

def pl_values(stake: float, back: float, lay: float, comm: float, lay_stake: float):
    # Scenario OVER esce (Back vince, Lay perde):
    pl_over = stake * (back - 1) - lay_stake * (lay - 1)
    # Scenario OVER NON esce (Back perde, Lay vince meno commissione):
    pl_no_over = -stake + lay_stake * (1 - comm)
    liability = lay_stake * (lay - 1)
    return pl_over, pl_no_over, liability

# =========================
# CALCOLO
# =========================
st.header("📊 Calcolo")

# blocco sicurezza: se quota live non ha senso
if lay_odds <= 1.01:
    st.error("Quota LIVE non valida.")
    st.stop()

# Stop-loss: definisci perdita massima
max_loss_default = float(st.session_state.get("max_loss", min(0.4 * stake_back, stake_back)))
if mode == "Stop-loss (perdita max)":
    max_loss = st.number_input("Perdita massima accettata (€)", min_value=0.0, max_value=float(stake_back), value=float(max_loss_default), step=1.0)
    st.session_state["max_loss"] = float(max_loss)
else:
    max_loss = 0.0

# Mostra allarme stop
if lay_odds >= stop_odds:
    st.error("🛑 STOP raggiunto/superato (quota live ≥ stop). Valuta uscita.")
else:
    st.success("🟢 Sotto lo stop (quota live < stop). In teoria puoi tenere.")

# Bottone calcolo
if st.button("CALCOLA ORA", use_container_width=True):
    if stake_back <= 0:
        st.error("Stake deve essere > 0")
        st.stop()

    if back_odds <= 1.01:
        st.error("Quota ingresso non valida")
        st.stop()

    if mode == "Pareggio (chiudi tutto)":
        lay_full = hedge_equal_profit(stake_back, back_odds, lay_odds, c)
        if lay_full is None:
            st.error("Errore: controlla quota live e commissione.")
            st.stop()
        lay_stake = lay_full * (cover_percent / 100.0)

    else:
        lay_full = hedge_stoploss_maxloss(stake_back, c, max_loss)
        if lay_full is None:
            st.error("Errore: controlla commissione.")
            st.stop()
        lay_stake = lay_full * (cover_percent / 100.0)

    pl_over, pl_no_over, liability = pl_values(stake_back, back_odds, lay_odds, c, lay_stake)

    st.subheader("✅ Risultato")
    st.write(f"**Partita:** {match_name if match_name else '—'}")
    st.write(f"**Ingresso (BACK):** {stake_back:.2f} € @ {back_odds:.2f}")
    st.write(f"**Live (LAY odds):** {lay_odds:.2f}  |  **Commissione:** {commission_pct:.1f}%")
    st.write(f"**Copertura:** {cover_percent}%  |  **Modalità:** {mode}")

    st.success(f"👉 BANCA Over 2.5: **{lay_stake:.2f} €**")
    st.info(f"💣 Liability (rischio se esce Over): **{liability:.2f} €**")

    st.markdown("### 🔍 Esiti finali stimati")
    st.warning(f"Se esce Over 2.5: **{pl_over:.2f} €**")
    st.warning(f"Se NON esce Over 2.5: **{pl_no_over:.2f} €**")

    # Protezione extra: avviso se liability supera lo stake (molti utenti lo trovano “troppo pesante”)
    st.markdown("### 🚨 Avvisi")
    if liability > stake_back:
        st.error("⚠️ Liability maggiore dello stake: copertura pesante. Valuta cash-out o copertura % più bassa.")
    elif abs(pl_no_over) > 0.5 * stake_back:
        st.warning("⚠️ La perdita nello scenario negativo è alta rispetto allo stake.")
    else:
        st.success("🟢 Rischio ragionevole rispetto allo stake.")