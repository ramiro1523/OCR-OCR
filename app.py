import streamlit as st
import html as _html
import pandas as pd
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


# ─────────────────────────────────────────────────────────────
# CARGA DE CSS EXTERNO
# ─────────────────────────────────────────────────────────────
def cargar_css():
    css_path = Path(__file__).parent / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>",
                    unsafe_allow_html=True)
    else:
        st.warning(f"No se encontró styles.css en: {css_path}")


cargar_css()


# ─────────────────────────────────────────────────────────────
# AGRUPACIÓN POR CRITERIOS (P / E / H)
# ─────────────────────────────────────────────────────────────
CRITERIOS = {
    "P": {
        "nombre": "Personas",
        "descripcion": "Trato con personas, comunicación, expresión y servicio.",
        "tipos": ["SOCIAL", "LIDERAZGO", "ARTÍSTICO"],
        "color": "#2563eb",
        "bg": "#eff6ff",
    },
    "E": {
        "nombre": "Empresa",
        "descripcion": "Organización, gestión, planeamiento y emprendimiento.",
        "tipos": ["ORGANIZADO", "EMPRENDEDOR"],
        "color": "#d97706",
        "bg": "#fffbeb",
    },
    "H": {
        "nombre": "Herramientas",
        "descripcion": "Análisis técnico, científico y manipulación de objetos.",
        "tipos": ["INVESTIGATIVO", "TÉCNICO MECÁNICO"],
        "color": "#059669",
        "bg": "#ecfdf5",
    },
}


def tipo_a_criterio(tipo: str) -> str:
    """Devuelve 'P', 'E' o 'H' según el tipo vocacional."""
    for k, meta in CRITERIOS.items():
        if tipo.upper() in [t.upper() for t in meta["tipos"]]:
            return k
    return "?"


def resumen_criterios(con_baremos: dict) -> dict:
    """Agrupa los resultados por criterio y calcula totales."""
    resumen = {k: {"pd_total": 0, "baremo_max": 0, "tipos": []} for k in CRITERIOS}
    for tipo, d in con_baremos.items():
        crit = tipo_a_criterio(tipo)
        if crit in resumen:
            resumen[crit]["pd_total"] += d.get("PD", 0)
            b = d.get("Baremo") or 0
            resumen[crit]["baremo_max"] = max(resumen[crit]["baremo_max"], b)
            resumen[crit]["tipos"].append(tipo)
    return resumen


def criterio_predominante(resumen: dict) -> str:
    """Devuelve la letra del criterio con mayor baremo máximo."""
    mejor = max(resumen.items(), key=lambda kv: kv[1]["baremo_max"])
    return mejor[0]


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


def _e(v) -> str:
    """Escapa HTML rápido."""
    return _html.escape(str(v if v is not None else "—"))


# ─────────────────────────────────────────────────────────────
# BARRA DE PROGRESO
# ─────────────────────────────────────────────────────────────
def barra_progreso():
    paso_actual = st.session_state.paso
    labels = ["Subir", "Verificar", "Top 2", "Resultado"]
    clases = []
    for i in range(1, 5):
        if i < paso_actual:
            clases.append("step done")
        elif i == paso_actual:
            clases.append("step active")
        else:
            clases.append("step")
    html_bar = "<div class='step-bar'>" + "".join(
        f"<div class='{c}'>{i} · {l}</div>"
        for i, (c, l) in enumerate(zip(clases, labels), 1)
    ) + "</div>"
    st.markdown(html_bar, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# COMPONENTE: PANEL DE CRITERIOS (P / E / H)
# ─────────────────────────────────────────────────────────────
def panel_criterios(con_baremos: dict, compacto: bool = False):
    """Muestra las 3 tarjetas de criterios con totales y predominante."""
    if not con_baremos:
        return

    resumen = resumen_criterios(con_baremos)
    pred = criterio_predominante(resumen)

    st.markdown("<div class='section-title'>Criterios vocacionales (P · E · H)</div>",
                unsafe_allow_html=True)

    cols = st.columns(3, gap="medium")
    for col, (letra, meta) in zip(cols, CRITERIOS.items()):
        r = resumen[letra]
        es_pred = (letra == pred)
        corona = "<span class='crit-tag'>Predominante</span>" if es_pred else ""
        with col:
            st.markdown(f"""
            <div class="crit-card {'pred' if es_pred else ''}"
                 style="border-top-color:{meta['color']};">
                <div class="crit-head">
                    <div class="crit-letter" style="background:{meta['color']};">{letra}</div>
                    <div>
                        <div class="crit-nombre">{meta['nombre']}</div>
                        <div class="crit-desc">{meta['descripcion']}</div>
                    </div>
                </div>
                <div class="crit-stats">
                    <div><span class="crit-k">Baremo máx</span>
                         <span class="crit-v">{r['baremo_max']}</span></div>
                    <div><span class="crit-k">PD total</span>
                         <span class="crit-v">{r['pd_total']}</span></div>
                </div>
                <div class="crit-tipos">
                    {''.join(f"<span class='crit-chip'>{_e(t)}</span>" for t in r['tipos'])}
                </div>
                {corona}
            </div>
            """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# PASO 1 — SUBIR FORMULARIO
# ─────────────────────────────────────────────────────────────
def paso_1():
    barra_progreso()
    st.title("IEPPO — Orientación Vocacional")
    st.caption("Sistema de evaluación vocacional · Paso 1 de 4")
    st.markdown("### Sube el formulario del estudiante")

    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        pdf = st.file_uploader(
            "Formulario escaneado (PDF, máx. 20 MB)",
            type=["pdf"],
            help="Sube el PDF del formulario IEPPO escaneado."
        )
    with c2:
        sexo = st.radio(
            "Sexo",
            options=["F", "M"],
            format_func=lambda x: "Mujer (F)" if x == "F" else "Varón (M)",
            horizontal=False
        )

    st.markdown("### Datos del estudiante")
    n1, n2, n3 = st.columns(3, gap="medium")
    with n1:
        nombre = st.text_input("Nombre(s)", placeholder="Ej. María Fernanda")
    with n2:
        apellido_paterno = st.text_input("Apellido paterno", placeholder="Ej. García")
    with n3:
        apellido_materno = st.text_input("Apellido materno", placeholder="Ej. López")

    nombre_completo = " ".join(
        p for p in [nombre.strip(), apellido_paterno.strip(), apellido_materno.strip()] if p
    )

    st.divider()
    _, btn_col = st.columns([4, 1])
    with btn_col:
        if st.button("Siguiente →", type="primary", use_container_width=True):
            if not pdf:
                st.error("Por favor sube el PDF del formulario.")
                return
            if not nombre.strip() or not apellido_paterno.strip() or not apellido_materno.strip():
                st.error("Completa los tres campos: Nombre(s), Apellido paterno y Apellido materno.")
                return

            with st.spinner("Procesando escaneo con OCR..."):
                dudosos = []
                ocr_exitoso = False
                try:
                    from ocr.pipeline import procesar_formulario_pdf
                    pdf.seek(0)
                    resultado_ocr = procesar_formulario_pdf(pdf)
                    marcas = resultado_ocr["marcas"]
                    ocr_exitoso = resultado_ocr.get("exito", False)

                    if not ocr_exitoso:
                        st.warning(f"{resultado_ocr.get('mensaje', 'OCR con problemas.')}")

                    # Prioridad 1: OCR reporta explícitamente qué ítems son dudosos
                    dudosos = resultado_ocr.get("dudosos") or []

                    # Prioridad 2: OCR reporta confianza por ítem → umbral
                    if not dudosos:
                        confianzas = resultado_ocr.get("confianzas") or {}
                        if confianzas:
                            dudosos = [k for k, v in confianzas.items() if v < 0.8]

                    # Prioridad 3 (fallback): solo "ambos" es intrínsecamente ambiguo
                    if not dudosos and ocr_exitoso:
                        dudosos = [k for k, v in marcas.items() if v == "ambos"]

                except Exception as e:
                    st.warning(f"OCR no disponible: {e}. Se habilitó verificación manual.")
                    marcas = generar_items_vacios()
                    ocr_exitoso = False
                    dudosos = []

            st.session_state.datos = {
                "nombre": nombre.strip(),
                "apellido_paterno": apellido_paterno.strip(),
                "apellido_materno": apellido_materno.strip(),
                "nombre_completo": nombre_completo,
                "sexo": sexo,
                "marcas": marcas,
                "ocr_exitoso": ocr_exitoso,
                "dudosos": dudosos,
            }
            ir_a_paso(2)


# ─────────────────────────────────────────────────────────────
# PASO 2 — VERIFICACIÓN + PUNTAJES + BAREMOS
# ─────────────────────────────────────────────────────────────
def paso_2():
    barra_progreso()
    st.title("Paso 2: Verificar marcas y puntajes")
    st.caption("Revisa cada bloque por pestañas. Solo los ítems dudosos aparecen resaltados.")

    marcas: dict = st.session_state.datos["marcas"]
    sexo: str = st.session_state.datos["sexo"]
    dudosos: set = set(st.session_state.datos.get("dudosos", []))

    OPCIONES_TEXTO = ["Vacío", "No", "Sí", "Ambos"]
    OPCIONES_VALOR = ["vacio", "no", "si", "ambos"]

    # Número de columnas por bloque
    N_COLS = 3

    col_items, col_pts = st.columns([3, 1.2], gap="large")

    # ─── Columna izquierda: tabs por bloque ───
    with col_items:
        st.markdown("### Lista de ítems")
        n_dud = len(dudosos)
        if n_dud:
            st.caption(f"{n_dud} ítem(s) marcados como dudosos por el OCR.")
        else:
            st.caption("Ningún ítem marcado como dudoso.")

        bloques = obtener_bloques()
        nombres_bloques = list(bloques.keys())
        nuevas_marcas = {}

        tabs = st.tabs(nombres_bloques)
        for tab, nombre_bloque in zip(tabs, nombres_bloques):
            items = bloques[nombre_bloque]
            n = len(items)
            per_col = -(-n // N_COLS)  # ceil(n / N_COLS)

            with tab:
                grid = st.columns(N_COLS, gap="small")

                for i, item in enumerate(items):
                    # Columna en orden vertical (column-major):
                    # H1  H8  H15
                    # H2  H9  H16
                    # ...
                    col_idx = min(i // per_col, N_COLS - 1)

                    actual = marcas.get(item, "vacio")
                    opt_idx = OPCIONES_VALOR.index(actual) if actual in OPCIONES_VALOR else 0
                    es_dudoso = item in dudosos
                    badge = "<span class='mini-badge'>Revisar</span>" if es_dudoso else ""
                    title_cls = "item-title dudoso" if es_dudoso else "item-title"

                    with grid[col_idx]:
                        with st.container(border=True):
                            st.markdown(
                                f"<div class='{title_cls}'>{_e(item)}{badge}</div>",
                                unsafe_allow_html=True
                            )
                            nuevo = st.radio(
                                label=item,
                                options=OPCIONES_TEXTO,
                                index=opt_idx,
                                horizontal=True,
                                key=f"r_{item}",
                                label_visibility="collapsed"
                            )
                        nuevas_marcas[item] = OPCIONES_VALOR[OPCIONES_TEXTO.index(nuevo)]

    st.session_state.datos["marcas"] = nuevas_marcas

    # ─── Columna derecha: resumen ───
    with col_pts:
        st.markdown("### Resumen")
        st.caption("Se actualiza automáticamente.")

        puntajes = calcular_pd(nuevas_marcas)
        con_baremos = calcular_baremos(puntajes, sexo)
        st.session_state.datos["puntajes"] = con_baremos

        filas = []
        for tipo, datos in con_baremos.items():
            baremo = datos["Baremo"]
            filas.append({
                "Tipo": tipo,
                "Crit": tipo_a_criterio(tipo),
                "PD": datos["PD"],
                "Baremo": baremo if baremo is not None else None
            })

        df = pd.DataFrame(filas).sort_values(
            "Baremo", ascending=False, na_position="last"
        )
        df["Baremo"] = df["Baremo"].apply(lambda v: v if v is not None else "—")
        st.dataframe(df, hide_index=True, use_container_width=True, height=280)

        audit = auditar_marcas(nuevas_marcas)
        if audit["vacios"]:
            st.caption(f"{len(audit['vacios'])} ítem(s) sin marcar.")
        if audit["ambos"]:
            st.caption(f"{len(audit['ambos'])} ítem(s) con doble marca.")

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
    st.caption("Selección de carreras en base a los dos tipos con mayor baremo.")

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

    # ─── Panel de criterios P / E / H ───
    panel_criterios(con_baremos)

    st.markdown("<div class='section-title'>Top 2 tipos vocacionales</div>",
                unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(f"""
        <div class="voc-card gold">
            <div class="voc-rank">Puesto 1 · Criterio {tipo_a_criterio(tipo1)}</div>
            <div class="voc-tipo">{_e(tipo1)}</div>
            <div class="voc-stats">
                <span>PD: <b>{top[0]['PD']}</b></span>
                <span>Baremo: <b>{top[0]['Baremo'] if top[0]['Baremo'] is not None else '—'}</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="voc-card silver">
            <div class="voc-rank">Puesto 2 · Criterio {tipo_a_criterio(tipo2)}</div>
            <div class="voc-tipo">{_e(tipo2)}</div>
            <div class="voc-stats">
                <span>PD: <b>{top[1]['PD']}</b></span>
                <span>Baremo: <b>{top[1]['Baremo'] if top[1]['Baremo'] is not None else '—'}</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    carreras = seleccionar_4_carreras(tipo1, tipo2)
    st.session_state.datos["carreras"] = carreras
    st.session_state.datos["top"] = top

    st.markdown("<div class='section-title'>Carreras afines recomendadas</div>",
                unsafe_allow_html=True)

    ca_col, re_col = st.columns(2, gap="large")
    with ca_col:
        st.markdown("**Carreras principales**")
        for c in carreras["principales"]:
            st.markdown(f"""
            <div class="career-card principal">
                <div class="career-badge">Principal · {tipo_a_criterio(c['tipo'])}</div>
                <div class="career-name">{_e(c['carrera'])}</div>
                <div class="career-tipo">{_e(c['tipo'])}</div>
                <div class="career-rel">{_e(c.get('relacion', ''))}</div>
            </div>
            """, unsafe_allow_html=True)

    with re_col:
        st.markdown("**Carreras de respaldo**")
        for c in carreras["respaldo"]:
            st.markdown(f"""
            <div class="career-card respaldo">
                <div class="career-badge">Respaldo · {tipo_a_criterio(c['tipo'])}</div>
                <div class="career-name">{_e(c['carrera'])}</div>
                <div class="career-tipo">{_e(c['tipo'])}</div>
                <div class="career-rel">{_e(c.get('relacion', ''))}</div>
            </div>
            """, unsafe_allow_html=True)

    with st.expander("Ver ranking completo de los 7 tipos"):
        ranking = ranking_tipos(con_baremos)
        df_ranking = pd.DataFrame([
            {"#": r["posicion"],
             "Criterio": tipo_a_criterio(r["tipo"]),
             "Tipo Vocacional": r["tipo"],
             "PD": r["PD"],
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
    st.caption("Resumen vocacional completo del estudiante.")

    datos    = st.session_state.datos
    nombre   = datos.get("nombre", "")
    ap_pat   = datos.get("apellido_paterno", "")
    ap_mat   = datos.get("apellido_materno", "")
    nombre_completo = datos.get("nombre_completo") or f"{nombre} {ap_pat} {ap_mat}".strip()
    sexo     = datos.get("sexo", "—")
    top      = datos.get("top", [])
    carreras = datos.get("carreras", {"principales": [], "respaldo": []})
    con_baremos = datos.get("puntajes", {})

    sexo_label = "Mujer (F)" if sexo == "F" else "Varón (M)"
    inicial = (nombre.strip()[:1] or "?").upper()

    # ─── Cabecera ───
    st.markdown(f"""
    <div class="student-header">
        <div class="student-avatar">{_e(inicial)}</div>
        <div>
            <div class="student-name">{_e(nombre_completo)}</div>
            <div class="student-meta">Sexo: {_e(sexo_label)} · Evaluación IEPPO</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ─── Panel de criterios P/E/H ───
    if con_baremos:
        panel_criterios(con_baremos)

    # ─── 3 columnas ───
    st.markdown("<div class='section-title'>Detalle de resultados</div>",
                unsafe_allow_html=True)

    col_top, col_prin, col_resp = st.columns(3, gap="large")

    with col_top:
        st.markdown("**Top vocacional**")
        if top:
            for i, t in enumerate(top[:2], 1):
                cls = "gold" if i == 1 else "silver"
                rank = "Puesto 1" if i == 1 else "Puesto 2"
                bar = t["Baremo"] if t["Baremo"] is not None else "—"
                st.markdown(f"""
                <div class="voc-card {cls}">
                    <div class="voc-rank">{rank} · Criterio {tipo_a_criterio(t['tipo'])}</div>
                    <div class="voc-tipo">{_e(t['tipo'])}</div>
                    <div class="voc-stats">
                        <span>PD: <b>{t['PD']}</b></span>
                        <span>Baremo: <b>{bar}</b></span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Sin datos de Top vocacional.")

    with col_prin:
        st.markdown("**Carreras principales**")
        for c in carreras.get("principales", []):
            st.markdown(f"""
            <div class="career-card principal">
                <div class="career-badge">Principal · {tipo_a_criterio(c['tipo'])}</div>
                <div class="career-name">{_e(c['carrera'])}</div>
                <div class="career-tipo">{_e(c['tipo'])}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_resp:
        st.markdown("**Carreras de respaldo**")
        for c in carreras.get("respaldo", []):
            st.markdown(f"""
            <div class="career-card respaldo">
                <div class="career-badge">Respaldo · {tipo_a_criterio(c['tipo'])}</div>
                <div class="career-name">{_e(c['carrera'])}</div>
                <div class="career-tipo">{_e(c['tipo'])}</div>
            </div>
            """, unsafe_allow_html=True)

    # ─── Texto para copiar ───
    c_pr = [c.get("carrera", "—") for c in carreras.get("principales", [])]
    c_re = [c.get("carrera", "—") for c in carreras.get("respaldo", [])]

    texto_copia = f"""RESULTADO IEPPO — ORIENTACIÓN VOCACIONAL
{'='*40}
Estudiante : {nombre_completo}
Sexo       : {sexo_label}

TOP 2 VOCACIONAL:
  1. {top[0]['tipo'] if len(top) > 0 else '—'} (Baremo {top[0]['Baremo'] if len(top) > 0 else '—'}) [Criterio {tipo_a_criterio(top[0]['tipo']) if len(top) > 0 else '—'}]
  2. {top[1]['tipo'] if len(top) > 1 else '—'} (Baremo {top[1]['Baremo'] if len(top) > 1 else '—'}) [Criterio {tipo_a_criterio(top[1]['tipo']) if len(top) > 1 else '—'}]

CARRERAS PRINCIPALES:
  1. {c_pr[0] if len(c_pr) > 0 else '—'}
  2. {c_pr[1] if len(c_pr) > 1 else '—'}

CARRERAS DE RESPALDO:
  3. {c_re[0] if len(c_re) > 0 else '—'}
  4. {c_re[1] if len(c_re) > 1 else '—'}
"""

    st.markdown("<div class='section-title'>Copiar resultado</div>",
                unsafe_allow_html=True)
    st.code(texto_copia, language=None)

    # ─── Guardar en BD ───
    puntajes = datos.get("puntajes", {})
    marcas   = datos.get("marcas", {})
    if puntajes and marcas:
        try:
            from db.models import guardar_evaluacion
            form_id = guardar_evaluacion(nombre_completo, sexo, marcas, puntajes, carreras)
            if form_id:
                st.caption(f"Evaluación guardada en base de datos (ID: {form_id})")
        except Exception:
            pass

    st.divider()
    retro_col, _, nuevo_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True):
            ir_a_paso(3)
    with nuevo_col:
        if st.button("Nuevo estudiante", type="primary", use_container_width=True):
            st.session_state.paso = 1
            st.session_state.datos = {}
            st.rerun()


# ─────────────────────────────────────────────────────────────
# ROUTER PRINCIPAL
# ─────────────────────────────────────────────────────────────
PASOS = {1: paso_1, 2: paso_2, 3: paso_3, 4: paso_4}
PASOS[st.session_state.paso]()