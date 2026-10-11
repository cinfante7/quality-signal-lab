"""Package only this project; verify original evidence and record file identities."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
original_zip = root.parent / "quality-signal-lab-oct2026.zip"
release_zip = root.parent / "quality-signal-lab-revision2.zip"
manifest_path = root / "RELEASE-MANIFEST-v2.json"
if release_zip.exists():
    raise FileExistsError("Preserve existing release ZIP; choose a new release name")
original_checks = {}
with zipfile.ZipFile(original_zip) as archive:
    for path in sorted((root / "artifacts").iterdir()):
        if path.is_file():
            name = path.relative_to(root).as_posix()
            before = hashlib.sha256(archive.read(name)).hexdigest()
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            if before != after:
                raise ValueError(f"Original artifact changed: {name}")
            original_checks[name] = after
    original_source_unchanged = archive.read("quality_lab.py") == (root / "quality_lab.py").read_bytes()
    if not original_source_unchanged:
        raise ValueError("Original implementation changed")
files = [p for p in sorted(root.rglob("*")) if p.is_file()
         and "__pycache__" not in p.parts and ".git" not in p.parts
         and p != manifest_path]
manifest = {
    "revision": 2, "original_zip_sha256": hashlib.sha256(original_zip.read_bytes()).hexdigest(),
    "original_artifacts_unchanged": original_checks,
    "original_source_unchanged": original_source_unchanged,
    "sha256": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
with zipfile.ZipFile(release_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files + [manifest_path]:
        archive.write(path, path.relative_to(root).as_posix())
with zipfile.ZipFile(release_zip) as archive:
    if archive.testzip() is not None:
        raise ValueError("Archive integrity failed")
print(json.dumps({"archive": str(release_zip), "files": len(files) + 1,
                  "sha256": hashlib.sha256(release_zip.read_bytes()).hexdigest(),
                  "original_evidence_preserved": True}, indent=2))
