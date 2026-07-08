#!/usr/bin/env python3
"""
Fine-tunes YOLO11n-seg on a pool segmentation dataset and exports to ONNX.

This script is intended to run on a machine with a GPU (CUDA).  It produces
``pool_seg.onnx`` which can be copied to ``servidor/ml_models/`` for use by
``PoolSegDetector``.

Usage
-----

    # 1. Prepare a dataset in YOLO segmentation format:
    #    dataset/
    #      images/
    #        train/  val/
    #      labels/
    #        train/  val/
    #
    #    Each label file has lines: class_id x1 y1 x2 y2 ... xn yn
    #    (normalized coordinates, one polygon per line).

    # 2. Create a dataset.yaml:
    #    names: ['pool']
    #    nc: 1
    #    train: /path/to/dataset/images/train
    #    val: /path/to/dataset/images/val

    # 3. Run training:
    python -m ml_models.utils.train_pool_seg --data dataset.yaml --epochs 200

Arguments
---------
--data       : path to dataset.yaml (required)
--epochs     : number of epochs (default: 200)
--imgsz      : input image size (default: 640)
--batch      : batch size (default: 16)
--device     : device (default: "0" for first GPU)
--output     : output directory for ONNX (default: .)
--model      : base model (default: "yolo11n-seg.pt")
--patience   : early stopping patience (default: 50)

The final ONNX file is saved as ``pool_seg.onnx`` in the output directory.

Requires: ultralytics>=8.3, torch, torchvision
"""
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLO11n-seg for pool segmentation",
    )
    parser.add_argument("--data", required=True, help="Path to dataset.yaml")
    parser.add_argument("--epochs", type=int, default=200, help="Training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--device", default="0", help="Device (e.g. '0', 'cpu')")
    parser.add_argument("--output", default=".", help="Output directory for ONNX")
    parser.add_argument("--model", default="yolo11n-seg.pt", help="Base YOLO model")
    parser.add_argument("--patience", type=int, default=50, help="Early stopping")
    args = parser.parse_args()

    from ultralytics import YOLO

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"ERROR: dataset.yaml not found: {data_path}")
        raise SystemExit(1)

    # Load pre-trained segmentation model
    model = YOLO(args.model)

    # Train
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        patience=args.patience,
        project="runs/pool_seg",
        name="train",
        exist_ok=True,
    )

    # Locate best weights
    best_pt = Path("runs/pool_seg/train/weights/best.pt")
    if not best_pt.exists():
        print(f"ERROR: trained weights not found at {best_pt}")
        raise SystemExit(1)

    # Export to ONNX
    model = YOLO(str(best_pt))
    onnx_path = model.export(format="onnx", imgsz=args.imgsz, simplify=True)
    print(f"ONNX exported to: {onnx_path}")

    # Copy to final destination
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "pool_seg.onnx"
    shutil.copy2(onnx_path, dest)
    print(f"Model copied to: {dest}")

    print("\nDone! Copy pool_seg.onnx to servidor/ml_models/ on the deployment machine.")


if __name__ == "__main__":
    main()
