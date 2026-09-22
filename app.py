import streamlit as st
import html as _html
import pandas as pd
import difflib
from pathlib import Path

from vocacional.puntajes import calcular_pd
from vocacional.baremos import calcular_baremos
from vocacional.areas import top_2, ranking_tipos
from vocacional.carreras import (
    seleccionar_4_carreras,
    CARRERAS,
    INDICE_TIPOS,
    INDICE_GRUPOS,
    PALABRAS,
    TIPOS_REL,
)
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


def cargar_css():
    css_path = Path(__file__).parent / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>",
                    unsafe_allow_html=True)
    else:
        st.warning(f"No se encontró styles.css en: {css_path}")


cargar_css()


# ─────────────────────────────────────────────────────────────
# CRITERIOS P / E / H
# ─────────────────────────────────────────────────────────────
CRITERIOS = {
    "P": {"nombre": "Personas",
          "descripcion": "Trato con personas, comunicación, expresión y servicio.",
          "tipos": ["SOCIAL", "LIDERAZGO", "ARTÍSTICO"],
          "color": "#2563eb"},
    "E": {"nombre": "Empresa",
          "descripcion": "Organización, gestión, planeamiento y emprendimiento.",
          "tipos": ["ORGANIZADO", "EMPRENDEDOR"],
          "color": "#d97706"},
    "H": {"nombre": "Herramientas",
          "descripcion": "Análisis técnico, científico y manipulación de objetos.",
          "tipos": ["INVESTIGATIVO", "TÉCNICO MECÁNICO"],
          "color": "#059669"},
}


def tipo_a_criterio(tipo: str) -> str:
    for k, meta in CRITERIOS.items():
        if tipo.upper() in [t.upper() for t in meta["tipos"]]:
            return k
    return "?"


def resumen_criterios(con_baremos: dict) -> dict:
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
    return max(resumen.items(), key=lambda kv: kv[1]["baremo_max"])[0]


# ─────────────────────────────────────────────────────────────
# NIVELES E INSTITUCIONES
# ─────────────────────────────────────────────────────────────
NIVELES = {
    "universitario": {"label": "Universitario",
                      "desc": "Carreras de 5 años a más (licenciatura).",
                      "jerarquia": 3, "chip": "nivel-univ"},
    "tecnico":       {"label": "Técnico",
                      "desc": "Institutos técnicos (2-3 años).",
                      "jerarquia": 2, "chip": "nivel-tec"},
    "cetpro":        {"label": "CETPRO / Ocupacional",
                      "desc": "Cursos cortos ocupacionales (6-18 meses).",
                      "jerarquia": 1, "chip": "nivel-cetpro"},
}

INSTITUCIONES = {
    "publica":     {"label": "Pública",      "chip": "inst-pub"},
    "privada":     {"label": "Privada",      "chip": "inst-priv"},
    "indiferente": {"label": "Indiferente",  "chip": ""},
}

CARRERAS_CETPRO = {
    "Operador de Maquinarias Pesadas", "Soldadura Industrial",
    "Cosmetología", "Auxiliar de Vuelo", "Dibujo y Pintura",
}
CARRERAS_TECNICAS = {
    "Tec en Informática", "Tec en Laboratorio", "Mecánica Automotriz",
    "Mecatrónica", "Metalúrgica", "Industrial", "Topografía",
    "Diseño de Interiores", "Gastronomía", "Gastronomía/Repostería",
    "Industria Alimentaria", "Informática",
}


def nivel_de_carrera(carrera: str) -> str:
    if carrera in CARRERAS_CETPRO:
        return "cetpro"
    if carrera in CARRERAS_TECNICAS:
        return "tecnico"
    return "universitario"


def es_financiable(nivel_carrera: str, nivel_max: str) -> bool:
    return NIVELES[nivel_carrera]["jerarquia"] <= NIVELES[nivel_max]["jerarquia"]


# ─────────────────────────────────────────────────────────────
# CATÁLOGO PLANO Y FUZZY MATCH
# ─────────────────────────────────────────────────────────────
def catalogo_plano() -> list[str]:
    seen = set()
    for carreras in CARRERAS.values():
        for c in carreras:
            seen.add(c)
    return sorted(seen)


CATALOGO = catalogo_plano()


def normalizar_carrera(texto: str) -> str | None:
    if not texto or not texto.strip():
        return None
    t = texto.strip()
    for c in CATALOGO:
        if c.lower() == t.lower():
            return c
    matches = difflib.get_close_matches(t, CATALOGO, n=1, cutoff=0.62)
    return matches[0] if matches else None


# ─────────────────────────────────────────────────────────────
# SISTEMA INTELIGENTE DE RECOMENDACIÓN
# ─────────────────────────────────────────────────────────────
# Pesos del sistema (todos ajustables en un solo lugar)
W_VOC        = 1.0    # peso afinidad con Top 2 tipos
W_PROP       = 2.5    # peso afinidad con propuestas del alumno  ← clave
W_TEST       = 0.8    # peso afinidad con carreras del test
BONUS_ALUMNO = 20     # bonus si la carrera está en la lista del alumno
BONUS_TEST   = 5      # bonus si la carrera está en la lista del test


def _tipos(c: str) -> set:
    return set(INDICE_TIPOS.get(c, []))


def _grupos(c: str) -> set:
    return {g["id"] for g in INDICE_GRUPOS.get(c, [])}


def _keywords(c: str) -> set:
    return set(PALABRAS.get(c, []))


def _score_vocacional(carrera: str, tipo1: str, tipo2: str) -> float:
    """0-24: qué tan alineada está la carrera con los 2 tipos Top."""
    tipos = _tipos(carrera)
    s = 0
    if tipo1 in tipos: s += 8
    if tipo2 in tipos: s += 8
    if tipo1 in tipos and tipo2 in tipos: s += 4  # bonus por pertenecer a ambos
    for rel in TIPOS_REL.get(tipo1, []):
        if rel in tipos: s += 2
    for rel in TIPOS_REL.get(tipo2, []):
        if rel in tipos: s += 2
    return s


def _similitud_con(a: str, b: str) -> float:
    """Cuánto se parece `a` a `b`: grupos + keywords + tipos comunes."""
    if a == b:
        return 0.0  # no autoreforzar
    s = 0
    if _grupos(a) & _grupos(b):         s += 4
    s += 2 * min(len(_keywords(a) & _keywords(b)), 3)
    s += 3 * len(_tipos(a) & _tipos(b))
    return s


def _score_afinidad_lista(carrera: str, lista: list[str]) -> float:
    """Promedio de similitud con las carreras de una lista."""
    if not lista:
        return 0.0
    otras = [c for c in lista if c != carrera]
    if not otras:
        return 0.0
    return sum(_similitud_con(carrera, o) for o in otras) / len(otras)


def _score_carrera(carrera, tipo1, tipo2, test_norm, alumno_norm):
    """Puntaje compuesto de una candidata."""
    s_voc  = _score_vocacional(carrera, tipo1, tipo2)
    s_prop = _score_afinidad_lista(carrera, alumno_norm)
    s_test = _score_afinidad_lista(carrera, test_norm)

    b_alumno = BONUS_ALUMNO if carrera in alumno_norm else 0
    b_test   = BONUS_TEST   if carrera in test_norm   else 0

    total = (s_voc  * W_VOC
             + s_prop * W_PROP
             + s_test * W_TEST
             + b_alumno
             + b_test)

    return {
        "carrera": carrera,
        "nivel":   nivel_de_carrera(carrera),
        "score":   round(total, 1),
        "s_voc":   round(s_voc, 1),
        "s_prop":  round(s_prop, 1),
        "s_test":  round(s_test, 1),
        "en_test": carrera in test_norm,
        "en_alumno": carrera in alumno_norm,
    }


def evaluar_propuesta(carreras_test, carreras_alumno, nivel_max, institucion, tipo1, tipo2):
    """
    Evalúa las 5 candidatas (2 test + 3 alumno) y devuelve 2 finales.
    Universo = sólo las 5 candidatas (deduplicadas).
    """
    # 1. Normalizar alumno (fuzzy)
    alumno_norm, no_encontradas = [], []
    for c in carreras_alumno:
        if not c or not c.strip():
            continue
        n = normalizar_carrera(c)
        if n:
            alumno_norm.append(n)
        else:
            no_encontradas.append(c.strip())

    test_norm = [c["carrera"] for c in carreras_test]

    # 2. Universo = 5 candidatas deduplicadas
    universo, seen = [], set()
    for c in test_norm + alumno_norm:
        if c not in seen:
            seen.add(c)
            universo.append(c)

    # 3. Puntuar
    scored = [_score_carrera(c, tipo1, tipo2, test_norm, alumno_norm) for c in universo]

    # 4. Filtrar por nivel financiable
    financiables = [s for s in scored if es_financiable(s["nivel"], nivel_max)]
    descartadas  = [s for s in scored if s not in financiables]

    # 5. Ordenar y tomar 2
    financiables.sort(key=lambda x: x["score"], reverse=True)
    finales = financiables[:2]
    for i, f in enumerate(finales, 1):
        f["rank"] = i

    return {
        "finales": finales,
        "no_encontradas": no_encontradas,
        "descartadas_nivel": descartadas,
        "nivel_max": nivel_max,
        "institucion": institucion,
    }


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
    return _html.escape(str(v if v is not None else "—"))


# ─────────────────────────────────────────────────────────────
# BARRA DE PROGRESO
# ─────────────────────────────────────────────────────────────
def barra_progreso():
    paso_actual = st.session_state.paso
    labels = ["Subir", "Verificar", "Top 2", "Propuesta", "Resultado"]
    clases = []
    for i in range(1, 6):
        if i < paso_actual:   clases.append("step done")
        elif i == paso_actual: clases.append("step active")
        else:                  clases.append("step")
    html_bar = "<div class='step-bar'>" + "".join(
        f"<div class='{c}'>{i} · {l}</div>"
        for i, (c, l) in enumerate(zip(clases, labels), 1)
    ) + "</div>"
    st.markdown(html_bar, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# COMPONENTE: PANEL DE CRITERIOS
# ─────────────────────────────────────────────────────────────
def panel_criterios(con_baremos: dict):
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
# PASO 1 — SUBIR
# ─────────────────────────────────────────────────────────────
def paso_1():
    barra_progreso()
    st.title("IEPPO — Orientación Vocacional")
    st.caption("Sistema de evaluación vocacional · Paso 1 de 5")
    st.markdown("### Sube el formulario del estudiante")

    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        pdf = st.file_uploader("Formulario escaneado (PDF, máx. 20 MB)",
                               type=["pdf"],
                               help="Sube el PDF del formulario IEPPO escaneado.")
    with c2:
        sexo = st.radio("Sexo", options=["F", "M"],
                        format_func=lambda x: "Mujer (F)" if x == "F" else "Varón (M)",
                        horizontal=False)

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
                dudosos, ocr_exitoso = [], False
                try:
                    from ocr.pipeline import procesar_formulario_pdf
                    pdf.seek(0)
                    resultado_ocr = procesar_formulario_pdf(pdf)
                    marcas = resultado_ocr["marcas"]
                    ocr_exitoso = resultado_ocr.get("exito", False)
                    if not ocr_exitoso:
                        st.warning(f"{resultado_ocr.get('mensaje', 'OCR con problemas.')}")
                    dudosos = resultado_ocr.get("dudosos") or []
                    if not dudosos:
                        confianzas = resultado_ocr.get("confianzas") or {}
                        if confianzas:
                            dudosos = [k for k, v in confianzas.items() if v < 0.8]
                    if not dudosos and ocr_exitoso:
                        dudosos = [k for k, v in marcas.items() if v == "ambos"]
                except Exception as e:
                    st.warning(f"OCR no disponible: {e}. Se habilitó verificación manual.")
                    marcas = generar_items_vacios()
                    ocr_exitoso, dudosos = False, []

            st.session_state.datos = {
                "nombre": nombre.strip(),
                "apellido_paterno": apellido_paterno.strip(),
                "apellido_materno": apellido_materno.strip(),
                "nombre_completo": nombre_completo,
                "sexo": sexo, "marcas": marcas,
                "ocr_exitoso": ocr_exitoso, "dudosos": dudosos,
            }
            ir_a_paso(2)


# ─────────────────────────────────────────────────────────────
# PASO 2 — VERIFICAR
# ─────────────────────────────────────────────────────────────
def paso_2():
    barra_progreso()
    st.title("Paso 2: Verificar marcas y puntajes")
    st.caption("Revisa cada bloque por pestañas. Solo los ítems dudosos aparecen resaltados.")

    marcas  = st.session_state.datos["marcas"]
    sexo    = st.session_state.datos["sexo"]
    dudosos = set(st.session_state.datos.get("dudosos", []))

    OPCIONES_TEXTO = ["Vacío", "No", "Sí", "Ambos"]
    OPCIONES_VALOR = ["vacio", "no", "si", "ambos"]
    N_COLS = 3

    col_items, col_pts = st.columns([3, 1.2], gap="large")

    with col_items:
        st.markdown("### Lista de ítems")
        n_dud = len(dudosos)
        st.caption(f"{n_dud} ítem(s) marcados como dudosos por el OCR." if n_dud
                   else "Ningún ítem marcado como dudoso.")

        bloques = obtener_bloques()
        nombres_bloques = list(bloques.keys())
        nuevas_marcas = {}

        tabs = st.tabs(nombres_bloques)
        for tab, nombre_bloque in zip(tabs, nombres_bloques):
            items = bloques[nombre_bloque]
            n = len(items)
            per_col = -(-n // N_COLS)
            with tab:
                grid = st.columns(N_COLS, gap="small")
                for i, item in enumerate(items):
                    col_idx = min(i // per_col, N_COLS - 1)
                    actual = marcas.get(item, "vacio")
                    opt_idx = OPCIONES_VALOR.index(actual) if actual in OPCIONES_VALOR else 0
                    es_dudoso = item in dudosos
                    badge = "<span class='mini-badge'>Revisar</span>" if es_dudoso else ""
                    title_cls = "item-title dudoso" if es_dudoso else "item-title"
                    with grid[col_idx]:
                        with st.container(border=True):
                            st.markdown(f"<div class='{title_cls}'>{_e(item)}{badge}</div>",
                                        unsafe_allow_html=True)
                            nuevo = st.radio(label=item, options=OPCIONES_TEXTO,
                                             index=opt_idx, horizontal=True,
                                             key=f"r_{item}", label_visibility="collapsed")
                        nuevas_marcas[item] = OPCIONES_VALOR[OPCIONES_TEXTO.index(nuevo)]

    st.session_state.datos["marcas"] = nuevas_marcas

    with col_pts:
        st.markdown("### Resumen")
        st.caption("Se actualiza automáticamente.")
        puntajes = calcular_pd(nuevas_marcas)
        con_baremos = calcular_baremos(puntajes, sexo)
        st.session_state.datos["puntajes"] = con_baremos

        filas = []
        for tipo, datos in con_baremos.items():
            baremo = datos["Baremo"]
            filas.append({"Tipo": tipo, "Crit": tipo_a_criterio(tipo),
                          "PD": datos["PD"],
                          "Baremo": baremo if baremo is not None else None})
        df = pd.DataFrame(filas).sort_values("Baremo", ascending=False, na_position="last")
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
        if st.button("← Retroceder"): ir_a_paso(2)
        return

    top = top_2(con_baremos)
    if len(top) < 2:
        st.error("No se pudieron determinar 2 tipos vocacionales con baremo válido.")
        if st.button("← Retroceder"): ir_a_paso(2)
        return

    tipo1, tipo2 = top[0]["tipo"], top[1]["tipo"]

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

    st.markdown("<div class='section-title'>Carreras sugeridas por el test</div>",
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
            {"#": r["posicion"], "Criterio": tipo_a_criterio(r["tipo"]),
             "Tipo Vocacional": r["tipo"], "PD": r["PD"],
             "Baremo": r["Baremo"] if r["Baremo"] is not None else "—"}
            for r in ranking
        ])
        st.dataframe(df_ranking, hide_index=True, use_container_width=True)

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(2)
    with conf_col:
        if st.button("Continuar →", type="primary", use_container_width=True): ir_a_paso(4)


# ─────────────────────────────────────────────────────────────
# PASO 4 — PROPUESTA DEL ESTUDIANTE
# ─────────────────────────────────────────────────────────────
def paso_4():
    barra_progreso()
    st.title("Paso 4: Propuesta del estudiante")
    st.caption("El estudiante propone 3 carreras. El sistema las combina con las del test.")

    datos = st.session_state.datos
    top = datos.get("top", [])
    carreras_test = datos.get("carreras", {"principales": [], "respaldo": []})
    tipo1 = top[0]["tipo"] if len(top) > 0 else ""
    tipo2 = top[1]["tipo"] if len(top) > 1 else ""

    if not tipo1 or not tipo2:
        st.error("Falta el Top 2. Regresa al paso 3.")
        if st.button("← Retroceder"): ir_a_paso(3)
        return

    # Las 2 carreras del test
    st.markdown("<div class='section-title'>Carreras sugeridas por el test</div>",
                unsafe_allow_html=True)
    principales = carreras_test.get("principales", [])
    for i, c in enumerate(principales, 1):
        st.markdown(f"""
        <div class="proposal-row">
            <div class="proposal-num">{i}</div>
            <div class="proposal-carrera">{_e(c['carrera'])}</div>
            <div class="proposal-origen test">Test</div>
        </div>
        """, unsafe_allow_html=True)

    # Formulario
    st.markdown("<div class='section-title'>Carreras propuestas por el estudiante</div>",
                unsafe_allow_html=True)
    st.markdown("""
    <div class="proposal-box">
        <h4>Ingresa 3 carreras de interés</h4>
        <p>Escribe los nombres tal como los conozcas. El sistema los emparejará
        con el catálogo y evaluará su afinidad con el test y entre ellas.</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1: prop1 = st.text_input("Carrera 1", placeholder="Ej. Agronomía", key="prop1")
    with c2: prop2 = st.text_input("Carrera 2", placeholder="Ej. Ing de Sistemas", key="prop2")
    with c3: prop3 = st.text_input("Carrera 3", placeholder="Ej. Biología", key="prop3")

    # Nivel
    st.markdown("<div class='section-title'>Nivel educativo que puede financiar</div>",
                unsafe_allow_html=True)
    nivel_max = st.radio(
        "Nivel máximo",
        options=list(NIVELES.keys()),
        format_func=lambda k: f"{NIVELES[k]['label']} — {NIVELES[k]['desc']}",
        horizontal=False, key="nivel_max", label_visibility="collapsed"
    )

    # Institución
    st.markdown("<div class='section-title'>Tipo de institución preferida</div>",
                unsafe_allow_html=True)
    institucion = st.radio(
        "Institución",
        options=list(INSTITUCIONES.keys()),
        format_func=lambda k: INSTITUCIONES[k]["label"],
        horizontal=True, key="institucion", label_visibility="collapsed"
    )

    # Preview de las candidatas
    carreras_alumno = [prop1, prop2, prop3]
    validas = [c for c in carreras_alumno if c and c.strip()]
    if validas:
        st.markdown("<div class='section-title'>Candidatas a evaluar</div>",
                    unsafe_allow_html=True)
        for c in principales:
            st.markdown(f"""
            <div class="proposal-row">
                <div class="proposal-num">•</div>
                <div class="proposal-carrera">{_e(c['carrera'])}</div>
                <div class="proposal-origen test">Test</div>
            </div>
            """, unsafe_allow_html=True)
        for c in validas:
            norm = normalizar_carrera(c)
            texto = norm if norm else f"{c} (no encontrada en catálogo)"
            st.markdown(f"""
            <div class="proposal-row">
                <div class="proposal-num">•</div>
                <div class="proposal-carrera">{_e(texto)}</div>
                <div class="proposal-origen alumno">Alumno</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(3)
    with conf_col:
        if st.button("Evaluar →", type="primary", use_container_width=True):
            if not any(v and v.strip() for v in carreras_alumno):
                st.error("Ingresa al menos una carrera propuesta.")
                return

            resultado = evaluar_propuesta(
                carreras_test=principales,
                carreras_alumno=carreras_alumno,
                nivel_max=nivel_max,
                institucion=institucion,
                tipo1=tipo1,
                tipo2=tipo2,
            )
            st.session_state.datos["propuesta"] = {
                "carreras_alumno": carreras_alumno,
                "nivel_max": nivel_max,
                "institucion": institucion,
                "resultado": resultado,
            }
            ir_a_paso(5)


# ─────────────────────────────────────────────────────────────
# PASO 5 — RESULTADO FINAL
# ─────────────────────────────────────────────────────────────
def paso_5():
    barra_progreso()
    st.title("Paso 5: Resultado final")
    st.caption("Recomendación final: síntesis del test y la propuesta del estudiante.")

    datos = st.session_state.datos
    nombre    = datos.get("nombre", "")
    ap_pat    = datos.get("apellido_paterno", "")
    ap_mat    = datos.get("apellido_materno", "")
    nombre_completo = datos.get("nombre_completo") or f"{nombre} {ap_pat} {ap_mat}".strip()
    sexo      = datos.get("sexo", "—")
    top       = datos.get("top", [])
    carreras  = datos.get("carreras", {"principales": [], "respaldo": []})
    con_baremos = datos.get("puntajes", {})
    propuesta = datos.get("propuesta", {})

    sexo_label = "Mujer (F)" if sexo == "F" else "Varón (M)"
    inicial = (nombre.strip()[:1] or "?").upper()

    st.markdown(f"""
    <div class="student-header">
        <div class="student-avatar">{_e(inicial)}</div>
        <div>
            <div class="student-name">{_e(nombre_completo)}</div>
            <div class="student-meta">Sexo: {_e(sexo_label)} · Evaluación IEPPO</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if con_baremos:
        panel_criterios(con_baremos)

    # ─── Finales ───
    resultado = propuesta.get("resultado", {})
    finales   = resultado.get("finales", [])
    inst_key  = propuesta.get("institucion", "indiferente")
    inst_meta = INSTITUCIONES.get(inst_key, INSTITUCIONES["indiferente"])

    if finales:
        st.markdown("<div class='section-title'>Carreras finales recomendadas</div>",
                    unsafe_allow_html=True)

        # Score máximo para normalizar la barra
        max_score = max(f["score"] for f in finales) or 1

        for f in finales:
            nivel_meta = NIVELES[f["nivel"]]
            afin_pct = min(int(f["score"] / max_score * 100), 100)

            if f["en_test"] and f["en_alumno"]:
                origen_txt = "Síntesis (test + alumno)"
                origen_clase = "sintesis"
            elif f["en_alumno"]:
                origen_txt = "Propuesta del estudiante"
                origen_clase = "alumno"
            elif f["en_test"]:
                origen_txt = "Sugerida por el test"
                origen_clase = "test"
            else:
                origen_txt = "Síntesis"
                origen_clase = "sintesis"

            st.markdown(f"""
            <div class="final-card">
                <div class="rank">Puesto {f['rank']}</div>
                <div class="name">{_e(f['carrera'])}</div>
                <div class="meta">
                    <span class="meta-chip {nivel_meta['chip']}">{nivel_meta['label']}</span>
                    <span class="meta-chip {inst_meta['chip']}">{inst_meta['label']}</span>
                    <span class="meta-chip">Score {f['score']}</span>
                </div>
                <div class="origen-line">Origen: <b>{origen_txt}</b></div>
                <div class="score-bar">
                    <div class="score-fill" style="width:{afin_pct}%;"></div>
                </div>
                <div class="score-detail">
                    <span>Vocacional <b>{f['s_voc']}</b></span>
                    <span>Afinidad personal <b>{f['s_prop']}</b></span>
                    <span>Afinidad test <b>{f['s_test']}</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ─── Advertencias ───
    no_enc = resultado.get("no_encontradas", [])
    if no_enc:
        st.warning("Carreras no encontradas en el catálogo (fueron ignoradas): "
                   + ", ".join(no_enc))

    desc_niv = resultado.get("descartadas_nivel", [])
    if desc_niv:
        with st.expander(f"{len(desc_niv)} carrera(s) descartadas por nivel financiable"):
            for c in desc_niv:
                st.caption(f"· {c['carrera']} — nivel {NIVELES[c['nivel']]['label']} "
                           f"· score {c['score']}")

    # ─── Detalle colapsable ───
    with st.expander("Ver Top 2, propuestas del alumno y sugerencias del test"):
        col_top, col_prin, col_resp = st.columns(3, gap="large")
        with col_top:
            st.markdown("**Top vocacional**")
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
        with col_prin:
            st.markdown("**Principales (test)**")
            for c in carreras.get("principales", []):
                st.markdown(f"""
                <div class="career-card principal">
                    <div class="career-badge">Principal</div>
                    <div class="career-name">{_e(c['carrera'])}</div>
                    <div class="career-tipo">{_e(c['tipo'])}</div>
                </div>
                """, unsafe_allow_html=True)
        with col_resp:
            st.markdown("**Respaldo (test)**")
            for c in carreras.get("respaldo", []):
                st.markdown(f"""
                <div class="career-card respaldo">
                    <div class="career-badge">Respaldo</div>
                    <div class="career-name">{_e(c['carrera'])}</div>
                    <div class="career-tipo">{_e(c['tipo'])}</div>
                </div>
                """, unsafe_allow_html=True)

    # ─── Texto para copiar ───
    nivel_label = NIVELES[propuesta.get("nivel_max", "universitario")]["label"]
    inst_label  = INSTITUCIONES.get(propuesta.get("institucion", "indiferente"))["label"]

    lineas_finales = [
        f"  {f['rank']}. {f['carrera']} — {NIVELES[f['nivel']]['label']} "
        f"· {inst_label} · score {f['score']}"
        for f in finales
    ]
    finales_txt = "\n".join(lineas_finales) if lineas_finales else "  —"

    c_pr = [c.get("carrera", "—") for c in carreras.get("principales", [])]
    c_re = [c.get("carrera", "—") for c in carreras.get("respaldo", [])]

    texto_copia = f"""RESULTADO IEPPO — ORIENTACIÓN VOCACIONAL
{'='*40}
Estudiante : {nombre_completo}
Sexo       : {sexo_label}

TOP 2 VOCACIONAL:
  1. {top[0]['tipo'] if len(top) > 0 else '—'} (Baremo {top[0]['Baremo'] if len(top) > 0 else '—'}) [Criterio {tipo_a_criterio(top[0]['tipo']) if len(top) > 0 else '—'}]
  2. {top[1]['tipo'] if len(top) > 1 else '—'} (Baremo {top[1]['Baremo'] if len(top) > 1 else '—'}) [Criterio {tipo_a_criterio(top[1]['tipo']) if len(top) > 1 else '—'}]

CARRERAS SUGERIDAS POR EL TEST:
  1. {c_pr[0] if len(c_pr) > 0 else '—'}
  2. {c_pr[1] if len(c_pr) > 1 else '—'}

NIVEL FINANCIABLE : {nivel_label}
INSTITUCIÓN       : {inst_label}

CARRERAS FINALES RECOMENDADAS:
{finales_txt}
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
            payload = dict(carreras)
            payload["finales"]    = finales
            payload["nivel_max"]  = propuesta.get("nivel_max")
            payload["institucion"] = propuesta.get("institucion")
            form_id = guardar_evaluacion(nombre_completo, sexo, marcas, puntajes, payload)
            if form_id:
                st.caption(f"Evaluación guardada en base de datos (ID: {form_id})")
        except Exception:
            pass

    st.divider()
    retro_col, _, nuevo_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(4)
    with nuevo_col:
        if st.button("Nuevo estudiante", type="primary", use_container_width=True):
            st.session_state.paso = 1
            st.session_state.datos = {}
            st.rerun()


# ─────────────────────────────────────────────────────────────
# ROUTER PRINCIPAL
# ─────────────────────────────────────────────────────────────
PASOS = {1: paso_1, 2: paso_2, 3: paso_3, 4: paso_4, 5: paso_5}
PASOS[st.session_state.paso]()