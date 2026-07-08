# Modelos de detección de objetos

Este directorio contiene los pesos de los modelos ML utilizados por los detectores.

Cada detector espera un archivo de modelo concreto en formato ONNX dentro de este
directorio. Cuando el archivo no existe, el detector entra en **modo reducido**
usando segmentación por color con OpenCV.

## Modelo actual

| Fichero | Modelo | Origen | Tamaño ONNX | Clases |
|---------|--------|--------|-------------|--------|
| `pool_detector.onnx` | YOLOv11n fine-tuned | [yourkln/pool-detection](https://github.com/yourkln/pool-detection) | ~5 MB | 1 (piscina) |

### Descarga automática

Al arrancar el servidor, `download.py` comprueba si `pool_detector.onnx` existe.
Si no, descarga el `.pt` original (~5 MB), lo convierte a ONNX con `ultralytics`
(se instala automáticamente si no está) y borra el `.pt` intermedio.

```bash
# Descarga manual
cd servidor
python -m ml_models.download
```

---

## Repositorios gratuitos de modelos pre-entrenados

### Hugging Face

La mayor colección de modelos open‑source. La mayoría permiten descarga directa
y exportación a ONNX.

| Modelo | Descripción | Enlace |
|--------|-------------|--------|
| **swimming-pool-detector** | YOLO11m fine-tuneado para detectar piscinas en imágenes satélite | https://huggingface.co/mozilla-ai/swimming-pool-detector |
| **YOLOv8** (Ultralytics) | Modelo oficial YOLOv8 pre-entrenado en COCO (clase "pool" incluida) | https://huggingface.co/Ultralytics/YOLOv8 |
| **YOLOv11** (Ultralytics) | Última generación YOLO, pre-entrenado en COCO | https://huggingface.co/ultralytics/YOLO11 |
| **yolov8s-visdrone** | YOLOv8s fine-tuneado en VisDrone (detección aérea, 10 clases) | https://huggingface.co/dronefreak/yolov8s-visdrone |
| **Building Footprint YOLO** | YOLOv8-seg para segmentación de edificios en ortofotos | https://huggingface.co/hotosm/yolo |

### GitHub

Repositorios con modelos entrenados, pesos descargables y datasets.

| Repositorio | Descripción | Enlace |
|-------------|-------------|--------|
| **MahdiYoussef / Swimming-pools-detection** | YOLO26s, 97.7% mAP50, detecta piscinas en aéreas | https://github.com/mahdiyoussef/Swimming-pools-detection-from-aerial-images |
| **yourkln / pool-detection** | YOLOv11n fine-tuneado + segmentación por color OpenCV | https://github.com/yourkln/pool-detection |
| **akhilchibber / Swimming-Pool-Detection** | Deep Learning, dataset Kaggle, Jupyter Notebook | https://github.com/akhilchibber/Swimming-Pool-Detection |
| **devanshu-08 / Pool-Detection** | YOLOv3 + DarkNet53, pesos en Google Drive | https://github.com/devanshu-08/Pool-Detection |
| **joshleh / aerotrack** | Pipeline YOLOv8 + ByteTrack para drones, exporta a ONNX | https://github.com/joshleh/aerotrack |

### Kaggle

Datasets etiquetados para fine‑tuning y modelos listos para usar.

| Dataset | Descripción | Enlace |
|---------|-------------|--------|
| Swimming Pool Detection | 1100+ imágenes aéreas etiquetadas (512×512) | https://www.kaggle.com/datasets/alexj21/swimming-pool-512x512 |
| Swimming Pool in Satellite Images | Dataset complementario para clasificación/detección | https://www.kaggle.com/datasets/cici118/swimming-pool-detection-in-satellite-images |

### Otros

| Fuente | Descripción | Enlace |
|--------|-------------|--------|
| **ArcGIS Living Atlas** | Modelo Pool Detection USA (FasterRCNN), requiere cuenta ArcGIS | https://livingatlas.arcgis.com |
| **ONNX Model Zoo** | Colección de modelos pre-entrenados en formato ONNX | https://github.com/onnx/models |
| **Roboflow Universe** | Datasets + modelos, varios de piscinas y objetos en aéreas | https://universe.roboflow.com |

---

## Formatos soportados por los detectores

| Formato | Extensión | Librería de carga | Notas |
|---------|-----------|-------------------|-------|
| **ONNX** | `.onnx` | `onnxruntime` | Recomendado: ligero, multiplataforma, sin dependencias pesadas |
| **YOLO PyTorch** | `.pt` | `ultralytics` | Peso nativo de YOLOv8/v11, requiere PyTorch |
| **PyTorch** | `.pt`, `.pth` | `torch` | Formato genérico de PyTorch |
| **TensorFlow Lite** | `.tflite` | `tflite-runtime` | Para dispositivos embebidos / edge |

---

## Cómo añadir un modelo nuevo

1. Descarga los pesos y colócalos aquí (ej: `pool_detector.onnx`).
2. Crea una clase detectora en `servidor/agent/ml/detectors/` heredando de `BaseDetector`.
3. Decórala con `@detector` para que se registre automáticamente.
4. Define la tool correspondiente en `servidor/agent/tools/executors.py` con `@register(...)`.
5. Listo. El LLM podrá invocarla cuando lo considere necesario.
