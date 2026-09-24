"""
templates.py — Plantillas HTML para IEPPO.

Cada función devuelve un string HTML que debe pasarse por render_html().
No importa Streamlit: son funciones puras.
"""
import html as _html


# ─────────────────────────────────────────────────────────────
# CONSTANTES DE PRESENTACIÓN
# ─────────────────────────────────────────────────────────────
NIVEL_LABEL = {
    "bajo":     "Bajo",
    "medio":    "Medio",
    "alto":     "Alto",
    "sin_dato": "—",
}

NIVEL_COLOR_HEX = {
    "bajo":  "#ef4444",
    "medio": "#f59e0b",
    "alto":  "#10b981",
}

NIVEL_CHIP_MAP = {
    "universitario": "nivel-univ",
    "tecnico":       "nivel-tec",
    "cetpro":        "nivel-cetpro",
}


def e(v) -> str:
    """Escapa HTML rápido."""
    return _html.escape(str(v if v is not None else "—"))


def nivel_de_score(score: float, max_score: float) -> str:
    """Clasifica un score en bajo/medio/alto por percentil relativo."""
    if max_score <= 0:
        return "sin_dato"
    pct = (score / max_score) * 100
    if pct >= 80:
        return "alto"
    if pct >= 50:
        return "medio"
    return "bajo"


# ─────────────────────────────────────────────────────────────
# BARRA DE PROGRESO
# ─────────────────────────────────────────────────────────────
def barra_progreso(paso_actual: int) -> str:
    labels = ["Subir", "Verificar", "Top 2", "Propuesta", "Carreras", "Informe"]
    partes = []
    for i in range(1, 7):
        if i < paso_actual:
            cls = "step done"
        elif i == paso_actual:
            cls = "step active"
        else:
            cls = "step"
        partes.append(f"<div class='{cls}'>{i} · {labels[i-1]}</div>")
    return "<div class='step-bar'>" + "".join(partes) + "</div>"


# ─────────────────────────────────────────────────────────────
# SECTION TITLE
# ─────────────────────────────────────────────────────────────
def section_title(texto: str) -> str:
    return f"<div class='section-title'>{texto}</div>"


# ─────────────────────────────────────────────────────────────
# CHIP DE NIVEL
# ─────────────────────────────────────────────────────────────
def chip_nivel(nivel: str) -> str:
    if nivel == "sin_dato":
        return ""
    return f"<span class='nivel-chip {nivel}'>{NIVEL_LABEL[nivel]}</span>"


# ─────────────────────────────────────────────────────────────
# PANEL DE CRITERIOS P / E / H
# ─────────────────────────────────────────────────────────────
def crit_card(letra: str, meta: dict, datos: dict, es_pred: bool) -> str:
    corona = "<span class='crit-tag'>Predominante</span>" if es_pred else ""
    tipos_html = "".join(f"<span class='crit-chip'>{e(t)}</span>"
                         for t in datos["tipos"])
    return (
        f"<div class='crit-card {'pred' if es_pred else ''}' "
        f"style='border-top-color:{meta['color']};'>"
        f"<div class='crit-head'>"
        f"<div class='crit-letter' style='background:{meta['color']};'>{letra}</div>"
        f"<div>"
        f"<div class='crit-nombre'>{meta['nombre']}</div>"
        f"<div class='crit-desc'>{meta['descripcion']}</div>"
        f"</div></div>"
        f"<div class='crit-stats'>"
        f"<div><span class='crit-k'>Baremo máx</span>"
        f"<span class='crit-v'>{datos['baremo_max']}</span></div>"
        f"<div><span class='crit-k'>PD total</span>"
        f"<span class='crit-v'>{datos['pd_total']}</span></div>"
        f"</div>"
        f"<div class='crit-tipos'>{tipos_html}</div>"
        f"{corona}</div>"
    )


# ─────────────────────────────────────────────────────────────
# VOC CARD (Top 1 / Top 2)
# ─────────────────────────────────────────────────────────────
def voc_card(tipo: str, baremo, pd: int, crit: str, rank: int) -> str:
    variante = "gold" if rank == 1 else "silver"
    rank_label = f"Puesto {rank}"
    b_txt = baremo if baremo is not None else "—"
    return (
        f"<div class='voc-card {variante}'>"
        f"<div class='voc-rank'>{rank_label} · Criterio {crit}</div>"
        f"{chip_nivel('alto' if (baremo or 0) >= 60 else 'medio' if (baremo or 0) > 40 else 'bajo')}"
        f"<div class='voc-tipo'>{e(tipo)}</div>"
        f"<div class='voc-stats'>"
        f"<span>PD: <b>{pd}</b></span>"
        f"<span>Baremo: <b>{b_txt}</b></span>"
        f"</div></div>"
    )


# ─────────────────────────────────────────────────────────────
# CAREER CARD
# ─────────────────────────────────────────────────────────────
def career_card(carrera: str, tipo: str, relacion: str, crit: str,
                variante: str = "principal") -> str:
    badge_txt = "Principal" if variante == "principal" else "Respaldo"
    rel_html = f"<div class='career-rel'>{e(relacion)}</div>" if relacion else ""
    return (
        f"<div class='career-card {variante}'>"
        f"<div class='career-badge'>{badge_txt} · {crit}</div>"
        f"<div class='career-name'>{e(carrera)}</div>"
        f"<div class='career-tipo'>{e(tipo)}</div>"
        f"{rel_html}"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────
# ITEM CARD (paso 2)
# ─────────────────────────────────────────────────────────────
def item_title(item: str, es_dudoso: bool) -> str:
    badge = "<span class='mini-badge'>Revisar</span>" if es_dudoso else ""
    cls = "item-title dudoso" if es_dudoso else "item-title"
    return f"<div class='{cls}'>{e(item)}{badge}</div>"


# ─────────────────────────────────────────────────────────────
# STUDENT HEADER
# ─────────────────────────────────────────────────────────────
def student_header(inicial: str, nombre: str, sexo_label: str) -> str:
    return (
        f"<div class='student-header'>"
        f"<div class='student-avatar'>{e(inicial)}</div>"
        f"<div>"
        f"<div class='student-name'>{e(nombre)}</div>"
        f"<div class='student-meta'>Sexo: {e(sexo_label)} · Evaluación IEPPO</div>"
        f"</div></div>"
    )


# ─────────────────────────────────────────────────────────────
# PROPOSAL ROW / BOX
# ─────────────────────────────────────────────────────────────
def proposal_row(num, carrera: str, origen: str, es_html: bool = False) -> str:
    """
    Fila de propuesta (paso 4 y 5).

    Args:
        num: número, viñeta o etiqueta a mostrar a la izquierda.
        carrera: nombre de la carrera (o HTML si es_html=True).
        origen: "test" | "alumno" | "sintesis".
        es_html: si True, NO escapa el HTML de `carrera`. Útil para
                 mostrar interpretaciones semánticas con <b>, <i>, etc.
                 Por defecto False (comportamiento original).
    """
    carrera_render = carrera if es_html else e(carrera)
    return (
        f"<div class='proposal-row'>"
        f"<div class='proposal-num'>{num}</div>"
        f"<div class='proposal-carrera'>{carrera_render}</div>"
        f"<div class='proposal-origen {origen}'>"
        f"{'Test' if origen == 'test' else 'Alumno' if origen == 'alumno' else 'Síntesis'}"
        f"</div></div>"
    )

def proposal_box() -> str:
    return (
        "<div class='proposal-box'>"
        "<h4>Ingresa carreras de interés (opcional)</h4>"
        "<p>Puedes escribir hasta 3 carreras tal como las conozcas. "
        "Si no escribes ninguna, el sistema evaluará solo con las "
        "carreras que sugirió el test. Los nombres se emparejarán "
        "automáticamente con el catálogo.</p>"
        "</div>"
    )

# ─────────────────────────────────────────────────────────────
# FINAL CARD (paso 5)
# ─────────────────────────────────────────────────────────────
def final_card(carrera: str, rank: int, nivel_meta: dict, inst_meta: dict,
               score: float, origen_txt: str, afin_pct: int,
               s_voc: float, s_prop: float, s_test: float) -> str:
    return (
        f"<div class='final-card'>"
        f"<div class='rank'>Puesto {rank}</div>"
        f"<div class='name'>{e(carrera)}</div>"
        f"<div class='meta'>"
        f"<span class='meta-chip {nivel_meta['chip']}'>{nivel_meta['label']}</span>"
        f"<span class='meta-chip {inst_meta['chip']}'>{inst_meta['label']}</span>"
        f"<span class='meta-chip'>Score {score}</span>"
        f"</div>"
        f"<div class='origen-line'>Origen: <b>{origen_txt}</b></div>"
        f"<div class='score-bar'>"
        f"<div class='score-fill' style='width:{afin_pct}%;'></div>"
        f"</div>"
        f"<div class='score-detail'>"
        f"<span>Vocacional <b>{s_voc}</b></span>"
        f"<span>Afinidad personal <b>{s_prop}</b></span>"
        f"<span>Afinidad test <b>{s_test}</b></span>"
        f"</div></div>"
    )


# ─────────────────────────────────────────────────────────────
# INFORME — HERO, LEYENDA, INFO BLOCK
# ─────────────────────────────────────────────────────────────
def hero_informe(nombre: str, sexo_label: str) -> str:
    return (
        f"<div class='niveles-hero'>"
        f"<div class='title'>Informe vocacional</div>"
        f"<div class='sub'>{e(nombre)} · {e(sexo_label)} · "
        f"Estilo personal y preferencia ocupacional</div>"
        f"</div>"
    )


def leyenda_informe() -> str:
    return (
        "<div class='niveles-legend'>"
        "<div class='legend-pill'><span class='dot' style='background:#ef4444;'></span> Bajo</div>"
        "<div class='legend-pill'><span class='dot' style='background:#f59e0b;'></span> Medio</div>"
        "<div class='legend-pill'><span class='dot' style='background:#10b981;'></span> Alto</div>"
        "<div class='legend-pill' style='margin-left:auto;'>Tipos → ≤40 / 41-59 / ≥60</div>"
        "<div class='legend-pill'>Carreras → ≤40% / 50-79% / ≥80%</div>"
        "</div>"
    )


def info_block(num, titulo: str, sub: str, contenido: str = "") -> str:
    return (
        f"<div class='informe-block'>"
        f"<div class='block-head'>"
        f"<div class='block-num'>{num}</div>"
        f"<div>"
        f"<div class='block-title'>{e(titulo)}</div>"
        f"<div class='block-sub'>{e(sub)}</div>"
        f"</div></div>"
        f"{contenido}"
        f"</div>"
    )


def empty_note(texto: str) -> str:
    return f"<div class='empty-note'>{e(texto)}</div>"


def viz_card(titulo: str, sub: str) -> str:
    return (
        f"<div class='viz-card'>"
        f"<div class='viz-title'>{e(titulo)}</div>"
        f"<div class='viz-sub'>{e(sub)}</div>"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────
# TABLA DE TIPOS VOCACIONALES
# ─────────────────────────────────────────────────────────────
def _mark_cell(nivel: str, col_nivel: str) -> str:
    if nivel == col_nivel and nivel != "sin_dato":
        return f"<span class='x {col_nivel}'>X</span>"
    return "<span class='empty'>·</span>"


def tabla_tipos(items: list) -> str:
    filas = []
    for i, it in enumerate(items, 1):
        baremo_txt = it["baremo"] if it["baremo"] is not None else "—"
        nivel = it["nivel"]
        filas.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td><span class='tipo-name'>{e(it['tipo'])}</span>"
            f"<span class='tipo-crit'>{it['crit']}</span></td>"
            f"<td><span class='baremo-val'>{baremo_txt}</span></td>"
            f"<td class='nivel-cell'>"
            f"<span class='nivel-chip {nivel}'>{NIVEL_LABEL[nivel]}</span></td>"
            f"<td class='mark-cell'>{_mark_cell(nivel, 'bajo')}</td>"
            f"<td class='mark-cell'>{_mark_cell(nivel, 'medio')}</td>"
            f"<td class='mark-cell'>{_mark_cell(nivel, 'alto')}</td>"
            f"</tr>"
        )
    return (
        "<table class='niveles-table'>"
        "<thead><tr>"
        "<th style='text-align:center;'>#</th>"
        "<th>Tipo vocacional</th>"
        "<th>Baremo</th>"
        "<th style='text-align:center;'>Nivel</th>"
        "<th style='text-align:center;'>Bajo</th>"
        "<th style='text-align:center;'>Medio</th>"
        "<th style='text-align:center;'>Alto</th>"
        "</tr></thead>"
        f"<tbody>{''.join(filas)}</tbody>"
        "</table>"
    )


# ─────────────────────────────────────────────────────────────
# TABLA DE CARRERAS (test / finales)
# ─────────────────────────────────────────────────────────────
def tabla_carreras(items: list, max_score: float) -> str:
    filas = []
    for i, it in enumerate(items, 1):
        nivel = it.get("nivel_score") or nivel_de_score(it["score"], max_score)
        origen = it.get("origen", "test")
        origen_label = {
            "test": "Test", "alumno": "Alumno", "sintesis": "Síntesis",
        }.get(origen, origen)
        filas.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td><span class='tipo-name'>{e(it['carrera'])}</span></td>"
            f"<td class='origen-cell'>"
            f"<span class='origen-tag {origen}'>{origen_label}</span></td>"
            f"<td><span class='score-val'>{it['score']}</span></td>"
            f"<td class='nivel-cell'>"
            f"<span class='nivel-chip {nivel}'>{NIVEL_LABEL[nivel]}</span></td>"
            f"<td class='mark-cell'>{_mark_cell(nivel, 'bajo')}</td>"
            f"<td class='mark-cell'>{_mark_cell(nivel, 'medio')}</td>"
            f"<td class='mark-cell'>{_mark_cell(nivel, 'alto')}</td>"
            f"</tr>"
        )
    return (
        "<table class='niveles-table carreras'>"
        "<thead><tr>"
        "<th style='text-align:center;'>#</th>"
        "<th>Carrera</th>"
        "<th style='text-align:center;'>Origen</th>"
        "<th>Score</th>"
        "<th style='text-align:center;'>Nivel</th>"
        "<th style='text-align:center;'>Bajo</th>"
        "<th style='text-align:center;'>Medio</th>"
        "<th style='text-align:center;'>Alto</th>"
        "</tr></thead>"
        f"<tbody>{''.join(filas)}</tbody>"
        "</table>"
    )


# ─────────────────────────────────────────────────────────────
# RESUMEN DE NIVELES
# ─────────────────────────────────────────────────────────────
def resumen_niveles(n_bajo: int, n_medio: int, n_alto: int) -> str:
    return (
        f"<div class='niveles-summary'>"
        f"<div class='card bajo'><div class='count'>{n_bajo}</div>"
        f"<div class='lbl'>Tipos en nivel bajo</div>"
        f"<div class='desc'>Baremo ≤ 40</div></div>"
        f"<div class='card medio'><div class='count'>{n_medio}</div>"
        f"<div class='lbl'>Tipos en nivel medio</div>"
        f"<div class='desc'>Baremo 41 – 59</div></div>"
        f"<div class='card alto'><div class='count'>{n_alto}</div>"
        f"<div class='lbl'>Tipos en nivel alto</div>"
        f"<div class='desc'>Baremo ≥ 60</div></div>"
        f"</div>"
    )


def predominante_banner(tipo: str, crit: str, baremo, nivel: str) -> str:
    return (
        f"<div class='predominante-banner'>"
        f"<div class='lbl'>Tipo predominante</div>"
        f"<div class='nombre'>{e(tipo)}</div>"
        f"<div class='meta'>"
        f"Criterio {crit} · Baremo {baremo} · Nivel {NIVEL_LABEL[nivel]}"
        f"</div></div>"
    )


# ─────────────────────────────────────────────────────────────
# COMPARACIÓN TOP 2 vs RESTO
# ─────────────────────────────────────────────────────────────
def comp_top2(items_tipos: list) -> str:
    if not items_tipos:
        return ""

    top1 = items_tipos[0]
    top2 = items_tipos[1] if len(items_tipos) > 1 else None
    resto = items_tipos[2:] if len(items_tipos) > 2 else []

    filas = []
    # Top 1
    b1_txt = top1["baremo"] if top1["baremo"] is not None else "—"
    filas.append(
        f"<div class='comp-row'>"
        f"<div class='comp-rank p1'>1</div>"
        f"<div class='comp-nombre'>{e(top1['tipo'])}</div>"
        f"<div class='comp-baremo'>{b1_txt}</div>"
        f"<div class='comp-diff pos'>Referencia</div>"
        f"</div>"
    )
    # Top 2 y resto vs Top 1
    for i, it in enumerate([top2] + resto if top2 else resto, 2):
        if it is None or it["baremo"] is None or not top1["baremo"]:
            continue
        diff_pct = ((it["baremo"] - top1["baremo"]) / top1["baremo"]) * 100
        clase = "neg" if diff_pct < 0 else "pos" if diff_pct > 0 else "eq"
        signo = f"{diff_pct:+.1f}%" if diff_pct != 0 else "0%"
        rank_cls = "p2" if i == 2 else "pr"
        filas.append(
            f"<div class='comp-row'>"
            f"<div class='comp-rank {rank_cls}'>{i}</div>"
            f"<div class='comp-nombre'>{e(it['tipo'])}</div>"
            f"<div class='comp-baremo'>{it['baremo']}</div>"
            f"<div class='comp-diff {clase}'>{signo}</div>"
            f"</div>"
        )

    return (
        f"<div class='viz-card'>"
        f"<div class='viz-title'>Comparación vs predominante</div>"
        f"<div class='viz-sub'>Diferencia porcentual respecto al tipo Top 1 "
        f"({e(top1['tipo'])}).</div>"
        f"{''.join(filas)}"
        f"</div>"
    )