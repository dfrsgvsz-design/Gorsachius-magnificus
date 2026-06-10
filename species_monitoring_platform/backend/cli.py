"""
Bird Sound Platform — Command Line Interface
类似 BirdNET-Analyzer 的 CLI 工具，支持批量分析音频文件。

用法:
    # 分析单个文件
    python cli.py analyze recording.wav

    # 分析目录下所有音频
    python cli.py analyze ./recordings/ --recursive

    # 指定输出格式
    python cli.py analyze recording.wav --output results.csv --format csv

    # 使用 ONNX 轻量推理（不需要 PyTorch）
    python cli.py analyze recording.wav --onnx --model model.onnx

    # 导出模型为 ONNX
    python cli.py export --checkpoint best_model.pth --output model.onnx

    # 量化 ONNX 模型
    python cli.py quantize model.onnx --output model_int8.onnx
"""

import argparse
import csv
import json
import sys
import time
import logging
from pathlib import Path
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma"}


def find_audio_files(path: str, recursive: bool = False) -> List[Path]:
    """Find audio files in a path (file or directory)."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
        return [p]
    if p.is_dir():
        pattern = "**/*" if recursive else "*"
        files = []
        for f in p.glob(pattern):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                files.append(f)
        return sorted(files)
    logger.error("Path not found or not an audio file: %s", path)
    return []


def load_engine(args):
    """Load the appropriate inference engine based on args."""
    if args.onnx:
        from onnx_engine import get_onnx_engine

        engine = get_onnx_engine()
        model_path = args.model or "checkpoints/model.onnx"
        mapping_path = args.mapping or "checkpoints/species_mapping.json"
        if not engine.load(model_path, mapping_path):
            logger.error("Failed to load ONNX model")
            sys.exit(1)
        return "onnx", engine
    else:
        import torch
        from shared.backend.models.cnn_model_v7 import ConvNeXtBirdV7, ConvNeXtBirdV7Student

        model_path = Path(args.model or "checkpoints/best_model.pth")
        mapping_path = Path(args.mapping or "checkpoints/species_mapping.json")

        if not model_path.exists() or not mapping_path.exists():
            logger.error("Model or mapping file not found")
            sys.exit(1)

        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        species_mapping = data["species_to_idx"]
        idx_to_species = {int(k): v for k, v in data["idx_to_species"].items()}
        num_species = len(species_mapping)

        device = torch.device(
            "cuda" if torch.cuda.is_available() and not args.cpu else "cpu"
        )
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)
        model_type = checkpoint.get("model_type", "student")

        if model_type == "teacher":
            model = ConvNeXtBirdV7(num_species=num_species, in_channels=2).to(device)
        else:
            model = ConvNeXtBirdV7Student(num_species=num_species, in_channels=2).to(
                device
            )

        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        logger.info(
            "PyTorch model loaded: %s (%d species, device=%s)",
            model_path.name,
            num_species,
            device,
        )

        return "pytorch", (model, device, idx_to_species)


def analyze_file(filepath: Path, engine_type: str, engine, args) -> List[dict]:
    """Analyze a single audio file and return detections."""
    import numpy as np
    from shared.backend.models.cnn_model_v7 import compute_dual_channel_mel

    try:
        import librosa

        y, sr = librosa.load(str(filepath), sr=48000, mono=True)
    except Exception as e:
        logger.warning("Failed to load %s: %s", filepath.name, e)
        return []

    segment_duration = 3.0
    segment_samples = int(segment_duration * 48000)
    overlap = 0.25
    hop = int(segment_samples * (1 - overlap))

    all_detections = []
    num_segments = 0

    for start in range(0, max(1, len(y) - segment_samples + 1), hop):
        seg = y[start : start + segment_samples]
        if len(seg) < segment_samples:
            seg = np.pad(seg, (0, segment_samples - len(seg)))

        mel = compute_dual_channel_mel(seg, sr=48000)
        num_segments += 1

        if engine_type == "onnx":
            predictions = engine.predict(mel, top_k=args.top_k)
        else:
            model, device, idx_to_species = engine
            import torch

            tensor = torch.FloatTensor(mel).unsqueeze(0).to(device)
            with torch.no_grad():
                logits = model(tensor)
            probs = torch.softmax(logits, dim=1)[0]
            top_probs, top_indices = probs.topk(args.top_k)

            predictions = []
            for prob, idx in zip(top_probs.cpu().numpy(), top_indices.cpu().numpy()):
                species = idx_to_species.get(int(idx), "Unknown")
                predictions.append(
                    {
                        "species_scientific": species,
                        "confidence": float(round(prob, 4)),
                        "reliable": float(prob) > 0.3,
                    }
                )

        time_start = start / 48000
        time_end = (start + segment_samples) / 48000

        for pred in predictions:
            if pred["confidence"] >= args.threshold:
                all_detections.append(
                    {
                        "file": str(filepath),
                        "species": pred["species_scientific"],
                        "confidence": pred["confidence"],
                        "time_start": round(time_start, 2),
                        "time_end": round(time_end, 2),
                    }
                )

    return all_detections


def write_results(detections: List[dict], output_path: str, fmt: str):
    """Write detection results to file."""
    p = Path(output_path)

    if fmt == "csv":
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["file", "species", "confidence", "time_start", "time_end"],
            )
            writer.writeheader()
            writer.writerows(detections)

    elif fmt == "json":
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"detections": detections, "total": len(detections)},
                f,
                ensure_ascii=False,
                indent=2,
            )

    elif fmt == "raven":
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(
                [
                    "Selection",
                    "View",
                    "Channel",
                    "Begin Time (s)",
                    "End Time (s)",
                    "Low Freq (Hz)",
                    "High Freq (Hz)",
                    "Species",
                    "Confidence",
                ]
            )
            for i, d in enumerate(detections, 1):
                writer.writerow(
                    [
                        i,
                        "Spectrogram 1",
                        1,
                        d["time_start"],
                        d["time_end"],
                        0,
                        15000,
                        d["species"],
                        d["confidence"],
                    ]
                )

    logger.info("Results written to %s (%d detections)", p, len(detections))


def cmd_analyze(args):
    """Handle the 'analyze' command."""
    files = find_audio_files(args.input, recursive=args.recursive)
    if not files:
        logger.error("No audio files found")
        sys.exit(1)

    logger.info("Found %d audio file(s)", len(files))
    engine_type, engine = load_engine(args)

    all_detections = []
    t0 = time.time()

    for i, filepath in enumerate(files):
        logger.info("[%d/%d] Analyzing: %s", i + 1, len(files), filepath.name)
        detections = analyze_file(filepath, engine_type, engine, args)
        all_detections.extend(detections)

        species_found = len(set(d["species"] for d in detections))
        logger.info("  → %d detections, %d species", len(detections), species_found)

    elapsed = time.time() - t0
    unique_species = set(d["species"] for d in all_detections)

    logger.info("=" * 50)
    logger.info("Analysis complete in %.1fs", elapsed)
    logger.info("  Files: %d", len(files))
    logger.info("  Detections: %d", len(all_detections))
    logger.info("  Unique species: %d", len(unique_species))

    if unique_species:
        from collections import Counter

        counts = Counter(d["species"] for d in all_detections)
        logger.info("  Top species:")
        for sp, cnt in counts.most_common(10):
            logger.info("    %s: %d detections", sp, cnt)

    if args.output:
        write_results(all_detections, args.output, args.format)
    elif not args.quiet:
        for d in all_detections[:20]:
            print(
                f"  {d['species']:40s}  conf={d['confidence']:.3f}  "
                f"t={d['time_start']:.1f}-{d['time_end']:.1f}s  [{d['file']}]"
            )
        if len(all_detections) > 20:
            print(f"  ... and {len(all_detections) - 20} more detections")


def cmd_export(args):
    """Handle the 'export' command."""
    import torch
    from shared.backend.models.cnn_model_v7 import create_model_v7, export_to_onnx

    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        logger.error("Checkpoint not found: %s", checkpoint_path)
        sys.exit(1)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model_type = checkpoint.get("model_type", "student")

    mapping_path = Path(args.mapping or "checkpoints/species_mapping.json")
    with open(mapping_path, "r") as f:
        data = json.load(f)
    num_species = len(data["species_to_idx"])

    model = create_model_v7(num_species=num_species, model_type=model_type)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    output_path = args.output or "model.onnx"
    export_to_onnx(model, output_path, num_species=num_species)
    logger.info("Exported ONNX model: %s", output_path)


def cmd_quantize(args):
    """Handle the 'quantize' command."""
    from onnx_engine import quantize_onnx_model

    output = args.output or str(Path(args.input).stem) + "_int8.onnx"
    quantize_onnx_model(args.input, output)


def main():
    parser = argparse.ArgumentParser(
        description="Bird Sound Platform CLI — 中国鸟声智能识别命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze
    p_analyze = subparsers.add_parser(
        "analyze", help="Analyze audio files for bird species"
    )
    p_analyze.add_argument("input", help="Audio file or directory path")
    p_analyze.add_argument(
        "--recursive", "-r", action="store_true", help="Recurse into subdirectories"
    )
    p_analyze.add_argument("--output", "-o", help="Output file path")
    p_analyze.add_argument(
        "--format",
        choices=["csv", "json", "raven"],
        default="csv",
        help="Output format",
    )
    p_analyze.add_argument(
        "--top-k", type=int, default=5, help="Top K predictions per segment"
    )
    p_analyze.add_argument(
        "--threshold", type=float, default=0.1, help="Confidence threshold"
    )
    p_analyze.add_argument("--model", help="Model path (.pth or .onnx)")
    p_analyze.add_argument("--mapping", help="Species mapping JSON path")
    p_analyze.add_argument(
        "--onnx", action="store_true", help="Use ONNX Runtime (no PyTorch needed)"
    )
    p_analyze.add_argument("--cpu", action="store_true", help="Force CPU inference")
    p_analyze.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress detailed output"
    )

    # export
    p_export = subparsers.add_parser("export", help="Export PyTorch model to ONNX")
    p_export.add_argument("--checkpoint", required=True, help="PyTorch checkpoint path")
    p_export.add_argument("--output", "-o", help="Output ONNX path")
    p_export.add_argument("--mapping", help="Species mapping JSON path")

    # quantize
    p_quant = subparsers.add_parser("quantize", help="Quantize ONNX model to INT8")
    p_quant.add_argument("input", help="Input ONNX model path")
    p_quant.add_argument("--output", "-o", help="Output quantized model path")

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "quantize":
        cmd_quantize(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
