"""Algo-D / P2-W3 :: build the BirdNET embedding KNN index used by the
inference fallback path.

Reads a manifest of (audio_file, species_scientific) entries, extracts
1024-dim BirdNET embeddings from every chunk in every file, stacks them with
their integer species labels, and writes four files to ``--output``:

  embeddings.npy       (N x 1024 float32)
  labels.npy           (N int32)
  species_mapping.json (idx <-> scientific_name copy of the master mapping)
  index_meta.json      (provenance / config)

Run once per training cycle; this is the *long* step (~30 min – 2 h on CPU
for ~20k recordings). Use --dry-run to estimate.

Requires the optional ``birdnet`` package (NOT GPU-bound):
  pip install birdnet

Usage:

  python scripts/algo_d/build_birdnet_knn_index.py `
    --manifest "f:\\...\\species_monitoring_platform\\data\\xc_expanded\\manifest.json" `
    --output   "f:\\...\\species_monitoring_platform\\backend\\checkpoints\\birdnet_knn" `
    --species-mapping "f:\\...\\species_monitoring_platform\\backend\\checkpoints\\species_mapping.json"

  python scripts/algo_d/build_birdnet_knn_index.py --dry-run --sample 10 ...

Exit codes:
  0 = built successfully (or dry-run completed)
  2 = inputs missing
  3 = birdnet package missing
  4 = no embeddings could be extracted from any file
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="path to manifest.json (list of {file_path, species_scientific})")
    ap.add_argument("--output", required=True, help="output dir for KNN index files")
    ap.add_argument("--species-mapping", required=True, help="path to species_mapping.json (canonical idx <-> name)")
    ap.add_argument("--dry-run", action="store_true", help="extract on a small sample, report ETA, do not write")
    ap.add_argument("--sample", type=int, default=10, help="size of dry-run sample (default 10)")
    ap.add_argument("--checkpoint-every", type=int, default=200,
                    help="save partial embeddings every N files (default 200)")
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output).resolve()
    mapping_path = Path(args.species_mapping).resolve()

    if not manifest_path.exists():
        print(f"[FATAL] manifest not found: {manifest_path}")
        return 2
    if not mapping_path.exists():
        print(f"[FATAL] species mapping not found: {mapping_path}")
        return 2

    manifest = _load_json(manifest_path)
    if not isinstance(manifest, list):
        print(f"[FATAL] manifest is not a list: {manifest_path}")
        return 2
    mapping = _load_json(mapping_path)
    species_to_idx: dict[str, int] = mapping.get("species_to_idx", {})
    if not species_to_idx:
        print(f"[FATAL] species_to_idx missing from mapping: {mapping_path}")
        return 2

    print("=" * 72)
    print(" Algo-D / P2-W3 :: build BirdNET KNN index")
    print(f"  manifest         = {manifest_path}")
    print(f"  manifest_rows    = {len(manifest)}")
    print(f"  species_mapping  = {mapping_path}  ({len(species_to_idx)} species)")
    print(f"  output           = {output_dir}")
    print(f"  dry_run          = {args.dry_run} (sample={args.sample})")
    print("=" * 72)

    # Defer the heavy import so --help / argument validation works without it.
    try:
        sys.path.insert(0, str(REPO_ROOT / "species_monitoring_platform" / "backend"))
        from birdnet_embeddings import BirdNETEmbeddingEngine  # type: ignore
    except ImportError as exc:
        print(f"[FATAL] cannot import birdnet_embeddings: {exc}")
        return 3

    engine = BirdNETEmbeddingEngine()
    if not engine.available:
        print("[FATAL] birdnet package not installed: pip install birdnet")
        return 3

    items_to_process = manifest if not args.dry_run else manifest[: args.sample]
    print(f"\n[1/3] extracting embeddings from {len(items_to_process)} files")

    try:
        import numpy as np
    except ImportError:
        print("[FATAL] numpy not installed")
        return 3

    embeddings: list = []
    labels: list[int] = []
    skipped_no_species_idx = 0
    skipped_no_embed = 0
    started = time.time()
    last_checkpoint_at = 0

    output_dir.mkdir(parents=True, exist_ok=True)
    emb_tmp = output_dir / "embeddings.partial.npy"
    lbl_tmp = output_dir / "labels.partial.npy"

    for i, item in enumerate(items_to_process, 1):
        if not isinstance(item, dict):
            continue
        sci = (item.get("species_scientific") or "").strip()
        fp = item.get("file_path") or ""
        if not sci or not fp:
            continue
        sp_idx = species_to_idx.get(sci)
        if sp_idx is None:
            skipped_no_species_idx += 1
            continue
        if not Path(fp).exists():
            print(f"  [warn] missing file: {fp}")
            continue
        try:
            chunks = engine.extract_embeddings(fp)
        except Exception as exc:
            print(f"  [warn] extract failed for {fp}: {exc}")
            continue
        if not chunks:
            skipped_no_embed += 1
            continue
        for ck in chunks:
            emb = ck.get("embedding")
            if emb is None:
                continue
            embeddings.append(np.asarray(emb, dtype=np.float32))
            labels.append(int(sp_idx))

        if i % 25 == 0 or i == len(items_to_process):
            elapsed = time.time() - started
            rate = i / max(elapsed, 1e-3)
            eta = (len(items_to_process) - i) / max(rate, 1e-6)
            print(f"  [{i:>5}/{len(items_to_process)}] embeddings={len(embeddings):>6} "
                  f"rate={rate:.2f} files/s  eta={eta/60:.1f} min")

        # Periodic checkpoint of partial arrays (insurance against ctrl-c)
        if not args.dry_run and len(embeddings) - last_checkpoint_at >= args.checkpoint_every * 3:
            np.save(emb_tmp, np.asarray(embeddings, dtype=np.float32))
            np.save(lbl_tmp, np.asarray(labels, dtype=np.int32))
            last_checkpoint_at = len(embeddings)

    elapsed = time.time() - started
    print(f"\n[2/3] aggregated {len(embeddings)} embeddings in {elapsed/60:.2f} min "
          f"(skipped_no_species_idx={skipped_no_species_idx}, skipped_no_embed={skipped_no_embed})")

    if not embeddings:
        print("[FATAL] zero embeddings extracted")
        return 4

    if args.dry_run:
        per_file = len(embeddings) / max(len(items_to_process), 1)
        full_est = per_file * len(manifest)
        eta = (elapsed / max(len(items_to_process), 1)) * len(manifest)
        print(f"\nDRY RUN summary:")
        print(f"  avg embeddings per file = {per_file:.1f}")
        print(f"  estimated total embeddings = {full_est:.0f}")
        print(f"  estimated build time on {len(manifest)} files = {eta/60:.1f} min")
        print("Run again without --dry-run to actually build.")
        # Clean partial files just in case
        for tmp in (emb_tmp, lbl_tmp):
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        return 0

    print("\n[3/3] writing index files")
    emb_arr = np.asarray(embeddings, dtype=np.float32)
    lbl_arr = np.asarray(labels, dtype=np.int32)
    np.save(output_dir / "embeddings.npy", emb_arr)
    np.save(output_dir / "labels.npy", lbl_arr)
    (output_dir / "species_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "manifest_rows": len(manifest),
        "files_processed": len(items_to_process),
        "embeddings_total": int(emb_arr.shape[0]),
        "embedding_dim": int(emb_arr.shape[1]),
        "n_species_in_index": int(len(set(int(x) for x in lbl_arr.tolist()))),
        "knn_default_k": 7,
        "distance": "cosine",
        "birdnet_model": "birdnet 2.4 (tf backend)",
        "ticket": "Algo-D / P2-W3",
    }
    (output_dir / "index_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Cleanup any partial checkpoints (they are now superseded)
    for tmp in (emb_tmp, lbl_tmp):
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    print(f"  embeddings.npy       -> {emb_arr.shape} float32 ({emb_arr.nbytes/1e6:.1f} MB)")
    print(f"  labels.npy           -> {lbl_arr.shape} int32")
    print(f"  species_mapping.json -> copy of {mapping_path.name}")
    print(f"  index_meta.json      -> {meta}")
    print(f"\nDONE in {elapsed/60:.2f} min. Index dir: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
