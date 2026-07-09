# TODO

## Modelo pool_seg (segmentacion de piscinas)

El detector `pool_seg_detector` ya tiene todo el codigo listo pero necesita
el fichero `pool_seg.onnx` (YOLO11n-seg fine-tuned). Pasos para obtenerlo:

### 1. Conseguir dataset con poligonos

No hay datasets gratuitos con poligonos de piscinas listos para descargar.
Opciones por orden de viabilidad:

- [ ] **Opcion A — Generar pseudo-labels automaticamente**
      Usar el detector actual (`pool_detector.onnx`) + pipeline OpenCV de yourkln
      para generar contornos sobre tiles del WMS PNOA. Convertir los contornos
      a formato YOLO-seg (coordenadas normalizadas de poligono).
      Script necesario: recorrer tiles, detectar, refinar contorno, guardar label.
      Calidad: media (depende del detector actual). ~1 dia de trabajo.

- [ ] **Opcion B — Dataset suizo (Canton de Ginebra)**
      Usar el framework del Swiss Territorial Data Lab para generar tiles +
      anotaciones COCO con poligonos desde datos catastrales de Ginebra.
      Repo: https://github.com/swiss-territorial-data-lab/object-detector
      Calidad: alta (ground truth catastral). ~2-3 dias de configuracion.

- [ ] **Opcion C — Etiquetar manualmente con CVAT o Roboflow**
      Etiquetar ~500+ imagenes aereas con poligonos de piscinas.
      Herramientas: CVAT (https://cvat.ai), Roboflow, LabelMe.
      Calidad: maxima. ~1 semana de trabajo manual.

### 2. Preparar dataset en formato YOLO-seg

Estructura esperada:
```
dataset/
  images/
    train/   # ~80% de las imagenes
    val/     # ~20% de las imagenes
  labels/
    train/   # un .txt por imagen
    val/     # un .txt por imagen
```

Cada fichero de label tiene una linea por piscina:
```
0 x1 y1 x2 y2 x3 y3 ... xn yn
```
(clase 0 = piscina, coordenadas normalizadas 0-1 del poligono)

Crear `dataset.yaml`:
```yaml
names: ['pool']
nc: 1
train: /ruta/al/dataset/images/train
val: /ruta/al/dataset/images/val
```

### 3. Entrenar en maquina con GPU

Requisitos: CUDA, ultralytics>=8.3, torch, torchvision.
Google Colab (gratis con T4) es suficiente.

```bash
python -m ml_models.utils.train_pool_seg \
  --data dataset.yaml \
  --epochs 200 \
  --batch 16 \
  --device 0
```

El script genera `pool_seg.onnx` en el directorio actual (~5-10 MB).

### 4. Desplegar

- [ ] Copiar `pool_seg.onnx` a `servidor/ml_models/`
- [ ] (Opcional) Subir el ONNX a una URL publica y añadir entrada en
      `ml_models/utils/download.py` para descarga automatica
- [ ] Verificar que `pool_seg_detector` carga el modelo y no usa fallback

## Ideas / Mejoras futuras

- CI/CD con GitHub Actions (ruff + tests en cada push)
- Multimodalidad (imagenes en el chat)
- Rate limiting / autenticacion basica
- Exportar conversacion como Markdown/PDF
- i18n del plugin (textos hardcodeados en español)
