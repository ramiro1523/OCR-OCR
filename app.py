import streamlit as st
import streamlit.components.v1 as components
import html as _html
import re
import pandas as pd
import difflib
from pathlib import Path

import templates as tpl
import viz

from vocacional.puntajes import calcular_pd
from vocacional.baremos import calcular_baremos, nivel_correspondencia
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
# RECOMENDADOR SEMÁNTICO (opcional: si falla el import, todo
# sigue funcionando con el sistema clásico)
# ─────────────────────────────────────────────────────────────
try:
    from vocacional.recomendador import recomendar_carreras as _recomendar_semantico
    _RECOMENDADOR_DISPONIBLE = True
except Exception as _e_rec:
    _recomendar_semantico = None
    _RECOMENDADOR_DISPONIBLE = False
    print(f"[AVISO] Recomendador semántico no disponible: {_e_rec}")


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
# HELPER: RENDER HTML SIN MARKDOWN
# ─────────────────────────────────────────────────────────────
def render_html(html: str):
    """Renderiza HTML sin pasar por el parser de markdown de Streamlit."""
    if not html:
        return
    minificado = re.sub(r">\s+<", "><", html.strip())
    if hasattr(st, "html"):
        st.html(minificado)
    else:
        st.markdown(minificado, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# ATAJO: ENTER PARA CONTINUAR
# ─────────────────────────────────────────────────────────────
def activar_enter():
    components.html("""
    <script>
    (function() {
        const doc = window.parent.document;
        const handler = function(e) {
            if (e.key !== 'Enter' || e.shiftKey) return;
            const t = e.target;
            if (t && t.tagName === 'TEXTAREA') return;
            const btn = doc.querySelector('button[kind="primary"]');
            if (btn) { e.preventDefault(); btn.click(); }
        };
        if (window._enterHandler) doc.removeEventListener('keydown', window._enterHandler);
        window._enterHandler = handler;
        doc.addEventListener('keydown', handler);
    })();
    </script>
    """, height=0)


# ─────────────────────────────────────────────────────────────
# PRESERVAR SCROLL
# ─────────────────────────────────────────────────────────────
def preservar_scroll():
    components.html("""
    <script>
    (function() {
        const win = window.parent;
        const doc = win.document;
        const paso = doc.querySelector('.step.active')?.textContent || 'x';
        const KEY = 'ieppo_scroll_' + paso.replace(/\\s+/g, '_');

        if (!win._scrollListenerAttached) {
            let timer = null;
            win.addEventListener('scroll', function() {
                clearTimeout(timer);
                timer = setTimeout(function() {
                    try {
                        const p = doc.querySelector('.step.active')?.textContent || 'x';
                        const k = 'ieppo_scroll_' + p.replace(/\\s+/g, '_');
                        sessionStorage.setItem(k, String(win.scrollY || 0));
                    } catch(e) {}
                }, 200);
            }, { passive: true });
            win._scrollListenerAttached = true;
        }

        if (!win._visibilityListenerAttached) {
            win.addEventListener('focus', function() {
                setTimeout(function() {
                    try {
                        const y = parseInt(sessionStorage.getItem(KEY) || '0', 10);
                        if (y > 0) win.scrollTo({ top: y, behavior: 'instant' });
                    } catch(e) {}
                }, 50);
            });
            doc.addEventListener('visibilitychange', function() {
                if (!doc.hidden) {
                    setTimeout(function() {
                        try {
                            const p = doc.querySelector('.step.active')?.textContent || 'x';
                            const k = 'ieppo_scroll_' + p.replace(/\\s+/g, '_');
                            const y = parseInt(sessionStorage.getItem(k) || '0', 10);
                            if (y > 0) win.scrollTo({ top: y, behavior: 'instant' });
                        } catch(e) {}
                    }, 50);
                }
            });
            win._visibilityListenerAttached = true;
        }

        setTimeout(function() {
            try {
                const y = parseInt(sessionStorage.getItem(KEY) || '0', 10);
                if (y > 0) win.scrollTo({ top: y, behavior: 'instant' });
            } catch(e) {}
        }, 120);
    })();
    </script>
    """, height=0)


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
# NIVELES EDUCATIVOS E INSTITUCIONES
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
    "publica":     {"label": "Pública",     "chip": "inst-pub"},
    "privada":     {"label": "Privada",     "chip": "inst-priv"},
    "indiferente": {"label": "Indiferente", "chip": ""},
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
# MAPEO DE 7 TIPOS VOCACIONALES → PERFIL RIASEC (para el recomendador)
# ─────────────────────────────────────────────────────────────
_TIPO_A_RIASEC = {
    "SOCIAL":             "S",
    "LIDERAZGO":          "E",
    "ARTÍSTICO":          "A",
    "ORGANIZADO":         "C",
    "EMPRENDEDOR":        "E",
    "INVESTIGATIVO":      "I",
    "TÉCNICO MECÁNICO":   "R",
}


def perfil_test_a_riasec(con_baremos: dict) -> dict:
    """
    Convierte el dict de baremos (7 tipos vocacionales) a un perfil
    RIASEC (6 áreas, valores 0-1) que el recomendador semántico
    puede consumir.

    Mapeo:
        SOCIAL              → S
        LIDERAZGO           → E
        ARTÍSTICO           → A
        ORGANIZADO          → C
        EMPRENDEDOR         → E
        INVESTIGATIVO       → I
        TÉCNICO MECÁNICO    → R

    Si dos tipos mapean a la misma letra RIASEC (LIDERAZGO y
    EMPRENDEDOR → E), se promedian sus baremos.
    """
    acumulado = {"R": 0.0, "I": 0.0, "A": 0.0, "S": 0.0, "E": 0.0, "C": 0.0}
    conteo = {"R": 0, "I": 0, "A": 0, "S": 0, "E": 0, "C": 0}

    for tipo, d in con_baremos.items():
        baremo = d.get("Baremo")
        if baremo is None:
            continue
        letra = _TIPO_A_RIASEC.get(tipo.upper())
        if not letra:
            continue
        acumulado[letra] += float(baremo)
        conteo[letra] += 1

    perfil = {}
    for letra in ("R", "I", "A", "S", "E", "C"):
        if conteo[letra] > 0:
            promedio = acumulado[letra] / conteo[letra]
            # Los baremos van típicamente 0-99 → normalizo a 0-1
            perfil[letra] = min(1.0, promedio / 99.0)
        else:
            perfil[letra] = 0.0
    return perfil


# ─────────────────────────────────────────────────────────────
# CATÁLOGO Y FUZZY MATCH
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
# INTERPRETACIÓN SEMÁNTICA DE CARRERAS LIBRES
# ─────────────────────────────────────────────────────────────
def interpretar_carrera_libre(texto: str, perfil_riasec: dict) -> dict | None:
    """
    Usa el recomendador semántico para traducir un texto libre
    ("corredor de motos") a una carrera del catálogo oficial
    ("Mecánica Automotriz").

    Devuelve None si:
      - El recomendador no está disponible.
      - No hubo matches razonables.
      - La carrera interpretada no existe en el catálogo oficial
        del test (porque el recomendador tiene su propio catálogo).
      - El match es demasiado débil (< 0.30).

    Devuelve un dict con:
      - "carrera": nombre exacto en el catálogo oficial
      - "match_usuario": similitud con el texto del alumno (0-1)
      - "afinidad_test": afinidad con el perfil del test (0-1)
      - "score_final": score combinado
      - "alternativas": otras carreras sugeridas con score
      - "texto_original": texto tal cual lo escribió el alumno
    """
    if not _RECOMENDADOR_DISPONIBLE or not texto or not texto.strip():
        return None

    try:
        resultado = _recomendar_semantico(
            perfil_test=perfil_riasec,
            carreras_usuario=[texto],
            top_k=5,
        )
    except Exception as e:
        print(f"[recomendador] error: {e}")
        return None

    recomendaciones = resultado.get("recomendaciones", [])
    if not recomendaciones:
        return None

    # Filtro los que matchean con el catálogo oficial del test
    validos = []
    for rec in recomendaciones:
        nombre_oficial = normalizar_carrera(rec["nombre"])
        if nombre_oficial and rec["match_usuario"] >= 0.30:
            validos.append({
                "carrera": nombre_oficial,
                "match_usuario": rec["match_usuario"],
                "afinidad_test": rec["afinidad_test"],
                "score_final": rec["score_final"],
            })

    if not validos:
        return None

    return {
        "carrera": validos[0]["carrera"],
        "match_usuario": validos[0]["match_usuario"],
        "afinidad_test": validos[0]["afinidad_test"],
        "score_final": validos[0]["score_final"],
        "alternativas": validos[1:],
        "texto_original": texto.strip(),
    }


# ─────────────────────────────────────────────────────────────
# SISTEMA DE RECOMENDACIÓN (clásico)
# ─────────────────────────────────────────────────────────────
W_VOC        = 1.0
W_PROP       = 2.5
W_TEST       = 0.8
BONUS_ALUMNO = 20
BONUS_TEST   = 5


def _tipos(c): return set(INDICE_TIPOS.get(c, []))
def _grupos(c): return {g["id"] for g in INDICE_GRUPOS.get(c, [])}
def _keywords(c): return set(PALABRAS.get(c, []))


def _score_vocacional(carrera, tipo1, tipo2):
    tipos = _tipos(carrera)
    s = 0
    if tipo1 in tipos: s += 8
    if tipo2 in tipos: s += 8
    if tipo1 in tipos and tipo2 in tipos: s += 4
    for rel in TIPOS_REL.get(tipo1, []):
        if rel in tipos: s += 2
    for rel in TIPOS_REL.get(tipo2, []):
        if rel in tipos: s += 2
    return s


def _similitud_con(a, b):
    if a == b: return 0.0
    s = 0
    if _grupos(a) & _grupos(b): s += 4
    s += 2 * min(len(_keywords(a) & _keywords(b)), 3)
    s += 3 * len(_tipos(a) & _tipos(b))
    return s


def _score_afinidad_lista(carrera, lista):
    if not lista: return 0.0
    otras = [c for c in lista if c != carrera]
    if not otras: return 0.0
    return sum(_similitud_con(carrera, o) for o in otras) / len(otras)


def _score_carrera(carrera, tipo1, tipo2, test_norm, alumno_norm):
    s_voc  = _score_vocacional(carrera, tipo1, tipo2)
    s_prop = _score_afinidad_lista(carrera, alumno_norm)
    s_test = _score_afinidad_lista(carrera, test_norm)
    b_alumno = BONUS_ALUMNO if carrera in alumno_norm else 0
    b_test   = BONUS_TEST   if carrera in test_norm   else 0
    total = s_voc * W_VOC + s_prop * W_PROP + s_test * W_TEST + b_alumno + b_test
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


def evaluar_propuesta(
    carreras_test,
    carreras_alumno,
    nivel_max,
    institucion,
    tipo1,
    tipo2,
    perfil_riasec=None,
):
    """
    Evalúa la propuesta del estudiante.

    Novedad: cuando una carrera libre no se encuentra por fuzzy
    clásico, se intenta INTERPRETAR con el recomendador semántico
    antes de descartarla. Las interpretaciones quedan registradas
    en el resultado para mostrarlas en el informe.
    """
    alumno_norm, no_encontradas = [], []
    interpretaciones = []      # log de traducciones semánticas

    for c in carreras_alumno:
        if not c or not c.strip():
            continue

        # 1. Intento normal (exacto + fuzzy)
        n = normalizar_carrera(c)
        if n:
            alumno_norm.append(n)
            continue

        # 2. Fallback semántico
        interp = None
        if perfil_riasec is not None:
            interp = interpretar_carrera_libre(c, perfil_riasec)

        if interp:
            alumno_norm.append(interp["carrera"])
            interpretaciones.append(interp)
        else:
            no_encontradas.append(c.strip())

    # Deduplicar preservando orden
    alumno_norm = list(dict.fromkeys(alumno_norm))

    test_norm = [c["carrera"] for c in carreras_test]
    universo, seen = [], set()
    for c in test_norm + alumno_norm:
        if c not in seen:
            seen.add(c)
            universo.append(c)

    scored = [_score_carrera(c, tipo1, tipo2, test_norm, alumno_norm) for c in universo]
    financiables = [s for s in scored if es_financiable(s["nivel"], nivel_max)]
    descartadas  = [s for s in scored if s not in financiables]
    financiables.sort(key=lambda x: x["score"], reverse=True)
    finales = financiables[:2]
    for i, f in enumerate(finales, 1):
        f["rank"] = i

    return {
        "finales": finales,
        "no_encontradas": no_encontradas,
        "interpretaciones": interpretaciones,
        "descartadas_nivel": descartadas,
        "nivel_max": nivel_max,
        "institucion": institucion,
    }


# ─────────────────────────────────────────────────────────────
# ESTADO
# ─────────────────────────────────────────────────────────────
def _init():
    if "paso" not in st.session_state: st.session_state.paso = 1
    if "datos" not in st.session_state: st.session_state.datos = {}


_init()


def ir_a_paso(n):
    st.session_state.paso = n
    st.rerun()


# ─────────────────────────────────────────────────────────────
# COMPONENTE: PANEL DE CRITERIOS (usa templates)
# ─────────────────────────────────────────────────────────────
def panel_criterios(con_baremos: dict):
    if not con_baremos:
        return
    resumen = resumen_criterios(con_baremos)
    pred = criterio_predominante(resumen)

    render_html(tpl.section_title("Criterios vocacionales (P · E · H)"))

    cols = st.columns(3, gap="medium")
    for col, (letra, meta) in zip(cols, CRITERIOS.items()):
        with col:
            render_html(tpl.crit_card(letra, meta, resumen[letra], letra == pred))


# ─────────────────────────────────────────────────────────────
# MAPEO DE MARCA A SÍ/NO
# ─────────────────────────────────────────────────────────────
def normalizar_marca(valor: str) -> str:
    return "si" if valor in ("si", "ambos") else "no"


# ─────────────────────────────────────────────────────────────
# PASO 1 — SUBIR
# ─────────────────────────────────────────────────────────────
def paso_1():
    render_html(tpl.barra_progreso(1))
    st.title("IEPPO — Orientación Vocacional")
    st.caption("Sistema de evaluación vocacional · Paso 1 de 6  ·  Presiona Enter para continuar")
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
    with n1: nombre = st.text_input("Nombre(s)", placeholder="Ej. María Fernanda")
    with n2: apellido_paterno = st.text_input("Apellido paterno", placeholder="Ej. García")
    with n3: apellido_materno = st.text_input("Apellido materno", placeholder="Ej. López")

    nombre_completo = " ".join(
        p for p in [nombre.strip(), apellido_paterno.strip(), apellido_materno.strip()] if p
    )

    st.divider()
    retro_col, _, btn_col = st.columns([1, 3, 1])
    with retro_col:
        st.button("← Retroceder", use_container_width=True, disabled=True)
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

    activar_enter()


# ─────────────────────────────────────────────────────────────
# PASO 2 — VERIFICAR
# ─────────────────────────────────────────────────────────────
def paso_2():
    render_html(tpl.barra_progreso(2))
    st.title("Paso 2: Verificar marcas")
    st.caption("Revisa cada bloque por pestañas. Marca 'Sí' donde el estudiante haya marcado.")

    marcas  = st.session_state.datos["marcas"]
    sexo    = st.session_state.datos["sexo"]
    dudosos = set(st.session_state.datos.get("dudosos", []))

    OPCIONES_TEXTO = ["No", "Sí"]
    OPCIONES_VALOR = ["no", "si"]
    N_COLS = 3

    col_items, col_pts = st.columns([3, 1.4], gap="large")

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

                    actual = normalizar_marca(marcas.get(item, "vacio"))
                    opt_idx = OPCIONES_VALOR.index(actual)
                    es_dudoso = item in dudosos

                    with grid[col_idx]:
                        with st.container(border=True):
                            render_html(tpl.item_title(item, es_dudoso))
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
                "Baremo": baremo if baremo is not None else None,
            })

        df = pd.DataFrame(filas).sort_values("Baremo", ascending=False, na_position="last")
        df["Baremo"] = df["Baremo"].apply(lambda v: v if v is not None else "—")
        st.dataframe(df, hide_index=True, use_container_width=True, height=280)

        n_si = sum(1 for v in nuevas_marcas.values() if v == "si")
        st.caption(f"{n_si} ítem(s) marcados como Sí de {len(nuevas_marcas)}.")

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(1)
    with conf_col:
        if st.button("Confirmar →", type="primary", use_container_width=True): ir_a_paso(3)

    activar_enter()


# ─────────────────────────────────────────────────────────────
# PASO 3 — TOP 2
# ─────────────────────────────────────────────────────────────
def paso_3():
    render_html(tpl.barra_progreso(3))
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

    render_html(tpl.section_title("Top 2 tipos vocacionales"))
    c1, c2 = st.columns(2, gap="large")
    with c1:
        render_html(tpl.voc_card(tipo1, top[0]["Baremo"], top[0]["PD"],
                                 tipo_a_criterio(tipo1), 1))
    with c2:
        render_html(tpl.voc_card(tipo2, top[1]["Baremo"], top[1]["PD"],
                                 tipo_a_criterio(tipo2), 2))

    carreras = seleccionar_4_carreras(tipo1, tipo2)
    st.session_state.datos["carreras"] = carreras
    st.session_state.datos["top"] = top

    render_html(tpl.section_title("Carreras sugeridas por el test"))
    ca_col, re_col = st.columns(2, gap="large")
    with ca_col:
        st.markdown("**Carreras principales**")
        for c in carreras["principales"]:
            render_html(tpl.career_card(c["carrera"], c["tipo"],
                                        c.get("relacion", ""),
                                        tipo_a_criterio(c["tipo"]), "principal"))
    with re_col:
        st.markdown("**Carreras de respaldo**")
        for c in carreras["respaldo"]:
            render_html(tpl.career_card(c["carrera"], c["tipo"],
                                        c.get("relacion", ""),
                                        tipo_a_criterio(c["tipo"]), "respaldo"))

    with st.expander("Ver ranking completo de los 7 tipos"):
        ranking = ranking_tipos(con_baremos)
        df_ranking = pd.DataFrame([
            {"#": r["posicion"],
             "Criterio": tipo_a_criterio(r["tipo"]),
             "Tipo Vocacional": r["tipo"],
             "PD": r["PD"],
             "Baremo": r["Baremo"] if r["Baremo"] is not None else "—",
             "Nivel": tpl.NIVEL_LABEL[nivel_correspondencia(r["Baremo"])]}
            for r in ranking
        ])
        st.dataframe(df_ranking, hide_index=True, use_container_width=True)

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(2)
    with conf_col:
        if st.button("Continuar →", type="primary", use_container_width=True): ir_a_paso(4)

    activar_enter()


# ─────────────────────────────────────────────────────────────
# PASO 4 — PROPUESTA (con interpretación semántica en vivo)
# ─────────────────────────────────────────────────────────────
def paso_4():
    render_html(tpl.barra_progreso(4))
    st.title("Paso 4: Propuesta del estudiante")
    st.caption("El estudiante propone 3 carreras. Presiona Enter para evaluar.")

    datos = st.session_state.datos
    top = datos.get("top", [])
    carreras_test = datos.get("carreras", {"principales": [], "respaldo": []})
    con_baremos = datos.get("puntajes", {})
    tipo1 = top[0]["tipo"] if len(top) > 0 else ""
    tipo2 = top[1]["tipo"] if len(top) > 1 else ""

    if not tipo1 or not tipo2:
        st.error("Falta el Top 2. Regresa al paso 3.")
        if st.button("← Retroceder"): ir_a_paso(3)
        return

    # Perfil RIASEC cacheado en session_state (evita recalcular en cada rerun)
    if "_perfil_riasec" not in st.session_state.datos:
        st.session_state.datos["_perfil_riasec"] = perfil_test_a_riasec(con_baremos)
    perfil_riasec = st.session_state.datos["_perfil_riasec"]

    render_html(tpl.section_title("Carreras sugeridas por el test"))
    principales = carreras_test.get("principales", [])
    for i, c in enumerate(principales, 1):
        render_html(tpl.proposal_row(i, c["carrera"], "test"))

    render_html(tpl.section_title("Carreras propuestas por el estudiante"))
    render_html(tpl.proposal_box())

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1: prop1 = st.text_input("Carrera 1", placeholder="Ej. Agronomía", key="prop1")
    with c2: prop2 = st.text_input("Carrera 2", placeholder="Ej. Ing de Sistemas", key="prop2")
    with c3: prop3 = st.text_input("Carrera 3", placeholder="Ej. Biología", key="prop3")

    render_html(tpl.section_title("Nivel educativo que puede financiar"))
    nivel_max = st.radio(
        "Nivel máximo",
        options=list(NIVELES.keys()),
        format_func=lambda k: f"{NIVELES[k]['label']} — {NIVELES[k]['desc']}",
        horizontal=False, key="nivel_max", label_visibility="collapsed"
    )

    render_html(tpl.section_title("Tipo de institución preferida"))
    institucion = st.radio(
        "Institución",
        options=list(INSTITUCIONES.keys()),
        format_func=lambda k: INSTITUCIONES[k]["label"],
        horizontal=True, key="institucion", label_visibility="collapsed"
    )

    # ── INTERPRETACIÓN SEMÁNTICA EN VIVO ─────────────────────
    carreras_alumno = [prop1, prop2, prop3]
    validas = [c for c in carreras_alumno if c and c.strip()]

    if validas:
        render_html(tpl.section_title("Candidatas a evaluar"))
        for c in principales:
            render_html(tpl.proposal_row("•", c["carrera"], "test"))

        # Acumulo interpretaciones para mostrarlas
        interpretaciones_vivo = []

        for c in validas:
            norm = normalizar_carrera(c)
            if norm:
                render_html(tpl.proposal_row("•", norm, "alumno"))
            else:
                # Intento semántico
                if _RECOMENDADOR_DISPONIBLE:
                    interp = interpretar_carrera_libre(c, perfil_riasec)
                    if interp:
                        interpretaciones_vivo.append(interp)
                        texto = (
                            f"{c} → interpretada como "
                            f"<b>{interp['carrera']}</b> "
                            f"(match {int(interp['match_usuario']*100)}%)"
                        )
                        render_html(tpl.proposal_row("•", texto, "alumno",es_html=True))
                    else:
                        render_html(tpl.proposal_row(
                            "•", f"{c} (no encontrada en catálogo)", "alumno"
                        ))
                else:
                    render_html(tpl.proposal_row(
                        "•", f"{c} (no encontrada en catálogo)", "alumno"
                    ))

        if interpretaciones_vivo:
            st.info(
                f"🧠 El sistema interpretó {len(interpretaciones_vivo)} "
                f"carrera(s) que no estaban en el catálogo. "
                f"Verás el detalle en el informe final."
            )

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
                perfil_riasec=perfil_riasec,   # ← nuevo
            )
            st.session_state.datos["propuesta"] = {
                "carreras_alumno": carreras_alumno,
                "nivel_max": nivel_max,
                "institucion": institucion,
                "resultado": resultado,
            }
            ir_a_paso(5)

    activar_enter()


# ─────────────────────────────────────────────────────────────
# PASO 5 — CARRERAS FINALES
# ─────────────────────────────────────────────────────────────
def paso_5():
    render_html(tpl.barra_progreso(5))
    st.title("Paso 5: Carreras finales recomendadas")
    st.caption("Síntesis del test vocacional y la propuesta del estudiante.")

    datos = st.session_state.datos
    nombre = datos.get("nombre", "")
    ap_pat = datos.get("apellido_paterno", "")
    ap_mat = datos.get("apellido_materno", "")
    nombre_completo = datos.get("nombre_completo") or f"{nombre} {ap_pat} {ap_mat}".strip()
    sexo = datos.get("sexo", "—")
    propuesta = datos.get("propuesta", {})

    sexo_label = "Mujer (F)" if sexo == "F" else "Varón (M)"
    inicial = (nombre.strip()[:1] or "?").upper()

    render_html(tpl.student_header(inicial, nombre_completo, sexo_label))

    resultado = propuesta.get("resultado", {})
    finales   = resultado.get("finales", [])
    inst_key  = propuesta.get("institucion", "indiferente")
    inst_meta = INSTITUCIONES.get(inst_key, INSTITUCIONES["indiferente"])

    if finales:
        render_html(tpl.section_title("Carreras finales recomendadas"))
        max_score = max(f["score"] for f in finales) or 1

        for f in finales:
            nivel_meta = NIVELES[f["nivel"]]
            afin_pct = min(int(f["score"] / max_score * 100), 100)

            if f["en_test"] and f["en_alumno"]:   origen_txt = "Síntesis (test + alumno)"
            elif f["en_alumno"]:                  origen_txt = "Propuesta del estudiante"
            elif f["en_test"]:                    origen_txt = "Sugerida por el test"
            else:                                 origen_txt = "Síntesis"

            render_html(tpl.final_card(
                carrera=f["carrera"], rank=f["rank"],
                nivel_meta=nivel_meta, inst_meta=inst_meta,
                score=f["score"], origen_txt=origen_txt, afin_pct=afin_pct,
                s_voc=f["s_voc"], s_prop=f["s_prop"], s_test=f["s_test"],
            ))

    # ── INTERPRETACIONES SEMÁNTICAS ──────────────────────────
    interps = resultado.get("interpretaciones", [])
    if interps:
        render_html(tpl.section_title("Interpretación de carreras libres"))
        st.caption(
            "Estas carreras no estaban en el catálogo tal como las "
            "escribió el estudiante. El sistema las tradujo usando "
            "el análisis semántico + el perfil del test."
        )
        for it in interps:
            with st.container(border=True):
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    st.markdown(f"**Texto original:** `{it['texto_original']}`")
                    st.markdown(f"**Interpretada como:** {it['carrera']}")
                with col_b:
                    st.metric("Similitud con el texto",
                              f"{int(it['match_usuario']*100)}%")
                    st.metric("Afinidad con el test",
                              f"{int(it['afinidad_test']*100)}%")
                if it.get("alternativas"):
                    with st.expander("Otras interpretaciones posibles"):
                        for alt in it["alternativas"]:
                            st.caption(
                                f"· {alt['carrera']} "
                                f"(match {int(alt['match_usuario']*100)}%, "
                                f"afinidad {int(alt['afinidad_test']*100)}%)"
                            )

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

    st.divider()
    retro_col, _, conf_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(4)
    with conf_col:
        if st.button("Ver informe final →", type="primary", use_container_width=True):
            ir_a_paso(6)

    activar_enter()


# ─────────────────────────────────────────────────────────────
# PASO 6 — INFORME FINAL
# ─────────────────────────────────────────────────────────────
def paso_6():
    render_html(tpl.barra_progreso(6))
    st.title("Paso 6: Informe final")
    st.caption("Tipos vocacionales, carreras del test y carreras finales, todo con su nivel.")

    datos = st.session_state.datos
    nombre = datos.get("nombre", "")
    ap_pat = datos.get("apellido_paterno", "")
    ap_mat = datos.get("apellido_materno", "")
    nombre_completo = datos.get("nombre_completo") or f"{nombre} {ap_pat} {ap_mat}".strip()
    sexo = datos.get("sexo", "—")
    con_baremos = datos.get("puntajes", {})
    carreras_test = datos.get("carreras", {"principales": [], "respaldo": []})
    propuesta = datos.get("propuesta", {})
    resultado = propuesta.get("resultado", {})
    finales = resultado.get("finales", [])

    sexo_label = "Mujer (F)" if sexo == "F" else "Varón (M)"

    if not con_baremos:
        st.error("No hay puntajes calculados. Regresa al Paso 2.")
        if st.button("← Retroceder"): ir_a_paso(5)
        return

    render_html(tpl.hero_informe(nombre_completo, sexo_label))
    render_html(tpl.leyenda_informe())

    # ─────────────────────────────────────────────────────────
    # SECCIÓN 0 — ANÁLISIS VISUAL
    # ─────────────────────────────────────────────────────────
    render_html(tpl.info_block(0, "Análisis visual",
                               "Radar de tipos, distribución de baremos, gauge y comparación."))

    col_r, col_b = st.columns(2, gap="medium")
    with col_r:
        render_html(tpl.viz_card("Perfil vocacional",
                                 "Vista radial de los 7 tipos según su baremo."))
        st.plotly_chart(viz.radar(con_baremos),
                        use_container_width=True,
                        config={"displayModeBar": False})
    with col_b:
        render_html(tpl.viz_card("Distribución de baremos",
                                 "Ordenados por baremo. Líneas roja/verde = umbrales bajo/alto."))
        st.plotly_chart(viz.barras_horizontales(con_baremos),
                        use_container_width=True,
                        config={"displayModeBar": False})

    # Ordenar tipos por baremo descendente
    items_tipos = []
    for tipo, d in con_baremos.items():
        baremo = d.get("Baremo")
        items_tipos.append({
            "tipo": tipo,
            "crit": tipo_a_criterio(tipo),
            "pd": d.get("PD", 0),
            "baremo": baremo,
            "nivel": nivel_correspondencia(baremo),
        })
    items_tipos.sort(key=lambda x: (x["baremo"] is None, -(x["baremo"] or 0)))

    col_g, col_c = st.columns(2, gap="medium")
    with col_g:
        if items_tipos and items_tipos[0]["baremo"] is not None:
            top1 = items_tipos[0]
            render_html(tpl.viz_card("Tipo predominante",
                                     "Baremo del tipo con mayor puntuación."))
            st.plotly_chart(viz.gauge(top1["baremo"], top1["tipo"]),
                            use_container_width=True,
                            config={"displayModeBar": False})
    with col_c:
        render_html(tpl.comp_top2(items_tipos))

    # ─────────────────────────────────────────────────────────
    # SECCIÓN 1 — TIPOS
    # ─────────────────────────────────────────────────────────
    render_html(tpl.info_block(
        1, "Tipos vocacionales",
        "Los 7 tipos evaluados, ordenados por baremo descendente.",
        tpl.tabla_tipos(items_tipos),
    ))

    # ─────────────────────────────────────────────────────────
    # SECCIÓN 2 — CARRERAS DEL TEST
    # ─────────────────────────────────────────────────────────
    carreras_test_list = (
        carreras_test.get("principales", []) + carreras_test.get("respaldo", [])
    )
    items_test = []
    max_test = 1
    if carreras_test_list:
        scores_test = [c.get("puntaje", 10) for c in carreras_test_list]
        max_test = max(scores_test) if scores_test else 1
        for c in carreras_test_list:
            items_test.append({
                "carrera": c["carrera"],
                "score": c.get("puntaje", 10),
                "origen": "test",
            })
        render_html(tpl.info_block(
            2, "Carreras sugeridas por el test",
            "Las 2 principales y 2 de respaldo que surgieron del Top 2 vocacional.",
            tpl.tabla_carreras(items_test, max_test),
        ))
    else:
        render_html(tpl.empty_note("Sin carreras del test registradas."))

    # ─────────────────────────────────────────────────────────
    # SECCIÓN 3 — CARRERAS FINALES
    # ─────────────────────────────────────────────────────────
    items_finales = []
    max_final = 1
    if finales:
        max_final = max(f["score"] for f in finales) or 1
        for f in finales:
            if f["en_test"] and f["en_alumno"]:   origen = "sintesis"
            elif f["en_alumno"]:                  origen = "alumno"
            elif f["en_test"]:                    origen = "test"
            else:                                 origen = "sintesis"
            items_finales.append({
                "carrera": f["carrera"],
                "score":   f["score"],
                "origen":  origen,
            })
        render_html(tpl.info_block(
            3, "Carreras finales recomendadas",
            "Síntesis del test + las 3 carreras que propuso el estudiante.",
            tpl.tabla_carreras(items_finales, max_final),
        ))
    else:
        render_html(tpl.empty_note("Aún no se evaluaron las carreras finales. Vuelve al Paso 4."))

    # ─────────────────────────────────────────────────────────
    # SECCIÓN 4 — INTERPRETACIÓN SEMÁNTICA (nueva)
    # ─────────────────────────────────────────────────────────
    interps = resultado.get("interpretaciones", [])
    if interps:
        lineas_interp = []
        for it in interps:
            lineas_interp.append(
                f"  · '{it['texto_original']}' → {it['carrera']} "
                f"(match {int(it['match_usuario']*100)}%, "
                f"afinidad test {int(it['afinidad_test']*100)}%)"
            )
        render_html(tpl.info_block(
            4, "Interpretación de carreras libres",
            "Carreras que el estudiante escribió coloquialmente y el "
            "sistema tradujo al catálogo.",
            "<pre>" + "\n".join(lineas_interp) + "</pre>",
        ))

    # ─────────────────────────────────────────────────────────
    # RESUMEN GLOBAL
    # ─────────────────────────────────────────────────────────
    n_bajo  = sum(1 for i in items_tipos if i["nivel"] == "bajo")
    n_medio = sum(1 for i in items_tipos if i["nivel"] == "medio")
    n_alto  = sum(1 for i in items_tipos if i["nivel"] == "alto")
    render_html(tpl.resumen_niveles(n_bajo, n_medio, n_alto))

    if items_tipos and items_tipos[0]["nivel"] != "sin_dato":
        top1 = items_tipos[0]
        render_html(tpl.predominante_banner(
            top1["tipo"], top1["crit"], top1["baremo"], top1["nivel"]
        ))

    # ─────────────────────────────────────────────────────────
    # TEXTO COPIABLE
    # ─────────────────────────────────────────────────────────
    lineas_tipos = []
    for i, it in enumerate(items_tipos, 1):
        b = it["baremo"] if it["baremo"] is not None else "—"
        lineas_tipos.append(
            f"  {i}. {it['tipo']:20} Baremo {b:>4} · {tpl.NIVEL_LABEL[it['nivel']]}"
        )
    tipos_txt = "\n".join(lineas_tipos)

    lineas_test = []
    if items_test:
        for i, it in enumerate(items_test, 1):
            lvl = tpl.nivel_de_score(it["score"], max_test)
            lineas_test.append(f"  {i}. {it['carrera']:30} Score {it['score']:>5} · {tpl.NIVEL_LABEL[lvl]}")
    test_txt = "\n".join(lineas_test) if lineas_test else "  —"

    lineas_final = []
    if items_finales:
        for i, it in enumerate(items_finales, 1):
            lvl = tpl.nivel_de_score(it["score"], max_final)
            lineas_final.append(f"  {i}. {it['carrera']:30} Score {it['score']:>5} · {tpl.NIVEL_LABEL[lvl]}")
    final_txt = "\n".join(lineas_final) if lineas_final else "  —"

    # Bloque de interpretaciones para copiar
    interp_txt = ""
    if interps:
        lineas_interp_txt = []
        for it in interps:
            lineas_interp_txt.append(
                f"  · '{it['texto_original']}' → {it['carrera']} "
                f"(match {int(it['match_usuario']*100)}%)"
            )
        interp_txt = "\n\n4. INTERPRETACIÓN DE CARRERAS LIBRES:\n" + "\n".join(lineas_interp_txt)

    texto_copia = f"""INFORME VOCACIONAL IEPPO
{'='*50}
Estudiante : {nombre_completo}
Sexo       : {sexo_label}

1. TIPOS VOCACIONALES (por baremo):
{tipos_txt}

2. CARRERAS SUGERIDAS POR EL TEST:
{test_txt}

3. CARRERAS FINALES RECOMENDADAS:
{final_txt}{interp_txt}

Regla de niveles:
  Tipos      → ≤40 Bajo · 41-59 Medio · ≥60 Alto
  Carreras   → ≤40% Bajo · 50-79% Medio · ≥80% Alto (del máximo)
"""

    render_html(tpl.section_title("Copiar informe"))
    st.code(texto_copia, language=None)

    st.divider()
    retro_col, _, nuevo_col = st.columns([1, 4, 1])
    with retro_col:
        if st.button("← Retroceder", use_container_width=True): ir_a_paso(5)
    with nuevo_col:
        if st.button("Nuevo estudiante", type="primary", use_container_width=True):
            st.session_state.paso = 1
            st.session_state.datos = {}
            st.rerun()


# ─────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────
PASOS = {1: paso_1, 2: paso_2, 3: paso_3, 4: paso_4, 5: paso_5, 6: paso_6}
PASOS[st.session_state.paso]()

preservar_scroll()