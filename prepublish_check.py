"""Conservative local release scan and static report checks. Never prints matches."""
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
EXCLUDE = {"__pycache__", ".git", ".venv"}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "aws_access_key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "api_key_literal": re.compile(r"(?i)(?:api[_-]?key|password|secret[_-]?key)\s*[:=]\s*[\"'][^\n\"']{8,}[\"']"),
    "email_address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn_shape": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "payment_card_shape": re.compile(r"(?<![.\d])\b(?:\d[ -]?){15,16}\b(?![.\d])"),
}
TEXT_SUFFIXES = {".py", ".md", ".json", ".csv", ".html", ".svg", ".txt"}
ALLOWED_SUFFIXES = TEXT_SUFFIXES | {".zip"}


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.counts = {}
        self.references = []
        self.viewport = False
        self.lang = False
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.counts[tag] = self.counts.get(tag, 0) + 1
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang") == "en"
        if tag == "meta" and attributes.get("name") == "viewport":
            self.viewport = "width=device-width" in attributes.get("content", "")
        if tag in {"script", "iframe", "form"}:
            self.errors.append("Unexpected active element")
        if tag in {"a", "img"}:
            self.references.append(attributes.get("href" if tag == "a" else "src", ""))
        if tag == "img" and not attributes.get("alt"):
            self.errors.append("Image lacks alternate text")
        if tag in {"section", "table", "tr", "th", "td", "pre", "style", "h1", "h2", "p", "div", "main"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in {"section", "table", "tr", "th", "td", "pre", "style", "h1", "h2", "p", "div", "main"}:
            if not self.stack or self.stack[-1] != tag:
                self.errors.append("Unbalanced layout tag: " + tag)
            else:
                self.stack.pop()


def scan_text(name, data, findings):
    if Path(name).suffix.lower() not in TEXT_SUFFIXES and Path(name).name != ".gitignore":
        findings.append({"file": name, "check": "unexpected_file_type"})
        return
    text = data.decode("utf-16" if data.startswith((bytes.fromhex("fffe"), bytes.fromhex("feff"))) else "utf-8")
    for label, pattern in PATTERNS.items():
        # This check's pattern definitions are not credential literals.
        if Path(name).name == "prepublish_check.py" and label == "api_key_literal":
            continue
        if pattern.search(text):
            findings.append({"file": name, "check": label})


def run():
    findings = []
    files = [p for p in sorted(ROOT.rglob("*")) if p.is_file() and not EXCLUDE.intersection(p.parts)]
    archive_members = 0
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        if path.name.startswith(".env") or path.name in {"credentials", "id_rsa", "id_ed25519"}:
            findings.append({"file": name, "check": "sensitive_filename"})
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if not member.is_dir():
                        archive_members += 1
                        scan_text(name + "/" + member.filename, archive.read(member), findings)
        else:
            scan_text(name, path.read_bytes(), findings)
    html_checks = []
    for name in ("artifacts/report.html", "refinement/report.html"):
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        parser = ReportParser()
        parser.feed(text)
        if parser.stack:
            parser.errors.append("Unclosed layout tags")
        for reference in parser.references:
            if not reference or "://" in reference or reference.startswith(("/", "\\")):
                parser.errors.append("Nonlocal report reference")
            elif not (path.parent / reference).resolve().is_relative_to(ROOT) or not (path.parent / reference).is_file():
                parser.errors.append("Missing or out-of-project report link")
        passed = parser.lang and parser.viewport and parser.counts.get("h1") == 1 and not parser.errors
        if not passed:
            findings.append({"file": name, "check": "static_html"})
        html_checks.append({"file": name, "passed": passed, "language": parser.lang,
                            "responsive_viewport": parser.viewport, "h1_count": parser.counts.get("h1"),
                            "local_references_checked": parser.references, "errors": parser.errors,
                            "visual_browser_qa": "unverified"})
    report = {"passed": not findings, "files_scanned": len(files),
              "archive_text_members_scanned": archive_members,
              "findings_without_values": findings, "html_checks": html_checks,
              "limitations": "Heuristic scan, not a guarantee. Only authorized name Christopher Infante and GitHub account cinfante7 are intended personal identifiers. No browser rendering reviewed."}
    (ROOT / "prepublish-checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return not findings


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
