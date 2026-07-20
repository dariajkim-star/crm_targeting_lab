"""Freshness metadata for pipeline stage outputs (AD-13).

Every stage output gets a sibling ``<output>.meta.json`` recording where it came
from. Every stage verifies its INPUTS' meta before running. Together these turn
"stale partial rerun" - the mart quietly mixing new features with old
probabilities - from a silent data defect into an immediate, named failure.

Definitions fixed here (do not reinterpret in later stories):

- ``config_hash`` is the SHA-256 of the BYTES of ``crm/config.py``. Not a hash
  of the values: a comment-only edit changes the hash on purpose, because
  over-invalidating is cheap and missing a real change is not.
- ``code_commit`` is best-effort context. It may be None (no git, detached
  checkout); freshness decisions NEVER depend on it.
- A stage is identified by its ``stage`` string (e.g. ``"01_download"``), not by
  filename conventions - filenames change, the contract should not.

KNOWN LIMITATION (story 1-1b review, scheduled for 1-3):
``build_meta`` records each input's SHA-256, but ``verify_inputs`` does NOT yet
compare those recorded hashes against the inputs as they stand now. So the
canonical AD-13 scenario - someone edits stage 02's CODE and reruns 02 and 05
while a colleague reruns only 05 - passes today whenever ``crm/config.py`` is
unchanged. Closing it needs the CONSUMING stage to compare its own previous
output meta against the current inputs (``is_output_stale(output, inputs)``),
which only becomes testable once a stage actually consumes another's output
(story 1-3). Until then this module catches config drift and wrong-producer
inputs, not code-driven staleness.

All functions are stateless and pure apart from reading the files they are
given (AD-1). Writing to disk goes through ``crm.common.atomic`` - that module
owns the write MECHANISM, while the pipeline layer owns the policy of what is
written where (AD-9, convention amended in story 1-1b review).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

_META_SUFFIX = ".meta.json"


class StaleInputError(RuntimeError):
    """An input failed freshness verification. Rerun its producing stage."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    """Content hash of a file, streamed so large parquet files are fine."""
    if not path.is_file():
        # Without this a directory argument surfaces as IsADirectoryError /
        # PermissionError far from the caller that passed the wrong path.
        raise ValueError(f"not a file: {path}")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_hash() -> str:
    """SHA-256 of crm/config.py's bytes - THE staleness reference (see module doc)."""
    from crm import config

    return sha256_bytes(Path(config.__file__).read_bytes())


def code_commit() -> str | None:
    """Current git HEAD, or None when unavailable. Context only, never a gate."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def meta_path_for(output: Path) -> Path:
    """``data/x.parquet`` -> ``data/x.parquet.meta.json``."""
    return output.with_suffix(output.suffix + _META_SUFFIX)


def build_meta(stage: str, inputs: Iterable[Path], rows: int) -> dict:
    """Assemble the meta payload for one stage output.

    ``inputs`` are the files the stage READ (hashed by name); an acquisition
    stage that reads only the network passes an empty list.

    Filenames must be unique: two inputs sharing a name from different
    directories would collide in the dict and one hash would vanish silently,
    leaving provenance incomplete in exactly the record meant to prove it.
    """
    input_list = list(inputs)
    names = [path.name for path in input_list]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise ValueError(
            f"duplicate input filenames would collide in meta: {sorted(duplicates)} - "
            f"rename them or pass distinguishable paths"
        )

    return {
        "stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": config_hash(),
        "code_commit": code_commit(),
        "rows": rows,
        "inputs": {path.name: file_sha256(path) for path in input_list},
    }


def verify_inputs(input_paths: Iterable[Path], expected_stage: str) -> None:
    """Fail (raise StaleInputError) unless every input is fresh.

    Fresh means: the file exists, its ``.meta.json`` exists and parses, it was
    produced by ``expected_stage``, and its ``config_hash`` matches the CURRENT
    crm/config.py. Partial reruns are allowed; STALE partial reruns are not.
    """
    current_hash = config_hash()

    for path in input_paths:
        if not path.exists():
            raise StaleInputError(f"input missing: {path} - run its producing stage first")

        meta_file = meta_path_for(path)
        if not meta_file.exists():
            raise StaleInputError(
                f"no meta for input: {path} - it was not produced by a pipeline stage "
                f"(expected {meta_file.name} alongside it)"
            )

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise StaleInputError(f"unreadable meta for input: {path} ({err})") from err

        if not isinstance(meta, dict):
            # Valid JSON but not an object (a list, a bare string): without this
            # the .get() calls below raise AttributeError, which tells whoever
            # is debugging nothing about the actual problem.
            raise StaleInputError(f"malformed meta for input: {path} - expected a JSON object")

        if meta.get("stage") != expected_stage:
            raise StaleInputError(
                f"wrong producing stage for {path}: expected '{expected_stage}', "
                f"meta says '{meta.get('stage')}'"
            )

        if meta.get("config_hash") != current_hash:
            raise StaleInputError(
                f"stale config for {path.name}: it was produced under a different "
                f"crm/config.py - rerun its producing stage ('{expected_stage}')"
            )
