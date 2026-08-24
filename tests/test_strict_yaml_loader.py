"""Every config in this repository must parse with duplicate keys rejected.

``yaml.safe_load`` keeps the last value when a mapping repeats a key, so a
config that sets ``batch_size`` twice parses cleanly and the run silently uses
whichever line came last. R0 found no such config, and this test is what keeps
that true: it is the cheapest guard against a whole class of "the experiment did
not use the setting you read" failures.

The loader lives here rather than in library code on purpose. It is a test-time
audit of the config corpus, not a runtime dependency of any entrypoint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


class DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that raises instead of silently keeping the last value."""


def _no_duplicate_keys(loader: yaml.Loader, node: yaml.Node) -> Dict[Any, Any]:
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "duplicate key %r at %s" % (key, key_node.start_mark),
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


DuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def strict_load(text: str) -> Any:
    return yaml.load(text, Loader=DuplicateKeyLoader)


def discover_configs() -> List[Path]:
    return sorted(
        path
        for pattern in ("*.yaml", "*.yml")
        for path in (REPO_ROOT / "configs").rglob(pattern)
    )


CONFIGS = discover_configs()


def test_config_corpus_is_not_empty() -> None:
    """A glob that matched nothing would make every other test vacuous."""

    assert CONFIGS, "no configs discovered under %s/configs" % REPO_ROOT


@pytest.mark.parametrize("config", CONFIGS, ids=lambda path: path.name)
def test_config_has_no_duplicate_keys(config: Path) -> None:
    with config.open("r", encoding="utf-8") as handle:
        strict_load(handle.read())


def test_loader_rejects_a_duplicate_key() -> None:
    """The guard must fail on the thing it exists to catch."""

    with pytest.raises(yaml.constructor.ConstructorError):
        strict_load("loader:\n  batch_size: 8\n  batch_size: 64\n")


def test_loader_rejects_a_duplicate_nested_key() -> None:
    with pytest.raises(yaml.constructor.ConstructorError):
        strict_load("training:\n  stereo_flip:\n    probability: 0.0\n    probability: 0.5\n")


def test_safe_load_would_have_accepted_it() -> None:
    """Pin the behaviour this guard replaces, so the motive stays legible."""

    document = "loader:\n  batch_size: 8\n  batch_size: 64\n"
    assert yaml.safe_load(document)["loader"]["batch_size"] == 64


def test_repeated_key_in_distinct_mappings_is_legal() -> None:
    parsed = strict_load("a:\n  seed: 1\nb:\n  seed: 1\n")
    assert parsed == {"a": {"seed": 1}, "b": {"seed": 1}}
