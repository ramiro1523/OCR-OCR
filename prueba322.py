import cv2
# Abrir plantilla
img = cv2.imread("data/plantilla_ieppo_gris.png", cv2.IMREAD_GRAYSCALE)
print(f"Shape: {img.shape}")
print(f"Media: {img.mean():.1f}")
print(f"Densidad de tinta: {(img < 128).sum() / img.size:.4f}")

# Mostrar
cv2.imshow("Plantilla", img)
cv2.waitKey(0)