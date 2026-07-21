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

DQ2 - CLOSED in story 1-3 (was: known limitation from 1-1b review):
``verify_inputs`` still only checks a fresh input's producer stage and
``config_hash`` - it does NOT compare recorded input hashes against the inputs
as they stand now, because it has no notion of a PREVIOUS output to reason
about. ``is_output_stale(output, inputs)`` closes that gap from the other side:
a CONSUMING stage reads its own previous output's meta and compares the
``inputs`` hashes recorded there against the current input files. If any differ
(or the output/meta is absent), the stage is stale and must recompute. Story
1-3 (02_features, the first stage to consume another stage's output) wires the
two gates in sequence: ``verify_inputs`` (right producer + no config drift) then
``is_output_stale`` (same producer, but the input CONTENT changed since our last
run). Together they make the canonical AD-13 scenario - 02's inputs change and
02/05 rerun while a colleague reruns only 05 - fail loudly instead of silently
committing a mart that mixes new features with old probabilities.

STILL OUT OF CONTRACT (do not claim otherwise): the OUTPUT's own content hash is
not recorded, so hand-editing a parquet in place is not detected (deferred-work
1-1b). ``is_output_stale`` reasons about input drift, not output tampering.

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


def is_output_stale(output: Path, inputs: Iterable[Path]) -> bool:
    """True if ``output`` must be recomputed because its inputs changed (DQ2).

    Closes the gap ``verify_inputs`` cannot see (module doc, DQ2): a consuming
    stage calls this against its OWN previous output before rerunning. It reads
    the output's ``.meta.json`` and compares the input SHA-256 hashes recorded
    there against the input files as they stand now.

    Stale (return True) when:
      - the output or its meta is missing (never produced -> must run),
      - the meta is unreadable or not a JSON object (cannot trust it -> rerun),
      - any current input's hash differs from the one recorded at production,
      - an input recorded before is now missing, or an input is passed now that
        the previous run did not record (the input SET changed).

    Fresh (return False) only when every passed input exists AND its current
    hash matches the recorded one AND the recorded and passed input sets are
    identical. Pure apart from reading the files it is given (AD-1).
    """
    meta_file = meta_path_for(output)
    if not output.exists() or not meta_file.exists():
        return True

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return True
    if not isinstance(meta, dict):
        return True

    recorded = meta.get("inputs")
    if not isinstance(recorded, dict):
        # A meta without a usable input record cannot prove freshness.
        return True

    current_paths = list(inputs)
    # Set mismatch is staleness on its own: a dropped or added input means the
    # previous output was built from a different set than we would feed now.
    if {path.name for path in current_paths} != set(recorded.keys()):
        return True

    for path in current_paths:
        if not path.exists():
            return True
        if file_sha256(path) != recorded.get(path.name):
            return True

    return False
