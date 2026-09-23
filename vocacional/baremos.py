"""
Baremación IEPPO según sexo.
Extraído de IEPPO!AI23:AO44 (mujeres) y AT23:AZ44 (varones).
Replica las fórmulas IF+SUM que usa el Excel.
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────
# TABLAS DE BAREMACIÓN
# puntaje_bruto → baremo
# ─────────────────────────────────────────────────────────────
_BAREMOS_MUJERES = {
    "LIDERAZGO":        {0:28, 1:30, 2:32, 3:34, 4:36, 5:38, 6:40, 7:42, 8:44, 9:46,
                         10:48, 11:50, 12:52, 13:54, 14:56, 15:58, 16:60, 17:62,
                         18:64, 19:66, 20:68, 21:71},
    "TÉCNICO MECÁNICO": {0:34, 1:38, 2:41, 3:44, 4:47, 5:51, 6:54, 7:57, 8:60, 9:64,
                         10:67, 11:70, 12:73, 13:77, 14:80},
    "SOCIAL":           {0:18, 1:21, 2:24, 3:27, 4:30, 5:33, 6:36, 7:40, 8:43, 9:46,
                         10:49, 11:52, 12:55, 13:59, 14:62, 15:65},
    "ORGANIZADO":       {0:30, 1:32, 2:34, 3:36, 4:38, 5:40, 6:41, 7:43, 8:45, 9:47,
                         10:49, 11:51, 12:53, 13:55, 14:57, 15:59, 16:61, 17:63,
                         18:65, 19:67, 20:69, 21:71},
    "ARTÍSTICO":        {0:25, 1:27, 2:30, 3:33, 4:35, 5:38, 6:40, 7:43, 8:45, 9:48,
                         10:50, 11:53, 12:56, 13:58, 14:61, 15:63, 16:66},
    "EMPRENDEDOR":      {0:23, 1:25, 2:27, 3:29, 4:31, 5:33, 6:35, 7:37, 8:39, 9:41,
                         10:43, 11:46, 12:48, 13:50, 14:52, 15:54, 16:56, 17:58,
                         18:60, 19:62, 20:65, 21:67},
    "INVESTIGATIVO":    {0:28, 1:31, 2:34, 3:37, 4:41, 5:44, 6:47, 7:50, 8:53, 9:56,
                         10:59, 11:62, 12:65},
}

_BAREMOS_VARONES = {
    "LIDERAZGO":        {0:30, 1:32, 2:34, 3:36, 4:38, 5:40, 6:42, 7:44, 8:46, 9:48,
                         10:50, 11:52, 12:54, 13:56, 14:58, 15:60, 16:62, 17:64,
                         18:66, 19:68, 20:70},
    "TÉCNICO MECÁNICO": {0:27, 1:30, 2:33, 3:36, 4:39, 5:41, 6:44, 7:47, 8:50, 9:53,
                         10:55, 11:58, 12:61, 13:64, 14:67},
    "SOCIAL":           {0:20, 1:30, 2:33, 3:36, 4:36, 5:41, 6:44, 7:47, 8:50, 9:53,
                         10:55, 11:58, 12:61, 13:64, 14:67, 15:70},
    "ORGANIZADO":       {0:29, 1:31, 2:33, 3:36, 4:38, 5:40, 6:42, 7:44, 8:46, 9:48,
                         10:50, 11:52, 12:54, 13:56, 14:58, 15:60, 16:62, 17:64,
                         18:66, 19:68, 20:70, 21:72},
    "ARTÍSTICO":        {0:29, 1:31, 2:34, 3:36, 4:39, 5:42, 6:44, 7:47, 8:49, 9:52,
                         10:54, 11:57, 12:60, 13:62, 14:65, 15:67, 16:70},
    "EMPRENDEDOR":      {0:23, 1:25, 2:27, 3:29, 4:32, 5:34, 6:36, 7:38, 8:40, 9:42,
                         10:44, 11:47, 12:49, 13:51, 14:53, 15:55, 16:57, 17:59,
                         18:62, 19:64, 20:66, 21:68},
    "INVESTIGATIVO":    {0:31, 1:34, 2:37, 3:40, 4:44, 5:47, 6:50, 7:53, 8:56, 9:59,
                         10:63, 11:66, 12:69},
}


def _lookup_baremo(tabla_tipo: dict, pd: int):
    """
    Replica la fórmula IF+SUM del Excel:
        IF(pd = 0, b0, 0) + IF(pd = 1, b1, 0) + ...
    Devuelve el baremo o None si pd está fuera de rango.
    """
    return tabla_tipo.get(pd, None)


def calcular_baremos(puntajes: dict, sexo: str) -> dict:
    """
    puntajes: {TIPO: {'PD': int, 'PD_E':..., 'PD_P':..., 'PD_H':...}}
    sexo: 'F' o 'M'
    Devuelve: {TIPO: {'PD': int, 'Baremo': int|None}}
    """
    tabla = _BAREMOS_MUJERES if sexo == "F" else _BAREMOS_VARONES

    resultado = {}
    for tipo, datos in puntajes.items():
        pd = datos["PD"] if isinstance(datos, dict) else int(datos)
        baremo = _lookup_baremo(tabla.get(tipo, {}), pd)
        resultado[tipo] = {
            "PD": pd,
            "Baremo": baremo,
        }
    return resultado


# ─────────────────────────────────────────────────────────────
# NIVEL DE CORRESPONDENCIA
# ─────────────────────────────────────────────────────────────
def nivel_correspondencia(baremo) -> str:
    """
    Replica las fórmulas de INFORME!X/Y/Z:
        Bajo  = IF(baremo <= 40, "X", " ")
        Medio = IF(baremo >= 60, " ", IF(baremo >= 41, "X", " "))
        Alto  = IF(baremo >= 60, "X", " ")
    """
    if baremo is None:
        return "sin_dato"
    if baremo <= 40:
        return "bajo"
    if baremo >= 60:
        return "alto"
    return "medio"  # 41-59