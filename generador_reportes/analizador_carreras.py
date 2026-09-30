# analizador_carreras.py
"""
Analiza las carreras que el alumno escribió a mano contra las
carreras sugeridas por el test.

IMPORTANTE: Todo el matching es CASE-INSENSITIVE y sin tildes.
  - "CIVIL"     → Ing Civil
  - "Civil"     → Ing Civil
  - "civil"     → Ing Civil
  - "ING CIVIL" → Ing Civil
  - "MOTOS"     → Mecánica Automotriz
  - "motos"     → Mecánica Automotriz

Sin LLM. Todo local. ~5ms por consulta.
"""
import os
import sys
import unicodedata
from difflib import SequenceMatcher

PADRE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PADRE not in sys.path:
    sys.path.insert(0, PADRE)

from vocacional.carreras import (
    CARRERAS,
    AFINIDAD,
    puntuar_afinidad,
    INDICE_TIPOS,
)


# ─────────────────────────────────────────────────────────────
# Umbrales
# ─────────────────────────────────────────────────────────────
UMBRAL_FUZZY = 0.72
AFINIDAD_ALTA = 10
AFINIDAD_MEDIA = 5


# ═════════════════════════════════════════════════════════════
# NORMALIZACIÓN (aquí se hace todo case-insensitive)
# ═════════════════════════════════════════════════════════════
def _sin_acentos(texto: str) -> str:
    """
    Convierte "Mecánica" → "mecanica", "INGENIERÍA" → "ingenieria".
    """
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin.lower().strip()   # ← .lower() hace todo minúscula


def _normalizar(texto: str) -> str:
    """
    Normaliza texto para comparación:
      - Pasa a minúsculas (CIVIL → civil, Civil → civil)
      - Quita tildes (Mecánica → mecanica)
      - Quita puntuación (.,;:!?()- → espacio)
      - Colapsa espacios múltiples

    Resultado SIEMPRE en minúsculas sin tildes.
    """
    t = _sin_acentos(texto)
    limpio = "".join(c if c.isalnum() or c == " " else " " for c in t)
    return " ".join(limpio.split())


# ═════════════════════════════════════════════════════════════
# ALIAS MANUALES
# Las CLAVES están TODAS en minúsculas, sin tildes.
# Como _normalizar() convierte la entrada a minúsculas sin tildes,
# la comparación funciona con cualquier caso.
# ═════════════════════════════════════════════════════════════
ALIAS_ESCRITOS = {
    # ═══════════════════════════════════════════════════════════
    # INGENIERÍAS
    # ═══════════════════════════════════════════════════════════
    "civil": "Ing Civil",
    "ing civil": "Ing Civil",
    "ingenieria civil": "Ing Civil",
    "ingeniero civil": "Ing Civil",

    "sistemas": "Ing de Sistemas",
    "sistema": "Ing de Sistemas",
    "ing sistemas": "Ing de Sistemas",
    "ing de sistemas": "Ing de Sistemas",
    "ingenieria de sistemas": "Ing de Sistemas",
    "ingenieria en sistemas": "Ing de Sistemas",
    "ingenieria sistemas": "Ing de Sistemas",
    "computacion": "Ing de Sistemas",
    "computacion e informatica": "Ing de Sistemas",

    "industrial": "Ing Industrial",
    "ing industrial": "Ing Industrial",
    "ingenieria industrial": "Ing Industrial",

    "mecanica": "Ing Mecánica",
    "mecanico": "Ing Mecánica",
    "ing mecanica": "Ing Mecánica",
    "ingenieria mecanica": "Ing Mecánica",
    "mecanica de mantenimiento": "Ing Mecánica",
    "mecanica industrial": "Ing Mecánica",

    "electrica": "Ing Eléctrica",
    "ing electrica": "Ing Eléctrica",
    "ingenieria electrica": "Ing Eléctrica",

    "electronica": "Ing Electrónica",
    "ing electronica": "Ing Electrónica",
    "ingenieria electronica": "Ing Electrónica",

    "ambiental": "Ing Ambiental",
    "ing ambiental": "Ing Ambiental",
    "ingenieria ambiental": "Ing Ambiental",
    "medio ambiente": "Ing Ambiental",

    "quimica": "Ing Química",
    "ing quimica": "Ing Química",
    "ingenieria quimica": "Ing Química",

    "minas": "Ing de Minas",
    "ing minas": "Ing de Minas",
    "ing de minas": "Ing de Minas",
    "ingenieria de minas": "Ing de Minas",
    "mineria": "Ing de Minas",

    "mecatronica": "Ing Mecatrónica",
    "ing mecatronica": "Ing Mecatrónica",
    "ingenieria mecatronica": "Ing Mecatrónica",
    "robotica": "Ing Mecatrónica",

    "automotriz": "Ing Automotriz",
    "ing automotriz": "Ing Automotriz",
    "ingenieria automotriz": "Ing Automotriz",

    "metalurgica": "Ing Metalúrgica",
    "ing metalurgica": "Ing Metalúrgica",
    "ingenieria metalurgica": "Ing Metalúrgica",

    "forestal": "Ing Forestal",
    "ing forestal": "Ing Forestal",
    "ingenieria forestal": "Ing Forestal",

    "sonido": "Ing de Sonido",
    "ing de sonido": "Ing de Sonido",
    "ingenieria de sonido": "Ing de Sonido",

    "alimentarias": "Ing de Industrias Alimentarias",
    "ing alimentarias": "Ing de Industrias Alimentarias",
    "ingenieria alimentaria": "Ing de Industrias Alimentarias",
    "industrias alimentarias": "Ing de Industrias Alimentarias",

    # ═══════════════════════════════════════════════════════════
    # MECÁNICA / MOTOS / VEHÍCULOS
    # ═══════════════════════════════════════════════════════════
    "moto": "Mecánica Automotriz",
    "motos": "Mecánica Automotriz",
    "motito": "Mecánica Automotriz",
    "motocicleta": "Mecánica Automotriz",
    "motocicletas": "Mecánica Automotriz",
    "mecanica automotriz": "Mecánica Automotriz",
    "mecanica de motos": "Mecánica Automotriz",
    "mecanica de autos": "Mecánica Automotriz",
    "motos automotriz": "Mecánica Automotriz",
    "moto automotriz": "Mecánica Automotriz",

    "carro": "Mecánica Automotriz",
    "carros": "Mecánica Automotriz",
    "auto": "Mecánica Automotriz",
    "autos": "Mecánica Automotriz",
    "vehiculo": "Mecánica Automotriz",
    "vehiculos": "Mecánica Automotriz",
    "motor": "Mecánica Automotriz",
    "motores": "Mecánica Automotriz",
    "taller": "Mecánica Automotriz",
    "taller de motos": "Mecánica Automotriz",
    "taller de autos": "Mecánica Automotriz",

    # ═══════════════════════════════════════════════════════════
    # SALUD
    # ═══════════════════════════════════════════════════════════
    "medicina": "Medicina",
    "medicina general": "Medicina",
    "medico": "Medicina",
    "medica": "Medicina",
    "doctor": "Medicina",
    "doctora": "Medicina",
    "dr": "Medicina",
    "dra": "Medicina",

    "enfermeria": "Enfermería",
    "enfermera": "Enfermería",
    "enfermero": "Enfermería",

    "psicologia": "Psicología",
    "psicologo": "Psicología",
    "psicologa": "Psicología",
    "psicologia clinica": "Psicología",

    "odontologia": "Odontología",
    "dentista": "Odontología",
    "odontologo": "Odontología",

    "nutricion": "Nutricionista",
    "nutricionista": "Nutricionista",
    "nutricion y dietetica": "Nutricionista",

    "veterinaria": "Veterinaria",
    "veterinario": "Veterinaria",
    "medicina veterinaria": "Veterinaria",

    "obstetricia": "Obstetricia",
    "obstetra": "Obstetricia",

    "farmacia": "Farmacia",
    "farmaceutico": "Farmacia",
    "quimico farmaceutico": "Farmacia",

    "tecnologia medica": "Tecnología Médica",
    "tec medica": "Tecnología Médica",
    "laboratorio clinico": "Tecnología Médica",

    "ciencias de la salud": "Ciencias de la Salud",

    # ═══════════════════════════════════════════════════════════
    # NEGOCIOS
    # ═══════════════════════════════════════════════════════════
    "administracion": "Administración",
    "admin": "Administración",
    "administracion de empresas": "Administración de Empresas",
    "administracion de negocios": "Administración",
    "gestion": "Administración",
    "gestion empresarial": "Administración",
    "gerencia": "Administración",

    "conta": "Contabilidad",
    "contabilidad": "Contabilidad",
    "contador": "Contabilidad",
    "contadora": "Contabilidad",
    "contaduria": "Contabilidad",

    "economia": "Economía",
    "economista": "Economía",

    "marketing": "Marketing",
    "mercadeo": "Marketing",
    "mercadotecnia": "Marketing",
    "ventas": "Marketing",
    "comercial": "Marketing",

    "negocios": "Negocios Internacionales",
    "negocios internacionales": "Negocios Internacionales",
    "comercio internacional": "Negocios Internacionales",
    "comercio exterior": "Negocios Internacionales",

    "finanzas": "Finanzas",
    "financiero": "Finanzas",
    "banca": "Finanzas",

    # ═══════════════════════════════════════════════════════════
    # TECNOLOGÍA
    # ═══════════════════════════════════════════════════════════
    "informatica": "Informática",
    "informatico": "Informática",
    "computacion e informatica": "Ing de Sistemas",
    "software": "Ing de Sistemas",
    "programacion": "Ing de Sistemas",
    "desarrollo de software": "Ing de Sistemas",
    "desarrollo web": "Ing de Sistemas",
    "programador": "Ing de Sistemas",

    "tec en informatica": "Tec en Informática",
    "tecnico en informatica": "Tec en Informática",
    "tecnico informatico": "Tec en Informática",

    # ═══════════════════════════════════════════════════════════
    # ARTE Y DISEÑO
    # ═══════════════════════════════════════════════════════════
    "diseno grafico": "Diseño Gráfico",
    "diseno": "Diseño Gráfico",
    "grafico": "Diseño Gráfico",
    "disenador grafico": "Diseño Gráfico",

    "diseno de interiores": "Diseño de Interiores",
    "interiores": "Diseño de Interiores",
    "diseno interior": "Diseño de Interiores",
    "decoracion de interiores": "Diseño de Interiores",

    "arquitectura": "Arquitectura",
    "arquitecto": "Arquitectura",
    "arquitecta": "Arquitectura",

    "musica": "Profesional Artístico Músico",
    "musico": "Profesional Artístico Músico",
    "cantante": "Profesional Artístico Músico",
    "canto": "Profesional Artístico Músico",

    "fotografia": "Fotografía",
    "fotografo": "Fotografía",
    "fotografa": "Fotografía",

    "actuacion": "Actuación",
    "actor": "Actuación",
    "actriz": "Actuación",
    "teatro": "Actuación",

    "pintura": "Dibujo y Pintura",
    "dibujo": "Dibujo y Pintura",
    "artes plasticas": "Artes Plásticas",
    "artes visuales": "Artes Visuales",

    "moda": "Diseño de Modas",
    "diseno de modas": "Diseño de Modas",
    "modas": "Diseño de Modas",

    "cosmetologia": "Cosmetología",
    "cosmetologa": "Cosmetología",
    "belleza": "Cosmetología",
    "estetica": "Cosmetología",

    "artes": "Artista Profesional",
    "artista": "Artista Profesional",
    "literatura": "Literatura",
    "escritor": "Literatura",

    # ═══════════════════════════════════════════════════════════
    # SOCIAL Y LEGAL
    # ═══════════════════════════════════════════════════════════
    "derecho": "Derecho Criminalística",
    "abogado": "Derecho Criminalística",
    "abogada": "Derecho Criminalística",
    "leyes": "Derecho Criminalística",
    "criminalistica": "Derecho Criminalística",
    "forense": "Derecho Criminalística",

    "educacion": "Educación",
    "educacion inicial": "Educación",
    "educacion primaria": "Educación",
    "educacion secundaria": "Educación",
    "profesor": "Educación",
    "profesora": "Educación",
    "maestro": "Educación",
    "maestra": "Educación",
    "docente": "Educación",
    "docencia": "Educación",
    "ensenanza": "Educación",

    "pedagogia": "Pedagogía",
    "pedagogo": "Pedagogía",

    "educacion artistica": "Educación Artística",

    "policia": "PNP",
    "pnp": "PNP",
    "policia nacional": "PNP",

    "militar": "Fuerzas Armadas",
    "soldado": "Fuerzas Armadas",
    "ejercito": "Fuerzas Armadas",
    "marina": "Fuerzas Armadas",
    "fuerzas armadas": "Fuerzas Armadas",
    "ffaa": "Fuerzas Armadas",

    "sociologia": "Sociología",
    "sociologo": "Sociología",

    "asistente social": "Asistente Social",
    "trabajo social": "Asistente Social",
    "trabajador social": "Asistente Social",

    "historia": "Historia",
    "historiador": "Historia",
    "antropologia": "Antropología",
    "arqueologia": "Arqueología",
    "filosofia": "Filosofía",
    "filosofo": "Filosofía",

    # ═══════════════════════════════════════════════════════════
    # COMUNICACIÓN
    # ═══════════════════════════════════════════════════════════
    "comunicacion": "C. Comunicación",
    "ciencias de la comunicacion": "C. Comunicación",
    "comunicacion social": "C. Comunicación",
    "periodismo": "C. Comunicación",
    "periodista": "C. Comunicación",

    "publicidad": "Publicidad",
    "publicista": "Publicidad",

    # ═══════════════════════════════════════════════════════════
    # TURISMO / AVIACIÓN
    # ═══════════════════════════════════════════════════════════
    "turismo": "Guía Oficial de Turismo",
    "guia de turismo": "Guía Oficial de Turismo",
    "guia oficial de turismo": "Guía Oficial de Turismo",
    "guia": "Guía Oficial de Turismo",
    "hoteleria": "Guía Oficial de Turismo",
    "hoteleria y turismo": "Guía Oficial de Turismo",

    "aviacion": "Aviación",
    "piloto": "Aviación",
    "piloto de avion": "Aviación",
    "piloto aviador": "Aviación",

    "auxiliar de vuelo": "Auxiliar de Vuelo",
    "azafata": "Auxiliar de Vuelo",
    "aeromoza": "Auxiliar de Vuelo",

    # ═══════════════════════════════════════════════════════════
    # ALIMENTOS
    # ═══════════════════════════════════════════════════════════
    "gastronomia": "Gastronomía",
    "cocina": "Gastronomía",
    "chef": "Gastronomía",
    "cocinero": "Gastronomía",

    "reposteria": "Gastronomía/Repostería",
    "pasteleria": "Gastronomía/Repostería",

    "industria alimentaria": "Industria Alimentaria",
    "alimentos": "Industria Alimentaria",

    # ═══════════════════════════════════════════════════════════
    # AGRO / CIENCIA
    # ═══════════════════════════════════════════════════════════
    "agronomia": "Agronomía",
    "agronomo": "Agronomía",
    "agro": "Agronomía",
    "agricultura": "Agronomía",

    "zootecnia": "Zootecnia",
    "zootecnista": "Zootecnia",
    "ganaderia": "Zootecnia",

    "biologia": "Biología",
    "biologo": "Biología",
    "biologa": "Biología",

    "quimica pura": "Química",
    "quimico": "Química",

    "fisica": "Física",
    "fisico": "Física",

    "matematica": "Matemática",
    "matematicas": "Matemática",
    "matematico": "Matemática",

    "estadistica": "Estadística",
    "estadistico": "Estadística",

    "astronomia": "Astronomía",
    "astronomo": "Astronomía",

    "laboratorio": "Tec en Laboratorio",
    "tecnico de laboratorio": "Tec en Laboratorio",

    # ═══════════════════════════════════════════════════════════
    # INDUSTRIAL / TÉCNICOS
    # ═══════════════════════════════════════════════════════════
    "soldadura": "Soldadura Industrial",
    "soldadura industrial": "Soldadura Industrial",
    "soldador": "Soldadura Industrial",

    "maquinaria pesada": "Operador de Maquinarias Pesadas",
    "operador de maquinaria": "Operador de Maquinarias Pesadas",

    "topografia": "Topografía",
    "topografo": "Topografía",

    "metalurgia": "Metalúrgica",
    "mecatronica tecnico": "Mecatrónica",
}


# ═════════════════════════════════════════════════════════════
# ÍNDICES PRECOMPUTADOS
# ═════════════════════════════════════════════════════════════
_INDICES = None


def _construir_indices():
    # 1. Todas las carreras únicas
    todas = set()
    for tipo, carreras in CARRERAS.items():
        for c in carreras:
            todas.add(c)

    # 2. Nombre normalizado → nombre original
    nombre_canonico = {}
    for c in todas:
        nombre_canonico[_normalizar(c)] = c

    # 3. keyword → carreras (desde afinidad.json)
    palabras_clave = AFINIDAD.get("palabras_clave", {})
    keyword_a_carreras = {}
    for carrera, kws in palabras_clave.items():
        if carrera not in todas:
            continue
        for kw in kws:
            kw_norm = _normalizar(kw)
            if not kw_norm:
                continue
            keyword_a_carreras.setdefault(kw_norm, [])
            if carrera not in keyword_a_carreras[kw_norm]:
                keyword_a_carreras[kw_norm].append(carrera)

    # 4. token → carreras
    token_a_carreras = {}
    for c in todas:
        for token in _normalizar(c).split():
            if len(token) >= 4:
                token_a_carreras.setdefault(token, [])
                if c not in token_a_carreras[token]:
                    token_a_carreras[token].append(c)

    return {
        "todas": todas,
        "nombre_canonico": nombre_canonico,
        "keyword_a_carreras": keyword_a_carreras,
        "token_a_carreras": token_a_carreras,
    }


def _get_indices():
    global _INDICES
    if _INDICES is None:
        _INDICES = _construir_indices()
    return _INDICES


# ═════════════════════════════════════════════════════════════
# BÚSQUEDA (case-insensitive)
# ═════════════════════════════════════════════════════════════
def _buscar_carrera(texto: str):
    """
    Devuelve el nombre canónico de una carrera.

    Todo el matching usa _normalizar() (minúsculas + sin tildes).
    Por eso "CIVIL", "Civil" y "civil" dan EXACTAMENTE el mismo resultado.
    """
    if not texto or not texto.strip():
        return None

    idx = _get_indices()
    texto_norm = _normalizar(texto)

    # ─── 1. Alias manual ───
    if texto_norm in ALIAS_ESCRITOS:
        canonico = ALIAS_ESCRITOS[texto_norm]
        if canonico in idx["todas"]:
            return canonico

    # ─── 2. Alias con plural/singular ───
    variantes = []
    if texto_norm.endswith("es") and len(texto_norm) > 4:
        variantes.append(texto_norm[:-2])
    if texto_norm.endswith("s") and len(texto_norm) > 3:
        variantes.append(texto_norm[:-1])
    variantes.append(texto_norm + "s")

    for v in variantes:
        if v in ALIAS_ESCRITOS:
            canonico = ALIAS_ESCRITOS[v]
            if canonico in idx["todas"]:
                return canonico

    # ─── 3. Match exacto contra nombres ───
    if texto_norm in idx["nombre_canonico"]:
        return idx["nombre_canonico"][texto_norm]

    # ─── 4. Match exacto contra keyword ───
    if texto_norm in idx["keyword_a_carreras"]:
        candidatos = idx["keyword_a_carreras"][texto_norm]
        return min(candidatos, key=len)

    # ─── 5. Token: palabra del texto matchea token del nombre ───
    tokens_texto = [t for t in texto_norm.split() if len(t) >= 4]
    if tokens_texto:
        candidatos_token = {}
        for t in tokens_texto:
            for c in idx["token_a_carreras"].get(t, []):
                candidatos_token[c] = candidatos_token.get(c, 0) + 1

        if candidatos_token:
            mejor = sorted(
                candidatos_token.items(),
                key=lambda x: (-x[1], len(x[0])),
            )[0]
            return mejor[0]

    # ─── 6. Substring controlado ───
    if len(texto_norm) >= 4:
        for nombre_norm, nombre_orig in idx["nombre_canonico"].items():
            if texto_norm in nombre_norm.split():
                return nombre_orig

    # ─── 7. Fuzzy final ───
    if len(texto_norm) < 4:
        return None

    mejor = None
    for c in idx["todas"]:
        c_norm = _normalizar(c)
        sim = SequenceMatcher(None, texto_norm, c_norm).ratio()

        for palabra in c_norm.split():
            if len(palabra) >= 5:
                sim_p = SequenceMatcher(None, texto_norm, palabra).ratio()
                if sim_p > sim:
                    sim = sim_p

        if sim >= UMBRAL_FUZZY and (mejor is None or sim > mejor[1]):
            mejor = (c, sim)

    if mejor:
        return mejor[0]

    return None


# ─────────────────────────────────────────────────────────────
# Afinidad
# ─────────────────────────────────────────────────────────────
def _afinidad_entre_carreras(carrera_escrita, carrera_test,
                              tipos_escritos, tipos_test):
    mejor = None
    for tipo_esc in tipos_escritos:
        for tipo_test in tipos_test:
            pts, rel = puntuar_afinidad(
                carrera_escrita, carrera_test,
                tipo_esc, tipo_test,
            )
            if mejor is None or pts > mejor["puntaje"]:
                mejor = {
                    "puntaje": pts,
                    "relacion": rel,
                    "tipo_escrito": tipo_esc,
                    "tipo_test": tipo_test,
                }
    return mejor


def _veredicto(afinidad: int) -> str:
    if afinidad >= AFINIDAD_ALTA:
        return "alta"
    if afinidad >= AFINIDAD_MEDIA:
        return "media"
    return "baja"


# ─────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────
def analizar_carreras_escritas(carreras_escritas, carreras_test):
    """
    Analiza cada carrera escrita contra las carreras sugeridas por el test.

    IMPORTANTE: las carreras del test vienen en MAYÚSCULAS (del PDF).
    Aquí se normalizan a su forma canónica antes de buscar sus tipos.

    Cada resultado incluye "afinidad_alta" (bool) que indica si la
    carrera escrita tiene afinidad >= AFINIDAD_ALTA con alguna del test.
    Esto se usa en la app para ofrecer incluirla en el informe final.
    """
    resultados = []

    # ─── 1. NORMALIZAR las carreras del test ───
    carreras_test_norm = []
    for ct in carreras_test:
        if not ct or not ct.strip():
            continue
        canonico = _buscar_carrera(ct)
        if canonico:
            carreras_test_norm.append(canonico)

    # ─── 2. Analizar cada carrera escrita ───
    for escrita in carreras_escritas:
        # Caja vacía
        if not escrita or not escrita.strip():
            resultados.append({
                "carrera_escrita": "",
                "estado": "vacio",
                "veredicto": None,
                "afinidad_alta": False,
            })
            continue

        # Normalizar a nombre canónico
        canonico = _buscar_carrera(escrita)
        if not canonico:
            resultados.append({
                "carrera_escrita": escrita,
                "estado": "no_reconocida",
                "veredicto": "desconocida",
                "afinidad_alta": False,
            })
            continue

        # Tipos vocacionales de la carrera escrita
        tipos_escritos = INDICE_TIPOS.get(canonico, [])

        if not tipos_escritos:
            resultados.append({
                "carrera_escrita": escrita,
                "carrera_canonica": canonico,
                "estado": "sin_match",
                "veredicto": "baja",
                "afinidad_alta": False,
                "motivo": f"'{canonico}' no tiene tipos asignados",
            })
            continue

        # Comparar contra las carreras del test YA normalizadas
        mejor_match = None
        for ct_canonico in carreras_test_norm:
            tipos_test = INDICE_TIPOS.get(ct_canonico, [])
            if not tipos_test:
                continue

            af = _afinidad_entre_carreras(
                canonico, ct_canonico,
                tipos_escritos, tipos_test,
            )
            if af is None:
                continue

            if mejor_match is None or af["puntaje"] > mejor_match["puntaje"]:
                mejor_match = {
                    "carrera_test": ct_canonico,
                    "puntaje": af["puntaje"],
                    "relacion": af["relacion"],
                }

        # Sin match
        if mejor_match is None:
            resultados.append({
                "carrera_escrita": escrita,
                "carrera_canonica": canonico,
                "afinidad": 0,
                "carrera_test_relacionada": "",
                "relacion": "",
                "estado": "sin_match",
                "veredicto": "baja",
                "afinidad_alta": False,
                "motivo": "las carreras del test no matchean con esta",
            })
            continue

        # Con match → agregar resultado
        puntaje = mejor_match["puntaje"]
        resultados.append({
            "carrera_escrita": escrita,
            "carrera_canonica": canonico,
            "afinidad": puntaje,
            "carrera_test_relacionada": mejor_match["carrera_test"],
            "relacion": mejor_match["relacion"],
            "estado": "analizada",
            "veredicto": _veredicto(puntaje),
            "afinidad_alta": puntaje >= AFINIDAD_ALTA,   # ← NUEVO CAMPO
        })

    return resultados


# ─────────────────────────────────────────────────────────────
# Prueba:  python analizador_carreras.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pruebas = [
        "CIVIL", "ING CIVIL", "MOTOS", "MOTO", "DOCTOR", "CARRO",
        "MECANICA AUTOMOTRIZ", "ENFERMERA", "ABOGADO", "PSICOLOGO",
        "ING MECANICA", "INGENIERIA CIVIL", "DISENO GRAFICO",
        "civil", "ing civil", "motos", "moto", "doctor", "carro",
        "mecanica automotriz", "enfermera", "abogado", "psicologo",
        "ing mecanica", "ingenieria civil", "diseno grafico",
        "Civil", "Ing Civil", "Motos", "Doctor", "Mecanica",
        "Abogado", "Conta", "Sistemas", "Cocina", "Chef",
        "Arquitecto", "Policia", "Profesor", "Maestro", "Musica",
        "Mecánica", "Ingeniería Civil", "Psicología", "Música",
        "Odontología", "Matemática", "Química",
    ]

    print("=" * 70)
    print("PRUEBA DE RECONOCIMIENTO (case-insensitive + sin tildes)")
    print("=" * 70)

    ok = 0
    fail = 0
    for texto in pruebas:
        canonico = _buscar_carrera(texto)
        if canonico:
            print(f"  {texto:30s} → {canonico}")
            ok += 1
        else:
            print(f"  {texto:30s} → ❌ NO RECONOCIDA")
            fail += 1

    print("=" * 70)
    print(f"Reconocidas: {ok} | No reconocidas: {fail} | Total: {len(pruebas)}")
    print("=" * 70)

    # Prueba de análisis con carreras del test en MAYÚSCULAS
    print("\n" + "=" * 70)
    print("PRUEBA DE ANÁLISIS CON CARRERAS DEL TEST EN MAYÚSCULAS")
    print("=" * 70)
    escritas = ["Ing CIVIL", "CIVIL", "COCINA", "DOCTOR"]
    carreras_test = ["DISEÑO DE INTERIORES", "ARQUITECTURA"]
    print(f"Escritas:      {escritas}")
    print(f"Carreras test: {carreras_test}\n")
    for r in analizar_carreras_escritas(escritas, carreras_test):
        print(f"  '{r.get('carrera_escrita', ''):15s}' → "
              f"estado={r.get('estado'):15s} "
              f"canon='{r.get('carrera_canonica', ''):25s}' "
              f"afinidad={r.get('afinidad', '-'):>3} "
              f"alta={r.get('afinidad_alta')} "
              f"veredicto={r.get('veredicto', '')}")
    print("=" * 70)