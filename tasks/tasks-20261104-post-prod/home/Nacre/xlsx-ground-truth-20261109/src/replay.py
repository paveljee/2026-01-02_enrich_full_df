"""Replay HCR reviews in the pipeline's pilot-then-numeric draw order.

Allowed dependencies: stdlib and local `shared`; no pipeline or third-party imports.
"""

import hashlib
import itertools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from shared import (
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    TEXT_ENCODING,
    SeedHandoff,
    hcr_review_script_name,
)

SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent
SCRIPTS = WORKDIR / "proof"
ERR_SEED_LENGTH = "The seed must contain one line per configured draw"
ERR_SEED_HASH = "The seed mask differs from the handed-off artifact"
ERR_NAMEKEY_ORDER = "NameKey order changed at position {position}"
ERR_MISSING_SCRIPT = "Missing HCR review script for draw {draw_label}: {script_name}"

handoff = SeedHandoff.load()
SEED = handoff.artifact(handoff.seed_mask_file)
MASTER = handoff.artifact(handoff.master_file)
pilot_count = handoff.pilot_draws
if hashlib.sha256(SEED.read_bytes()).hexdigest() != handoff.seed_mask_sha256:
    raise ValueError(ERR_SEED_HASH)
with SEED.open(encoding=TEXT_ENCODING) as file:
    if sum(1 for _ in file) != handoff.total_draws:
        raise ValueError(ERR_SEED_LENGTH)
shutil.copyfile(SEED, MASTER)

with SEED.open(encoding=TEXT_ENCODING) as drawn_keys:
    for position, line in enumerate(drawn_keys, start=1):
        serialized_key = next(iter(json.loads(line)))
        with MASTER.open(encoding=TEXT_ENCODING) as current_mask:
            current_line = next(itertools.islice(current_mask, position - 1, None))
        current_entry = json.loads(current_line)
        if serialized_key not in current_entry:
            raise ValueError(ERR_NAMEKEY_ORDER.format(position=position))
        if not current_entry[serialized_key]:
            continue  # Its seed award was claimed by an earlier drawn researcher.

        namekey = json.loads(serialized_key)
        draw_label = f"pilot.{position}" if position <= pilot_count else str(position - pilot_count)
        script = SCRIPTS / hcr_review_script_name(
            draw_label, namekey[KTP_FIRST_NAME_COL], namekey[KTP_LAST_NAME_COL]
        )
        if not script.is_file():
            raise FileNotFoundError(
                ERR_MISSING_SCRIPT.format(draw_label=draw_label, script_name=script.name)
            )
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(SCRIPT_DIR), env.get("PYTHONPATH"))))
        subprocess.run([sys.executable, str(script)], check=True, env=env)
