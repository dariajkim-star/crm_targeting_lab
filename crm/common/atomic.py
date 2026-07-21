"""Atomic writes for pipeline outputs (AD-13: fail fast, no partial outputs).

Contract: a stage either leaves (output + meta) both in place, or leaves the
target exactly as it was - including preserving the previous good artifact when
a rerun fails. Temp files live in the TARGET's directory so ``os.replace`` is a
same-filesystem atomic rename.

``write_with_meta`` is the only sanctioned way for a stage to emit an output:
it guarantees no orphan artifacts (an output missing its ``.meta.json`` would
fail every downstream ``verify_inputs`` with a symptom far from the cause).

Functions are stateless (AD-1); the CALLER decides what to write and where
(AD-9 - orchestration owns I/O policy, this module owns only atomicity).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from crm.common.freshness import meta_path_for


def _tmp_beside(target: Path) -> Path:
    """A unique temp path in the target's directory (same-FS rename)."""
    return target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"


def _atomic_write(target: Path, write: Callable[[Path], None]) -> None:
    """Run ``write`` against a temp path, then rename over ``target``."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_beside(target)
    try:
        write(tmp)
        os.replace(tmp, target)
    finally:
        # Cleanup must never mask the real failure: on Windows an unreleased
        # handle (or a scanner) can make unlink raise, and that exception would
        # replace the one explaining what actually went wrong.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_bytes(target: Path, data: bytes) -> None:
    _atomic_write(target, lambda tmp: tmp.write_bytes(data))


def atomic_write_text(target: Path, text: str) -> None:
    _atomic_write(target, lambda tmp: tmp.write_text(text, encoding="utf-8"))


def atomic_write_parquet(target: Path, frame: pd.DataFrame) -> None:
    _atomic_write(target, lambda tmp: frame.to_parquet(tmp, index=False))


def write_parquet_with_meta(target: Path, frame: pd.DataFrame, meta: dict[str, Any]) -> None:
    """Emit (parquet output + meta) atomically.

    Convenience over ``write_with_meta`` so a pipeline stage passes a frame and
    meta without spelling the parquet-writing mechanism itself - the writer
    closure lives here (AD-9: this module owns the write MECHANISM; the stage
    owns only the policy of what/where). Keeping the closure out of ``pipelines/``
    also satisfies the pipeline-shape guard, which forbids a stage defining any
    callable besides ``main``.
    """
    write_with_meta(target, lambda tmp: frame.to_parquet(tmp, index=False), meta)


def write_with_meta(
    target: Path,
    writer: Callable[[Path], None],
    meta: dict[str, Any],
    meta_path: Path | None = None,
) -> None:
    """Emit (output + meta) as one unit, or leave the target untouched.

    Sequence: write output to temp -> rename into place -> write meta. If the
    meta step fails AFTER the output landed, the output is rolled back (restored
    to the previous version when one existed, removed otherwise) so no orphan
    artifact survives.

    ``meta_path`` defaults to the AD-13 sibling (``<output>.meta.json``). Story
    1-6b passes it explicitly for the AD-5 IDENTITY record, which AD-5 names
    ``models/churn_model.meta.json`` - a different file from the freshness
    sibling. The all-or-nothing guarantee is the same either way, which is why
    the identity record reuses this rather than re-deriving the rollback.
    """
    meta_file = meta_path_for(target) if meta_path is None else meta_path
    # Widening a shared contract means widening its failure modes: with the same
    # path for both, the meta write lands ON the output and the caller is told
    # it succeeded, leaving a "model" that is actually JSON. Resolve first so an
    # alias or symlink cannot smuggle the collision past a string comparison.
    if target.resolve(strict=False) == meta_file.resolve(strict=False):
        raise ValueError(
            f"meta_path must differ from the output path (both are {target}) - "
            f"the meta write would overwrite the artifact it describes"
        )
    previous: Path | None = None
    try:
        if target.exists():
            # Park the previous good artifact so a failed rerun can restore it.
            # Parking lives INSIDE the try: if it succeeded and then anything
            # raised (KeyboardInterrupt included) before the try began, the
            # rollback below would be unreachable and the artifact stranded.
            previous = _tmp_beside(target)
            os.replace(target, previous)

        _atomic_write(target, writer)
        atomic_write_text(meta_file, json.dumps(meta, indent=2))
    except BaseException as err:
        # Roll back. The meta write is atomic and is the LAST step, so on any
        # exception a meta file on disk can only be the PREVIOUS run's - keep it
        # when restoring the previous output (deleting it would manufacture the
        # exact orphan this module exists to prevent).
        if previous is not None:
            try:
                os.replace(previous, target)
            except OSError as rollback_err:
                # Never let the rollback failure hide the original cause, and
                # never leave the previous artifact hidden under a uuid name
                # with no way to find it.
                raise RuntimeError(
                    f"rollback failed for {target}: the previous artifact is parked at "
                    f"{previous} and must be restored by hand ({rollback_err})"
                ) from err
        else:
            target.unlink(missing_ok=True)
            meta_file.unlink(missing_ok=True)
        raise
    else:
        if previous is not None:
            try:
                previous.unlink(missing_ok=True)
            except OSError:
                pass
