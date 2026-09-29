# =====================================================================
# CONFIG_CAMPOS.PY
# =====================================================================
# Coordenadas PDF: origen (0,0) = esquina INFERIOR IZQUIERDA
# Página: 612 x 792 puntos (US Letter)
#
# 📏 CÓMO AJUSTAR CADA CAMPO:
#   ⇦ IZQUIERDA  →  resta al valor de "x"      (ej. x=200 → 190)
#   ⇨ DERECHA    →  suma al valor de "x"       (ej. x=200 → 210)
#   ⇧ ARRIBA     →  SUMA al valor de "y"       (ej. y=650 → 660)
#   ⇩ ABAJO      →  RESTA al valor de "y"      (ej. y=650 → 640)
#
#   Regla mental: "y" es la altura desde el piso.
#     y grande = arriba | y pequeña = abajo
# =====================================================================


# =====================================================================
# PÁGINA 1 — CABECERA
# =====================================================================
CAMPOS_TEXTO_P1 = {

    # ---------- NOMBRE DEL EVALUADO ----------
    # 🚫 NO TOCAR
    "campo_nombre":  {"x": 240.0, "y": 695.0, "width": 282.5, "height": 13.5, "font_size":8},

    # ---------- FECHA DE EVALUACIÓN ----------
    "campo_fecha":   {"x": 299.0, "y": 672.5, "width": 65.0,  "height": 13.0, "font_size": 7},

    # ---------- EDAD ----------
    # ⇨ se movió +2 a la derecha
    "campo_edad":    {"x": 396.5, "y": 673.0, "width": 28.0,  "height": 12.5, "font_size": 7},

    # ---------- GÉNERO ----------
    # ⇨ se movió +2 a la derecha
    "campo_genero":  {"x": 474.0, "y": 673.0, "width": 15.5,  "height": 12.5, "font_size": 7},

    # ---------- DNI ----------
    "campo_dni":     {"x": 187.0, "y": 648.0, "width": 42.0,  "height": 14.5, "font_size": 6},

    # ---------- GRADO DE INSTRUCCIÓN ----------
    # ⇩ −1 abajo  |  ⇦ −3 izquierda
    "campo_grado":   {"x": 294.5, "y": 648.0, "width": 39.5,  "height": 14.5, "font_size": 5},

    # ---------- SECUNDARIA (colegio/institución educativa) ----------
    # ⇧ +5 arriba  |  ⇨ +6 derecha
    # colegio (SANTO DOMINGO): ⇩ −3 · ⇨ +4
    "campo_colegio": {"x": 395.0, "y": 649.0, "width": 124.5, "height": 12.0, "font_size":5.7},
}


# =====================================================================
# PÁGINA 2 — 21 CELDAS DE LA TABLA (marcas "X")
# =====================================================================
# Estructura: marca_<area>_<nivel>
# Áreas: liderazgo, tecnico_mecanico, social, organizado,
#        artistico, emprendimiento, investigacion
# Niveles: bajo, medio, alto
#
# 🚫 NO TOCAR (ya están calibradas al pixel)
# =====================================================================
CAMPOS_MARCAS_P2 = {

    # ---------------- LIDERAZGO ----------------
    "marca_liderazgo_bajo":   {"x": 229.5, "y": 497.5, "width": 66.0, "height": 12.0, "font_size": 10},
    "marca_liderazgo_medio":  {"x": 298.0, "y": 497.5, "width": 67.5, "height": 12.0, "font_size": 10},
    "marca_liderazgo_alto":   {"x": 368.0, "y": 497.5, "width": 77.0, "height": 12.0, "font_size": 10},

    # ---------------- TÉCNICO-MECÁNICO ----------------
    "marca_tecnico_mecanico_bajo":   {"x": 229.5, "y": 483.0, "width": 66.0, "height": 11.5, "font_size": 10},
    "marca_tecnico_mecanico_medio":  {"x": 298.0, "y": 483.0, "width": 67.5, "height": 11.5, "font_size": 10},
    "marca_tecnico_mecanico_alto":   {"x": 368.0, "y": 483.0, "width": 77.5, "height": 11.5, "font_size": 10},

    # ---------------- SOCIAL ----------------
    "marca_social_bajo":   {"x": 229.5, "y": 469.0, "width": 66.0, "height": 13.0, "font_size": 10},
    "marca_social_medio":  {"x": 298.0, "y": 469.0, "width": 67.5, "height": 12.5, "font_size": 10},
    "marca_social_alto":   {"x": 368.0, "y": 469.0, "width": 78.0, "height": 12.0, "font_size": 10},

    # ---------------- ORGANIZADO ----------------
    "marca_organizado_bajo":   {"x": 229.5, "y": 454.5, "width": 66.0, "height": 11.5, "font_size": 10},
    "marca_organizado_medio":  {"x": 298.0, "y": 454.5, "width": 67.5, "height": 11.5, "font_size": 10},
    "marca_organizado_alto":   {"x": 368.0, "y": 454.5, "width": 77.5, "height": 12.0, "font_size": 10},

    # ---------------- ARTÍSTICO ----------------
    "marca_artistico_bajo":   {"x": 229.5, "y": 440.5, "width": 65.5, "height": 12.0, "font_size": 10},
    "marca_artistico_medio":  {"x": 297.5, "y": 440.5, "width": 68.0, "height": 12.0, "font_size": 10},
    "marca_artistico_alto":   {"x": 368.0, "y": 440.5, "width": 78.0, "height": 11.5, "font_size": 10},

    # ---------------- EMPRENDIMIENTO ----------------
    "marca_emprendimiento_bajo":   {"x": 229.5, "y": 426.0, "width": 65.5, "height": 11.5, "font_size": 10},
    "marca_emprendimiento_medio":  {"x": 297.5, "y": 426.0, "width": 68.0, "height": 11.5, "font_size": 10},
    "marca_emprendimiento_alto":   {"x": 368.5, "y": 426.0, "width": 77.5, "height": 11.5, "font_size": 10},

    # ---------------- INVESTIGACIÓN ----------------
    "marca_investigacion_bajo":   {"x": 229.5, "y": 412.5, "width": 65.5, "height": 11.5, "font_size": 10},
    "marca_investigacion_medio":  {"x": 298.0, "y": 412.5, "width": 67.5, "height": 11.0, "font_size": 10},
    "marca_investigacion_alto":   {"x": 368.0, "y": 412.5, "width": 78.0, "height": 12.5, "font_size": 10},
}


# =====================================================================
# PÁGINA 2 — POTENCIAL + ORACIÓN FINAL
# =====================================================================
CAMPOS_TEXTO_P2 = {

    # ---------- POTENCIAL EMPRESARIAL (BAJO/MEDIO/ALTO) ----------
    "potencial_puesto": {"x": 289.5, "y": 358.0, "width": 103.5, "height": 24.0, "font_size": 8, "alignment": 0},

    # ---------- HUECOS DE LA ORACIÓN FINAL ----------
    # Línea 1: "…dentro de los tipos ____ y ____."
    "campo_areas":      {"x": 163.0, "y": 228.0, "width": 170.0, "height": 8.0,  "font_size": 8},
    "campo_areas_2":    {"x": 363.0, "y": 228.0, "width": 175.0, "height": 8.5,  "font_size": 8},

    # Línea 2: "…como primera opción ____ y ____."
    "campo_carreras":   {"x": 163.0, "y": 209.0, "width": 170.0, "height": 10.0, "font_size": 8},
    "campo_carreras_2": {"x": 363.0, "y": 209.0, "width": 175.0, "height": 8.5,  "font_size": 8},
}