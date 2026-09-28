# paso3_detectar.py
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

COLORES = {
    "texto":    (255, 0, 255),    # magenta
    "checkbox": (0, 255, 0),      # verde
    "otros":    (255, 128, 0),    # naranja
}
TOL = 40
AREA_MIN = 80
PAGE_H_PT = 792
ZOOM = 2


def detectar(ruta_png, ruta_txt):
    img = Image.open(ruta_png).convert("RGB")
    arr = np.array(img)
    r = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    b = arr[:, :, 2].astype(int)

    debug = img.copy()
    dibujar = ImageDraw.Draw(debug)

    print(f"\n=== {ruta_png} ===")
    with open(ruta_txt, "w", encoding="utf-8") as f:
        for tipo, color in COLORES.items():
            mask = (
                (np.abs(r - color[0]) < TOL) &
                (np.abs(g - color[1]) < TOL) &
                (np.abs(b - color[2]) < TOL)
            )
            labeled, n = ndimage.label(mask)
            cajas = []
            for i in range(1, n + 1):
                ys, xs = np.where(labeled == i)
                if len(xs) < AREA_MIN:
                    continue
                x0, x1 = int(xs.min()), int(xs.max())
                y0, y1 = int(ys.min()), int(ys.max())

                pdf_x = round(x0 / ZOOM, 1)
                pdf_y = round(PAGE_H_PT - (y1 / ZOOM), 1)
                pdf_w = round((x1 - x0) / ZOOM, 1)
                pdf_h = round((y1 - y0) / ZOOM, 1)
                cajas.append((pdf_x, pdf_y, pdf_w, pdf_h, x0, y0, x1, y1))

            cajas.sort(key=lambda c: (c[5] // 20, c[4]))

            print(f"  [{tipo.upper()}]: {len(cajas)} cajas")
            for idx, (px, py, pw, ph, x0, y0, x1, y1) in enumerate(cajas, start=1):
                print(f"    #{idx:02d}  x={px:6.1f}  y={py:6.1f}  w={pw:6.1f}  h={ph:6.1f}")
                f.write(f"{tipo}\t{idx}\t{px}\t{py}\t{pw}\t{ph}\n")
                dibujar.rectangle([x0, y0, x1, y1], outline=(0, 0, 0), width=2)
                dibujar.text((x0 + 2, y0 + 2), f"{tipo[:2]}{idx}", fill=(0, 0, 0))

    debug_path = ruta_png.replace(".png", "_detectado.png")
    debug.save(debug_path)
    print(f"  → Guardado: {debug_path}")
    print(f"  → Datos:    {ruta_txt}")


if __name__ == "__main__":
    detectar("pagina_1_marcada.png", "cajas_1.txt")
    detectar("pagina_2_marcada.png", "cajas_2.txt")