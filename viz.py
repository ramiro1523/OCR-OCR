"""
viz.py — Visualizaciones Plotly para IEPPO.
"""
import plotly.graph_objects as go

from templates import NIVEL_COLOR_HEX


def radar(con_baremos: dict) -> go.Figure:
    """Radar (Scatterpolar) de los 7 tipos vocacionales."""
    from vocacional.baremos import nivel_correspondencia

    tipos, baremos, colores = [], [], []
    for tipo, d in con_baremos.items():
        b = d.get("Baremo")
        nivel = nivel_correspondencia(b)
        tipos.append(tipo.title())
        baremos.append(b if b is not None else 0)
        colores.append(NIVEL_COLOR_HEX.get(nivel, "#94a3b8"))

    tipos_c = tipos + [tipos[0]]
    baremos_c = baremos + [baremos[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=baremos_c, theta=tipos_c, fill="toself",
        fillcolor="rgba(37, 99, 235, 0.15)",
        line=dict(color="#2563eb", width=2),
        marker=dict(color=colores + [colores[0]], size=10,
                    line=dict(color="white", width=2)),
        hovertemplate="<b>%{theta}</b><br>Baremo: %{r}<extra></extra>",
        name="Baremo",
    ))
    fig.add_trace(go.Scatterpolar(
        r=[60] * len(tipos_c), theta=tipos_c, mode="lines",
        line=dict(color="#10b981", width=1, dash="dot"),
        name="Umbral Alto (60)", hoverinfo="skip",
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True,
                range=[0, max(baremos + [70]) + 5],
                gridcolor="rgba(148,163,184,.25)",
                tickfont=dict(size=9, color="#94a3b8"),
            ),
            angularaxis=dict(
                gridcolor="rgba(148,163,184,.25)",
                tickfont=dict(size=11, color="#475569"),
            ),
        ),
        showlegend=False,
        margin=dict(l=40, r=40, t=10, b=10),
        height=380,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, Inter, sans-serif"),
    )
    return fig


def barras_horizontales(con_baremos: dict) -> go.Figure:
    """Barras horizontales con color por nivel."""
    from vocacional.baremos import nivel_correspondencia

    filas = []
    for tipo, d in con_baremos.items():
        b = d.get("Baremo")
        nivel = nivel_correspondencia(b)
        filas.append({
            "tipo": tipo.title(),
            "baremo": b if b is not None else 0,
            "color": NIVEL_COLOR_HEX.get(nivel, "#94a3b8"),
        })
    filas.sort(key=lambda x: x["baremo"])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[f["baremo"] for f in filas],
        y=[f["tipo"] for f in filas],
        orientation="h",
        marker=dict(
            color=[f["color"] for f in filas],
            line=dict(color="rgba(255,255,255,.4)", width=1),
        ),
        text=[f" {f['baremo']}" for f in filas],
        textposition="outside",
        textfont=dict(size=12, color="#0f172a", family="Consolas, monospace"),
        hovertemplate="<b>%{y}</b><br>Baremo: %{x}<extra></extra>",
    ))
    for x, lbl, col in [(40, "Bajo ≤40", "#ef4444"), (60, "Alto ≥60", "#10b981")]:
        fig.add_vline(x=x, line_dash="dash", line_color=col,
                      annotation_text=lbl, annotation_position="top",
                      annotation_font_size=10, annotation_font_color=col)

    fig.update_layout(
        margin=dict(l=10, r=60, t=30, b=10),
        height=340,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,.18)",
                   zeroline=False,
                   range=[0, max([f["baremo"] for f in filas] + [70]) + 10],
                   tickfont=dict(size=10, color="#94a3b8")),
        yaxis=dict(tickfont=dict(size=11, color="#475569"), showgrid=False),
        showlegend=False,
        font=dict(family="Segoe UI, Inter, sans-serif"),
        bargap=0.35,
    )
    return fig


def gauge(baremo, tipo: str) -> go.Figure:
    """Gauge del baremo del tipo predominante."""
    from vocacional.baremos import nivel_correspondencia

    b = baremo if baremo is not None else 0
    nivel = nivel_correspondencia(baremo)
    color = NIVEL_COLOR_HEX.get(nivel, "#94a3b8")

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=b,
        number=dict(font=dict(size=52, color=color,
                              family="Segoe UI, Inter, sans-serif")),
        title=dict(
            text=f"<span style='font-size:12px;color:#475569;"
                 f"letter-spacing:1px;'>{tipo.upper()}</span>",
            font=dict(size=14),
        ),
        gauge=dict(
            axis=dict(range=[0, 80], tickwidth=1, tickcolor="#cbd5e1",
                      tickfont=dict(size=10, color="#94a3b8"),
                      ticks="outside", tickvals=[0, 20, 40, 60, 80]),
            bar=dict(color=color, thickness=0.35),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0, 40],  color="rgba(239,68,68,.10)"),
                dict(range=[40, 60], color="rgba(245,158,11,.10)"),
                dict(range=[60, 80], color="rgba(16,185,129,.10)"),
            ],
            threshold=dict(line=dict(color=color, width=3),
                           thickness=0.8, value=b),
        ),
    ))
    fig.update_layout(
        height=280, margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, Inter, sans-serif"),
    )
    return fig