import json

import pytest

from app.core.paths import (
    CATALOG_MARKER,
    RepositoryRootNotFound,
    data_root,
    find_repository_root,
    repository_root,
)


def build_catalog(root):
    marker = root / CATALOG_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps([]), encoding="utf-8")
    return root


def test_host_layout_resolves_from_backend_app_and_tests(tmp_path):
    """`<repo>/backend/app/...` and `<repo>/backend/tests/...`, catalogs at `<repo>/data`."""
    repo = build_catalog(tmp_path / "repo")
    app_module = repo / "backend" / "app" / "core"
    tests_dir = repo / "backend" / "tests"
    app_module.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    assert find_repository_root(app_module) == repo
    assert find_repository_root(tests_dir) == repo


def test_container_layout_resolves_from_app_and_tests(tmp_path):
    """`/app/app/...` and `/app/tests/...`, catalogs bind-mounted at `/app/data`.

    This is the layout the documented `docker compose exec backend ... pytest`
    command uses. Counting parent directories was correct for the host layout
    only, so fifteen tests failed there on a missing file.
    """
    app = build_catalog(tmp_path / "app")
    app_module = app / "app" / "core"
    tests_dir = app / "tests"
    app_module.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    assert find_repository_root(app_module) == app
    assert find_repository_root(tests_dir) == app


def test_nearest_catalog_wins(tmp_path):
    """A checkout nested inside another checkout resolves to the inner one."""
    outer = build_catalog(tmp_path / "outer")
    inner = build_catalog(outer / "workspace" / "inner")
    nested = inner / "backend" / "tests"
    nested.mkdir(parents=True)

    assert find_repository_root(nested) == inner


def test_directory_named_data_without_the_catalog_is_not_a_root(tmp_path):
    """Matching on the catalog file, not the directory name, avoids false roots."""
    decoy = tmp_path / "decoy"
    (decoy / "data").mkdir(parents=True)
    start = decoy / "backend" / "tests"
    start.mkdir(parents=True)

    with pytest.raises(RepositoryRootNotFound):
        find_repository_root(start)


def test_missing_catalog_names_the_marker(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(RepositoryRootNotFound) as error:
        find_repository_root(empty)
    assert CATALOG_MARKER.as_posix() in str(error.value)


def test_real_checkout_exposes_the_committed_catalogs():
    """Whatever layout this suite is running under, the catalogs are reachable."""
    root = repository_root()
    assert (root / CATALOG_MARKER).is_file()
    assert data_root() == root / "data"
    assert (data_root() / "fixtures" / "planning-v2" / "final-scope-multislot.json").is_file()
