#!/usr/bin/env python3
"""
模型训练示例脚本 — 使用下载的 Xeno-canto 数据训练鸟声CNN分类模型
Train bird sound CNN classifier using downloaded Xeno-canto data.

Usage:
    python scripts/train_example.py --data ./data/xc_china
    python scripts/train_example.py --data ./data/xc_china --epochs 30 --lite
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
from cnn_model import create_model, count_parameters
from train import train_model, build_species_mapping


def validate_manifest(manifest_path: str) -> bool:
    """Check manifest file and report dataset statistics."""
    if not os.path.exists(manifest_path):
        print(f"[ERROR] 清单文件不存在: {manifest_path}")
        print("  请先运行数据下载脚本:")
        print("  python scripts/download_data.py --key YOUR_KEY")
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not manifest:
        print("[ERROR] 清单文件为空，没有可用的训练数据。")
        return False

    # Statistics
    species_counts = {}
    missing_files = 0
    for item in manifest:
        sp = item["species_scientific"]
        species_counts[sp] = species_counts.get(sp, 0) + 1
        if not os.path.exists(item["file_path"]):
            missing_files += 1

    print(f"\n数据集统计:")
    print(f"  总录音数: {len(manifest)}")
    print(f"  物种数: {len(species_counts)}")
    print(f"  缺失文件: {missing_files}")
    print(f"\n  每种录音数分布:")
    counts = sorted(species_counts.values())
    print(f"    最少: {counts[0]}, 最多: {counts[-1]}, "
          f"中位数: {counts[len(counts)//2]}, 平均: {sum(counts)/len(counts):.1f}")

    print(f"\n  物种列表:")
    for sp, count in sorted(species_counts.items(), key=lambda x: -x[1]):
        cn = next((m["species_chinese"] for m in manifest if m["species_scientific"] == sp), "")
        print(f"    {cn} ({sp}): {count} 条")

    if missing_files > len(manifest) * 0.5:
        print(f"\n[WARNING] 超过50%的文件缺失 ({missing_files}/{len(manifest)})，训练效果可能较差。")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="训练鸟声CNN分类模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础训练（ResNet，50 epochs）
  python scripts/train_example.py --data ./data/xc_china

  # 轻量模型（MobileNet-style，适合边缘部署）
  python scripts/train_example.py --data ./data/xc_china --lite --epochs 30

  # 自定义参数
  python scripts/train_example.py --data ./data/xc_china --epochs 100 --batch-size 16 --lr 0.0005

  # 指定输出目录
  python scripts/train_example.py --data ./data/xc_china --output ./models/v1
        """,
    )
    parser.add_argument("--data", type=str, required=True,
                        help="数据目录（包含 manifest.json）")
    parser.add_argument("--output", type=str, default="./checkpoints",
                        help="模型输出目录 (default: ./checkpoints)")
    parser.add_argument("--epochs", type=int, default=50,
                        help="训练轮数 (default: 50)")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="批次大小 (default: 32)")
    parser.add_argument("--lr", type=float, default=0.001,
                        help="学习率 (default: 0.001)")
    parser.add_argument("--val-split", type=float, default=0.2,
                        help="验证集比例 (default: 0.2)")
    parser.add_argument("--lite", action="store_true",
                        help="使用轻量模型 (MobileNet-style)")
    parser.add_argument("--validate-only", action="store_true",
                        help="仅验证数据集，不训练")
    args = parser.parse_args()

    print("=" * 60)
    print("  鸟声CNN分类模型训练")
    print("  Bird Sound CNN Classifier Training")
    print("=" * 60)

    manifest_path = os.path.join(args.data, "manifest.json")

    # Validate dataset
    if not validate_manifest(manifest_path):
        sys.exit(1)

    if args.validate_only:
        print("\n[VALIDATE ONLY] 数据验证完成。")
        return

    # Show model info
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n训练配置:")
    print(f"  设备: {device}")
    print(f"  模型: {'BirdSoundCNNLite (MobileNet)' if args.lite else 'BirdSoundCNN (ResNet)'}")
    print(f"  轮数: {args.epochs}")
    print(f"  批次: {args.batch_size}")
    print(f"  学习率: {args.lr}")
    print(f"  验证集: {args.val_split*100:.0f}%")
    print(f"  输出: {os.path.abspath(args.output)}")

    # Preview model parameters
    species_to_idx, _ = build_species_mapping(manifest_path)
    preview_model = create_model(num_species=len(species_to_idx), lite=args.lite)
    print(f"  参数量: {count_parameters(preview_model):,}")
    del preview_model

    print(f"\n{'=' * 60}")
    print("  开始训练...")
    print(f"{'=' * 60}\n")

    history = train_model(
        manifest_path=manifest_path,
        output_dir=args.output,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        val_split=args.val_split,
        lite=args.lite,
    )

    # Summary
    best_epoch = max(range(len(history["val_acc"])), key=lambda i: history["val_acc"][i])
    print(f"\n{'=' * 60}")
    print(f"  训练完成!")
    print(f"  最佳验证准确率: {history['val_acc'][best_epoch]:.4f} (Epoch {best_epoch+1})")
    print(f"  最终训练损失: {history['train_loss'][-1]:.4f}")
    print(f"  模型保存位置: {os.path.abspath(args.output)}")
    print(f"\n  文件列表:")
    print(f"    best_model.pth        — 最佳验证模型权重")
    print(f"    final_model.pth       — 最终模型权重")
    print(f"    species_mapping.json  — 物种ID映射表")
    print(f"    training_history.json — 训练历史曲线")
    print(f"\n  部署到平台:")
    print(f"    将 best_model.pth 复制到 backend/checkpoints/")
    print(f"    重启后端服务即可使用训练好的模型进行推理")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
