"""Run local HACS schema/brand checks inside the pinned HACS action image.

This is a subset, not authenticated GitHub repository validation. Run with
--network none and PYTHONPATH=/hacs so imports use the image's HACS implementation.
"""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

from custom_components.hacs.utils.validate import (
    HACS_MANIFEST_JSON_SCHEMA,
    INTEGRATION_MANIFEST_JSON_SCHEMA,
)
from custom_components.hacs.validate.brands import Validator

ROOT = Path("/github/workspace")
INTEGRATION = "custom_components/iaqualink_tcx"


def prepare():
    HACS_MANIFEST_JSON_SCHEMA(json.loads((ROOT / "hacs.json").read_text()))
    INTEGRATION_MANIFEST_JSON_SCHEMA(json.loads((ROOT / INTEGRATION / "manifest.json").read_text()))
    # Minimal read-only repository facade supplies local tree metadata to the
    # real HACS brands validator. No network session exists for fallback.
    return SimpleNamespace(
        hacs=SimpleNamespace(session=None),
        logger=logging.getLogger("hacs_local_check"),
        treefiles=[str(path.relative_to(ROOT)) for path in (ROOT / INTEGRATION).rglob("*")],
        repository_manifest=SimpleNamespace(content_in_root=False),
        content=SimpleNamespace(path=SimpleNamespace(remote=INTEGRATION)),
    )


if __name__ == "__main__":
    asyncio.run(Validator(prepare()).async_validate())
    print("PASS: official HACS local manifest schemas and brand validator (remote checks pending)")
