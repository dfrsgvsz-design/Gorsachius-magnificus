"""
Build a Windows desktop bundle for the Biodiversity Field Survey Platform.

Default mode packages the current PyTorch runtime.
Lite mode keeps the same shell but expects an ONNX runtime flow.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
FRONTEND_DIST = FRONTEND / "dist"
STATIC_DIR = BACKEND / "static"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
RUNTIME_STAGING = BUILD_DIR / "runtime_staging"
LAUNCHER = ROOT / "launcher.py"
EXE_SMOKE = ROOT / "scripts" / "exe_smoke.py"

REQUIRED_RUNTIME_FILES = [
    BACKEND / "checkpoints" / "best_model.pth",
    BACKEND / "checkpoints" / "species_mapping.json",
    BACKEND / "checkpoints" / "calibration.json",
    BACKEND / "data" / "china_birds.json",
]

OPTIONAL_RUNTIME_FILES = [
    BACKEND / "checkpoints" / "best_teacher.pth",
]


def step(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"{title}")
    print(f"{'=' * 72}")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    resolved = list(cmd)
    if os.name == "nt" and resolved and resolved[0] == "npm":
        resolved[0] = "npm.cmd"
    print(">", " ".join(resolved))
    subprocess.run(resolved, cwd=str(cwd or ROOT), check=True)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        step("Installing PyInstaller")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def stop_running_bundle(app_name: str) -> None:
    """Stop any running packaged app process so Windows can replace the files."""
    if os.name != "nt":
        return
    candidates = [app_name, f"{app_name}.exe"]
    for image_name in candidates:
        subprocess.run(
            ["taskkill", "/IM", image_name, "/F"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    time.sleep(1)


def ensure_frontend(skip_frontend: bool) -> None:
    if skip_frontend:
        step("Skipping frontend build")
        return

    step("Building frontend")
    if not (FRONTEND / "package.json").exists():
        raise FileNotFoundError("frontend/package.json not found")

    if (FRONTEND / "package-lock.json").exists():
        run(["npm", "install"], cwd=FRONTEND)
    else:
        run(["npm", "install"], cwd=FRONTEND)
    run(["npm", "run", "build"], cwd=FRONTEND)

    if not FRONTEND_DIST.exists():
        raise FileNotFoundError("frontend/dist was not produced by the build")


def copy_frontend_to_static() -> None:
    step("Syncing frontend bundle into backend/static")
    if STATIC_DIR.exists():
        shutil.rmtree(STATIC_DIR)
    shutil.copytree(FRONTEND_DIST, STATIC_DIR)
    print(f"Copied {FRONTEND_DIST} -> {STATIC_DIR}")


def validate_runtime_files(lite: bool) -> None:
    step("Validating runtime assets")
    missing = [path for path in REQUIRED_RUNTIME_FILES if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required runtime files:\n" + "\n".join(str(path) for path in missing))

    if lite:
        onnx_model = BACKEND / "checkpoints" / "model.onnx"
        if not onnx_model.exists():
            print("Lite build note: model.onnx is missing; the lite bundle shell can build, but inference will not work until ONNX assets are added.")


def reset_runtime_staging() -> None:
    if RUNTIME_STAGING.exists():
        shutil.rmtree(RUNTIME_STAGING)
    (RUNTIME_STAGING / "backend" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (RUNTIME_STAGING / "backend" / "data" / "detections").mkdir(parents=True, exist_ok=True)
    (RUNTIME_STAGING / "backend" / "static").mkdir(parents=True, exist_ok=True)


def stage_runtime_files(lite: bool) -> None:
    step("Staging runtime files")
    reset_runtime_staging()

    for source in REQUIRED_RUNTIME_FILES + OPTIONAL_RUNTIME_FILES:
        if source.exists():
            destination = RUNTIME_STAGING / "backend" / source.relative_to(BACKEND)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    if lite:
        onnx_path = BACKEND / "checkpoints" / "model.onnx"
        if onnx_path.exists():
            destination = RUNTIME_STAGING / "backend" / "checkpoints" / onnx_path.name
            shutil.copy2(onnx_path, destination)

    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, RUNTIME_STAGING / "backend" / "static", dirs_exist_ok=True)

    # Start packaged apps with a clean detections store.
    detections_db = RUNTIME_STAGING / "backend" / "data" / "detections" / "detections.db"
    detections_db.touch()


def build_with_pyinstaller(lite: bool) -> Path:
    step("Running PyInstaller")
    app_name = "BirdSoundPlatform_Lite" if lite else "BirdSoundPlatform"
    stop_running_bundle(app_name)

    common_hidden_imports = [
        "main",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "pydantic",
        "starlette",
        "librosa",
        "soundfile",
        "sklearn",
        "sklearn.cluster",
        "sklearn.decomposition",
        "scipy.special",
        "scipy.spatial",
        "scipy.spatial.distance",
        "numpy",
        "matplotlib",
        "PIL",
    ]

    hidden_imports = list(common_hidden_imports)
    excludes: list[str] = []
    if lite:
        hidden_imports.append("onnxruntime")
        excludes.extend(["torch", "torchaudio", "torchvision", "caffe2"])
    else:
        hidden_imports.extend(["torch", "torchaudio", "torchvision"])

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        app_name,
        "--onedir",
        "--console",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / "pyinstaller"),
        "--specpath",
        str(BUILD_DIR / "spec"),
        "--paths",
        str(BACKEND),
    ]

    for module_name in hidden_imports:
        cmd.extend(["--hidden-import", module_name])

    for module_name in excludes:
        cmd.extend(["--exclude-module", module_name])

    staged_backend = RUNTIME_STAGING / "backend"
    cmd.extend(["--add-data", f"{staged_backend}{';'}backend"])
    cmd.append(str(LAUNCHER))

    run(cmd, cwd=ROOT)
    return DIST_DIR / app_name


def print_summary(output_dir: Path, lite: bool) -> None:
    step("Build complete")
    exe_name = f"{output_dir.name}.exe"
    print(f"Output directory: {output_dir}")
    print(f"Executable: {output_dir / exe_name}")
    print("If the browser does not open automatically, check output/last-launch-url.txt inside the app directory after launch.")
    if lite:
        print("Lite mode reminder: ONNX assets must be present before inference can work.")
    else:
        print("Full mode reminder: package size will be large because it includes the PyTorch runtime.")


def smoke_test_executable(output_dir: Path) -> None:
    step("Smoke-testing packaged executable")
    exe_path = output_dir / f"{output_dir.name}.exe"
    if not EXE_SMOKE.exists():
        raise FileNotFoundError(f"Smoke test script not found: {EXE_SMOKE}")
    run([sys.executable, str(EXE_SMOKE), "--exe", str(exe_path)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Biodiversity Field Survey Platform desktop bundle")
    parser.add_argument("--lite", action="store_true", help="Build the lite shell for ONNX-based inference")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip npm build and reuse the current frontend/dist")
    parser.add_argument("--smoke-test", action="store_true", help="Launch the packaged executable and verify the main routes")
    args = parser.parse_args()

    ensure_pyinstaller()
    ensure_frontend(skip_frontend=args.skip_frontend)
    copy_frontend_to_static()
    validate_runtime_files(lite=args.lite)
    stage_runtime_files(lite=args.lite)
    output_dir = build_with_pyinstaller(lite=args.lite)
    if args.smoke_test:
        smoke_test_executable(output_dir)
    print_summary(output_dir, lite=args.lite)


if __name__ == "__main__":
    main()
