import streamlit as st

st.set_page_config(page_title="Trading Tool Semplice", layout="centered")
st.title("⚽ Trading Tool Semplice (NO API)")
st.caption("Decidi: **perdita max se perdi** e **profitto minimo se vinci**. L'app prepara quota stop e bancata.")

st.divider()

def nome_mercato(key: str) -> str:
    return {
        "over15": "Over 1.5",
        "over25": "Over 2.5",
        "goal": "GOAL (Entrambe segnano - Sì)",
        "nogoal": "NO GOAL (Entrambe segnano - No)",
    }.get(key, key)

def fmt_euro(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_q(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")

def bounds_bancata(puntata: float, quota_ingresso: float, quota_stop: float, comm: float, perdita_max: float, profitto_min: float):
    """
    Vogliamo una bancata x tale che:

    (A) Se PERDI:  pl_perdi = -puntata + x*(1-comm) >= -perdita_max
        => x*(1-comm) >= puntata - perdita_max
        => x >= (puntata - perdita_max)/(1-comm)   = x_min

    (B) Se VINCI: pl_vinci = puntata*(quota_ingresso-1) - x*(quota_stop-1) >= profitto_min
        => x*(quota_stop-1) <= puntata*(quota_ingresso-1) - profitto_min
        => x <= (puntata*(quota_ingresso-1) - profitto_min)/(quota_stop-1) = x_max

    Se x_min <= x_max allora esiste una bancata che rispetta entrambi.
    """
    denom1 = 1.0 - comm
    denom2 = quota_stop - 1.0

    if denom1 <= 0 or denom2 <= 0:
        return None, None

    x_min = (puntata - perdita_max) / denom1
    x_max = (puntata * (quota_ingresso - 1.0) - profitto_min) / denom2

    return x_min, x_max

def stima_esiti(puntata: float, quota_ingresso: float, quota_stop: float, comm: float, bancata: float):
    vincita_back = puntata * (quota_ingresso - 1.0)
    liability = bancata * (quota_stop - 1.0)

    esito_vinci = vincita_back - liability
    esito_perdi = -puntata + bancata * (1.0 - comm)
    return esito_vinci, esito_perdi, liability

# Defaults
if "partita" not in st.session_state: st.session_state["partita"] = ""
if "mercato" not in st.session_state: st.session_state["mercato"] = "over15"
if "puntata" not in st.session_state: st.session_state["puntata"] = 10.0
if "quota_ingresso" not in st.session_state: st.session_state["quota_ingresso"] = 1.70
if "commissione_pct" not in st.session_state: st.session_state["commissione_pct"] = 5.0
if "perdita_max" not in st.session_state: st.session_state["perdita_max"] = 4.0
if "profitto_min" not in st.session_state: st.session_state["profitto_min"] = 1.0
if "stop_custom_pct" not in st.session_state: st.session_state["stop_custom_pct"] = 35.0

st.header("📝 Dati d’ingresso (chiari)")

partita = st.text_input("Partita (opzionale)", value=st.session_state["partita"])
st.session_state["partita"] = partita

mercato = st.selectbox(
    "Che cosa stai giocando?",
    options=["over15", "over25", "goal", "nogoal"],
    format_func=nome_mercato,
    index=["over15","over25","goal","nogoal"].index(st.session_state["mercato"])
)
st.session_state["mercato"] = mercato

c1, c2 = st.columns(2)
with c1:
    puntata = st.number_input("Puntata d’ingresso (€)", min_value=1.0, max_value=5000.0, value=float(st.session_state["puntata"]), step=1.0)
with c2:
    quota_ingresso = st.number_input("Quota d’ingresso (reale Betflag)", min_value=1.01, max_value=200.0, value=float(st.session_state["quota_ingresso"]), step=0.01)

st.session_state["puntata"] = float(puntata)
st.session_state["quota_ingresso"] = float(quota_ingresso)

c3, c4 = st.columns(2)
with c3:
    commissione_pct = st.number_input("Commissione exchange (%)", min_value=0.0, max_value=20.0, value=float(st.session_state["commissione_pct"]), step=0.5)
with c4:
    perdita_max = st.number_input("Perdita max se PERDI (€)", min_value=0.0, max_value=float(puntata), value=float(st.session_state["perdita_max"]), step=0.5)

st.session_state["commissione_pct"] = float(commissione_pct)
st.session_state["perdita_max"] = float(perdita_max)

commissione = commissione_pct / 100.0

profitto_min = st.number_input(
    "Profitto minimo se VINCI (€)",
    min_value=0.0,
    max_value=float(puntata * (quota_ingresso - 1.0)),
    value=float(st.session_state["profitto_min"]),
    step=0.5
)
st.session_state["profitto_min"] = float(profitto_min)

st.divider()

st.header("🛑 Scegli la quota STOP (quando vuoi uscire)")

stop_levels = [25, 35, 50]
rows = []

for sp in stop_levels:
    quota_stop = quota_ingresso * (1.0 + sp / 100.0)
    x_min, x_max = bounds_bancata(puntata, quota_ingresso, quota_stop, commissione, perdita_max, profitto_min)

    if x_min is None or x_max is None:
        rows.append({
            "Stop": f"+{sp}%",
            "Quota stop": fmt_q(quota_stop),
            "Banca consigliata": "—",
            "Esito se VINCI": "—",
            "Esito se PERDI": "—",
            "Note": "Parametri non validi"
        })
        continue

    if x_min <= x_max:
        # scegliamo una bancata semplice: la minima che rispetta la perdita (x_min), ma dentro l'intervallo
        bancata = max(0.0, x_min)
        # clamp
        bancata = min(bancata, x_max)

        ev, ep, liab = stima_esiti(puntata, quota_ingresso, quota_stop, commissione, bancata)
        rows.append({
            "Stop": f"+{sp}%",
            "Quota stop": fmt_q(quota_stop),
            "Banca consigliata": fmt_euro(bancata),
            "Esito se VINCI": fmt_euro(ev),
            "Esito se PERDI": fmt_euro(ep),
            "Note": "OK ✅"
        })
    else:
        rows.append({
            "Stop": f"+{sp}%",
            "Quota stop": fmt_q(quota_stop),
            "Banca consigliata": "—",
            "Esito se VINCI": "—",
            "Esito se PERDI": "—",
            "Note": "Impossibile: chiedi troppo profitto o troppo poca perdita"
        })

st.dataframe(rows, use_container_width=True, hide_index=True)

st.subheader("✨ Stop personalizzato")
stop_custom_pct = st.slider("Stop (%)", min_value=0, max_value=150, value=int(st.session_state["stop_custom_pct"]), step=1)
st.session_state["stop_custom_pct"] = float(stop_custom_pct)

quota_stop_custom = quota_ingresso * (1.0 + stop_custom_pct / 100.0)
x_min, x_max = bounds_bancata(puntata, quota_ingresso, quota_stop_custom, commissione, perdita_max, profitto_min)

st.divider()
st.header("✅ Piano pronto (semplice)")

if x_min is None or x_max is None:
    st.error("Parametri non validi (controlla commissione / quote).")
else:
    if x_min <= x_max:
        bancata = max(0.0, x_min)
        bancata = min(bancata, x_max)

        ev, ep, liab = stima_esiti(puntata, quota_ingresso, quota_stop_custom, commissione, bancata)

        st.success(f"🎯 QUOTA STOP: **{fmt_q(quota_stop_custom)}**")
        st.success(f"👉 Quando la quota LIVE arriva a **{fmt_q(quota_stop_custom)}**, banca: **{fmt_euro(bancata)}**")

        st.info(f"💣 Liability stimata (se esegui a quella quota): **{fmt_euro(liab)}**")
        st.markdown("### 🔍 Esiti stimati")
        st.warning(f"✅ Se VINCI: **{fmt_euro(ev)}** (>= {fmt_euro(profitto_min)} richiesto)")
        st.warning(f"❌ Se PERDI: **{fmt_euro(ep)}** (>= -{fmt_euro(perdita_max)} richiesto)")
    else:
        st.error("❌ Con questi parametri è IMPOSSIBILE avere sia perdita max che profitto minimo.")
        st.write("👉 Soluzioni semplici:")
        st.write("- abbassa **Profitto minimo se VINCI**")
        st.write("- aumenta **Perdita max se PERDI**")
        st.write("- usa uno stop meno aggressivo (stop % più basso → quota stop più vicina)")
        st.write("- oppure entra a quota migliore (quota ingresso più alta)")

st.divider()
st.header("📱 LIVE (opzionale)")

quota_live = st.number_input("Quota LIVE attuale (Betflag) — (opzionale)", min_value=1.01, max_value=500.0, value=float(quota_stop_custom), step=0.01)

if quota_live >= quota_stop_custom:
    st.error("🛑 Sei in STOP: quota live ≥ quota stop. Se vuoi rispettare il piano, esegui la bancata.")
else:
    st.success("🟢 Non sei ancora in stop.")

st.info(
    "📌 Regola pratica: scegli i parametri **prima** (perdita max e profitto min), "
    "poi in live devi solo controllare se la quota ha raggiunto la **quota stop**."
)