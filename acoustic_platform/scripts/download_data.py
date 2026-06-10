#!/usr/bin/env python3
"""
数据下载脚本 — 从 Xeno-canto 下载中国鸟类录音构建训练集
Download Chinese bird recordings from Xeno-canto for CNN training.

Usage:
    python scripts/download_data.py --key YOUR_XC_API_KEY
    python scripts/download_data.py --key YOUR_XC_API_KEY --species 10 --max-per-species 20
    python scripts/download_data.py --key YOUR_XC_API_KEY --species-list custom_species.json
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from xeno_canto_client import (
    CHINA_BIRD_SPECIES, set_api_key, get_api_key,
    build_training_dataset, search_recordings,
)


def check_api_key(key: str = None) -> bool:
    """Verify API key works by making a test query."""
    if key:
        set_api_key(key)
    current_key = get_api_key()
    if not current_key:
        print("[ERROR] 未配置 Xeno-canto API Key。")
        print("  1. 访问 https://xeno-canto.org/account 注册并验证邮箱")
        print("  2. 在账户页面复制你的 API Key")
        print("  3. 使用 --key YOUR_KEY 参数运行本脚本")
        return False

    print(f"[INFO] API Key: {current_key[:6]}...")
    print("[INFO] 测试 API 连接...")
    results = search_recordings("Pycnonotus sinensis", country="China",
                                quality="", max_results=1)
    if results and isinstance(results[0], dict) and "error" in results[0]:
        print(f"[ERROR] API 测试失败: {results[0]['error']}")
        return False
    print(f"[OK] API 连接成功，测试查询返回 {len(results)} 条结果")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="从 Xeno-canto 下载中国鸟类录音",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 下载全部50种鸟，每种最多30条录音
  python scripts/download_data.py --key YOUR_KEY

  # 只下载前10种鸟，每种最多20条
  python scripts/download_data.py --key YOUR_KEY --species 10 --max-per-species 20

  # 使用自定义物种列表
  python scripts/download_data.py --key YOUR_KEY --species-list my_species.json

  # 指定输出目录
  python scripts/download_data.py --key YOUR_KEY --output ./data/xc_china
        """,
    )
    parser.add_argument("--key", type=str, help="Xeno-canto API Key")
    parser.add_argument("--output", type=str, default="./data/xc_china",
                        help="数据保存目录 (default: ./data/xc_china)")
    parser.add_argument("--species", type=int, default=0,
                        help="下载前N种鸟 (0=全部50种)")
    parser.add_argument("--max-per-species", type=int, default=30,
                        help="每种鸟最多下载录音数 (default: 30)")
    parser.add_argument("--country", type=str, default="China",
                        help="国家筛选 (default: China)")
    parser.add_argument("--species-list", type=str,
                        help="自定义物种列表JSON文件路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅显示将要下载的物种，不实际下载")
    args = parser.parse_args()

    print("=" * 60)
    print("  中国鸟声数据下载工具 (Xeno-canto API v3)")
    print("  Chinese Bird Sound Dataset Downloader")
    print("=" * 60)

    # Step 1: Check API key
    if not check_api_key(args.key):
        sys.exit(1)

    # Step 2: Determine species list
    if args.species_list:
        with open(args.species_list, "r", encoding="utf-8") as f:
            species_list = json.load(f)
        print(f"\n[INFO] 使用自定义物种列表: {len(species_list)} 种")
    else:
        species_list = CHINA_BIRD_SPECIES
        if args.species > 0:
            species_list = species_list[:args.species]

    print(f"\n[INFO] 目标物种数: {len(species_list)}")
    print(f"[INFO] 每种最多录音: {args.max_per_species}")
    print(f"[INFO] 国家筛选: {args.country or '全球'}")
    print(f"[INFO] 输出目录: {os.path.abspath(args.output)}")
    print(f"[INFO] 预估最大下载数: {len(species_list) * args.max_per_species} 条录音")

    print("\n将下载以下物种:")
    for i, sp in enumerate(species_list):
        print(f"  {i+1:3d}. {sp['chinese']} ({sp['scientific']}) - {sp['english']}")

    if args.dry_run:
        print("\n[DRY RUN] 仅显示模式，未实际下载。")
        return

    print("\n开始下载...")
    manifest = build_training_dataset(
        data_dir=args.output,
        species_list=species_list,
        max_per_species=args.max_per_species,
        country=args.country,
    )

    print(f"\n{'=' * 60}")
    print(f"  下载完成!")
    print(f"  总录音数: {len(manifest)}")
    print(f"  物种数: {len(set(m['species_scientific'] for m in manifest))}")
    print(f"  数据目录: {os.path.abspath(args.output)}")
    print(f"  清单文件: {os.path.abspath(args.output)}/manifest.json")
    print(f"\n  下一步: 运行训练脚本")
    print(f"  python scripts/train_example.py --data {args.output}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
