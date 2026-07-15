"""Detect likely secrets in a screenshot.

tesseract's TSV output provides word bounding boxes, but its idea of a
"word" is unstable on screenshots: anti-aliasing can split
admin@host.com into two fragments on one capture and not the next. So
detection works on reconstructed tokens - fragments on the same line
with a sub-character gap are merged before classification - and the
whole thing runs twice with different page segmentation modes (auto
and uniform-block, which suits terminal text), unioning the results.

Patterns lean toward catching too much rather than too little: the
editor applies all matches as one undoable step, so a false positive
costs a single Ctrl+Z while a false negative leaks a credential.
"""

import re
from dataclasses import dataclass

from .ocr import OcrError
from .utils import has_command, run_cmd

MIN_CONFIDENCE = 30
PSM_MODES = ("3", "6")  # auto, uniform block

# Well-known credential prefixes: Stripe, GitHub, GitLab, Slack, AWS,
# Google, JWTs.
KEY_PREFIXES = (
    "sk-", "sk_", "pk_", "rk_",
    "ghp_", "gho_", "ghu_", "ghs_", "github_pat_",
    "glpat-", "xoxb-", "xoxp-", "xoxs-",
    "AKIA", "ASIA", "AIza", "ya29.", "eyJ",
)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z][\w.-]*")
IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$")
KEY_VALUE = re.compile(
    r"(?i)^(api[_-]?key|apikey|access[_-]?key|token|secret|"
    r"passw(?:or)?d|auth(?:orization)?)[=:]\S+$")
# A bare credential keyword; whatever token follows it on the line is
# treated as the secret ("password: hunter2", "Bearer eyJ...").
KEY_WORD = re.compile(
    r"(?i)^(api[_-]?key|apikey|access[_-]?key|token|secret|"
    r"passw(?:or)?d|auth(?:orization)?|bearer)[=:]?$")
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


@dataclass
class _Token:
    text: str
    x: int
    y: int
    width: int
    height: int


def classify(word: str) -> str | None:
    """The kind of secret *word* looks like, or None."""
    w = word.strip().strip("\"'`,;()[]{}")
    if len(w) < 6:
        return None
    if EMAIL.search(w):
        return "email"
    if IPV4.match(w):
        return "ip address"
    if KEY_VALUE.match(w):
        return "credential"
    for prefix in KEY_PREFIXES:
        index = w.find(prefix)
        if index >= 0 and len(w) - index >= 12:
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

    regions: list[SensitiveRegion] = []
    errors: list[str] = []
    for psm in PSM_MODES:
        cmd = ["tesseract", filepath, "stdout", "--psm", psm, "tsv"]
        if language:
            cmd[2:2] = ["-l", language]
        result = run_cmd(cmd)
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            errors.append(detail[-1] if detail else "?")
            continue
        regions.extend(_scan_tsv(result.stdout))

    if errors and not regions and len(errors) == len(PSM_MODES):
        raise OcrError(f"tesseract failed: {errors[-1]}")
    return _dedupe(regions)


def _scan_tsv(tsv: str) -> list[SensitiveRegion]:
    regions = []
    for line_tokens in _lines(tsv):
        tokens = _merge_fragments(line_tokens)
        flag_next = False
        for token in tokens:
            label = classify(token.text)
            if label is None and flag_next and len(token.text.strip()) >= 4:
                label = "credential"
            flag_next = bool(KEY_WORD.match(token.text.strip().strip("\"'`,;")))
            if label:
                regions.append(SensitiveRegion(
                    token.x, token.y, token.width, token.height,
                    label, token.text))
    return regions


def _lines(tsv: str) -> list[list[_Token]]:
    """Word tokens grouped by visual line, in reading order."""
    lines: dict[tuple, list[_Token]] = {}
    for row in tsv.splitlines()[1:]:
        fields = row.split("\t")
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
        key = tuple(fields[1:5])  # page, block, paragraph, line
        lines.setdefault(key, []).append(_Token(text, left, top, width, height))
    return [sorted(tokens, key=lambda t: t.x) for tokens in lines.values()]


def _merge_fragments(tokens: list[_Token]) -> list[_Token]:
    """Rejoin fragments tesseract split despite no visual gap: if the
    space between two neighbours is under ~three-quarters of a character
    width, they are one token.
    """
    if not tokens:
        return []
    merged = [tokens[0]]
    for token in tokens[1:]:
        prev = merged[-1]
        char_width = prev.width / max(len(prev.text), 1)
        gap = token.x - (prev.x + prev.width)
        if gap <= max(4, char_width * 0.75):
            bottom = max(prev.y + prev.height, token.y + token.height)
            prev.text += token.text
            prev.width = token.x + token.width - prev.x
            prev.y = min(prev.y, token.y)
            prev.height = bottom - prev.y
        else:
            merged.append(token)
    return merged


def _dedupe(regions: list[SensitiveRegion]) -> list[SensitiveRegion]:
    """Union of the OCR passes: drop regions mostly covered by one we
    already kept."""
    kept: list[SensitiveRegion] = []
    for region in regions:
        if not any(_mostly_overlaps(region, other) for other in kept):
            kept.append(region)
    return kept


def _mostly_overlaps(a: SensitiveRegion, b: SensitiveRegion) -> bool:
    overlap_w = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    overlap_h = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if overlap_w <= 0 or overlap_h <= 0:
        return False
    overlap = overlap_w * overlap_h
    smaller = min(a.width * a.height, b.width * b.height)
    return smaller > 0 and overlap / smaller > 0.5
