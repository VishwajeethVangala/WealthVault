"""Build the zip you upload to Azure by hand.

    python scripts/build_release_zip.py                  tests, web build, then D:\\Gravity\\wealthvault-release.zip
    python scripts/build_release_zip.py --skip-tests     skip the Python tests
    python scripts/build_release_zip.py --skip-web       reuse the existing dist/ (no npm build)
    python scripts/build_release_zip.py --out some.zip   write somewhere else

What goes in: the files git knows about, tracked or new but not ignored (so .env and client-secret files, which
.gitignore hides, can never be included by accident), plus the freshly built dist/. What stays out: the Android app, tests, CI files, design
mock-ups, saved broker tokens and sessions. It mirrors what .github/workflows/azure-app-service.yml packs.

Upload it with: az webapp deploy --resource-group <rg> --name <app> --src-path <zip> --type zip
or in the portal: your app > Advanced Tools (Kudu) > Tools > Zip Push Deploy, or Deployment Center.
"""

import argparse
import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path("D:/Gravity/wealthvault-release.zip") if sys.platform == "win32" else ROOT.parent / "wealthvault-release.zip"

# Tracked files that the server does not need.
EXCLUDE = [
    ".git/*", ".github/*", ".gitattributes", ".gitignore",
    "android/*",                      # the native app is built and published separately
    "tests/*", "*/tests/*",
    "web/node_modules/*", "Stitch Designs/*",
    "*/__pycache__/*", "*.pyc",
    "storage/blobs/*token*", "storage/blobs/*session*", "storage/blobs/indmoney_client.json",
    ".env", ".env.*", "client_secret*.json", "*.zip", "*.keystore", "*.jks",
]
KEEP = [".env.example"]  # an example with no secrets


def excluded(rel: str) -> bool:
    if rel in KEEP:
        return False
    return any(fnmatch.fnmatch(rel, pat) for pat in EXCLUDE)


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("  $", " ".join(cmd))
    # shell=True on Windows so npm.cmd resolves
    subprocess.run(cmd, cwd=cwd, check=True, shell=(sys.platform == "win32"))


def tracked_files() -> list[str]:
    # tracked files plus new ones not yet added; anything in .gitignore (.env, client secrets, dist, node_modules) is left out
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--skip-web", action="store_true")
    args = ap.parse_args()

    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print("Note: you have uncommitted changes; the zip uses the files as they are on disk right now.\n")

    if not args.skip_tests:
        print("1/3 Python tests")
        run([sys.executable, "-m", "pytest", "-q", "-x"])
    if not args.skip_web:
        print("2/3 Web build into dist/")
        web = ROOT / "web"
        if not (web / "node_modules").exists():
            run(["npm", "ci"], cwd=web)
        run(["npm", "run", "build"], cwd=web)
    if not (ROOT / "dist" / "index.html").exists():
        print("dist/index.html is missing. Run without --skip-web.")
        return 1

    print("3/3 Zip")
    files = [f for f in tracked_files() if not excluded(f) and (ROOT / f).is_file()]
    dist = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "dist").rglob("*") if p.is_file())
    names = sorted(set(files) | set(dist))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in names:
            z.write(ROOT / rel, rel)  # forward slashes, as Linux expects

    # A last look for anything that must never leave this machine.
    with zipfile.ZipFile(args.out) as z:
        bad = [n for n in z.namelist() if n == ".env" or n.startswith("client_secret") or n.endswith((".jks", ".keystore"))]
    if bad:
        args.out.unlink()
        print("Refusing: secrets found in the zip:", bad)
        return 1

    mb = args.out.stat().st_size / 1024 / 1024
    print(f"\nDone: {args.out}  ({len(names)} files, {mb:.1f} MB)")
    print("Upload it to Azure, then open the site and check Overview loads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
