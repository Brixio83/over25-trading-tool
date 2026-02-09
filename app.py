import streamlit as st

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Trading Tool (No API)", layout="centered")
st.title("⚽ Trading Tool (NO API) — Over / Under / Goal")
st.caption(
    "Inserisci **puntata** e **quota ingresso reale Betflag**. "
    "Decidi **perdita max se perdi** e **profitto minimo se vinci**. "
    "Il tool ti prepara **quota stop** e **quanto bancare**. "
    "In più: **Uscita ADESSO** con la quota live attuale."
)

st.divider()

# =========================
# FUNZIONI
# =========================
def fmt_euro(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_q(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")

def nome_mercato(key: str) -> str:
    mapping = {
        "over15": "Over 1.5",
        "over25": "Over 2.5",
        "over35": "Over 3.5",
        "over45": "Over 4.5",
        "under35": "Under 3.5",
        "under45": "Under 4.5",
        "goal": "GOAL (Entrambe segnano - Sì)",
        "nogoal": "NO GOAL (Entrambe segnano - No)",
    }
    return mapping.get(key, key)

def bounds_bancata(
    puntata: float,
    quota_ingresso: float,
    quota_banca: float,
    comm: float,
    perdita_max: float,
    profitto_min: float
):
    """
    Intervallo bancata [x_min, x_max] per rispettare:
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
    Esiti finali stimati:
    Se VINCI (esce quello che hai giocato):
      esito_vinci = puntata*(quota_ingresso-1) - bancata*(quota_banca-1)

    Se PERDI (non esce):
      esito_perdi = -puntata + bancata*(1-comm)

    Liability = bancata*(quota_banca-1)
    """
    vincita_back = puntata * (quota_ingresso - 1.0)
    liability = bancata * (quota_banca - 1.0)
    esito_vinci = vincita_back - liability
    esito_perdi = -puntata + bancata * (1.0 - comm)
    return esito_vinci, esito_perdi, liability

# =========================
# SESSION DEFAULTS
# =========================
defaults = {
    "partita": "",
    "mercato": "over15",
    "puntata": 10.0,
    "quota_ingresso": 1.70,
    "commissione_pct": 5.0,
    "perdita_max": 4.0,
    "profitto_min": 0.0,
    "stop_custom_pct": 35,
    "quota_live_uscita": 2.00,
    "copertura_percent": 100,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# FORM (per sistemare i "tasti" e i ricaricamenti a caso su mobile)
# =========================
st.header("📝 Dati d’ingresso (stabili su telefono)")

with st.form("form_input", clear_on_submit=False):
    partita = st.text_input("Partita (opzionale)", value=st.session_state["partita"], key="inp_partita")

    mercato = st.selectbox(
        "Che cosa stai giocando?",
        options=["over15", "over25", "over35", "over45", "under35", "under45", "goal", "nogoal"],
        format_func=nome_mercato,
        index=["over15","over25","over35","over45","under35","under45","goal","nogoal"].index(st.session_state["mercato"]),
        key="inp_mercato"
    )

    c1, c2 = st.columns(2)
    with c1:
        puntata = st.number_input(
            "Puntata d’ingresso (€)",
            min_value=1.0, max_value=5000.0,
            value=float(st.session_state["puntata"]),
            step=1.0,
            key="inp_puntata"
        )
    with c2:
        quota_ingresso = st.number_input(
            "Quota d’ingresso (reale Betflag)",
            min_value=1.01, max_value=200.0,
            value=float(st.session_state["quota_ingresso"]),
            step=0.01,
            key="inp_quota_ingresso"
        )

    c3, c4 = st.columns(2)
    with c3:
        commissione_pct = st.number_input(
            "Commissione exchange (%)",
            min_value=0.0, max_value=20.0,
            value=float(st.session_state["commissione_pct"]),
            step=0.5,
            key="inp_commissione"
        )
    with c4:
        perdita_max = st.number_input(
            "Perdita max se PERDI (€)",
            min_value=0.0,
            max_value=float(puntata),
            value=float(st.session_state["perdita_max"]),
            step=0.5,
            key="inp_perdita_max"
        )

    profitto_min = st.number_input(
        "Profitto minimo se VINCI (€)",
        min_value=0.0,
        max_value=max(0.0, float(puntata * (quota_ingresso - 1.0))),
        value=float(st.session_state["profitto_min"]),
        step=0.5,
        key="inp_profitto_min"
    )

    stop_custom_pct = st.slider(
        "Stop (%) — quanto può salire la quota prima di bancare",
        min_value=0, max_value=150,
        value=int(st.session_state["stop_custom_pct"]),
        step=1,
        key="inp_stop_pct"
    )

    submitted = st.form_submit_button("✅ CALCOLA (aggiorna risultati)", use_container_width=True)

# salva in sessione SOLO quando premi CALCOLA
if submitted:
    st.session_state["partita"] = partita
    st.session_state["mercato"] = mercato
    st.session_state["puntata"] = float(puntata)
    st.session_state["quota_ingresso"] = float(quota_ingresso)
    st.session_state["commissione_pct"] = float(commissione_pct)
    st.session_state["perdita_max"] = float(perdita_max)
    st.session_state["profitto_min"] = float(profitto_min)
    st.session_state["stop_custom_pct"] = int(stop_custom_pct)

# usa valori da sessione (così non cambiano a caso mentre tocchi)
partita = st.session_state["partita"]
mercato = st.session_state["mercato"]
puntata = float(st.session_state["puntata"])
quota_ingresso = float(st.session_state["quota_ingresso"])
commissione_pct = float(st.session_state["commissione_pct"])
perdita_max = float(st.session_state["perdita_max"])
profitto_min = float(st.session_state["profitto_min"])
stop_custom_pct = int(st.session_state["stop_custom_pct"])
commissione = commissione_pct / 100.0

st.divider()

# =========================
# INFO MERCATO (solo spiegazione)
# =========================
st.header("ℹ️ Nota importante (Over vs Under)")
st.write(
    "Il calcolo della bancata è **uguale** per Over e Under.\n\n"
    "📌 Regola pratica: lo **STOP** lo usi quando la quota del tuo mercato **SALE** (ti sta andando contro)."
)

st.divider()

# =========================
# QUOTE STOP PRONTE
# =========================
st.header("🛑 Quote STOP pronte (ti prepari prima)")

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
        ev, ep, _liab = stima_esiti(puntata, quota_ingresso, quota_stop, commissione, bancata)
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
            "Note": "Impossibile (profitto minimo troppo alto o perdita max troppo bassa)"
        })

st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()

# =========================
# STOP PERSONALIZZATO
# =========================
st.header("✨ Piano STOP personalizzato (quello che userai davvero)")

quota_stop_custom = quota_ingresso * (1.0 + stop_custom_pct / 100.0)
x_min, x_max = bounds_bancata(puntata, quota_ingresso, quota_stop_custom, commissione, perdita_max, profitto_min)

st.write(f"**Partita:** {partita if partita else '—'}")
st.write(f"**Mercato:** {nome_mercato(mercato)}")
st.write(f"**Ingresso:** {fmt_euro(puntata)} @ {fmt_q(quota_ingresso)}")
st.write(f"**Stop scelto:** +{stop_custom_pct}%  →  **Quota STOP:** {fmt_q(quota_stop_custom)}")

if x_min is None or x_max is None:
    st.error("Parametri non validi (controlla quota/commissione).")
else:
    if x_min <= x_max:
        bancata_stop = max(0.0, x_min)
        bancata_stop = min(bancata_stop, x_max)

        ev, ep, liab = stima_esiti(puntata, quota_ingresso, quota_stop_custom, commissione, bancata_stop)

        st.success(f"👉 Quando la quota LIVE arriva a **{fmt_q(quota_stop_custom)}**, banca: **{fmt_euro(bancata_stop)}**")
        st.info(f"💣 Liability stimata (se esegui allo stop): **{fmt_euro(liab)}**")

        st.markdown("### 🔍 Esiti stimati se esegui lo STOP a quella quota")
        st.warning(f"✅ Se VINCI: **{fmt_euro(ev)}** (target ≥ {fmt_euro(profitto_min)})")
        st.warning(f"❌ Se PERDI: **{fmt_euro(ep)}** (target ≥ -{fmt_euro(perdita_max)})")
    else:
        st.error("❌ Con questi parametri è IMPOSSIBILE rispettare sia perdita max che profitto minimo con questo stop.")
        st.write("👉 Soluzioni rapide:")
        st.write("- abbassa **Profitto minimo se VINCI** (anche 0 va bene)")
        st.write("- aumenta **Perdita max se PERDI**")
        st.write("- scegli stop % più basso")
        st.write("- entra a quota più alta (se possibile)")

st.divider()

# =========================
# USCITA ADESSO (LIVE)
# =========================
st.header("🚪 Uscita ADESSO (live) — quota attuale")

st.caption(
    "Se sei in live e vuoi uscire **adesso**, inserisci la quota LIVE attuale (Betflag). "
    "Il tool calcola la bancata **adesso** rispettando i tuoi vincoli (se possibile)."
)

with st.form("form_uscita_adesso", clear_on_submit=False):
    quota_live_uscita = st.number_input(
        "Quota LIVE attuale (Betflag)",
        min_value=1.01,
        max_value=500.0,
        value=float(st.session_state["quota_live_uscita"]),
        step=0.01,
        key="inp_quota_live_uscita"
    )

    copertura_percent = st.radio(
        "Quanto vuoi coprirti ADESSO?",
        [30, 60, 100],
        index=[30,60,100].index(int(st.session_state.get("copertura_percent", 100))),
        horizontal=True,
        key="inp_copertura_percent"
    )

    go_now = st.form_submit_button("🚪 CALCOLA USCITA ADESSO", use_container_width=True)

if go_now:
    st.session_state["quota_live_uscita"] = float(quota_live_uscita)
    st.session_state["copertura_percent"] = int(copertura_percent)

quota_live_uscita = float(st.session_state["quota_live_uscita"])
copertura_percent = int(st.session_state.get("copertura_percent", 100))

if go_now:
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
        st.write("- oppure usa copertura 30%/60%")
    else:
        bancata_now_full = max(0.0, x_min_now)
        bancata_now_full = min(bancata_now_full, x_max_now)
        bancata_now = bancata_now_full * (copertura_percent / 100.0)

        ev_now, ep_now, liab_now = stima_esiti(
            puntata, quota_ingresso, quota_live_uscita, commissione, bancata_now
        )

        st.subheader("✅ Risultato uscita adesso")
        st.success(f"👉 BANCA ADESSO: **{fmt_euro(bancata_now)}** @ **{fmt_q(quota_live_uscita)}** (copertura {copertura_percent}%)")
        st.info(f"💣 Liability: **{fmt_euro(liab_now)}**")

        st.markdown("### 🔍 Esiti stimati se esegui ADESSO")
        st.warning(f"✅ Se VINCI: **{fmt_euro(ev_now)}**")
        st.warning(f"❌ Se PERDI: **{fmt_euro(ep_now)}**")

        st.caption("Suggerimento: se vuoi 'tenere la partita' ma ridurre rischio, usa 30% o 60%. Se vuoi protezione dura, usa 100%.")

st.divider()

# =========================
# RIEPILOGO
# =========================
st.header("🧾 Riepilogo")

st.write(f"**Mercato:** {nome_mercato(mercato)}")
st.write(f"**Ingresso:** {fmt_euro(puntata)} @ {fmt_q(quota_ingresso)}")
st.write(f"**Commissione:** {commissione_pct:.1f}%")
st.write(f"**Perdita max se PERDI:** {fmt_euro(perdita_max)}")
st.write(f"**Profitto minimo se VINCI:** {fmt_euro(profitto_min)}")
st.write(f"**Stop scelto:** +{stop_custom_pct}%  →  Quota stop: {fmt_q(quota_stop_custom)}")

st.info(
    "📌 Come usarlo:\n"
    "1) Inserisci la quota d’ingresso reale Betflag e premi **CALCOLA**.\n"
    "2) Ti segni **Quota STOP** e **Banca consigliata**.\n"
    "3) In live, quando la quota sale fino allo stop, banchi.\n"
    "4) Se vuoi uscire prima, usa **Uscita ADESSO**."
)
