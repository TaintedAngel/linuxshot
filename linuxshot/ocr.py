"""Text extraction from images via tesseract."""

from .utils import has_command, run_cmd


class OcrError(Exception):
    pass


def extract_text(filepath: str, language: str = "") -> str:
    if not has_command("tesseract"):
        raise OcrError(
            "tesseract is not installed.\n"
            "  Arch:   sudo pacman -S tesseract tesseract-data-eng\n"
            "  Debian: sudo apt install tesseract-ocr\n"
            "  Fedora: sudo dnf install tesseract"
        )
    cmd = ["tesseract", filepath, "stdout"]
    if language:
        cmd += ["-l", language]
    result = run_cmd(cmd)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "loading language" in stderr or "initialize tesseract" in stderr:
            wanted = language or "eng"
            available = ", ".join(installed_languages()) or "none"
            raise OcrError(
                f"tesseract has no '{wanted}' language data "
                f"(installed: {available}).\n"
                f"  Arch:   sudo pacman -S tesseract-data-{wanted}\n"
                f"  Debian: sudo apt install tesseract-ocr-{wanted}\n"
                f"Or point LinuxShot at an installed language:\n"
                f"  linuxshot config --set ocr_language LANG"
            )
        detail = stderr.splitlines()
        raise OcrError(f"tesseract failed: {detail[-1] if detail else result.returncode}")
    return result.stdout.strip()


def installed_languages() -> list[str]:
    """Languages tesseract can actually load ('osd' is orientation
    detection, not a language)."""
    result = run_cmd(["tesseract", "--list-langs"])
    if result.returncode != 0:
        return []
    langs = [line.strip() for line in result.stdout.splitlines()]
    return [lang for lang in langs
            if lang and not lang.startswith("List of") and lang != "osd"]
