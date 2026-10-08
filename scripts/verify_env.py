#!/usr/bin/env python3
"""
Standalone environment verification for waste_demarcation_feasibility_study.

Run it any time, in whichever interpreter you want to check:

    python scripts/verify_env.py

It does four things:
  1. Prints interpreter / platform details.
  2. Imports every required package and prints its version.
  3. Reports torch device availability (torch.cuda.is_available() and friends).
  4. Actually computes NIQE on a real image from data/processed/1024 with
     pyiqa, to prove the metric path works end to end rather than merely
     that the import succeeded.

Exit code 0 = everything good. Non-zero = something is wrong (and the
summary at the bottom says what).
"""

from __future__ import annotations

import importlib
import platform
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = PROJECT_ROOT / "data" / "processed" / "1024"

# (import name, pretty name, required?)
PACKAGES = [
    ("numpy", "numpy", True),
    ("cv2", "opencv-python", True),
    ("matplotlib", "matplotlib", True),
    ("pandas", "pandas", True),
    ("torch", "torch", True),
    ("torchvision", "torchvision", True),
    ("pyiqa", "pyiqa", True),
    ("PIL", "Pillow", True),
    ("timm", "timm (pyiqa dep)", False),
    ("piexif", "piexif", False),
]

GREEN, RED, YELLOW, BOLD, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"


def hdr(text: str) -> None:
    print(f"\n{BOLD}{'=' * 70}\n{text}\n{'=' * 70}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}[ OK ]{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    # ---------------------------------------------------------------- 1
    hdr("1. INTERPRETER")
    print(f"  python            : {sys.version.split()[0]}  ({sys.executable})")
    print(f"  platform          : {platform.platform()}")
    print(f"  machine           : {platform.machine()}")
    print(f"  project root      : {PROJECT_ROOT}")

    major, minor = sys.version_info[:2]
    if (major, minor) in {(3, 11), (3, 12)}:
        ok(f"Python {major}.{minor} is the supported target for this project")
    elif (major, minor) == (3, 10):
        warn(f"Python {major}.{minor} is older than the 3.12 target but should work")
        warnings.append(f"Python {major}.{minor} (project targets 3.12)")
    elif (major, minor) >= (3, 13):
        warn(f"Python {major}.{minor} is newer than the 3.12 target; "
             "wheels exist but you get the newest major version of every "
             "dependency, which is less well tested with pyiqa")
        warnings.append(f"Python {major}.{minor} (project targets 3.12)")
    else:
        fail(f"Python {major}.{minor} is too old")
        problems.append(f"Python {major}.{minor} unsupported")

    # Are we actually inside an env, or did this land in system Python?
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    conda_env = None
    import os
    conda_env = os.environ.get("CONDA_DEFAULT_ENV")
    if conda_env:
        ok(f"running inside conda env: {conda_env}")
        if conda_env == "base":
            warn("this is the conda 'base' env - prefer the dedicated 'wdfs' env")
            warnings.append("running in conda base rather than wdfs")
    elif in_venv:
        ok(f"running inside a virtualenv: {sys.prefix}")
    else:
        warn("NOT inside a venv or conda env - this looks like system Python")
        warnings.append("not running in an isolated environment")

    # ---------------------------------------------------------------- 2
    hdr("2. PACKAGE IMPORTS AND VERSIONS")
    mods: dict[str, object] = {}
    for import_name, pretty, required in PACKAGES:
        try:
            m = importlib.import_module(import_name)
            mods[import_name] = m
            ver = getattr(m, "__version__", None) or getattr(m, "VERSION", "?")
            ok(f"{pretty:22s} {ver}")
        except Exception as exc:
            if required:
                fail(f"{pretty:22s} import failed: {type(exc).__name__}: {exc}")
                problems.append(f"{pretty} will not import")
            else:
                warn(f"{pretty:22s} not installed ({type(exc).__name__})")
                warnings.append(f"{pretty} missing (optional)")

    # ---------------------------------------------------------------- 3
    hdr("3. TORCH DEVICE AVAILABILITY")
    torch = mods.get("torch")
    device = "cpu"
    if torch is None:
        fail("torch unavailable - skipping device checks")
    else:
        cuda_avail = bool(torch.cuda.is_available())
        print(f"  torch.cuda.is_available()      : {cuda_avail}")
        print(f"  torch.version.cuda             : {getattr(torch.version, 'cuda', None)}")
        print(f"  torch.backends.mps.is_available(): "
              f"{bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available())}")
        print(f"  torch.get_num_threads()        : {torch.get_num_threads()}")
        if cuda_avail:
            device = "cuda"
            try:
                print(f"  GPU count                      : {torch.cuda.device_count()}")
                for i in range(torch.cuda.device_count()):
                    p = torch.cuda.get_device_properties(i)
                    print(f"    [{i}] {p.name}  {p.total_memory / 1024**3:.1f} GiB")
            except Exception as exc:
                warn(f"could not enumerate GPUs: {exc}")
            ok("CUDA available - deep enhancement will run on GPU")
        else:
            ok("No CUDA. Running CPU-only - expected on this machine "
               "(AMD GPU; PyTorch has no ROCm support on Windows).")
            warnings.append("CPU-only torch: deep methods will be slow")

        # prove tensor math actually executes
        try:
            a = torch.randn(256, 256, device=device)
            b = (a @ a.T).sum().item()
            ok(f"tensor matmul on '{device}' works (checksum {b:.3f})")
        except Exception as exc:
            fail(f"tensor matmul failed: {exc}")
            problems.append("torch cannot execute basic tensor ops")

    # ---------------------------------------------------------------- 4
    hdr("4. END-TO-END pyiqa NIQE ON A REAL IMAGE")
    pyiqa = mods.get("pyiqa")
    if pyiqa is None or torch is None:
        fail("pyiqa or torch unavailable - cannot run the metric check")
        problems.append("pyiqa end-to-end check could not run")
    else:
        imgs = sorted(IMAGE_DIR.glob("*.jpg")) if IMAGE_DIR.is_dir() else []
        if not imgs:
            fail(f"no images found in {IMAGE_DIR}")
            print("        Run scripts/preprocess.py first to populate it.")
            problems.append(f"no test image in {IMAGE_DIR}")
        else:
            test_img = imgs[0]
            print(f"  test image : {test_img.name}  (of {len(imgs)} available)")
            print(f"  device     : {device}")
            print("  note       : first run downloads metric weights; "
                  "this can take a minute.")
            try:
                niqe = pyiqa.create_metric("niqe", device=device)
                score = niqe(str(test_img))
                val = float(score.item() if hasattr(score, "item") else score)
                lower_better = getattr(niqe, "lower_better", True)
                ok(f"NIQE = {val:.4f}   (lower_better={lower_better})")
                if not (0.0 < val < 100.0):
                    warn(f"NIQE {val} is outside the usual 0-100 range - inspect")
                    warnings.append("NIQE value looks unusual")
                else:
                    ok("NIQE value is in a plausible range - pyiqa works end to end")
            except Exception as exc:
                fail(f"NIQE computation failed: {type(exc).__name__}: {exc}")
                traceback.print_exc()
                problems.append("pyiqa NIQE computation failed")

            # BRISQUE too - cheap, and confirms a second metric path
            try:
                brisque = pyiqa.create_metric("brisque", device=device)
                s = brisque(str(test_img))
                ok(f"BRISQUE = {float(s.item() if hasattr(s, 'item') else s):.4f}")
            except Exception as exc:
                warn(f"BRISQUE failed ({type(exc).__name__}: {exc}) - "
                     "NIQE is the one that matters, so this is not fatal")
                warnings.append("BRISQUE unavailable")

    # ---------------------------------------------------------------- summary
    hdr("SUMMARY")
    if not problems and not warnings:
        print(f"  {GREEN}{BOLD}ALL CHECKS PASSED.{RESET} Environment is ready.")
        return 0
    if not problems:
        print(f"  {GREEN}{BOLD}PASSED{RESET} with {len(warnings)} note(s):")
        for w in warnings:
            print(f"    - {w}")
        print("\n  Nothing blocking. You can proceed.")
        return 0
    print(f"  {RED}{BOLD}{len(problems)} PROBLEM(S):{RESET}")
    for p in problems:
        print(f"    - {p}")
    if warnings:
        print(f"\n  plus {len(warnings)} note(s):")
        for w in warnings:
            print(f"    - {w}")
    print(f"\n  Fix: activate the project env first ->  conda activate wdfs")
    print(f"       or recreate it      ->  powershell -File scripts\\setup_env.ps1")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
