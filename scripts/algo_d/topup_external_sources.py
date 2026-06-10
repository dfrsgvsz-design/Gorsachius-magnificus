"""Algo-D / P0-W1 supporting tool: top up low-sample species from non-XC sources.

Three subcommands:

  inat       Auto-download CC-licensed sounds from iNaturalist for a species
             (and its taxonomic synonyms via --also-as).
  macaulay   Generate a Macaulay Library deep-link + CSV template you can fill
             in after manually downloading per Cornell TOS. Macaulay's catalog
             API rejects anonymous bulk fetches, so we do NOT auto-download.
  import     Register a folder of audio files you already downloaded (from any
             source) into xc_expanded/manifest.json with the correct species
             label.

This script complements ``topup_low_sample_species.py`` (which talks to the
Xeno-canto v3 API). Same manifest, same on-disk layout; the ``source`` field
records where each row came from.

TAXONOMIC NOTE (important for Zoothera dauma):
  IOC v14 split ``Zoothera dauma`` into Z. dauma s.s., Z. aurea (NE Asia),
  Z. major (Amami) and Z. neilgherriensis. iNaturalist follows the split,
  so a query for "Zoothera dauma" may return zero results. Pass:
      --also-as "Zoothera aurea" --also-as "Zoothera major"
  so the script merges all four legacy-synonym records under the *legacy*
  ``--species`` label you supply, keeping species_mapping.json valid.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("[FATAL] 'requests' not installed; pip install requests")
    sys.exit(3)

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP_DATA = REPO_ROOT / "species_monitoring_platform" / "data" / "xc_expanded"
MANIFEST_PATH = SMP_DATA / "manifest.json"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"

INAT_API = "https://api.inaturalist.org/v1/observations"
ML_CATALOG_SEARCH = "https://search.macaulaylibrary.org/catalog"
ML_ASSET_MP3 = "https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset_id}/audio"
USER_AGENT = "algo-d-research/1.0 (academic biodiversity monitoring; species_monitoring_platform)"
HTTP_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 90
REQUEST_DELAY = 0.6


# ============================================================
# Shared helpers
# ============================================================

def load_manifest() -> tuple[list[dict], dict[str, int], set[str]]:
    if not MANIFEST_PATH.exists():
        print(f"[FATAL] manifest not found: {MANIFEST_PATH}")
        sys.exit(3)
    rows = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    paths: set[str] = set()
    for it in rows:
        sp = it.get("species_scientific", "")
        counts[sp] = counts.get(sp, 0) + 1
        fp = it.get("file_path")
        if fp:
            paths.add(fp)
    return rows, counts, paths


def save_manifest(rows: list[dict]) -> None:
    MANIFEST_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def write_session_log(name: str, payload: dict) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    p = ARTIFACTS_DIR / f"{name}_{stamp}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ============================================================
# iNaturalist auto-download
# ============================================================

def inat_search_observations(scientific: str, per_page: int = 100,
                             max_pages: int = 6, research_only: bool = True) -> list[dict]:
    """Return iNat observations with at least one downloadable sound."""
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    observations: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "taxon_name": scientific,
            "sounds": "true",
            "per_page": per_page,
            "page": page,
        }
        if research_only:
            params["quality_grade"] = "research"
        try:
            r = sess.get(INAT_API, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            print(f"  [warn] iNat page={page} request failed: {exc}")
            break
        if r.status_code != 200:
            print(f"  [warn] iNat page={page} HTTP {r.status_code}")
            break
        data = r.json()
        results = data.get("results", [])
        if not results:
            break
        observations.extend(results)
        total = int(data.get("total_results", 0))
        if len(observations) >= total or len(observations) >= per_page * max_pages:
            break
        time.sleep(REQUEST_DELAY)
    return observations


def _iter_sound_urls(obs: dict):
    """Yield (sound_id, url, content_type, license_code, attribution) per sound."""
    for s in obs.get("sounds", []) or []:
        url = s.get("file_url")
        if not url:
            continue
        yield (s.get("id"), url, s.get("file_content_type", "audio/mpeg"),
               s.get("license_code", "unknown"), s.get("attribution", ""))


def inat_download_one(url: str, dest: Path) -> bool:
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    try:
        r = sess.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True, allow_redirects=True)
        if r.status_code != 200:
            return False
        if "html" in r.headers.get("content-type", "").lower():
            return False
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return dest.stat().st_size > 1000
    except requests.RequestException:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


DEFAULT_ALLOWED_LICENSES = {"cc0", "cc-by", "cc-by-nc"}


def cmd_inat(args: argparse.Namespace) -> int:
    rows, counts, paths = load_manifest()
    label = args.species
    aliases = [args.species] + (args.also_as or [])
    target = args.target
    allowed = set(args.allowed_licenses) if args.allowed_licenses else DEFAULT_ALLOWED_LICENSES
    print(f"[inat] target species (manifest label): '{label}'")
    print(f"[inat] querying aliases: {aliases}")
    print(f"[inat] manifest has {counts.get(label, 0)} record(s) for '{label}', target={target}")
    print(f"[inat] allowed licenses: {sorted(allowed)} (use --allowed-licenses to override)")

    sp_dir = SMP_DATA / label.replace(" ", "_")
    if not args.dry_run:
        sp_dir.mkdir(parents=True, exist_ok=True)

    stats = {"label": label, "aliases": aliases, "target": target,
             "allowed_licenses": sorted(allowed),
             "have_before": counts.get(label, 0),
             "downloaded": 0, "from_cache": 0, "skipped_dup": 0,
             "skipped_license": 0,
             "failed": 0, "obs_seen": 0, "obs_with_sound": 0,
             "license_breakdown": {}}

    seen_inat_ids: set[int] = set()
    for alias in aliases:
        if counts.get(label, 0) >= target:
            print(f"  -> already at target ({target}), stopping alias loop")
            break
        print(f"  searching iNat for alias '{alias}'...")
        obs_list = inat_search_observations(alias)
        stats["obs_seen"] += len(obs_list)
        print(f"    iNat returned {len(obs_list)} observation(s)")
        for obs in obs_list:
            if counts.get(label, 0) >= target:
                break
            obs_id = obs.get("id")
            if obs_id in seen_inat_ids:
                continue
            seen_inat_ids.add(obs_id)
            sounds = list(_iter_sound_urls(obs))
            if not sounds:
                continue
            stats["obs_with_sound"] += 1
            for sound_id, url, ctype, lic, attrib in sounds:
                if counts.get(label, 0) >= target:
                    break
                lic_norm = (lic or "none").lower()
                stats["license_breakdown"][lic_norm] = stats["license_breakdown"].get(lic_norm, 0) + 1
                if lic_norm not in allowed:
                    stats["skipped_license"] += 1
                    if args.dry_run:
                        print(f"    [skip-lic] obs={obs_id} sound={sound_id} lic={lic_norm}")
                    continue
                ext = ".wav" if "wav" in ctype else ".mp3"
                filepath = sp_dir / f"INAT{obs_id}_{sound_id}{ext}"
                if str(filepath) in paths:
                    stats["skipped_dup"] += 1
                    continue
                if args.dry_run:
                    print(f"    [dry] obs={obs_id} sound={sound_id} {lic_norm} {url}")
                    continue
                if filepath.exists() and filepath.stat().st_size > 1000:
                    stats["from_cache"] += 1
                else:
                    ok = inat_download_one(url, filepath)
                    time.sleep(REQUEST_DELAY)
                    if not ok:
                        stats["failed"] += 1
                        print(f"    [fail] obs={obs_id} sound={sound_id}")
                        continue
                    stats["downloaded"] += 1
                entry = {
                    "file_path": str(filepath),
                    "species_scientific": label,
                    "species_chinese": "",
                    "species_english": obs.get("taxon", {}).get("preferred_common_name", ""),
                    "xc_id": "",
                    "inat_observation_id": obs_id,
                    "inat_sound_id": sound_id,
                    "inat_alias_used": alias,
                    "license": lic,
                    "attribution": attrib,
                    "quality": "iNat-research",
                    "country": (obs.get("place_guess") or "").split(",")[-1].strip(),
                    "source": "inaturalist",
                }
                rows.append(entry)
                paths.add(str(filepath))
                counts[label] = counts.get(label, 0) + 1
                print(f"    [ok]  {filepath.name}  lic={lic}")
                if not args.dry_run:
                    save_manifest(rows)

    stats["have_after"] = counts.get(label, 0)
    log = write_session_log("topup_inat", {
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "manifest_rows_after": len(rows),
        "stats": stats,
    })
    print(f"\n[inat] DONE. have_before={stats['have_before']} have_after={stats['have_after']}"
          f" downloaded={stats['downloaded']} cached={stats['from_cache']}"
          f" failed={stats['failed']} skipped_license={stats['skipped_license']}")
    print(f"[inat] license breakdown (seen): {stats['license_breakdown']}")
    print(f"[inat] session log: {log}")
    return 0


# ============================================================
# Macaulay metadata-only (no auto-download)
# ============================================================

def cmd_macaulay(args: argparse.Namespace) -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    base = ARTIFACTS_DIR / f"macaulay_{args.species.replace(' ', '_')}_{stamp}"

    # 1) deep link into the Macaulay catalog UI (works in any browser)
    qparams = {
        "mediaType": "audio",
        "sort": "rating_rank_desc",
        "q": args.species,
    }
    if args.ebird_code:
        qparams["taxonCode"] = args.ebird_code
    deep_link = f"{ML_CATALOG_SEARCH}?{urllib.parse.urlencode(qparams)}"

    # 2) CSV template the user can fill in after manually picking assets
    csv_path = base.with_suffix(".csv")
    csv_lines = [
        "# Algo-D Macaulay Library manual import template",
        f"# species_scientific = {args.species}",
        f"# generated_at_utc   = {datetime.now(timezone.utc).isoformat()}",
        "# Workflow:",
        "#   1) Open the deep-link URL printed by this script in a browser",
        "#   2) Sign in with your Cornell Lab account (required by ML TOS)",
        "#   3) Pick recordings, click the download button, save files to a folder",
        "#   4) Optionally fill in the rows below with asset_id, quality, country",
        "#   5) Run:",
        f"#        python {Path(__file__).name} import --species \"{args.species}\" --folder <download_folder>",
        "#",
        "asset_id,quality,country,notes",
    ]
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    # 3) HTML brief with the link + TOS reminders + 5 sample direct-download URLs
    #    (the sample URLs are *predictable from asset ID*; we don't have a list yet)
    html_path = base.with_suffix(".html")
    html_path.write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Macaulay top-up :: {args.species}</title>
<style>body{{font-family:sans-serif;max-width:820px;margin:24px auto;line-height:1.5}}
code{{background:#f4f4f4;padding:1px 4px;border-radius:3px}}
.warn{{background:#fff3cd;padding:10px;border-left:4px solid #f5c518;margin:10px 0}}</style>
</head><body>
<h1>Macaulay Library top-up for <i>{args.species}</i></h1>

<p><a href="{deep_link}" target="_blank">Open Macaulay catalog search</a></p>

<div class="warn"><b>Cornell Lab Terms of Use:</b> Macaulay Library media is downloadable
for research/education only with attribution. Bulk programmatic download is not permitted
without a data partner agreement. This script therefore <b>never auto-downloads</b> from
Macaulay; download manually with your Cornell Lab account.</div>

<h2>After downloading</h2>
<ol>
  <li>Save the audio files to one folder, e.g. <code>F:\\ml_dauma_dump\\</code></li>
  <li>(Optional) fill in <code>{csv_path.name}</code> with asset_id / quality / country</li>
  <li>Run:
    <pre>python scripts/algo_d/topup_external_sources.py import \\
  --species "{args.species}" \\
  --folder F:\\ml_dauma_dump\\ \\
  --source macaulay</pre>
  </li>
</ol>

<h2>Asset URL pattern (if you have asset IDs)</h2>
<p>Direct download URL for a known asset id <code>{{asset_id}}</code>:</p>
<pre>{ML_ASSET_MP3.format(asset_id='{asset_id}')}</pre>

<h2>Attribution requirement</h2>
<p>Every imported Macaulay asset gets <code>"license": "Macaulay/Cornell-Lab"</code> and
<code>"attribution": "Macaulay Library, Cornell Lab of Ornithology, asset ML&lt;ID&gt;"</code>
in the manifest. Honor these when publishing trained-model outputs.</p>
</body></html>
""", encoding="utf-8")

    log = write_session_log("topup_macaulay", {
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "species": args.species,
        "ebird_code": args.ebird_code,
        "deep_link": deep_link,
        "csv_template": str(csv_path),
        "html_brief": str(html_path),
        "tos_note": "Manual download only per Cornell Lab TOS.",
    })
    print(f"[macaulay] deep link : {deep_link}")
    print(f"[macaulay] csv tmpl  : {csv_path}")
    print(f"[macaulay] html brief: {html_path}")
    print(f"[macaulay] session   : {log}")
    print("\nManually download per Cornell TOS, then run the 'import' subcommand.")
    return 0


# ============================================================
# Folder import (manual sources, including Macaulay)
# ============================================================

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a")


def cmd_import(args: argparse.Namespace) -> int:
    folder = Path(args.folder).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"[FATAL] folder not found: {folder}")
        return 3
    label = args.species
    source = args.source
    rows, counts, paths = load_manifest()
    print(f"[import] label='{label}'  source='{source}'  folder='{folder}'")

    sp_dir = SMP_DATA / label.replace(" ", "_")
    sp_dir.mkdir(parents=True, exist_ok=True)

    stats = {"label": label, "source": source, "have_before": counts.get(label, 0),
             "copied": 0, "in_place": 0, "skipped_dup": 0, "ignored_ext": 0}

    for src in sorted(folder.iterdir()):
        if not src.is_file():
            continue
        if src.suffix.lower() not in AUDIO_EXTS:
            stats["ignored_ext"] += 1
            continue
        prefix = {"macaulay": "ML", "birdnet": "BN", "manual": "MAN"}.get(source, "IMP")
        new_name = f"{prefix}_{src.stem}{src.suffix.lower()}"
        dest = sp_dir / new_name
        if str(dest) in paths:
            stats["skipped_dup"] += 1
            continue
        if args.in_place:
            dest = src
            stats["in_place"] += 1
        else:
            shutil.copy2(src, dest)
            stats["copied"] += 1
        entry = {
            "file_path": str(dest),
            "species_scientific": label,
            "species_chinese": "",
            "species_english": "",
            "xc_id": "",
            "source": source,
            "imported_from": str(src),
            "license": ("Macaulay/Cornell-Lab" if source == "macaulay"
                        else args.license or "unknown"),
            "attribution": args.attribution or "",
            "quality": "manual-import",
            "country": "",
        }
        rows.append(entry)
        paths.add(str(dest))
        counts[label] = counts.get(label, 0) + 1
        print(f"  [ok] {src.name} -> {dest.name}")
    save_manifest(rows)
    stats["have_after"] = counts.get(label, 0)
    log = write_session_log(f"topup_import_{source}", {
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "folder": str(folder),
        "manifest_rows_after": len(rows),
        "stats": stats,
    })
    print(f"\n[import] DONE. have_before={stats['have_before']} have_after={stats['have_after']}"
          f"  copied={stats['copied']}  in_place={stats['in_place']}  dup={stats['skipped_dup']}"
          f"  ignored={stats['ignored_ext']}")
    print(f"[import] session log: {log}")
    return 0


# ============================================================
# CLI
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_inat = sub.add_parser("inat", help="auto-download CC-licensed sounds from iNaturalist")
    p_inat.add_argument("--species", required=True,
                        help="manifest label (legacy / lumped name). e.g. 'Zoothera dauma'")
    p_inat.add_argument("--also-as", action="append", default=[],
                        help="taxonomic synonym to also query. e.g. --also-as 'Zoothera aurea'")
    p_inat.add_argument("--target", type=int, default=50)
    p_inat.add_argument("--allowed-licenses", action="append", default=[],
                        help="license code to accept; repeatable. defaults: cc0, cc-by, cc-by-nc")
    p_inat.add_argument("--dry-run", action="store_true")
    p_inat.set_defaults(func=cmd_inat)

    p_ml = sub.add_parser("macaulay", help="generate deep link + CSV template (no auto-download)")
    p_ml.add_argument("--species", required=True,
                      help="scientific name to display in the brief")
    p_ml.add_argument("--ebird-code", default="",
                      help="optional eBird species code, e.g. 'scathr1' for tighter search")
    p_ml.set_defaults(func=cmd_macaulay)

    p_imp = sub.add_parser("import", help="register a folder of audio files into manifest")
    p_imp.add_argument("--species", required=True,
                       help="manifest label to assign to every file in the folder")
    p_imp.add_argument("--folder", required=True,
                       help="folder containing the audio files you downloaded")
    p_imp.add_argument("--source", default="manual",
                       choices=["macaulay", "birdnet", "manual"])
    p_imp.add_argument("--license", default="",
                       help="license string to record (default depends on --source)")
    p_imp.add_argument("--attribution", default="",
                       help="attribution string to record")
    p_imp.add_argument("--in-place", action="store_true",
                       help="do not copy; reference the files where they are")
    p_imp.set_defaults(func=cmd_import)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
