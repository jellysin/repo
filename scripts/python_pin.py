"""Refuse an interpreter from another minor line than the one .python-version pins."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN_FILE = ROOT / ".python-version"
PIN = re.compile(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})")


class InterpreterError(Exception):
    """The running interpreter is not the pinned one, or the pin cannot be read."""


def pinned(path):
    """Return the pinned version as three integers; refuse a missing file and anything but one full version."""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError as error:
        raise InterpreterError(f"Cannot read {path}: {error}") from error
    match = PIN.fullmatch(text)
    if not match:
        raise InterpreterError(f"{path} must hold one full version such as 3.14.8, found {text!r}")
    return tuple(int(part) for part in match.groups())


def check(pin, running):
    """Return a note for a differing patch level, an empty string for an equal version; refuse another minor line."""
    if tuple(running[:2]) != tuple(pin[:2]):
        raise InterpreterError(
            f"Python {running[0]}.{running[1]} is running; .python-version pins the {pin[0]}.{pin[1]} line"
        )
    if tuple(running[:3]) != tuple(pin):
        return f"python-pin: pin {pin[0]}.{pin[1]}.{pin[2]}, running {running[0]}.{running[1]}.{running[2]}"
    return ""


def main(path=PIN_FILE, running=sys.version_info):
    """Return 0 when the running interpreter is on the pinned minor line, 2 otherwise."""
    try:
        note = check(pinned(path), running)
    except InterpreterError as error:
        print(f"python-pin: {error}", file=sys.stderr)
        return 2
    if note:
        print(note, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
