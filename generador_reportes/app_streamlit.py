# app_streamlit.py
"""
Generador de Informes Vocacionales SOVIO
Interfaz Streamlit — 4 fases, diseño horizontal compacto.
Sin emojis. El CSS se carga desde estilos.css
Procesamiento paralelo con procesador.procesar_lote_paralelo.
Análisis de afinidad de carreras escritas con analizador_carreras.
"""
import io
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from parser_filename import parsear_filename
from motor_pdf import generar_pdf
from pipeline_vocacional import procesar_alumno
from procesador import procesar_lote_paralelo
from analizador_carreras import analizar_carreras_escritas


# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════
MAX_WORKERS = 4   # cuántos PDFs procesar en paralelo (3-4 recomendado)

# Mapeo del potencial para el PDF final
POTENCIAL_TEXTO = {
    "ALTO": "ALTO",
    "MEDIO": "EN DESARROLLO",
    "BAJO": "BAJO",
}


# ═══════════════════════════════════════════════════════════════
# CSS EXTERNO
# ═══════════════════════════════════════════════════════════════
def cargar_css():
    ruta_css = Path(__file__).parent / "estilos.css"
    if ruta_css.exists():
        with open(ruta_css, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# ESTADO
# ═══════════════════════════════════════════════════════════════
def inicializar_estado():
    if "alumnos" not in st.session_state:
        st.session_state.alumnos = []
    if "fase" not in st.session_state:
        st.session_state.fase = 1
    if "zip_data" not in st.session_state:
        st.session_state.zip_data = None


# ═══════════════════════════════════════════════════════════════
# FASE 1: ENTRADA
# ═══════════════════════════════════════════════════════════════
def fase_1_entrada():
    st.markdown("""
    <div class="page-header">
        <h2>Generador de Informes Vocacionales SOVIO</h2>
        <p>Completa los datos generales y sube los PDFs escaneados.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("form_datos_globales"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            ie = st.text_input("Institución Educativa",
                               value="SANTO DOMINGO DE PANGOA")
        with col2:
            fecha = st.date_input("Fecha de evaluación")
        with col3:
            grado = st.selectbox("Grado", ["3", "4", "5"], index=2)
        with col4:
            nivel = st.selectbox("Nivel", ["COMPLETA", "INCOMPLETA"], index=0)

        st.markdown("---")

        archivos = st.file_uploader(
            "Sube los PDFs escaneados (uno por alumno)",
            type=["pdf"],
            accept_multiple_files=True,
            help="Formato: nombre-apellido_edad_sexo.pdf  →  Ej: ana-rozas-hucho_16_F.pdf",
        )

        iniciar = st.form_submit_button(
            "Procesar archivos", type="primary", use_container_width=True
        )

    if iniciar:
        if not archivos:
            st.error("Sube al menos un PDF.")
            return

        # ─── 1. Validar nombres ───
        errores_formato = []
        archivos_validos = []
        for a in archivos:
            try:
                parsear_filename(a.name)
                archivos_validos.append((a.name, a.getbuffer().tobytes()))
            except ValueError as e:
                errores_formato.append(str(e))

        if errores_formato:
            st.error("Algunos archivos tienen formato incorrecto:")
            for e in errores_formato:
                st.code(e)
            return

        # ─── 2. Procesar en paralelo ───
        progreso = st.progress(0, text="Iniciando procesamiento paralelo...")

        def actualizar(completados, total):
            progreso.progress(
                completados / total,
                text=f"Procesando {completados}/{total} PDFs en paralelo...",
            )

        alumnos_nuevos, errores_proceso = procesar_lote_paralelo(
            archivos=archivos_validos,
            pipeline_fn=procesar_alumno,
            max_workers=MAX_WORKERS,
            on_progress=actualizar,
        )

        progreso.empty()

        if errores_proceso:
            st.warning(f"{len(errores_proceso)} archivo(s) fallaron:")
            for nombre, error in errores_proceso:
                st.code(f"{nombre}: {error}")

        if not alumnos_nuevos:
            st.error("No se pudo procesar ningún archivo.")
            return

        # ─── 3. Completar con datos globales ───
        for alumno in alumnos_nuevos:
            alumno["_ie"] = ie
            alumno["_fecha"] = fecha.strftime("%d/%m/%Y")
            alumno["_grado"] = grado
            alumno["_nivel"] = nivel
            alumno["_analisis_escritas"] = []

        st.session_state.alumnos = alumnos_nuevos
        st.session_state.fase = 3
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# FASE 3: REVISIÓN — UNA FILA POR ALUMNO
# ═══════════════════════════════════════════════════════════════
def _render_veredicto(item: dict):
    """Muestra el veredicto de afinidad de una carrera escrita."""
    estado = item.get("estado")

    if estado == "vacio":
        return

    if estado == "no_reconocida":
        st.markdown(
            '<div style="font-size:9px; color:#991b1b; padding:2px 0; '
            'line-height:1.2;">No reconocida</div>',
            unsafe_allow_html=True,
        )
        return

    if estado == "sin_match":
        st.markdown(
            '<div style="font-size:9px; color:#92400e; padding:2px 0; '
            'line-height:1.2;">Sin relación con el test</div>',
            unsafe_allow_html=True,
        )
        return

    if estado == "analizada":
        veredicto = item["veredicto"]
        colores = {
            "alta":  ("#065f46", "#d1fae5", "#86efac"),
            "media": ("#92400e", "#fef3c7", "#fcd34d"),
            "baja":  ("#991b1b", "#fee2e2", "#fca5a5"),
        }
        fg, bg, border = colores.get(veredicto, ("#374151", "#e5e7eb", "#d1d5db"))

        st.markdown(
            f'<div style="font-size:9px; color:{fg}; background:{bg}; '
            f'border:1px solid {border}; padding:3px 6px; '
            f'border-radius:4px; line-height:1.3; margin-top:2px;">'
            f'<strong>{item["carrera_canonica"]}</strong> · '
            f'{item["afinidad"]} pts · {veredicto.upper()}'
            f'<br><span style="opacity:0.75;">'
            f'↔ {item["carrera_test_relacionada"]}'
            f'</span></div>',
            unsafe_allow_html=True,
        )


def fase_3_revision():
    n = len(st.session_state.alumnos)
    st.markdown(f"""
    <div class="page-header">
        <h2>Revisión y edición</h2>
        <p>Verifica y ajusta los resultados antes de generar los PDFs finales.</p>
    </div>
    <div class="counter">{n} alumno{'s' if n != 1 else ''} procesado{'s' if n != 1 else ''}</div>
    """, unsafe_allow_html=True)

    if not st.session_state.alumnos:
        st.warning("No hay alumnos procesados.")
        if st.button("Volver al inicio"):
            st.session_state.fase = 1
            st.rerun()
        return

    # ─── Cabecera de columnas ───
    st.markdown("""
    <div class="col-header">
        <div>Alumno</div>
        <div>Área 1</div>
        <div>Área 2</div>
        <div>Carrera 1</div>
        <div>Carrera 2</div>
        <div class="manuscrita">Escrita 1</div>
        <div class="manuscrita">Escrita 2</div>
        <div class="manuscrita">Escrita 3</div>
    </div>
    """, unsafe_allow_html=True)

    # ─── Fila por alumno ───
    for i, alumno in enumerate(st.session_state.alumnos):
        cols = st.columns([1.8, 1, 1, 1.2, 1.2, 1, 1, 1], gap="small")

        with cols[0]:
            st.markdown(
                f'<div style="padding:8px 4px; font-size:13px; font-weight:700; '
                f'color:#1e3a8a; white-space:nowrap; overflow:hidden; '
                f'text-overflow:ellipsis;">{alumno["nombre"]}</div>',
                unsafe_allow_html=True,
            )

        with cols[1]:
            a1 = st.text_input("a1", value=alumno.get("area_1", ""),
                               key=f"a1_{i}", label_visibility="collapsed")
        with cols[2]:
            a2 = st.text_input("a2", value=alumno.get("area_2", ""),
                               key=f"a2_{i}", label_visibility="collapsed")
        with cols[3]:
            c1 = st.text_input("c1", value=alumno.get("carrera_1", ""),
                               key=f"c1_{i}", label_visibility="collapsed")
        with cols[4]:
            c2 = st.text_input("c2", value=alumno.get("carrera_2", ""),
                               key=f"c2_{i}", label_visibility="collapsed")
        with cols[5]:
            m1 = st.text_input("m1", value=alumno.get("carrera_manual_1", ""),
                               key=f"m1_{i}", label_visibility="collapsed")
        with cols[6]:
            m2 = st.text_input("m2", value=alumno.get("carrera_manual_2", ""),
                               key=f"m2_{i}", label_visibility="collapsed")
        with cols[7]:
            m3 = st.text_input("m3", value=alumno.get("carrera_manual_3", ""),
                               key=f"m3_{i}", label_visibility="collapsed")

        # Guardar cambios en session_state
        st.session_state.alumnos[i]["area_1"] = a1
        st.session_state.alumnos[i]["area_2"] = a2
        st.session_state.alumnos[i]["carrera_1"] = c1
        st.session_state.alumnos[i]["carrera_2"] = c2
        st.session_state.alumnos[i]["carrera_manual_1"] = m1
        st.session_state.alumnos[i]["carrera_manual_2"] = m2
        st.session_state.alumnos[i]["carrera_manual_3"] = m3

        # ─── Análisis de afinidad de carreras escritas ───
        escritas = [m1, m2, m3]
        if any(e and e.strip() for e in escritas):
            try:
                carreras_test = [c1, c2]
                analisis = analizar_carreras_escritas(escritas, carreras_test)
            except Exception as e:
                analisis = []
                st.session_state.alumnos[i]["_analisis_escritas"] = []
                st.warning(f"No se pudo analizar carreras de {alumno['nombre']}: {e}")
            else:
                st.session_state.alumnos[i]["_analisis_escritas"] = analisis

                # Renderizar veredictos debajo de cada caja de escritas
                cols_inf = st.columns([1.8, 1, 1, 1.2, 1.2, 1, 1, 1], gap="small")
                for idx, item in enumerate(analisis):
                    with cols_inf[5 + idx]:
                        _render_veredicto(item)

    # ─── Botones finales ───
    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Volver al inicio", use_container_width=True):
            st.session_state.alumnos = []
            st.session_state.fase = 1
            st.rerun()
    with col2:
        if st.button("Generar reportes finales",
                     type="primary", use_container_width=True):
            st.session_state.fase = 4
            st.rerun()


# ═══════════════════════════════════════════════════════════════
# FASE 4: GENERACIÓN Y DESCARGA
# ═══════════════════════════════════════════════════════════════
def fase_4_descarga():
    alumnos = st.session_state.alumnos
    if not alumnos:
        st.warning("No hay alumnos.")
        return

    st.markdown("""
    <div class="page-header">
        <h2>Descarga de reportes</h2>
        <p>Generando PDFs individuales y Excel consolidado.</p>
    </div>
    """, unsafe_allow_html=True)

    progreso = st.progress(0, text="Generando PDFs...")
    zip_buffer = io.BytesIO()
    filas_excel = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, alumno in enumerate(alumnos):
            progreso.progress(
                (i + 1) / len(alumnos),
                text=f"Generando PDF de {alumno['nombre']}...",
            )

            # ─── Mapear potencial para el PDF (MEDIO → EN DESARROLLO) ───
            potencial_pdf = POTENCIAL_TEXTO.get(
                alumno["potencial"], alumno["potencial"]
            )

            datos_pdf = {
                "campo_nombre": alumno["nombre"],
                "campo_edad": alumno["edad"],
                "campo_genero": alumno["sexo"],
                "campo_fecha": alumno["_fecha"],
                "campo_grado_instruccion": alumno["_grado"],
                "campo_grado": alumno["_nivel"],
                "campo_colegio": alumno["_ie"],
                "niveles": alumno["niveles"],
                "potencial_puesto": potencial_pdf,
                "campo_areas": alumno["area_1"],
                "campo_areas_2": alumno["area_2"],
                "campo_carreras": alumno["carrera_1"],
                "campo_carreras_2": alumno["carrera_2"],
            }

            ruta_tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".pdf"
            ).name
            try:
                generar_pdf(datos_pdf, ruta_salida=ruta_tmp)
                with open(ruta_tmp, "rb") as f:
                    pdf_bytes = f.read()
                nombre_pdf = alumno["nombre"].replace(" ", "_") + ".pdf"
                zf.writestr(nombre_pdf, pdf_bytes)
            finally:
                try:
                    os.remove(ruta_tmp)
                except Exception:
                    pass

            # ─── Fila base del Excel ───
            fila = {
                "Nombre": alumno["nombre"],
                "Edad": alumno["edad"],
                "Sexo": alumno["sexo"],
                "Potencial": potencial_pdf,   # también en el Excel
                "Área 1": alumno["area_1"],
                "Área 2": alumno["area_2"],
                "Carrera 1": alumno["carrera_1"],
                "Carrera 2": alumno["carrera_2"],
                "Carrera escrita 1": alumno["carrera_manual_1"],
                "Carrera escrita 2": alumno["carrera_manual_2"],
                "Carrera escrita 3": alumno["carrera_manual_3"],
            }

            # ─── Análisis de afinidad ───
            analisis = alumno.get("_analisis_escritas", [])
            for idx, item in enumerate(analisis, start=1):
                estado = item.get("estado")
                if estado == "analizada":
                    fila[f"Escrita {idx} → canónica"] = item.get("carrera_canonica", "")
                    fila[f"Escrita {idx} → afinidad"] = item.get("afinidad", 0)
                    fila[f"Escrita {idx} → veredicto"] = item.get("veredicto", "").upper()
                    fila[f"Escrita {idx} → match con test"] = item.get("carrera_test_relacionada", "")
                    fila[f"Escrita {idx} → relación"] = item.get("relacion", "")
                elif estado == "no_reconocida":
                    fila[f"Escrita {idx} → veredicto"] = "NO RECONOCIDA"
                elif estado == "sin_match":
                    fila[f"Escrita {idx} → veredicto"] = "SIN RELACIÓN"

            # ─── Puntajes y niveles ───
            for area, puntaje in alumno["puntajes_directos"].items():
                fila[f"Puntaje {area.replace('_', ' ').title()}"] = puntaje
            for area, nivel in alumno["niveles"].items():
                fila[f"Nivel {area.replace('_', ' ').title()}"] = nivel

            filas_excel.append(fila)

        progreso.progress(1.0, text="Generando Excel...")
        df = pd.DataFrame(filas_excel)
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Resultados")
        zf.writestr("resultados_salon.xlsx", excel_buffer.getvalue())

    progreso.empty()
    zip_buffer.seek(0)
    st.session_state.zip_data = zip_buffer.getvalue()

    st.markdown(f"""
    <div class="resumen-card">
        <h3>{len(alumnos)} informes generados</h3>
        <p>Descarga el paquete con los PDFs y el Excel consolidado.</p>
    </div>
    """, unsafe_allow_html=True)

    st.download_button(
        label="Descargar ZIP (PDFs + Excel)",
        data=st.session_state.zip_data,
        file_name=f"informes_sovio_{datetime.now():%Y%m%d_%H%M%S}.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

    if st.button("Procesar otro salón", use_container_width=True):
        st.session_state.alumnos = []
        st.session_state.zip_data = None
        st.session_state.fase = 1
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════
def main():
    st.set_page_config(
        page_title="Generador SOVIO",
        page_icon=None,
        layout="wide",
    )
    cargar_css()
    inicializar_estado()

    if st.session_state.fase == 1:
        fase_1_entrada()
    elif st.session_state.fase == 3:
        fase_3_revision()
    elif st.session_state.fase == 4:
        fase_4_descarga()


if __name__ == "__main__":
    main()