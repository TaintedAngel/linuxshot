"""Detect likely secrets in a screenshot.

Runs tesseract in TSV mode to get word bounding boxes, then flags words
that look like credentials: emails, API-key prefixes, key=value pairs,
IP addresses, and long high-entropy tokens. The editor pixelates the
matches as one undoable step, so a false positive costs a single
Ctrl+Z - which is why the patterns lean toward catching too much
rather than too little.
"""

import re
from dataclasses import dataclass

from .ocr import OcrError
from .utils import has_command, run_cmd

MIN_CONFIDENCE = 40

# Well-known credential prefixes: Stripe, GitHub, GitLab, Slack, AWS,
# Google, JWTs.
KEY_PREFIXES = (
    "sk-", "sk_", "pk_", "rk_",
    "ghp_", "gho_", "ghu_", "ghs_", "github_pat_",
    "glpat-", "xoxb-", "xoxp-", "xoxs-",
    "AKIA", "ASIA", "AIza", "ya29.", "eyJ",
)

EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$")
KEY_VALUE = re.compile(
    r"(?i)^(api[_-]?key|apikey|access[_-]?key|token|secret|"
    r"passw(?:or)?d|auth(?:orization)?)=\S+$")
LONG_TOKEN = re.compile(r"^[A-Za-z0-9_\-+/=]{24,}$")
DATE_LIKE = re.compile(r"\d{4}-\d{2}-\d{2}")
FILE_LIKE = re.compile(r"\.(png|jpe?g|webp|gif|mp4|webm|txt|md|py|sh|conf)$",
                       re.IGNORECASE)


@dataclass
class SensitiveRegion:
    x: int
    y: int
    width: int
    height: int
    label: str
    text: str


def classify(word: str) -> str | None:
    """The kind of secret *word* looks like, or None."""
    w = word.strip().strip("\"'`,;()[]{}")
    if len(w) < 6:
        return None
    if EMAIL.match(w):
        return "email"
    if IPV4.match(w):
        return "ip address"
    if KEY_VALUE.match(w):
        return "credential"
    for prefix in KEY_PREFIXES:
        if w.startswith(prefix) and len(w) >= 12:
            return "api key"
    if (LONG_TOKEN.match(w)
            and sum(c.isdigit() for c in w) >= 3
            and any(c.isalpha() for c in w)
            and not DATE_LIKE.search(w)
            and not FILE_LIKE.search(w)):
        return "token"
    return None


def find_sensitive_regions(filepath: str, language: str = "") -> list[SensitiveRegion]:
    """OCR *filepath* and return bounding boxes of suspected secrets."""
    if not has_command("tesseract"):
        raise OcrError(
            "Secret detection needs tesseract (see 'linuxshot ocr' docs).")
    cmd = ["tesseract", filepath, "stdout", "tsv"]
    if language:
        cmd[3:3] = ["-l", language]
    result = run_cmd(cmd)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        raise OcrError(f"tesseract failed: {detail[-1] if detail else '?'}")
    return _scan_tsv(result.stdout)


def _scan_tsv(tsv: str) -> list[SensitiveRegion]:
    regions = []
    for line in tsv.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) < 12 or fields[0] != "5":  # level 5 = word
            continue
        try:
            left, top, width, height = (int(fields[i]) for i in range(6, 10))
            confidence = float(fields[10])
        except ValueError:
            continue
        text = fields[11].strip()
        if confidence < MIN_CONFIDENCE or not text:
            continue
        label = classify(text)
        if label:
            regions.append(SensitiveRegion(left, top, width, height, label, text))
    return regions
