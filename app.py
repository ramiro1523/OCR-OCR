import streamlit as st
from pathlib import Path
import json

from vocacional.puntajes import calcular_pd
from vocacional.baremos import calcular_baremos
from vocacional.areas import top_2, ranking_tipos
from vocacional.carreras import seleccionar_4_carreras

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="IEPPO - Análisis Vocacional",
    page_icon="📋",
    layout="wide"
)

# Estado de la sesión
if "paso" not in st.session_state:
    st.session_state.paso = 1
if "datos" not in st.session_state:
    st.session_state.datos = {}


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────
def ir_a_paso(n):
    st.session_state.paso = n
    st.rerun()


# ─────────────────────────────────────────────
# PASO 1 — SUBIR FORMULARIO
# ─────────────────────────────────────────────
def paso_1():
    st.title("📋 IEPPO — Análisis Vocacional")
    st.subheader("Paso 1 de 4: Subir formulario")
    
    pdf = st.file_uploader("Sube el PDF del formulario escaneado", type=["pdf"])
    sexo = st.radio("Sexo del estudiante", options=["M", "F"], horizontal=True)
    nombre = st.text_input("Nombre del estudiante")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("Siguiente →", type="primary"):
            if not pdf:
                st.error("Sube un PDF")
                return
            if not nombre.strip():
                st.error("Ingresa el nombre")
                return
            
            st.session_state.datos["pdf"] = pdf
            st.session_state.datos["sexo"] = sexo
            st.session_state.datos["nombre"] = nombre.strip()
            st.session_state.datos["marcas"] = {}  # aquí irá el resultado del OCR
            ir_a_paso(2)


# ─────────────────────────────────────────────
# PASO 2 — VERIFICACIÓN + PUNTAJES
# ─────────────────────────────────────────────
def paso_2():
    st.title("Paso 2 de 4: Verificar marcas")
    
    # Aquí llamarías al OCR para obtener las marcas del PDF
    # marcas = procesar_pdf(st.session_state.datos["pdf"])
    # Por ahora, diccionario vacío para pruebas
    
    if "marcas" not in st.session_state.datos or not st.session_state.datos["marcas"]:
        from data_loader import generar_items_vacios
        st.session_state.datos["marcas"] = generar_items_vacios()
    
    marcas = st.session_state.datos["marcas"]
    
    col_izq, col_der = st.columns([2, 1])
    
    # ─── Columna izquierda: lista de ítems ───
    with col_izq:
        st.markdown("### Lista de ítems (editable)")
        
        for bloque, items in [
            ("ESTILOS PERSONALES", [f"E{i}" for i in range(1, 34)]),
            ("ACTIVIDADES DE PREFERENCIA", [f"P{i}" for i in range(1, 48)]),
            ("PERCEPCIÓN DE HABILIDAD", [f"H{i}" for i in range(1, 39)]),
        ]:
            st.markdown(f"**{bloque}**")
            for item in items:
                actual = marcas.get(item, "vacio")
                opciones = ["no", "si", "ambos", "vacio"]
                idx = opciones.index(actual) if actual in opciones else 3
                
                nuevo = st.radio(
                    item,
                    options=["No", "Sí", "Ambos (X X)", "Vacío"],
                    index=idx,
                    horizontal=True,
                    key=f"radio_{item}",
                    label_visibility="visible"
                )
                
                mapa = {"No": "no", "Sí": "si", "Ambos (X X)": "ambos", "Vacío": "vacio"}
                marcas[item] = mapa[nuevo]
    
    # ─── Columna derecha: puntajes ───
    with col_der:
        st.markdown("### Tabla de puntajes (auto)")
        
        puntajes = calcular_pd(marcas)
        sexo = st.session_state.datos["sexo"]
        con_baremos = calcular_baremos(puntajes, sexo)
        
        # Guardar para el siguiente paso
        st.session_state.datos["puntajes"] = con_baremos
        
        for tipo, datos in con_baremos.items():
            st.metric(
                label=tipo,
                value=f"PD {datos['PD']}",
                delta=f"Baremo {datos['Baremo'] if datos['Baremo'] else '—'}"
            )
    
    st.divider()
    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("← Retroceder"):
            ir_a_paso(1)
    with col2:
        if st.button("Confirmar →", type="primary"):
            ir_a_paso(3)


# ─────────────────────────────────────────────
# PASO 3 — TOP 2 + CARRERAS AFINES
# ─────────────────────────────────────────────
def paso_3():
    st.title("Paso 3 de 4: Top 2 y carreras afines")
    
    con_baremos = st.session_state.datos["puntajes"]
    top = top_2(con_baremos)
    
    if len(top) < 2:
        st.error("No se pudieron determinar 2 tipos vocacionales.")
        return
    
    tipo1 = top[0]["tipo"]
    tipo2 = top[1]["tipo"]
    
    st.markdown("### Top 2 tipos vocacionales")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(tipo1, f"Baremo {top[0]['Baremo']}", f"PD {top[0]['PD']}")
    with col2:
        st.metric(tipo2, f"Baremo {top[1]['Baremo']}", f"PD {top[1]['PD']}")
    
    # Calcular carreras afines
    carreras = seleccionar_4_carreras(tipo1, tipo2)
    st.session_state.datos["carreras"] = carreras
    st.session_state.datos["top"] = top
    
    st.markdown("### Carreras afines recomendadas")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**PRINCIPALES**")
        for c in carreras["principales"]:
            st.success(f"• {c['carrera']} ({c['tipo']})")
    with col_b:
        st.markdown("**RESPALDO**")
        for c in carreras["respaldo"]:
            st.info(f"• {c['carrera']} ({c['tipo']})")
    
    st.divider()
    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("← Retroceder"):
            ir_a_paso(2)
    with col2:
        if st.button("Confirmar →", type="primary"):
            ir_a_paso(4)


# ─────────────────────────────────────────────
# PASO 4 — RESULTADO FINAL
# ─────────────────────────────────────────────
def paso_4():
    st.title("Paso 4 de 4: Resultado final")
    
    nombre = st.session_state.datos["nombre"]
    sexo = st.session_state.datos["sexo"]
    top = st.session_state.datos["top"]
    carreras = st.session_state.datos["carreras"]
    
    st.markdown(f"### Estudiante: **{nombre}** — Sexo: **{sexo}**")
    
    st.markdown("### Top 2 tipos vocacionales")
    for t in top:
        st.markdown(f"- **{t['tipo']}** — PD: {t['PD']} · Baremo: {t['Baremo']}")
    
    st.markdown("### Carreras principales")
    for c in carreras["principales"]:
        st.success(f"• {c['carrera']} ({c['tipo']})")
    
    st.markdown("### Carreras de respaldo")
    for c in carreras["respaldo"]:
        st.info(f"• {c['carrera']} ({c['tipo']})")
    
    # Texto para copiar
    texto = f"""RESULTADO IEPPO

Estudiante: {nombre}
Sexo: {sexo}

Top 2 tipos vocacionales:
1. {top[0]['tipo']} (Baremo {top[0]['Baremo']})
2. {top[1]['tipo']} (Baremo {top[1]['Baremo']})

Carreras principales:
- {carreras['principales'][0]['carrera'] if len(carreras['principales']) > 0 else '—'}
- {carreras['principales'][1]['carrera'] if len(carreras['principales']) > 1 else '—'}

Carreras de respaldo:
- {carreras['respaldo'][0]['carrera'] if len(carreras['respaldo']) > 0 else '—'}
- {carreras['respaldo'][1]['carrera'] if len(carreras['respaldo']) > 1 else '—'}
"""
    
    st.divider()
    st.markdown("### Copiar resultado")
    st.code(texto, language=None)
    
    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("← Retroceder"):
            ir_a_paso(3)
    with col2:
        if st.button("Nuevo estudiante", type="primary"):
            st.session_state.paso = 1
            st.session_state.datos = {}
            st.rerun()


# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────
PASOS = {1: paso_1, 2: paso_2, 3: paso_3, 4: paso_4}
PASOS[st.session_state.paso]()