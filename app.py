import streamlit as st

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Trading Tool Semplice", layout="centered")

st.title("⚽ Trading Tool Semplice (NO API)")
st.caption("Tu inserisci ingresso e perdita massima. L'app ti prepara la **quota stop** e **quanto bancare**.")

st.divider()

# =========================
# UTILS
# =========================
def nome_mercato(key: str) -> str:
    return {
        "over15": "Over 1.5",
        "over25": "Over 2.5",
        "goal": "GOAL (Entrambe segnano - Sì)",
        "nogoal": "NO GOAL (Entrambe segnano - No)",
    }.get(key, key)

def calcola_bancata_per_perdita_massima(puntata_ingresso: float, perdita_massima: float, commissione: float) -> float:
    """
    Obiettivo: se la tua giocata perde, vuoi perdere ~perdita_massima.

    Se la tua giocata perde:
      risultato = -puntata_ingresso + bancata*(1-commissione)
    Impongo:
      risultato = -perdita_massima
    => bancata*(1-commissione) = puntata_ingresso - perdita_massima
    => bancata = (puntata_ingresso - perdita_massima) / (1-commissione)
    """
    denom = 1.0 - commissione
    if denom <= 0:
        return 0.0
    x = (puntata_ingresso - perdita_massima) / denom
    return max(0.0, x)

def stima_esiti(puntata_ingresso: float, quota_ingresso: float, quota_stop: float, commissione: float, bancata: float):
    """
    Scenario A: la tua giocata vince (es. Over esce / Goal esce / NoGoal esce)
      - vinci dal BACK: puntata*(quota-1)
      - perdi dalla LAY: liability = bancata*(quota_stop-1)

    Scenario B: la tua giocata perde
      - perdi il BACK: -puntata
      - vinci la LAY netto commissione: + bancata*(1-commissione)
    """
    vincita_back = puntata_ingresso * (quota_ingresso - 1.0)
    liability = bancata * (quota_stop - 1.0)

    esito_se_vinci = vincita_back - liability
    esito_se_perdi = -puntata_ingresso + bancata * (1.0 - commissione)

    return esito_se_vinci, esito_se_perdi, liability

def fmt_euro(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_q(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")

# =========================
# DEFAULTS
# =========================
if "partita" not in st.session_state: st.session_state["partita"] = ""
if "mercato" not in st.session_state: st.session_state["mercato"] = "over25"
if "puntata_ingresso" not in st.session_state: st.session_state["puntata_ingresso"] = 10.0
if "quota_ingresso" not in st.session_state: st.session_state["quota_ingresso"] = 2.12
if "commissione_pct" not in st.session_state: st.session_state["commissione_pct"] = 5.0
if "perdita_massima" not in st.session_state: st.session_state["perdita_massima"] = 4.0
if "stop_custom_pct" not in st.session_state: st.session_state["stop_custom_pct"] = 35.0

# =========================
# INPUTS
# =========================
st.header("📝 Dati d’ingresso (semplici)")

partita = st.text_input("Partita (opzionale)", value=st.session_state["partita"], placeholder="Es: Juventus - Lazio")
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
    puntata_ingresso = st.number_input(
        "Puntata d’ingresso (€)",
        min_value=1.0, max_value=5000.0,
        value=float(st.session_state["puntata_ingresso"]),
        step=1.0
    )
with c2:
    quota_ingresso = st.number_input(
        "Quota d’ingresso (reale Betflag)",
        min_value=1.01, max_value=200.0,
        value=float(st.session_state["quota_ingresso"]),
        step=0.01
    )

st.session_state["puntata_ingresso"] = float(puntata_ingresso)
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
    perdita_massima = st.number_input(
        "Perdita massima che accetto (€)",
        min_value=0.0, max_value=float(puntata_ingresso),
        value=float(st.session_state["perdita_massima"]),
        step=0.5
    )

st.session_state["commissione_pct"] = float(commissione_pct)
st.session_state["perdita_massima"] = float(perdita_massima)

commissione = commissione_pct / 100.0

st.divider()

# =========================
# OUTPUT PRINCIPALE (BANCATA)
# =========================
st.header("✅ Risultato principale (super semplice)")

bancata = calcola_bancata_per_perdita_massima(puntata_ingresso, perdita_massima, commissione)

# Card principale
st.markdown(
    f"""
<div style="padding:14px;border-radius:14px;border:1px solid #2a2a2a;background:rgba(255,255,255,0.03);">
  <div style="font-size:18px;font-weight:700;">🎯 Quanto bancare (per limitare la perdita)</div>
  <div style="margin-top:8px;font-size:16px;">
    Se vuoi perdere circa <b>{fmt_euro(perdita_massima)}</b> quando va male, devi bancare:
  </div>
  <div style="margin-top:10px;font-size:26px;font-weight:800;">
    {fmt_euro(bancata)}
  </div>
  <div style="margin-top:6px;opacity:0.85;">
    (questa cifra dipende da: puntata ingresso, perdita massima, commissione)
  </div>
</div>
""",
    unsafe_allow_html=True
)

st.caption("👉 Ora manca solo decidere **a che quota stop** vuoi uscire (25% / 35% / 50% o personalizzato).")

st.divider()

# =========================
# STOP PRONTI + CUSTOM
# =========================
st.header("🛑 Quote STOP pronte (così ti prepari prima)")

st.write("Scegli uno stop. Quando la quota LIVE su Betflag arriva a quella **Quota stop**, esegui la bancata calcolata sopra.")

stop_levels = [25, 35, 50]

rows = []
for sp in stop_levels:
    quota_stop = quota_ingresso * (1.0 + sp / 100.0)
    es_vinci, es_perdi, liab = stima_esiti(puntata_ingresso, quota_ingresso, quota_stop, commissione, bancata)
    rows.append({
        "Stop (%)": f"+{sp}%",
        "Quota stop": fmt_q(quota_stop),
        "Banca": fmt_euro(bancata),
        "Liability (rischio se VINCI)": fmt_euro(liab),
        "Esito se VINCI": fmt_euro(es_vinci),
        "Esito se PERDI": fmt_euro(es_perdi),
    })

st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()

st.subheader("✨ Stop personalizzato (se vuoi)")
stop_custom_pct = st.slider(
    "Scegli il tuo stop (%)",
    min_value=0, max_value=150,
    value=int(st.session_state["stop_custom_pct"]),
    step=1
)
st.session_state["stop_custom_pct"] = float(stop_custom_pct)

quota_stop_custom = quota_ingresso * (1.0 + stop_custom_pct / 100.0)
es_vinci_c, es_perdi_c, liab_c = stima_esiti(puntata_ingresso, quota_ingresso, quota_stop_custom, commissione, bancata)

st.markdown(
    f"""
<div style="padding:14px;border-radius:14px;border:1px solid #2a2a2a;background:rgba(255,255,255,0.03);">
  <div style="font-size:18px;font-weight:700;">📌 Il tuo stop personalizzato</div>
  <div style="margin-top:8px;">
    <b>Quota stop:</b> <span style="font-size:20px;font-weight:800;">{fmt_q(quota_stop_custom)}</span>
  </div>
  <div style="margin-top:6px;">
    Quando la quota LIVE arriva a <b>{fmt_q(quota_stop_custom)}</b>, banca <b>{fmt_euro(bancata)}</b>.
  </div>
  <div style="margin-top:10px;opacity:0.95;">
    💣 Liability stimata: <b>{fmt_euro(liab_c)}</b><br/>
    ✅ Se VINCI: <b>{fmt_euro(es_vinci_c)}</b><br/>
    ❌ Se PERDI: <b>{fmt_euro(es_perdi_c)}</b>
  </div>
</div>
""",
    unsafe_allow_html=True
)

st.divider()

# =========================
# LIVE CHECK (OPZIONALE)
# =========================
st.header("📱 LIVE (opzionale): controlla se ci sei arrivato")

st.caption("Qui puoi inserire la quota LIVE attuale solo per vedere subito: 'sei in stop' oppure no.")

quota_live = st.number_input(
    "Quota LIVE attuale (Betflag) — (opzionale)",
    min_value=1.01, max_value=500.0,
    value=float(quota_stop_custom),
    step=0.01
)

if quota_live >= quota_stop_custom:
    st.error("🛑 SEI IN STOP: quota live ≥ quota stop. Se vuoi rispettare il piano, banca adesso.")
else:
    st.success("🟢 Non sei ancora in stop. Aspetta (se questa è la tua regola).")

st.divider()

# =========================
# RIEPILOGO SUPER CHIARO
# =========================
st.header("🧾 Riepilogo (da leggere al volo)")

st.write(f"**Partita:** {partita if partita else '—'}")
st.write(f"**Mercato:** {nome_mercato(mercato)}")
st.write(f"**Puntata d’ingresso:** {fmt_euro(puntata_ingresso)}")
st.write(f"**Quota d’ingresso:** {fmt_q(quota_ingresso)}")
st.write(f"**Perdita massima accettata:** {fmt_euro(perdita_massima)}")
st.write(f"**Quanto bancare:** {fmt_euro(bancata)}")
st.write(f"**Quota stop (personalizzata):** {fmt_q(quota_stop_custom)}")

st.info(
    "📌 Regola pratica: **Prima della partita** ti segni *Quota stop* e *Quanto bancare*. "
    "In live guardi solo Betflag: quando la quota arriva a quella cifra, esegui."
)