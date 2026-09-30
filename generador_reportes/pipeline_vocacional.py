# pipeline_vocacional.py
"""
Une el OCR + el motor vocacional completo.
Llama directamente a las funciones ya creadas en ocr/ y vocacional/.
"""
import os
import sys

PADRE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PADRE not in sys.path:
    sys.path.insert(0, PADRE)

from ocr.pipeline import procesar_formulario_pdf
from vocacional.puntajes import calcular_pd
from vocacional.baremos import calcular_baremos, nivel_correspondencia
from vocacional.areas import top_2
from vocacional.carreras import seleccionar_4_carreras
from vocacional.utils import auditar_marcas


_ALIAS = {
    "investigativo": "investigacion",
    "emprendedor":   "emprendimiento",
}


def _normalizar_clave(nombre_tipo: str) -> str:
    clave = (nombre_tipo.lower()
             .replace(" ", "_")
             .replace("é", "e").replace("á", "a")
             .replace("í", "i").replace("ó", "o")
             .replace("ú", "u"))
    return _ALIAS.get(clave, clave)


def _calcular_potencial(niveles: dict) -> str:
    nivel_emprend = niveles.get("emprendimiento", "bajo")
    nivel_lider   = niveles.get("liderazgo", "bajo")
    if nivel_emprend == "alto":
        return "ALTO"
    if nivel_emprend == "medio":
        return "MEDIO"
    return "BAJO"


def procesar_alumno(ruta_pdf: str, sexo: str, debug: bool = False) -> dict:
    """
    Pipeline completo: PDF → diccionario listo para el generador de PDFs.
    
    Si debug=True, imprime en consola el detalle de cada paso.
    """
    def log(msg):
        if debug:
            print(msg)

    # ── 1. OCR ────────────────────────────────────────────
    log(f"\n{'='*60}")
    log(f"[1/6] EJECUTANDO OCR sobre: {ruta_pdf}")
    log(f"{'='*60}")

    resultado = procesar_formulario_pdf(ruta_pdf)
    if not resultado["exito"]:
        raise RuntimeError(f"OCR falló: {resultado.get('mensaje', 'Error')}")

    marcas = resultado["marcas"]
    log(f"  ✓ OCR exitoso")
    log(f"  ✓ Modo: {resultado.get('modo', 'desconocido')}")
    log(f"  ✓ Total procesados: {resultado.get('total_procesados', 0)}/118")
    log(f"  ✓ Mensaje: {resultado.get('mensaje', '')}")

    # Contar marcas por tipo
    conteo = {"si": 0, "no": 0, "vacio": 0, "ambos": 0}
    for v in marcas.values():
        if v in conteo:
            conteo[v] += 1
    log(f"\n  Conteo de marcas:")
    log(f"    SI (marcadas):  {conteo['si']}")
    log(f"    NO:             {conteo['no']}")
    log(f"    VACIO:          {conteo['vacio']}")
    log(f"    AMBOS:          {conteo['ambos']}")

    if debug:
        items_si = sorted([k for k, v in marcas.items() if v in ("si", "ambos")])
        log(f"\n  Ítems marcados (SI/AMBOS): {items_si}")

    # ── 2. Cálculo de PD por tipo ─────────────────────────
    log(f"\n{'='*60}")
    log(f"[2/6] CALCULANDO PD POR TIPO VOCACIONAL")
    log(f"{'='*60}")

    pd_por_tipo = calcular_pd(marcas)
    for tipo, datos in pd_por_tipo.items():
        log(f"  {tipo:22s} PD={datos['PD']:3d}  "
            f"(E={datos['PD_E']}, P={datos['PD_P']}, H={datos['PD_H']})")

    # ── 3. Baremos según sexo ─────────────────────────────
    log(f"\n{'='*60}")
    log(f"[3/6] APLICANDO BAREMOS (sexo: {sexo})")
    log(f"{'='*60}")

    con_baremo = calcular_baremos(pd_por_tipo, sexo)
    for tipo, datos in con_baremo.items():
        log(f"  {tipo:22s} PD={datos['PD']:3d}  →  Baremo={datos['Baremo']}")

    # ── 4. Niveles Bajo/Medio/Alto ────────────────────────
    log(f"\n{'='*60}")
    log(f"[4/6] CALCULANDO NIVELES")
    log(f"{'='*60}")

    puntajes_directos = {}
    niveles = {}
    for tipo, datos in con_baremo.items():
        clave = _normalizar_clave(tipo)
        puntajes_directos[clave] = datos["PD"]
        niveles[clave] = nivel_correspondencia(datos["Baremo"])
        log(f"  {clave:22s} → {niveles[clave]}")

    # ── 5. Top 2 áreas ────────────────────────────────────
    log(f"\n{'='*60}")
    log(f"[5/6] SELECCIONANDO TOP 2 ÁREAS")
    log(f"{'='*60}")

    top = top_2(con_baremo)
    tipo_top1 = top[0]["tipo"]
    tipo_top2 = top[1]["tipo"] if len(top) > 1 else tipo_top1
    log(f"  Top 1: {tipo_top1} (Baremo={top[0]['Baremo']})")
    log(f"  Top 2: {tipo_top2} (Baremo={top[1]['Baremo'] if len(top) > 1 else 'N/A'})")

    areas_top = [_normalizar_clave(tipo_top1), _normalizar_clave(tipo_top2)]

    # ── 6. Carreras sugeridas ─────────────────────────────
    log(f"\n{'='*60}")
    log(f"[6/6] SELECCIONANDO CARRERAS")
    log(f"{'='*60}")

    carreras_info = seleccionar_4_carreras(tipo_top1, tipo_top2)
    principales = carreras_info.get("principales", [])
    respaldo = carreras_info.get("respaldo", [])

    log(f"  Principales:")
    for c in principales:
        log(f"    - {c['carrera']:35s} [{c['tipo']}]  → {c['relacion']} ({c['puntaje']} pts)")
    log(f"  Respaldo:")
    for c in respaldo:
        log(f"    - {c['carrera']:35s} [{c['tipo']}]  → {c['relacion']} ({c['puntaje']} pts)")

    carreras_top = [c["carrera"] for c in principales]

    # ── Potencial ─────────────────────────────────────────
    potencial = _calcular_potencial(niveles)
    log(f"\n  Potencial Empresarial: {potencial}")

    log(f"\n{'='*60}")
    log(f"PIPELINE COMPLETO")
    log(f"{'='*60}\n")

    return {
        "puntajes_directos": puntajes_directos,
        "niveles": niveles,
        "areas_top": areas_top,
        "carreras_top": carreras_top,
        "potencial": potencial,
        "auditoria": auditar_marcas(marcas),
        "total_procesados": resultado["total_procesados"],
        "items_revisar": resultado.get("items_revisar", []),
    }