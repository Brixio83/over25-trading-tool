import streamlit as st

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Trading Tool Semplice", layout="centered")
st.title("⚽ Trading Tool Semplice (NO API)")
st.caption(
    "Decidi: **perdita max se perdi** e **profitto minimo se vinci**. "
    "L'app prepara **quota stop** e **quanto bancare**. "
    "In più: **Uscita ADESSO** con quota live attuale."
)

st.divider()

# =========================
# FUNZIONI (nomi semplici)
# =========================
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

def bounds_bancata(
    puntata: float,
    quota_ingresso: float,
    quota_banca: float,
    comm: float,
    perdita_max: float,
    profitto_min: float
):
    """
    Calcola l'intervallo di bancata [x_min, x_max] che soddisfa:
    - Se PERDI: risultato >= -perdita_max
    - Se VINCI: risultato >= profitto_min

    Se PERDI:
      pl_perdi = -puntata + x*(1-comm) >= -perdita_max
      => x >= (puntata - perdita_max)/(1-comm) = x_min

    Se VINCI:
      pl_vinci = puntata*(quota_ingresso-1) - x*(quota_banca-1) >= profitto_min
      => x <= (puntata*(quota_ingresso-1) - profitto_min)/(quota_banca-1) = x_max
    """
    denom1 = 1.0 - comm
    denom2 = quota_banca - 1.0
    if denom1 <= 0 or denom2 <= 0:
        return None, None

    x_min = (puntata - perdita_max) / denom1
    x_max = (puntata * (quota_ingresso - 1.0) - profitto_min) / denom2
    return x_min, x_max

def stima_esiti(
    puntata: float,
    quota_ingresso: float,
    quota_banca: float,
    comm: float,
    bancata: float
):
    """
    Esiti finali stimati se fai:
      BACK a quota_ingresso
      LAY (banca) a quota_banca

    Se VINCI (esce ciò che hai giocato):
      vinci back = puntata*(quota_ingresso-1)
      perdi lay = bancata*(quota_banca-1)
      => esito_vinci

    Se PERDI (non esce):
      perdi back = -puntata
      vinci lay netto = bancata*(1-comm)
      => esito_perdi

    Liability (rischio se VINCI) = bancata*(quota_banca-1)
    """
    vincita_back = puntata * (quota_ingresso - 1.0)
    liability = bancata * (quota_banca - 1.0)
    esito_vinci = vincita_back - liability
    esito_perdi = -puntata + bancata * (1.0 - comm)
    return esito_vinci, esito_perdi, liability


# =========================
# DEFAULTS
# =========================
if "partita" not in st.session_state: st.session_state["partita"] = ""
if "mercato" not in st.session_state: st.session_state["mercato"] = "over15"
if "puntata" not in st.session_state: st.session_state["puntata"] = 10.0
if "quota_ingresso" not in st.session_state: st.session_state["quota_ingresso"] = 1.70
if "commissione_pct" not in st.session_state: st.session_state["commissione_pct"] = 5.0
if "perdita_max" not in st.session_state: st.session_state["perdita_max"] = 4.0
if "profitto_min" not in st.session_state: st.session_state["profitto_min"] = 1.0
if "stop_custom_pct" not in st.session_state: st.session_state["stop_custom_pct"] = 35.0
if "quota_live_uscita" not in st.session_state: st.session_state["quota_live_uscita"] = 2.00


# =========================
# INPUT SEMPLICI
# =========================
st.header("📝 Dati d’ingresso")

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
    puntata = st.number_input(
        "Puntata d’ingresso (€)",
        min_value=1.0, max_value=5000.0,
        value=float(st.session_state["puntata"]),
        step=1.0
    )
with c2:
    quota_ingresso = st.number_input(
        "Quota d’ingresso (reale Betflag)",
        min_value=1.01, max_value=200.0,
        value=float(st.session_state["quota_ingresso"]),
        step=0.01
    )

st.session_state["puntata"] = float(puntata)
st.session_state["quota_ingresso"] = float(quota_ingresso)

c3, c4 = st.columns(2)
with c3:
    commissione_pct = st.number_input(
        "Commissione exchange (%)",
        min_value=0.0, max_value=20.0,
        value=float(st.session_state["commissione_pct"]),
        step=0.5
    )
with c4:
    perdita_max = st.number_input(
        "Perdita max se PERDI (€)",
        min_value=0.0, max_value=float(puntata),
        value=float(st.session_state["perdita_max"]),
        step=0.5
    )

st.session_state["commissione_pct"] = float(commissione_pct)
st.session_state["perdita_max"] = float(perdita_max)

commissione = commissione_pct / 100.0

profitto_min = st.number_input(
    "Profitto minimo se VINCI (€)",
    min_value=0.0,
    max_value=float(puntata * (quota_ingresso - 1.0)) if quota_ingresso > 1 else 0.0,
    value=float(st.session_state["profitto_min"]),
    step=0.5
)
st.session_state["profitto_min"] = float(profitto_min)

st.divider()

# =========================
# QUOTE STOP PRONTE
# =========================
st.header("🛑 Quote STOP pronte (ti prepari prima)")

st.write(
    "Scegli uno stop. Quando la quota LIVE su Betflag arriva a quella **Quota stop**, "
    "esegui la bancata che ti propongo (se è possibile con i tuoi vincoli)."
)

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
        bancata = max(0.0, x_min)
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
            "Note": "Impossibile (profitto troppo alto o perdita troppo bassa)"
        })

st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()

# =========================
# STOP PERSONALIZZATO + PIANO PRONTO
# =========================
st.header("✨ Stop personalizzato + Piano pronto")

stop_custom_pct = st.slider("Stop (%)", min_value=0, max_value=150, value=int(st.session_state["stop_custom_pct"]), step=1)
st.session_state["stop_custom_pct"] = float(stop_custom_pct)

quota_stop_custom = quota_ingresso * (1.0 + stop_custom_pct / 100.0)

x_min, x_max = bounds_bancata(puntata, quota_ingresso, quota_stop_custom, commissione, perdita_max, profitto_min)

if x_min is None or x_max is None:
    st.error("Parametri non validi (controlla quote/commissione).")
else:
    if x_min <= x_max:
        bancata_stop = max(0.0, x_min)
        bancata_stop = min(bancata_stop, x_max)

        ev, ep, liab = stima_esiti(puntata, quota_ingresso, quota_stop_custom, commissione, bancata_stop)

        st.success(f"🎯 QUOTA STOP: **{fmt_q(quota_stop_custom)}**")
        st.success(f"👉 Quando la quota LIVE arriva a **{fmt_q(quota_stop_custom)}**, banca: **{fmt_euro(bancata_stop)}**")

        st.info(f"💣 Liability stimata (se esegui a quella quota): **{fmt_euro(liab)}**")
        st.markdown("### 🔍 Esiti stimati se esegui lo stop a quella quota")
        st.warning(f"✅ Se VINCI: **{fmt_euro(ev)}** (>= {fmt_euro(profitto_min)} richiesto)")
        st.warning(f"❌ Se PERDI: **{fmt_euro(ep)}** (>= -{fmt_euro(perdita_max)} richiesto)")
    else:
        st.error("❌ Con questi parametri è IMPOSSIBILE avere sia perdita max che profitto minimo con questo stop.")
        st.write("👉 Soluzioni semplici:")
        st.write("- abbassa **Profitto minimo se VINCI**")
        st.write("- aumenta **Perdita max se PERDI**")
        st.write("- scegli uno stop meno aggressivo (stop % più basso)")
        st.write("- entra a quota migliore (quota ingresso più alta)")

st.divider()

# =========================
# USCITA ADESSO (LIVE)
# =========================
st.header("🚪 Uscita ADESSO (live) — quota attuale")

st.caption(
    "Qui NON aspetti la quota stop. Mi dici la quota live di Betflag adesso (es. 2,00) "
    "e io ti dico come uscire nel modo più sensato rispettando i tuoi vincoli."
)

quota_live_uscita = st.number_input(
    "Quota LIVE attuale (Betflag) — la userò per calcolare l’uscita adesso",
    min_value=1.01,
    max_value=500.0,
    value=float(st.session_state["quota_live_uscita"]),
    step=0.01
)
st.session_state["quota_live_uscita"] = float(quota_live_uscita)

copertura_percent = st.radio(
    "Quanto vuoi coprirti ADESSO?",
    [30, 60, 100],
    index=2,
    horizontal=True
)

if st.button("CALCOLA USCITA ADESSO", use_container_width=True):
    x_min_now, x_max_now = bounds_bancata(
        puntata, quota_ingresso, quota_live_uscita, commissione, perdita_max, profitto_min
    )

    if x_min_now is None or x_max_now is None:
        st.error("Parametri non validi (controlla quota/commissione).")
    elif x_min_now > x_max_now:
        st.error("❌ Impossibile rispettare sia perdita max che profitto minimo a questa quota live.")
        st.write("👉 Soluzioni rapide:")
        st.write("- abbassa **Profitto minimo se VINCI**")
        st.write("- aumenta **Perdita max se PERDI**")
        st.write("- oppure fai copertura parziale (30% / 60%)")
    else:
        bancata_now_full = max(0.0, x_min_now)
        bancata_now_full = min(bancata_now_full, x_max_now)

        bancata_now = bancata_now_full * (copertura_percent / 100.0)

        ev_now, ep_now, liab_now = stima_esiti(
            puntata, quota_ingresso, quota_live_uscita, commissione, bancata_now
        )

        st.subheader("✅ Uscita adesso (risultato)")
        st.success(
            f"👉 BANCA ADESSO: **{fmt_euro(bancata_now)}** @ **{fmt_q(quota_live_uscita)}** "
            f"(copertura {copertura_percent}%)"
        )
        st.info(f"💣 Liability: **{fmt_euro(liab_now)}**")

        st.markdown("### 🔍 Esiti stimati se esegui adesso")
        st.warning(f"✅ Se VINCI (esce ciò che hai giocato): **{fmt_euro(ev_now)}**")
        st.warning(f"❌ Se PERDI (non esce): **{fmt_euro(ep_now)}**")

        st.caption("Suggerimento: se vuoi 'tenere la partita' ma ridurre rischio, usa 30% o 60%. Se vuoi protezione dura, usa 100%.")

st.divider()

# =========================
# RIEPILOGO
# =========================
st.header("🧾 Riepilogo (veloce)")

st.write(f"**Partita:** {partita if partita else '—'}")
st.write(f"**Mercato:** {nome_mercato(mercato)}")
st.write(f"**Puntata d’ingresso:** {fmt_euro(puntata)}")
st.write(f"**Quota d’ingresso:** {fmt_q(quota_ingresso)}")
st.write(f"**Perdita max se PERDI:** {fmt_euro(perdita_max)}")
st.write(f"**Profitto minimo se VINCI:** {fmt_euro(profitto_min)}")
st.write(f"**Stop personalizzato (%):** {int(stop_custom_pct)}%  → Quota stop: {fmt_q(quota_stop_custom)}")

st.info(
    "📌 Metodo pratico: prepara prima **Quota stop** e **Banca**. "
    "In live controlli Betflag: quando arriva in stop, esegui. "
    "Se invece vuoi uscire subito, usa **Uscita ADESSO**."
)
```0