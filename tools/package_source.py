"""Export source only; never archive the live deployment directory indiscriminately."""
import argparse
import hashlib
from pathlib import Path
import re
import sys
import tarfile
import zipfile
from urllib.parse import urlsplit
from probe import read_env

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-rc1"
FILES = ("README.md", "LICENSE", "SECURITY.md", "CHANGELOG.md", "CONTRIBUTING.md", ".gitignore",
         ".dockerignore", ".gitattributes", ".env.example", "compose.yaml", "Dockerfile",
         "requirements.txt", "requirements-dev.txt", "bridgectl", "certs/.gitkeep", "ca/.gitkeep")
PATTERNS = ("bridge/*.py", "tools/*.py", "tests/*.py", "docs/*.md", ".github/workflows/*.yml")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / ".local/releases")
    args = parser.parse_args()
    paths = {ROOT / file for file in FILES}
    for pattern in PATTERNS:
        paths.update(ROOT.glob(pattern))
    protected = []
    if (ROOT / ".env").is_file():
        env = read_env(ROOT / ".env")
        protected += [env.get("PUBLIC_API_KEY", ""), env.get("UPSTREAM_API_KEY", "")]
        protected += [env.get("PUBLIC_HOSTNAME", ""), urlsplit(env.get("UPSTREAM_BASE_URL", "")).hostname or ""]
    protected = [p.encode() for p in protected if len(p) >= 12 and ".invalid" not in p and not p.startswith("REPLACE_")]
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing source file or disallowed symlink: " + str(path.relative_to(ROOT)))
        data = path.read_bytes()
        if any(p in data for p in protected) or re.search(rb"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----", data):
            raise RuntimeError("Potential credential/private material in: " + str(path.relative_to(ROOT)))
    args.out.mkdir(parents=True, exist_ok=True)
    base = "vcf-ai-openai-bridge-" + VERSION
    prefix = "vcf-ai-openai-bridge/"
    tar_path, zip_path = args.out / (base + ".tar.gz"), args.out / (base + ".zip")
    with tarfile.open(tar_path, "w:gz") as archive, zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
        for path in sorted(paths):
            name = prefix + path.relative_to(ROOT).as_posix()
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid, info.gid, info.uname, info.gname = 0, 0, "", ""
            info.mode = 0o755 if path.name == "bridgectl" else 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
            zip_out.write(path, arcname=name)
    for path in (tar_path, zip_path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name + ".sha256").write_text(digest + "  " + path.name + "\n")
        print(path)
    print(f"SOURCE PACKAGE OK: {len(paths)} files; no .env, certificates, backups or runtime logs included.")
    print("This is an allowlist export with basic secret checks, not a complete security audit.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"PACKAGING FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
