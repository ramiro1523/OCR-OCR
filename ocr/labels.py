import logging
import re
from functools import lru_cache

import cv2
import numpy as np
import pytesseract


logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURACIÓN
# ============================================================

CONFIG_TESSERACT_ETIQUETAS = (
    r"--psm 7 "
    r"-c tessedit_char_whitelist=EPH0123456789"
)

CONFIG_TESSERACT_ETIQUETAS_PSM8 = (
    r"--psm 8 "
    r"-c tessedit_char_whitelist=EPH0123456789"
)

PATRON_ETIQUETA = re.compile(
    r"^[EPH]\d{1,2}$"
)

CONFIANZA_MINIMA_ETIQUETA = 60.0
CONFIANZA_MINIMA_ANCLA = 60.0

ESCALA_OCR = 2


# ============================================================
# TESSERACT DISPONIBLE
# ============================================================

@lru_cache(maxsize=1)
def tesseract_disponible() -> bool:
    """
    Comprueba si Tesseract está instalado y disponible.

    El resultado queda cacheado para no ejecutar
    get_tesseract_version() en cada celda.
    """

    try:
        pytesseract.get_tesseract_version()
        return True

    except Exception as e:
        logger.debug(
            "Tesseract no está disponible: %s",
            e
        )
        return False


# ============================================================
# PREPROCESAMIENTO
# ============================================================

def preparar_imagen_ocr(
    imagen: np.ndarray,
    escala: int = ESCALA_OCR,
    binarizar: bool = True
) -> np.ndarray:
    """
    Prepara una imagen para OCR.

    Pasos:
        1. Escala de grises.
        2. Upscaling.
        3. Normalización.
        4. Binarización Otsu opcional.
    """

    if imagen is None or imagen.size == 0:
        return imagen

    resultado = imagen.copy()

    # --------------------------------------------------------
    # Escala de grises
    # --------------------------------------------------------

    if len(resultado.shape) == 3:

        resultado = cv2.cvtColor(
            resultado,
            cv2.COLOR_BGR2GRAY
        )

    # --------------------------------------------------------
    # Upscaling
    # --------------------------------------------------------

    if escala > 1:

        h, w = resultado.shape[:2]

        if h > 0 and w > 0:

            resultado = cv2.resize(
                resultado,
                (w * escala, h * escala),
                interpolation=cv2.INTER_CUBIC
            )

    # --------------------------------------------------------
    # Normalización
    # --------------------------------------------------------

    resultado = cv2.normalize(
        resultado,
        None,
        0,
        255,
        cv2.NORM_MINMAX
    )

    # --------------------------------------------------------
    # Binarización Otsu
    # --------------------------------------------------------

    if binarizar:

        _, resultado = cv2.threshold(
            resultado,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

    return resultado


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def normalizar_texto(texto: str) -> str:
    """
    Limpia el resultado de Tesseract.
    """

    if not texto:
        return ""

    texto = texto.upper().strip()

    # Elimina espacios, saltos de línea y tabulaciones.
    texto = re.sub(r"\s+", "", texto)

    return texto


# ============================================================
# CORREGIR ETIQUETA
# ============================================================

def corregir_etiqueta(texto: str) -> str:
    """
    Corrige errores comunes de OCR en etiquetas.

    Ejemplos:

        EI  -> E1
        PI  -> P1
        HI  -> H1
        EL  -> E1
        1E  -> E1
        12P -> P12
    """

    texto = normalizar_texto(texto)

    if not texto:
        return ""

    # Errores frecuentes de caracteres.
    texto = texto.replace("I", "1")
    texto = texto.replace("L", "1")

    # --------------------------------------------------------
    # Formato normal
    # --------------------------------------------------------

    if re.fullmatch(r"[EPH]\d{1,2}", texto):
        return texto

    # --------------------------------------------------------
    # Formato invertido
    # --------------------------------------------------------

    match = re.fullmatch(
        r"(\d{1,2})([EPH])",
        texto
    )

    if match:

        numero = match.group(1)
        letra = match.group(2)

        return f"{letra}{numero}"

    return texto


# ============================================================
# VALIDAR ETIQUETA
# ============================================================

def validar_etiqueta(texto: str) -> bool:
    """
    Valida el formato básico:

        E1
        P1
        H1

    hasta dos dígitos.
    """

    if not texto:
        return False

    return bool(
        PATRON_ETIQUETA.fullmatch(texto)
    )


# ============================================================
# VALIDAR RANGO REAL
# ============================================================

def validar_etiqueta_con_rango(texto: str) -> bool:
    """
    Valida los rangos conocidos del formulario:

        E1  - E33
        P1  - P47
        H1  - H38
    """

    if not validar_etiqueta(texto):
        return False

    letra = texto[0]
    numero = int(texto[1:])

    if letra == "E":
        return 1 <= numero <= 33

    if letra == "P":
        return 1 <= numero <= 47

    if letra == "H":
        return 1 <= numero <= 38

    return False


# ============================================================
# OBTENER CONFIANZA DEL OCR
# ============================================================

def obtener_confianza_ocr(
    datos: dict
) -> float:
    """
    Obtiene la mayor confianza válida encontrada
    en los resultados de Tesseract.
    """

    confianzas = []

    for confianza in datos.get("conf", []):

        try:

            valor = float(confianza)

            if valor >= 0:
                confianzas.append(valor)

        except (
            ValueError,
            TypeError
        ):
            continue

    if not confianzas:
        return 0.0

    return max(confianzas)


# ============================================================
# EXTRAER RESULTADO DE TESSERACT
# ============================================================

def extraer_texto_y_confianza(
    imagen: np.ndarray,
    config: str,
    lang: str
) -> tuple[str, float]:
    """
    Ejecuta image_to_data() y devuelve:

        texto
        confianza
    """

    datos = pytesseract.image_to_data(
        imagen,
        config=config,
        lang=lang,
        output_type=pytesseract.Output.DICT
    )

    textos = []

    for texto in datos.get("text", []):

        texto = texto.strip()

        if texto:
            textos.append(texto)

    texto_final = "".join(textos)

    confianza = obtener_confianza_ocr(
        datos
    )

    return (
        texto_final,
        confianza
    )


# ============================================================
# LEER ETIQUETA
# ============================================================

def leer_etiqueta_celda(
    subimagen_etiqueta: np.ndarray,
    escala: int = ESCALA_OCR,
    binarizar: bool = True,
    confianza_minima: float = CONFIANZA_MINIMA_ETIQUETA,
    validar_rango: bool = True
) -> str:
    """
    Lee una etiqueta de una celda.

    Etiquetas esperadas:

        E1 ... E33
        P1 ... P47
        H1 ... H38

    No utiliza caché por nombre de etiqueta.
    Esto evita que un resultado de otro formulario
    sea reutilizado incorrectamente.

    Devuelve:
        "E1"
        "P25"
        "H38"

    o "" si no se reconoce correctamente.
    """

    if not tesseract_disponible():
        return ""

    if (
        subimagen_etiqueta is None
        or subimagen_etiqueta.size == 0
    ):
        return ""

    try:

        # ----------------------------------------------------
        # Preparar imagen
        # ----------------------------------------------------

        imagen = preparar_imagen_ocr(
            subimagen_etiqueta,
            escala=escala,
            binarizar=binarizar
        )

        # ----------------------------------------------------
        # Primer intento: PSM 7
        # ----------------------------------------------------

        texto, confianza = (
            extraer_texto_y_confianza(
                imagen,
                CONFIG_TESSERACT_ETIQUETAS,
                "eng"
            )
        )

        texto = corregir_etiqueta(
            texto
        )

        # ----------------------------------------------------
        # Validación
        # ----------------------------------------------------

        if validar_rango:

            valido = validar_etiqueta_con_rango(
                texto
            )

        else:

            valido = validar_etiqueta(
                texto
            )

        # ----------------------------------------------------
        # Si es válido y tiene suficiente confianza
        # ----------------------------------------------------

        if (
            valido
            and confianza >= confianza_minima
        ):
            return texto

        # ----------------------------------------------------
        # Segundo intento: PSM 8
        #
        # PSM 8 trata la región como una sola palabra.
        # Puede funcionar mejor si hay líneas o ruido
        # alrededor de la etiqueta.
        # ----------------------------------------------------

        texto, confianza = (
            extraer_texto_y_confianza(
                imagen,
                CONFIG_TESSERACT_ETIQUETAS_PSM8,
                "eng"
            )
        )

        texto = corregir_etiqueta(
            texto
        )

        if validar_rango:

            valido = validar_etiqueta_con_rango(
                texto
            )

        else:

            valido = validar_etiqueta(
                texto
            )

        if (
            valido
            and confianza >= confianza_minima
        ):
            return texto

        # ----------------------------------------------------
        # No se pudo reconocer con suficiente confianza
        # ----------------------------------------------------

        return ""

    except Exception as e:

        logger.debug(
            "Tesseract no pudo leer la etiqueta: %s",
            e
        )

        return ""


# ============================================================
# LEER TEXTO GENERAL
# ============================================================

def leer_texto_celda(
    celda_gris: np.ndarray,
    config: str = "--psm 7",
    lang: str = "spa",
    escala: int = ESCALA_OCR,
    binarizar: bool = True
) -> str:
    """
    Lee texto general de una celda.

    Por defecto utiliza español.

    Ejemplo:

        leer_texto_celda(
            imagen,
            lang="spa"
        )
    """

    if not tesseract_disponible():
        return ""

    if (
        celda_gris is None
        or celda_gris.size == 0
    ):
        return ""

    try:

        imagen = preparar_imagen_ocr(
            celda_gris,
            escala=escala,
            binarizar=binarizar
        )

        texto = pytesseract.image_to_string(
            imagen,
            config=config,
            lang=lang
        )

        return texto.strip()

    except Exception as e:

        logger.debug(
            "Tesseract no pudo leer la celda: %s",
            e
        )

        return ""


# ============================================================
# BUSCAR ANCLA
# ============================================================

def buscar_ancla(
    imagen_gris: np.ndarray,
    texto_buscar: str,
    confianza_minima: float = CONFIANZA_MINIMA_ANCLA,
    coincidencia_exacta: bool = True,
    escala: int = ESCALA_OCR,
    binarizar: bool = True
) -> list[dict]:
    """
    Busca un texto dentro del documento.

    Ejemplo:

        resultados = buscar_ancla(
            imagen,
            "EDUCACION"
        )

    Devuelve:

        [
            {
                "texto": "EDUCACION",
                "x": 100,
                "y": 200,
                "w": 120,
                "h": 30,
                "confianza": 94.5
            }
        ]
    """

    if not tesseract_disponible():
        return []

    if (
        imagen_gris is None
        or imagen_gris.size == 0
    ):
        return []

    if not texto_buscar:
        return []

    try:

        # ----------------------------------------------------
        # PREPROCESAMIENTO
        # ----------------------------------------------------

        imagen = preparar_imagen_ocr(
            imagen_gris,
            escala=escala,
            binarizar=binarizar
        )

        # ----------------------------------------------------
        # OCR
        # ----------------------------------------------------

        datos = pytesseract.image_to_data(
            imagen,
            lang="spa",
            config="--psm 6",
            output_type=pytesseract.Output.DICT
        )

        coincidencias = []

        texto_objetivo = (
            texto_buscar
            .upper()
            .strip()
        )

        n_cajas = len(
            datos.get("text", [])
        )

        for i in range(n_cajas):

            texto = (
                datos["text"][i]
                .strip()
                .upper()
            )

            if not texto:
                continue

            # ------------------------------------------------
            # Confianza
            # ------------------------------------------------

            try:

                confianza = float(
                    datos["conf"][i]
                )

            except (
                ValueError,
                TypeError
            ):

                confianza = -1

            if confianza < confianza_minima:
                continue

            # ------------------------------------------------
            # Comparación
            # ------------------------------------------------

            if coincidencia_exacta:

                coincide = (
                    texto == texto_objetivo
                )

            else:

                coincide = (
                    texto_objetivo in texto
                )

            if not coincide:
                continue

            # ------------------------------------------------
            # Coordenadas
            #
            # IMPORTANTE:
            # Si la imagen fue escalada, convertimos
            # las coordenadas nuevamente a la escala
            # original.
            # ------------------------------------------------

            x = int(datos["left"][i])
            y = int(datos["top"][i])
            w = int(datos["width"][i])
            h = int(datos["height"][i])

            if escala > 1:

                x = int(x / escala)
                y = int(y / escala)
                w = int(w / escala)
                h = int(h / escala)

            coincidencias.append({
                "texto": texto,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "confianza": confianza
            })

        return coincidencias

    except Exception as e:

        logger.debug(
            "Error buscando ancla con Tesseract: %s",
            e
        )

        return []


# ============================================================
# CONFIGURAR / LIMPIAR CACHE DE TESSERACT
# ============================================================

def limpiar_cache_tesseract() -> None:
    """
    Limpia solamente la caché de disponibilidad de Tesseract.

    No existe caché de resultados OCR por etiqueta,
    por lo que diferentes formularios nunca comparten
    resultados incorrectamente.
    """

    tesseract_disponible.cache_clear()
