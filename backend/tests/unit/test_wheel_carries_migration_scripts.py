"""The built distribution must carry the migration scripts (S-075).

Why this is not simply ``assert expected_head() is not None``
-------------------------------------------------------------
That assertion already exists in ``tests/unit/test_readiness.py`` and it stayed
green through the whole life of the defect, because the suite runs from the
source tree, where ``backend/migrations`` sits next to ``backend/app`` and any
way of locating it works. ``backend/Dockerfile`` runs ``uv sync --no-editable``,
so the deployed layout is different: ``app`` lands in ``site-packages`` and the
scripts did not travel with it. Measured 2026-08-22 from a built image, the
production entrypoint raised ``RuntimeError: Database is not ready (migrations:
unknown)`` against a database that was at head.

So these tests do not read the source tree. They build the wheel, unpack it into
a scratch directory, and ask a subprocess that can see **only that directory**
for the head revision. That is the deployed layout, minus the container.

What they still cannot see
--------------------------
They do not build or run the container image. A Dockerfile change that dropped
the virtualenv, or a base image missing a runtime dependency, would pass here and
fail in production. The image is checked by hand today; making CI build it is
S-074.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app.core.readiness import expected_head

pytestmark = [pytest.mark.unit, pytest.mark.slow]

# Runs against the unpacked wheel with nothing else of ours on the path. It
# reports where each module was loaded from, so a shadowing import surfaces as a
# failure with a readable message instead of as an accidental pass.
_PROBE = """
import json, os, sys

source_root = os.path.abspath(os.environ["S075_SOURCE_ROOT"])
sys.path = [p for p in sys.path if os.path.abspath(p) != source_root]

import app.core.readiness as readiness
import migrations

print(json.dumps({
    "head": readiness.expected_head(),
    "readiness_file": readiness.__file__,
    "migrations_file": migrations.__file__,
}))
"""


def _project_root() -> Path:
    """The directory holding this project's ``pyproject.toml``.

    Found by walking up and reading each candidate, not by counting parents. The
    defect these tests exist for was a parent count that stopped being right."""
    for candidate in Path(__file__).resolve().parents:
        manifest = candidate / "pyproject.toml"
        if manifest.is_file() and 'name = "family-roots-backend"' in manifest.read_text():
            return candidate
    raise AssertionError("could not find the family-roots-backend pyproject.toml")


@pytest.fixture(scope="module")
def unpacked_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the project wheel and unpack it. This is what the image installs."""
    tmp_path = tmp_path_factory.mktemp("s075")
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=_project_root(),
        check=True,
        capture_output=True,
    )
    wheels = sorted(dist.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(wheels[0]) as archive:
        archive.extractall(unpacked)
    return unpacked


def _read_head_from(import_roots: list[Path], cwd: Path) -> dict[str, str]:
    """Ask a subprocess for the head with only ``import_roots`` on the path."""
    probe = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(str(root) for root in import_roots),
            "S075_SOURCE_ROOT": str(_project_root()),
        },
    )
    # Not check=True: an ImportError here is the defect itself, and the reader
    # needs to see which module was missing, not a subprocess traceback.
    assert probe.returncode == 0, (
        f"the installed layout could not report a head:\n{probe.stderr.strip()}"
    )
    result: dict[str, str] = json.loads(probe.stdout)
    return result


def test_head_is_readable_from_the_unpacked_wheel(unpacked_wheel: Path, tmp_path: Path) -> None:
    """The wheel must carry the migration scripts.

    Before S-075 this failed with ``head`` equal to ``None``: the wheel held
    ``app`` and no ``migrations`` at all."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    reported = _read_head_from([unpacked_wheel], cwd=elsewhere)

    # If either module came from anywhere but the unpacked wheel then this test
    # is reading the source tree again, and it proves nothing.
    assert reported["readiness_file"].startswith(str(unpacked_wheel)), reported
    assert reported["migrations_file"].startswith(str(unpacked_wheel)), reported
    assert reported["head"] == expected_head(), reported


def test_head_lookup_does_not_assume_the_scripts_sit_next_to_the_package(
    unpacked_wheel: Path, tmp_path: Path
) -> None:
    """``migrations`` is found by import, not by its position relative to ``app``.

    The previous ``Path(__file__).resolve().parents[2]`` required the scripts to
    be a sibling of the ``app`` package on the same path root. Shipping them in
    the wheel makes that true again in today's image, which is exactly why it
    needs its own test: the arithmetic would keep working by luck, and would
    break silently the next time this module moves a directory or an installer
    splits the two roots.

    Here the two are deliberately put on different roots. Import does not care.
    A parent count returns ``head: None`` and fails."""
    split_app = tmp_path / "root-a"
    split_scripts = tmp_path / "root-b"
    shutil.copytree(unpacked_wheel, split_app)
    split_scripts.mkdir()
    shutil.move(str(split_app / "migrations"), str(split_scripts / "migrations"))
    assert not (split_app / "migrations").exists()

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    reported = _read_head_from([split_app, split_scripts], cwd=elsewhere)

    assert reported["readiness_file"].startswith(str(split_app)), reported
    assert reported["migrations_file"].startswith(str(split_scripts)), reported
    assert reported["head"] == expected_head(), reported
