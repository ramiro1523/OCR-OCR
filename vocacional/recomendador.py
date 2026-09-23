"""
Sistema experto de recomendación de carreras.

NO usa ML. NO usa internet. TODO local.
Recursos: ~40 KB RAM para 50 carreras, carga <50ms, query ~3ms.

Diseño:
  - Índices precomputados al cargar (alias, keywords invertidos).
  - Fast path O(1) para alias/keywords exactos.
  - Token-overlap como segundo nivel (O(tokens), no O(carreras)).
  - Expansión semántica con jerga y variantes coloquiales.
  - Fuzzy matching SOLO como último recurso, y solo contra los
    top-N candidatos ya filtrados, no contra todo el catálogo.
  - numpy para similitud coseno (vectorizado).

"IA sin IA" hecha liviana.
"""

import functools
import json
import logging
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

RUTA_CATALOGO = "vocacional/data/catalogo_carreras.json"

# --- Umbrales de matching ---
UMBRAL_EXACTO = 1.0              # alias/keyword exacto
UMBRAL_TOKEN_OVERLAP = 0.34      # 2 de 6 tokens en común
UMBRAL_FUZZY_ALIAS = 0.85        # fuzzy solo si el resto falla
UMBRAL_FUZZY_KEYWORD = 0.78
MAX_FUZZY_CANDIDATOS = 8         # fuzzy solo contra los top-8 por tokens

# --- Pesos de la decisión final ---
PESO_TEST = 0.55
PESO_USUARIO = 0.30
PESO_CONTEXTO = 0.15

# --- Umbrales de interpretación ---
AFINIDAD_MINIMA_CONFIANZA = 0.60  # por debajo → alerta_conflicto
COHERENCIA_BAJA = 0.55
COHERENCIA_ALTA = 0.80

# --- Cache de resultados (LRU 256) ---
CACHE_SIZE_RECOMENDACIONES = 256


# =============================================================================
# NORMALIZACIÓN RÁPIDA
# =============================================================================

# Tabla de traducción de acentos precomputada (mucho más rápido que NFD)
_TRADUCCION_ACENTOS = str.maketrans(
    "áàäâãéèëêíìïîóòöôõúùüûñçÁÀÄÂÃÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇ",
    "aaaaaeeeeiiiiooooouuuuncAAAAAEEEEIIIIOOOOOUUUUNC",
)


# =============================================================================
# STEMMER ESPAÑOL SIMPLE
# =============================================================================

def _stem_es(token: str) -> str:
    """
    Reduce plurales simples del español.

    "motos"  → "moto"
    "libros" → "libro"
    "lápices" no aplica (se queda igual por longitud)
    """
    if len(token) <= 3:
        return token
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token


# =============================================================================
# EXPANSIÓN SEMÁNTICA
# =============================================================================
# Mapea tokens coloquiales (verbos, sustantivos de acción, jerga) a keywords
# que SÍ están en el catálogo. Ej: "corredor" → atletismo, deporte, carreras.
# Cada entrada es un puente entre lo que dice el alumno y lo que hay en el
# catálogo. Si agregas carreras nuevas, revisa esta tabla.

EXPANSION_SEMANTICA = {
    # -------------------------------------------------------------------------
    # Deportes y cuerpo
    # -------------------------------------------------------------------------
    "corredor":  ["atletismo", "deporte", "automovilismo", "carreras"],
    "correr":    ["atletismo", "deporte", "carreras"],
    "corredora": ["atletismo", "deporte", "automovilismo"],
    "atleta":    ["atletismo", "deporte", "entrenamiento"],
    "futbol":    ["educacion fisica", "deporte", "entrenamiento"],
    "futbolista": ["educacion fisica", "deporte"],
    "entrenar":  ["educacion fisica", "entrenamiento", "deporte"],
    "gimnasio":  ["educacion fisica", "entrenamiento", "deporte"],
    "entrenador": ["educacion fisica", "entrenamiento", "deporte"],

    # -------------------------------------------------------------------------
    # Motores y transporte
    # -------------------------------------------------------------------------
    "moto":      ["mecanica", "automotriz", "vehiculo"],
    "motos":     ["mecanica", "automotriz", "vehiculo"],
    "carro":     ["mecanica", "automotriz", "vehiculo"],
    "carros":    ["mecanica", "automotriz", "vehiculo"],
    "auto":      ["mecanica", "automotriz", "vehiculo"],
    "autos":     ["mecanica", "automotriz", "vehiculo"],
    "piloto":    ["aviacion", "automovilismo", "maritimo"],
    "camion":    ["mecanica", "automotriz", "transporte"],
    "camiones":  ["mecanica", "automotriz", "transporte"],
    "motor":     ["mecanica", "automotriz"],
    "motores":   ["mecanica", "automotriz"],

    # -------------------------------------------------------------------------
    # Salud y cuidado
    # -------------------------------------------------------------------------
    "curar":     ["medicina", "salud", "enfermeria"],
    "curandero": ["medicina", "salud"],
    "cuidar":    ["enfermeria", "salud", "psicologia"],
    "enfermo":   ["medicina", "enfermeria", "salud"],
    "enfermos":  ["medicina", "enfermeria", "salud"],
    "hospital":  ["medicina", "enfermeria", "salud"],
    "terapia":   ["psicologia", "salud"],
    "mente":     ["psicologia", "salud"],

    # -------------------------------------------------------------------------
    # Arte y creatividad
    # -------------------------------------------------------------------------
    "dibujar":   ["diseno", "arte", "ilustracion"],
    "dibujo":    ["diseno", "arte", "ilustracion"],
    "pintar":    ["arte", "diseno", "ilustracion"],
    "pintura":   ["arte", "diseno"],
    "crear":     ["arte", "diseno", "arquitectura"],
    "creativo":  ["arte", "diseno", "publicidad"],
    "musica":    ["musica", "artes", "sonido"],
    "cancion":   ["musica", "artes"],
    "canciones": ["musica", "artes"],
    "cantar":    ["musica", "artes"],
    "instrumento": ["musica", "artes"],

    # -------------------------------------------------------------------------
    # Tecnología
    # -------------------------------------------------------------------------
    "computadora":  ["sistemas", "informatica", "software"],
    "computadoras": ["sistemas", "informatica", "software"],
    "computador":   ["sistemas", "informatica", "software"],
    "programar":    ["sistemas", "software", "programacion"],
    "programa":     ["sistemas", "software", "programacion"],
    "codigo":       ["sistemas", "software", "programacion"],
    "app":          ["sistemas", "software"],
    "celular":      ["sistemas", "electronica", "telecomunicaciones"],
    "internet":     ["sistemas", "redes", "telecomunicaciones"],

    # -------------------------------------------------------------------------
    # Construcción
    # -------------------------------------------------------------------------
    "construir":    ["arquitectura", "construccion", "ingenieria civil"],
    "construccion": ["arquitectura", "construccion", "ingenieria civil"],
    "casa":         ["arquitectura", "construccion"],
    "edificio":     ["arquitectura", "construccion"],
    "planos":       ["arquitectura", "construccion", "dibujo tecnico"],

    # -------------------------------------------------------------------------
    # Negocios y sociedad
    # -------------------------------------------------------------------------
    "vender":     ["administracion", "marketing", "negocios"],
    "ventas":     ["administracion", "marketing", "negocios"],
    "emprender":  ["administracion", "negocios", "gestion"],
    "empresa":    ["administracion", "negocios", "gestion"],
    "gerente":    ["administracion", "negocios"],
    "plata":      ["contabilidad", "finanzas", "administracion"],
    "dinero":     ["contabilidad", "finanzas", "administracion"],
    "numeros":    ["contabilidad", "matematica", "finanzas"],
    "leyes":      ["derecho", "abogado"],
    "defender":   ["derecho", "abogado"],
    "justicia":   ["derecho", "abogado"],
    "ninos":      ["educacion", "pedagogia"],
    "ninas":      ["educacion", "pedagogia"],
    "ensenar":    ["educacion", "pedagogia", "profesor"],
    "enseno":     ["educacion", "pedagogia"],
    "profesor":   ["educacion", "pedagogia"],
    "maestro":    ["educacion", "pedagogia"],

    # -------------------------------------------------------------------------
    # Naturaleza y animales
    # -------------------------------------------------------------------------
    "animales":   ["veterinaria", "biologia", "agronomia"],
    "animal":     ["veterinaria", "biologia", "agronomia"],
    "plantas":    ["agronomia", "biologia"],
    "cultivar":   ["agronomia", "agricultura"],
    "campo":      ["agronomia", "agricultura", "veterinaria"],
    "naturaleza": ["biologia", "agronomia", "ambiental"],

    # -------------------------------------------------------------------------
    # Cocina
    # -------------------------------------------------------------------------
    "cocinar":     ["cocina", "gastronomia", "chef"],
    "cocina":      ["cocina", "gastronomia", "chef"],
    "chef":        ["cocina", "gastronomia", "chef"],
    "recetas":     ["cocina", "gastronomia"],
    "restaurante": ["cocina", "gastronomia", "administracion"],

    # =========================================================================
    # AMPLIACIÓN: JERGA PERUANA Y VARIANTES COLOQUIALES
    # =========================================================================

    # -------------------------------------------------------------------------
    # Jerga Perú
    # -------------------------------------------------------------------------
    "chamba":    ["administracion", "negocios"],
    "pata":      ["negocios", "administracion"],   # "hacer la pata" = ganar dinero
    "jato":      ["arquitectura", "construccion"], # casa

    # -------------------------------------------------------------------------
    # Variantes de transporte
    # -------------------------------------------------------------------------
    "motocicleta":  ["mecanica", "automotriz", "vehiculo"],
    "motocicletas": ["mecanica", "automotriz", "vehiculo"],
    "scooter":      ["mecanica", "automotriz", "vehiculo"],
    "cuatrimoto":   ["mecanica", "automotriz", "vehiculo"],
    "bici":         ["mecanica", "deporte"],
    "bicicleta":    ["mecanica", "deporte"],

    # -------------------------------------------------------------------------
    # Variantes de salud
    # -------------------------------------------------------------------------
    "doctor":    ["medicina", "salud"],
    "doctora":   ["medicina", "salud"],
    "enfermera": ["enfermeria", "salud"],
    "enfermero": ["enfermeria", "salud"],
    "psicologo": ["psicologia", "salud"],
    "terapeuta": ["psicologia", "salud"],

    # -------------------------------------------------------------------------
    # Variantes de computación
    # -------------------------------------------------------------------------
    "pc":       ["sistemas", "informatica"],
    "laptop":   ["sistemas", "informatica"],
    "software": ["sistemas", "informatica"],
    "hardware": ["sistemas", "electronica"],
    "robotica": ["sistemas", "electronica", "mecatronica"],

    # -------------------------------------------------------------------------
    # Variantes de arte
    # -------------------------------------------------------------------------
    "disenar":    ["diseno", "arte", "arquitectura"],
    "dibujante":  ["diseno", "arte", "ilustracion"],
    "artista":    ["arte", "musica", "diseno"],
    "fotografia": ["diseno", "artes visuales", "comunicacion"],

    # -------------------------------------------------------------------------
    # Variantes de educación
    # -------------------------------------------------------------------------
    "docente":  ["educacion", "pedagogia"],
    "docencia": ["educacion", "pedagogia"],
    "colegio":  ["educacion", "pedagogia"],
}


def _expandir_tokens(tokens: List[str]) -> List[str]:
    """
    Expande una lista de tokens con asociaciones semánticas.
    Ej: ["corredor", "motos"] → ["corredor", "motos", "atletismo",
        "deporte", "automovilismo", "carreras", "mecanica", ...]

    Liviano: solo consulta un dict. Sin fuzzy, sin loops costosos.
    """
    expandidos = set()
    for t in tokens:
        expandidos.add(t)
        stem = _stem_es(t)
        expandidos.add(stem)

        # Buscar tanto la forma original como el stem en la tabla
        for forma in (t, stem, stem + "s"):
            if forma in EXPANSION_SEMANTICA:
                expandidos.update(EXPANSION_SEMANTICA[forma])

    return list(expandidos)


def normalizar(texto: str) -> str:
    """
    Normaliza texto: minúsculas, sin acentos, sin caracteres raros.
    Usa str.translate (C-level) en vez de NFD (Python-level).

    ~15x más rápido que unicodedata.normalize.
    """
    if not texto:
        return ""
    # Translate acentos + lower + strip en una sola pasada
    texto = texto.translate(_TRADUCCION_ACENTOS).lower().strip()
    # Solo deja alfanuméricos y espacios
    texto = "".join(c if c.isalnum() or c == " " else " " for c in texto)
    # Colapsa espacios
    return " ".join(texto.split())


# =============================================================================
# CATÁLOGO CON ÍNDICES PRECOMPUTADOS
# =============================================================================

class CatalogoCarreras:
    """
    Catálogo con índices precomputados para búsqueda O(1).

    Estructuras internas:
      - self.carreras: lista de dicts completos
      - self.riasec_matrix: numpy (n_carreras, 6) para coseno rápido
      - self.alias_index: {alias_normalizado: carrera_idx}
      - self.keyword_index: {token: [carrera_idx, ...]}
      - self.frase_keyword_index: {keyword_entera: [carrera_idx]}
    """

    __slots__ = (
        "ruta", "carreras", "riasec_matrix",
        "alias_index", "keyword_index", "frase_keyword_index",
        "_cargado",
    )

    def __init__(self, ruta: str = RUTA_CATALOGO):
        self.ruta = ruta
        self.carreras: List[Dict] = []
        self.riasec_matrix: Optional[np.ndarray] = None
        self.alias_index: Dict[str, int] = {}
        self.keyword_index: Dict[str, List[int]] = {}
        self.frase_keyword_index: Dict[str, List[int]] = {}
        self._cargado = False

    def cargar(self) -> bool:
        """Carga el catálogo y precomputa todos los índices."""
        if self._cargado:
            return True

        ruta = Path(self.ruta)
        if not ruta.exists():
            logger.error("Catálogo no encontrado: %s", ruta)
            return False

        with open(ruta, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw = data.get("carreras", [])
        if not raw:
            logger.error("Catálogo vacío.")
            return False

        perfiles = []

        for idx, c in enumerate(raw):
            # Pre-normalizar campos de texto
            c["_norm_nombre"] = normalizar(c["nombre"])
            c["_norm_alias"] = [normalizar(a) for a in c.get("alias", [])]
            c["_norm_keywords"] = [normalizar(k) for k in c.get("keywords", [])]

            # Normalizar nivel / institución a sets para O(1) lookup
            nivel = c.get("nivel", [])
            c["_nivel_set"] = set(nivel if isinstance(nivel, list) else [nivel])
            inst = c.get("institucion", [])
            c["_inst_set"] = set(inst if isinstance(inst, list) else [inst])

            # Perfil RIASEC como array
            perfil = c.get("perfil_riasec", [0] * 6)
            perfiles.append(perfil)

            # Índice de alias → idx
            for alias_norm in c["_norm_alias"]:
                self.alias_index[alias_norm] = idx
            # El nombre también actúa como alias exacto
            self.alias_index[c["_norm_nombre"]] = idx

            # Índice invertido de keywords (token → carreras)
            for kw_norm in c["_norm_keywords"]:
                # Como frase completa
                self.frase_keyword_index.setdefault(kw_norm, []).append(idx)
                # Como tokens individuales (para overlap parcial)
                for token in kw_norm.split():
                    if len(token) < 3:
                        continue
                    self.keyword_index.setdefault(token, [])
                    if idx not in self.keyword_index[token]:
                        self.keyword_index[token].append(idx)

            self.carreras.append(c)

        # Matriz RIASEC numpy (n, 6) con normas precalculadas
        self.riasec_matrix = np.array(perfiles, dtype=np.float32)
        # Pre-normalizar filas para que el coseno sea solo producto punto
        normas = np.linalg.norm(self.riasec_matrix, axis=1, keepdims=True)
        normas[normas < 1e-9] = 1.0
        self.riasec_matrix = self.riasec_matrix / normas

        self._cargado = True
        logger.info(
            "Catálogo cargado: %d carreras, %d alias, %d tokens",
            len(self.carreras),
            len(self.alias_index),
            len(self.keyword_index),
        )
        return True

    # -------------------------------------------------------------------------
    # BÚSQUEDA EN 3 NIVELES (fast → slow)
    # -------------------------------------------------------------------------

    def buscar(self, texto_usuario: str, top_k: int = 3) -> List[Tuple[int, float]]:
        """
        Devuelve lista de (carrera_idx, score) ordenada por score.

        Nivel 1: exacto contra alias_index → O(1)
        Nivel 2: token overlap + expansión semántica → O(tokens)
        Nivel 3: fuzzy contra top-N candidatos del nivel 2 → O(top_n)
        """
        if not self._cargado:
            return []

        texto_norm = normalizar(texto_usuario)
        if not texto_norm:
            return []

        # --- Nivel 1: match exacto ---
        if texto_norm in self.alias_index:
            idx = self.alias_index[texto_norm]
            return [(idx, 1.0)]

        # --- Nivel 2: token overlap CON expansión semántica ---
        tokens_originales = [t for t in texto_norm.split() if len(t) >= 3]
        if not tokens_originales:
            # Texto muy corto: probamos fuzzy directo contra todo
            return self._buscar_fuzzy(texto_norm, range(len(self.carreras)), top_k)

        # Expande con jerga y variantes antes de buscar
        tokens_expandidos = _expandir_tokens(tokens_originales)

        candidatos_score: Dict[int, float] = {}

        for token in tokens_expandidos:
            for idx in self.keyword_index.get(token, ()):
                candidatos_score[idx] = candidatos_score.get(idx, 0.0) + 1.0

        # Bonus: frase exacta en frase_keyword_index
        for idx in self.frase_keyword_index.get(texto_norm, ()):
            candidatos_score[idx] = candidatos_score.get(idx, 0.0) + 2.0

        if candidatos_score:
            # Normaliza por cantidad de tokens ORIGINALES (no expandidos)
            # para no penalizar al usuario por la expansión.
            n_tokens = max(1, len(tokens_originales))
            for idx in candidatos_score:
                candidatos_score[idx] /= n_tokens

            ordenados = sorted(
                candidatos_score.items(), key=lambda x: x[1], reverse=True
            )

            # Si el mejor supera UMBRAL_TOKEN_OVERLAP, devolvemos ya
            if ordenados[0][1] >= UMBRAL_TOKEN_OVERLAP:
                return ordenados[:top_k]

            # Si no, guardamos para el nivel 3
            mejores_token = ordenados[:MAX_FUZZY_CANDIDATOS]
        else:
            mejores_token = []

        # --- Nivel 3: fuzzy SOLO contra los top candidatos ---
        if mejores_token:
            candidatos_fuzzy = [idx for idx, _ in mejores_token]
        else:
            candidatos_fuzzy = list(range(len(self.carreras)))

        return self._buscar_fuzzy(texto_norm, candidatos_fuzzy, top_k)

    def _buscar_fuzzy(
        self, texto_norm: str, indices, top_k: int
    ) -> List[Tuple[int, float]]:
        """Fuzzy contra un subset de carreras. Devuelve (idx, score)."""
        resultados: List[Tuple[int, float]] = []
        for idx in indices:
            c = self.carreras[idx]
            mejor_sim = 0.0

            # Nombre
            sim = SequenceMatcher(None, texto_norm, c["_norm_nombre"]).ratio()
            if sim > mejor_sim:
                mejor_sim = sim

            # Alias
            for alias_norm in c["_norm_alias"]:
                sim = SequenceMatcher(None, texto_norm, alias_norm).ratio()
                if sim > mejor_sim:
                    mejor_sim = sim
                    if sim >= UMBRAL_FUZZY_ALIAS:
                        break

            # Keywords (frases)
            for kw in c["_norm_keywords"]:
                sim = SequenceMatcher(None, texto_norm, kw).ratio()
                if sim > mejor_sim:
                    mejor_sim = sim

            if mejor_sim >= UMBRAL_FUZZY_KEYWORD:
                resultados.append((idx, mejor_sim * 0.9))

        resultados.sort(key=lambda x: x[1], reverse=True)
        return resultados[:top_k]

    # -------------------------------------------------------------------------
    # COSENO VECTORIZADO
    # -------------------------------------------------------------------------

    def afinidad_con_perfil(self, perfil_test: np.ndarray) -> np.ndarray:
        """
        Devuelve array (n_carreras,) con la similitud coseno entre el
        perfil del test y cada carrera. Vectorizado con numpy.
        """
        if self.riasec_matrix is None or len(self.riasec_matrix) == 0:
            return np.zeros(0, dtype=np.float32)

        perfil = np.asarray(perfil_test, dtype=np.float32)
        norma = np.linalg.norm(perfil)
        if norma < 1e-9:
            return np.zeros(len(self.riasec_matrix), dtype=np.float32)

        return self.riasec_matrix @ (perfil / norma)


# =============================================================================
# CACHÉ DE CATÁLOGO (singleton)
# =============================================================================

_CATALOGO_SINGLETON: Optional[CatalogoCarreras] = None


def obtener_catalogo() -> CatalogoCarreras:
    """Devuelve el catálogo cargado (lazy, singleton)."""
    global _CATALOGO_SINGLETON
    if _CATALOGO_SINGLETON is None:
        _CATALOGO_SINGLETON = CatalogoCarreras()
        _CATALOGO_SINGLETON.cargar()
    return _CATALOGO_SINGLETON


# =============================================================================
# CONTEXTO
# =============================================================================

def _score_contexto(
    nivel_usuario: Optional[str],
    institucion_usuario: Optional[str],
    carrera: Dict,
) -> float:
    """Score 0-1 según encaje de nivel/institución. Neutral = 0.5."""
    score = 0.5

    if nivel_usuario:
        if nivel_usuario in carrera["_nivel_set"]:
            score += 0.25
        else:
            score -= 0.20

    if institucion_usuario:
        if institucion_usuario in carrera["_inst_set"]:
            score += 0.25
        else:
            score -= 0.15

    return max(0.0, min(1.0, score))


# =============================================================================
# COHERENCIA ENTRE CARRERAS
# =============================================================================

def _coherencia_entre(perfiles: List[np.ndarray]) -> float:
    """
    Coherencia promedio entre pares de perfiles RIASEC.
    Usa producto punto (perfiles ya normalizados).
    """
    n = len(perfiles)
    if n < 2:
        return 0.5

    total = 0.0
    pares = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += float(np.dot(perfiles[i], perfiles[j]))
            pares += 1

    return total / pares if pares > 0 else 0.5


# =============================================================================
# MOTOR PRINCIPAL
# =============================================================================

def _recomendar_core(
    perfil_test_tuple: Tuple[float, ...],
    carreras_usuario_tuple: Tuple[str, ...],
    nivel_usuario: Optional[str],
    institucion_usuario: Optional[str],
    top_k: int,
) -> Dict:
    """Core sin caché. Recibe tuples para poder ser cacheado."""
    cat = obtener_catalogo()
    if not cat._cargado:
        return {"error": "Catálogo no disponible."}

    perfil_test = np.array(perfil_test_tuple, dtype=np.float32)
    afinidades_test = cat.afinidad_con_perfil(perfil_test)

    candidatos: Dict[int, Dict] = {}
    textos_no_encontrados: List[str] = []

    for texto_usuario in carreras_usuario_tuple:
        if not texto_usuario or not texto_usuario.strip():
            continue

        matches = cat.buscar(texto_usuario, top_k=3)

        # Filtra matches demasiado débiles (< 0.30) → probablemente ruido
        matches_validos = [(i, s) for i, s in matches if s >= 0.30]

        if not matches_validos:
            textos_no_encontrados.append(texto_usuario)
            continue

        for idx, score_match in matches_validos:
            c = cat.carreras[idx]
            afinidad_test = float(afinidades_test[idx]) if idx < len(afinidades_test) else 0.0
            score_ctx = _score_contexto(nivel_usuario, institucion_usuario, c)

            score_final = (
                PESO_TEST * afinidad_test +
                PESO_USUARIO * score_match +
                PESO_CONTEXTO * score_ctx
            )

            if idx not in candidatos or score_final > candidatos[idx]["score_final"]:
                candidatos[idx] = {
                    "idx": idx,
                    "carrera": c,
                    "score_final": score_final,
                    "afinidad_test": afinidad_test,
                    "score_match": score_match,
                    "score_contexto": score_ctx,
                    "texto_origen": texto_usuario,
                }

    recomendaciones = sorted(
        candidatos.values(), key=lambda x: x["score_final"], reverse=True
    )[:top_k]

    perfiles_rec = [cat.riasec_matrix[r["idx"]] for r in recomendaciones]
    coherencia = _coherencia_entre(perfiles_rec)

    alerta = bool(
        recomendaciones
        and recomendaciones[0]["afinidad_test"] < AFINIDAD_MINIMA_CONFIANZA
    )

    razonamiento = _generar_razonamiento(
        dict(zip(["R", "I", "A", "S", "E", "C"], perfil_test_tuple)),
        recomendaciones,
        coherencia,
        alerta,
    )

    # Interpretación para textos no encontrados: sugerir las top carreras
    # por afinidad al test como "probable interpretación".
    interpretaciones = []
    if textos_no_encontrados and len(afinidades_test) > 0:
        top_idx = np.argsort(afinidades_test)[::-1][:3]
        alternativas = [
            {
                "nombre": cat.carreras[i]["nombre"],
                "afinidad_test": round(float(afinidades_test[i]), 3),
            }
            for i in top_idx
        ]
        for texto in textos_no_encontrados:
            interpretaciones.append({
                "texto_usuario": texto,
                "mensaje": (
                    f"'{texto}' no está en el catálogo. "
                    f"¿Quizás quisiste decir una de estas carreras "
                    f"que encajan con tu perfil del test?"
                ),
                "alternativas": alternativas,
            })

    return {
        "recomendaciones": [
            {
                "nombre": r["carrera"]["nombre"],
                "area": r["carrera"].get("area", ""),
                "score_final": round(r["score_final"], 3),
                "afinidad_test": round(r["afinidad_test"], 3),
                "match_usuario": round(r["score_match"], 3),
                "score_contexto": round(r["score_contexto"], 3),
                "texto_usuario": r["texto_origen"],
            }
            for r in recomendaciones
        ],
        "coherencia_global": round(coherencia, 3),
        "alerta_conflicto": alerta,
        "razonamiento": razonamiento,
        "textos_no_encontrados": textos_no_encontrados,
        "interpretaciones_sugeridas": interpretaciones,
    }


@functools.lru_cache(maxsize=CACHE_SIZE_RECOMENDACIONES)
def _recomendar_cacheado(
    perfil_test_tuple: Tuple[float, ...],
    carreras_usuario_tuple: Tuple[str, ...],
    nivel_usuario: Optional[str],
    institucion_usuario: Optional[str],
    top_k: int,
) -> Dict:
    return _recomendar_core(
        perfil_test_tuple, carreras_usuario_tuple,
        nivel_usuario, institucion_usuario, top_k,
    )


def recomendar_carreras(
    perfil_test: Dict[str, float],
    carreras_usuario: List[str],
    nivel_usuario: Optional[str] = None,
    institucion_usuario: Optional[str] = None,
    top_k: int = 3,
) -> Dict:
    """
    Recomienda carreras combinando test + texto del usuario + contexto.

    Args:
        perfil_test: {"R": 0-1, "I": 0-1, ..., "C": 0-1}
        carreras_usuario: ["corredor de motos", "mecanica", ...]
        nivel_usuario: "universitario" | "tecnico" | "cetpro" | None
        institucion_usuario: "publico" | "privado" | None
        top_k: cuántas carreras devolver

    Returns:
        dict con recomendaciones, coherencia_global, alerta_conflicto,
        razonamiento, textos_no_encontrados e interpretaciones_sugeridas.

    Performance:
        - Primera llamada: ~35ms (carga catálogo).
        - Siguientes: ~2-4ms.
        - Cache hit (misma query): <1ms.
    """
    perfil_tuple = (
        float(perfil_test.get("R", 0.0)),
        float(perfil_test.get("I", 0.0)),
        float(perfil_test.get("A", 0.0)),
        float(perfil_test.get("S", 0.0)),
        float(perfil_test.get("E", 0.0)),
        float(perfil_test.get("C", 0.0)),
    )

    carreras_tuple = tuple(
        c.strip() for c in carreras_usuario if c and c.strip()
    )

    if not carreras_tuple:
        return {
            "recomendaciones": [],
            "coherencia_global": 0.0,
            "alerta_conflicto": False,
            "razonamiento": "No ingresaste ninguna carrera para evaluar.",
            "textos_no_encontrados": [],
            "interpretaciones_sugeridas": [],
        }

    return _recomendar_cacheado(
        perfil_tuple, carreras_tuple,
        nivel_usuario, institucion_usuario, top_k,
    )


# =============================================================================
# RAZONAMIENTO EN LENGUAJE NATURAL
# =============================================================================

_AREAS_TEXTO = {
    "R": "Realista (práctico, manual, técnico)",
    "I": "Investigador (analítico, científico)",
    "A": "Artístico (creativo, expresivo)",
    "S": "Social (ayudar, enseñar, cuidar)",
    "E": "Emprendedor (liderar, persuadir)",
    "C": "Convencional (organizar, sistematizar)",
}


def _generar_razonamiento(perfil_test, recomendaciones, coherencia, alerta):
    if not recomendaciones:
        return (
            "No se encontró ninguna carrera del catálogo que coincida "
            "con lo que escribiste. Intenta con el nombre completo o "
            "sinónimos."
        )

    ordenadas = sorted(perfil_test.items(), key=lambda x: x[1], reverse=True)
    top_area, top_valor = ordenadas[0]
    segunda, seg_valor = ordenadas[1]

    partes = [
        f"Tu perfil del test destaca en {_AREAS_TEXTO[top_area]} "
        f"({top_valor:.2f}), seguido de {_AREAS_TEXTO[segunda]} ({seg_valor:.2f})."
    ]

    mejor = recomendaciones[0]
    partes.append(
        f"De lo que escribiste, la carrera con mejor encaje es "
        f"'{mejor['carrera']['nombre']}' "
        f"(afinidad con el test: {mejor['afinidad_test']:.2f}, "
        f"similitud con tu texto: {mejor['score_match']:.2f})."
    )

    if len(recomendaciones) >= 2:
        segunda_rec = recomendaciones[1]
        partes.append(
            f"En segundo lugar aparece '{segunda_rec['carrera']['nombre']}' "
            f"(afinidad: {segunda_rec['afinidad_test']:.2f})."
        )

    if alerta:
        partes.append(
            "⚠️ ALERTA: lo que escribiste tiene afinidad baja con tu "
            "perfil del test. Puede que tu interés no coincida con tus "
            "aptitudes. Recomendamos revisar esto con un orientador."
        )

    if coherencia < COHERENCIA_BAJA:
        partes.append(
            f"Las carreras que mencionaste son poco coherentes entre sí "
            f"(coherencia: {coherencia:.2f}). Aún estás explorando opciones "
            f"diversas. Considera enfocarte en un área."
        )
    elif coherencia > COHERENCIA_ALTA:
        partes.append(
            f"Las carreras que mencionaste son muy coherentes entre sí "
            f"(coherencia: {coherencia:.2f}). Tienes una dirección clara."
        )

    return " ".join(partes)