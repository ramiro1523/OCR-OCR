import streamlit as st
from pathlib import Path

from vocacional.puntajes import calcular_pd
from vocacional.baremos import calcular_baremos
from vocacional.areas import top_2, ranking_tipos
from vocacional.carreras import seleccionar_4_carreras
from vocacional.utils import generar_items_vacios, obtener_bloques, auditar_marcas

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IEPPO — Orientación Vocacional",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizado para look profesional y barra de progreso
st.markdown("""
<style>
    /* Ocultar menú y pie de Streamlit */
    #MainMenu, footer, header { visibility: hidden; }
    /* Tipografía */
    html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }
    /* Barra de progreso de pasos */
    .step-bar { display: flex; justify-content: center; gap: 0; margin-bottom: 24px; }
    .step { padding: 8px 28px; font-size: 13px; font-weight: 600; border-radius: 0;
            background: #e9ecef; color: #6c757d; border: 1px solid #dee2e6; }
    .step:first-child { border-radius: 8px 0 0 8px; }
    .step:last-child  { border-radius: 0 8px 8px 0; }
    .step.active  { background: #1976D2; color: white; border-color: #1565C0; }
    .step.done    { background: #43a047; color: white; border-color: #388e3c; }
    /* Tarjeta de métricas */
    [data-testid="metric-container"] { background:#f8f9fa; border-radius:8px; padding:8px 12px; }
    /* Separador de bloques */
    .bloque-titulo { font-size: 13px; font-weight: 700; color: #1976D2;
                     border-left: 4px solid #1976D2; padding-left: 8px;
                     margin: 12px 0 4px 0; text-transform: uppercase; letter-spacing:.5px; }
    /* Items con advertencia */
    .item-warning { background: #fff3cd; border-radius: 4px; padding: 2px 6px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# ESTADO DE SESIÓN
# ─────────────────────────────────────────────────────────────
def _init():
    if "paso" not in st.session_state:
        st.session_state.paso = 1
    if "datos" not in st.session_state:
        st.session_state.datos = {}

_init()


def ir_a_paso(n: int):
    st.session_state.paso = n
    st.rerun()


# ─────────────────────────────────────────────────────────────
# BARRA DE PROGRESO
# ─────────────────────────────────────────────────────────────
def barra_progreso():
    paso_actual = st.session_state.paso
    labels = ["1 · Subir", "2 · Verificar", "3 · Top 2", "4 · Resultado"]
    clases = []
    for i in range(1, 5):
        if i < paso_actual:
            clases.append("step done")
        elif i == paso_actual:
            clases.append("step active")
        else:
            clases.append("step")
    html = "<div class='step-bar'>" + "".join(
        f"<div class='{c}'>{l}</div>" for c, l in zip(clases, labels)
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# PASO 1 — SUBIR FORMULARIO
# ─────────────────────────────────────────────────────────────
def paso_1():
    barra_progreso()
    st.title("📋 IEPPO — Orientación Vocacional")
    st.subheader("Paso 1: Subir formulario del estudiante")

    c1, c2 = st.columns([2, 1])
    with c1:
        pdf = st.file_uploader(
            "Formulario escaneado (PDF, máx. 20 MB)",
            type=["pdf"],
            help="Sube el PDF del formulario IEPPO escaneado."
        )
        nombre = st.text_input("Nombre completo del estudiante", placeholder="Ej. María García López")
    with c2:
        sexo = st.radio(
            "Sexo",
            options=["F", "M"],
            format_func=lambda x: "Mujer (F)" if x == "F" else "Varón (M)",
            horizontal=False
        )

    st.divider()
    _, btn_col = st.columns([4, 1])
    with btn_col:
        if st.button("Siguiente →", type="primary", use_container_width=True):
            if not pdf:
                st.error("⚠️ Por favor sube el PDF del formulario.")
                return
            if not nombre.strip():
                st.error("⚠️ Ingresa el nombre del estudiante.")
                return

            # Intentar OCR automático
            with st.spinner("Procesando escaneo con OCR..."):
                try:
                    from ocr.pipeline import procesar_formulario_pdf
                    pdf.seek(0)
                    resultado_ocr = procesar_formulario_pdf(pdf)
                    marcas = resultado_ocr["marcas"]
                    if not resultado_ocr["exito"]:
                        st.warning(f"⚠️ {resultado_ocr['mensaje']}")
                except Exception as e:
                    st.warning(f"⚠️ OCR no disponible: {e}. Se habilitó verificación manual.")
                    marcas = generar_items_vacios()

            st.session_state.datos = {
                "nombre": nombre.strip(),
                "sexo": sexo,
                "marcas": marcas,
            }
            ir_a_paso(2)


# ─────────────────────────────────────────────────────────────
# PASO 2 — VERIFICACIÓN + PUNTAJES + BAREMOS
# ─────────────────────────────────────────────────────────────
def paso_2():
    barra_progreso()
    st.title("Paso 2: Verificar marcas y puntajes")

    marcas: dict = st.session_state.datos["marcas"]
    sexo: str = st.session_state.datos["sexo"]

    OPCIONES_TEXTO = ["Vacío", "No", "Sí", "Ambos (X X)"]
    OPCIONES_VALOR = ["vacio", "no", "si", "ambos"]
    # Mapa visual para indicar confianza
    ETIQUETA_EST = {"si": "✅", "no": "✅", "ambos": "⚠️", "vacio": "⚠️"}

    col_items, col_pts = st.columns([3, 2])

    # ─── Columna izquierda: lista editable de ítems ───
    with col_items:
        st.markdown("### 📝 Lista de ítems (editable)")
        st.caption("Verifica y corrige las marcas detectadas automáticamente. ⚠️ = requiere revisión.")

        bloques = obtener_bloques()
        nuevas_marcas = {}

        for nombre_bloque, items in bloques.items():
            st.markdown(f"<div class='bloque-titulo'>{nombre_bloque}</div>", unsafe_allow_html=True)

            for item in items:
                actual = marcas.get(item, "vacio")
                idx = OPCIONES_VALOR.index(actual) if actual in OPCIONES_VALOR else 0
                etiqueta = ETIQUETA_EST.get(actual, "⚠️")

                col_lbl, col_radio = st.columns([1, 5])
                with col_lbl:
                    st.write(f"**{item}** {etiqueta}")
                with col_radio:
                    nuevo = st.radio(
                        label=item,
                        options=OPCIONES_TEXTO,
                        index=idx,
                        horizontal=True,
                        key=f"r_{item}",
                        label_visibility="collapsed"
                    )
                nuevas_marcas[item] = OPCIONES_VALOR[OPCIONES_TEXTO.index(nuevo)]

    # Sincronizar marcas en tiempo real para que los puntajes se actualicen
    st.session_state.datos["marcas"] = nuevas_marcas

    # ─── Columna derecha: puntajes y baremos ───
    with col_pts:
        st.markdown("### 📊 Tabla de puntajes")
        st.caption("Se actualiza automáticamente según las marcas de la izquierda.")

        puntajes = calcular_pd(nuevas_marcas)
        con_baremos = calcular_baremos(puntajes, sexo)
        st.session_state.datos["puntajes"] = con_baremos

        # Tabla de resumen
        import pandas as pd
        filas = []
        for tipo, datos in con_baremos.items():
            baremo = datos["Baremo"]
            filas.append({
                "Tipo Vocacional": tipo,
                "PD": datos["PD"],
                "Baremo": baremo if baremo is not None else "—"
            })

        df = pd.DataFrame(filas).sort_values("Baremo", ascending=False, key=lambda x: x.map(lambda v: -1 if v == "—" else v))
        st.dataframe(df, hide_index=True, use_container_width=True)

        # Auditoría
        audit = auditar_marcas(nuevas_marcas)
        if audit["vacios"]:
            st.warning(f"⚠️ {len(audit['vacios'])} ítem(s) sin marcar.")
        if audit["ambos"]:
            st.info(f"ℹ️ {len(audit['ambos'])} ítem(s) con doble marca (cuenta como Sí).")

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True):
            ir_a_paso(1)
    with conf_col:
        if st.button("Confirmar →", type="primary", use_container_width=True):
            ir_a_paso(3)


# ─────────────────────────────────────────────────────────────
# PASO 3 — TOP 2 + CARRERAS AFINES
# ─────────────────────────────────────────────────────────────
def paso_3():
    barra_progreso()
    st.title("Paso 3: Top 2 vocacional y carreras afines")

    con_baremos = st.session_state.datos.get("puntajes", {})
    if not con_baremos:
        st.error("No hay puntajes calculados. Regresa al Paso 2.")
        if st.button("← Retroceder"):
            ir_a_paso(2)
        return

    top = top_2(con_baremos)
    if len(top) < 2:
        st.error("No se pudieron determinar 2 tipos vocacionales con baremo válido.")
        if st.button("← Retroceder"):
            ir_a_paso(2)
        return

    tipo1 = top[0]["tipo"]
    tipo2 = top[1]["tipo"]

    # --- Top 2 ---
    st.markdown("### 🏆 Top 2 tipos vocacionales")
    c1, c2 = st.columns(2)
    with c1:
        st.metric(
            label=f"🥇 {tipo1}",
            value=f"Baremo: {top[0]['Baremo']}",
            delta=f"PD: {top[0]['PD']}"
        )
    with c2:
        st.metric(
            label=f"🥈 {tipo2}",
            value=f"Baremo: {top[1]['Baremo']}",
            delta=f"PD: {top[1]['PD']}"
        )

    # --- Carreras afines ---
    carreras = seleccionar_4_carreras(tipo1, tipo2)
    st.session_state.datos["carreras"] = carreras
    st.session_state.datos["top"] = top

    st.markdown("### 🎓 Carreras afines recomendadas")
    ca_col, re_col = st.columns(2)

    with ca_col:
        st.markdown("**✅ PRINCIPALES (2)**")
        for c in carreras["principales"]:
            relacion = c.get("relacion", "")
            st.success(f"**{c['carrera']}** ({c['tipo']})\n\n_{relacion}_")

    with re_col:
        st.markdown("**🔵 RESPALDO (2)**")
        for c in carreras["respaldo"]:
            relacion = c.get("relacion", "")
            st.info(f"**{c['carrera']}** ({c['tipo']})\n\n_{relacion}_")

    # --- Ranking completo ---
    with st.expander("Ver ranking completo de los 7 tipos"):
        import pandas as pd
        ranking = ranking_tipos(con_baremos)
        df_ranking = pd.DataFrame([
            {"#": r["posicion"], "Tipo Vocacional": r["tipo"], "PD": r["PD"],
             "Baremo": r["Baremo"] if r["Baremo"] is not None else "—"}
            for r in ranking
        ])
        st.dataframe(df_ranking, hide_index=True, use_container_width=True)

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True):
            ir_a_paso(2)
    with conf_col:
        if st.button("Confirmar →", type="primary", use_container_width=True):
            ir_a_paso(4)


# ─────────────────────────────────────────────────────────────
# PASO 4 — RESULTADO FINAL
# ─────────────────────────────────────────────────────────────
def paso_4():
    barra_progreso()
    st.title("Paso 4: Resultado final")

    datos = st.session_state.datos
    nombre  = datos.get("nombre", "—")
    sexo    = datos.get("sexo", "—")
    top     = datos.get("top", [])
    carreras = datos.get("carreras", {"principales": [], "respaldo": []})

    sexo_label = "Mujer (F)" if sexo == "F" else "Varón (M)"

    # --- Cabecera del estudiante ---
    st.markdown(f"""
    | Campo | Valor |
    |---|---|
    | **Estudiante** | {nombre} |
    | **Sexo** | {sexo_label} |
    """)

    # --- Top 2 ---
    if top:
        st.markdown("### 🏆 Top 2 vocacional")
        for i, t in enumerate(top, 1):
            med = "🥇" if i == 1 else "🥈"
            bar = t["Baremo"] if t["Baremo"] is not None else "—"
            st.markdown(f"{med} **{t['tipo']}** — PD: `{t['PD']}` · Baremo: `{bar}`")

    # --- Carreras ---
    st.markdown("### 🎓 Carreras recomendadas")
    pr = carreras.get("principales", [])
    re = carreras.get("respaldo", [])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Carreras principales**")
        for i, c in enumerate(pr, 1):
            st.success(f"{i}. **{c['carrera']}** ({c['tipo']})")
    with c2:
        st.markdown("**Carreras de respaldo**")
        for i, c in enumerate(re, 1):
            st.info(f"{i+2}. **{c['carrera']}** ({c['tipo']})")

    # --- Texto para copiar ---
    c_pr = [c.get("carrera", "—") for c in pr]
    c_re = [c.get("carrera", "—") for c in re]

    texto_copia = f"""RESULTADO IEPPO — ORIENTACIÓN VOCACIONAL
={'='*40}
Estudiante : {nombre}
Sexo       : {sexo_label}

TOP 2 VOCACIONAL:
  1. {top[0]['tipo'] if len(top) > 0 else '—'} (Baremo {top[0]['Baremo'] if len(top) > 0 else '—'})
  2. {top[1]['tipo'] if len(top) > 1 else '—'} (Baremo {top[1]['Baremo'] if len(top) > 1 else '—'})

CARRERAS PRINCIPALES:
  1. {c_pr[0] if len(c_pr) > 0 else '—'}
  2. {c_pr[1] if len(c_pr) > 1 else '—'}

CARRERAS DE RESPALDO:
  3. {c_re[0] if len(c_re) > 0 else '—'}
  4. {c_re[1] if len(c_re) > 1 else '—'}
"""

    st.divider()
    st.markdown("### 📋 Copiar resultado")
    st.code(texto_copia, language=None)

    # --- Guardar en BD (silencioso si no está disponible) ---
    puntajes = datos.get("puntajes", {})
    marcas   = datos.get("marcas", {})
    if puntajes and marcas:
        try:
            from db.models import guardar_evaluacion
            form_id = guardar_evaluacion(nombre, sexo, marcas, puntajes, carreras)
            if form_id:
                st.caption(f"✅ Evaluación guardada en base de datos (ID: {form_id})")
        except Exception:
            pass  # BD no disponible — modo offline sin ruido

    # --- Botones finales ---
    st.divider()
    retro_col, _, nuevo_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True):
            ir_a_paso(3)
    with nuevo_col:
        if st.button("🔄 Nuevo estudiante", type="primary", use_container_width=True):
            st.session_state.paso = 1
            st.session_state.datos = {}
            st.rerun()


# ─────────────────────────────────────────────────────────────
# ROUTER PRINCIPAL
# ─────────────────────────────────────────────────────────────
PASOS = {1: paso_1, 2: paso_2, 3: paso_3, 4: paso_4}
PASOS[st.session_state.paso]()