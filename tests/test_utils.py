import pytest

from npe2.manifest.contributions import ContributionPoints
from npe2.manifest.schema import PluginManifest
from npe2.manifest.utils import (
    Version,
    deep_update,
    merge_contributions,
    merge_manifests,
)


def test_version():
    v = Version.parse(b"0.1.2")

    assert v == "0.1.2"
    assert v > {"major": 0, "minor": 1, "patch": 0}
    assert v <= (0, 2, 0)
    assert v == Version(0, 1, 2)
    assert list(v) == [0, 1, 2, None, None]
    assert str(v) == "0.1.2"

    with pytest.raises(TypeError):
        assert v == 1.2

    with pytest.raises(ValueError):
        Version.parse("alkfdjs")

    with pytest.raises(TypeError):
        Version.parse(1.2)  # type: ignore[arg-type]


def test_merge_manifests():
    with pytest.raises(ValueError):
        merge_manifests([])

    with pytest.raises(AssertionError) as e:
        merge_manifests([PluginManifest(name="plug1"), PluginManifest(name="plug2")])
    assert "All manifests must have same name" in str(e.value)

    pm1 = PluginManifest(
        name="plugin",
        contributions={
            "commands": [{"id": "plugin.command", "title": "some writer"}],
            "writers": [{"command": "plugin.command", "layer_types": ["image"]}],
        },
    )
    pm2 = PluginManifest(
        name="plugin",
        contributions={
            "commands": [{"id": "plugin.command", "title": "some reader"}],
            "readers": [{"command": "plugin.command", "filename_patterns": [".tif"]}],
        },
    )
    expected_merge = PluginManifest(
        name="plugin",
        contributions={
            "commands": [
                {"id": "plugin.command", "title": "some writer"},
                {"id": "plugin.command_2", "title": "some reader"},  # no dupes
            ],
            "writers": [{"command": "plugin.command", "layer_types": ["image"]}],
            "readers": [{"command": "plugin.command_2", "filename_patterns": [".tif"]}],
        },
    )

    assert merge_manifests([pm1]) is pm1
    assert merge_manifests([pm1, pm2]) == expected_merge


def test_merge_contributions():
    a = ContributionPoints(
        commands=[
            {"id": "plugin.command", "title": "some writer"},
        ],
        writers=[{"command": "plugin.command", "layer_types": ["image"]}],
    )
    b = ContributionPoints(
        commands=[
            {"id": "plugin.command", "title": "some writer"},
        ],
        writers=[{"command": "plugin.command", "layer_types": ["image"]}],
    )
    c = ContributionPoints(
        commands=[
            {"id": "plugin.command", "title": "some writer"},
        ],
        writers=[{"command": "plugin.command", "layer_types": ["image"]}],
    )
    expected = ContributionPoints(
        commands=[
            {"id": "plugin.command", "title": "some writer"},
            {"id": "plugin.command_2", "title": "some writer"},
            {"id": "plugin.command_3", "title": "some writer"},
        ],
        writers=[
            {"command": "plugin.command", "layer_types": ["image"]},
            {"command": "plugin.command_2", "layer_types": ["image"]},
            {"command": "plugin.command_3", "layer_types": ["image"]},
        ],
    )

    d = ContributionPoints(**merge_contributions((a, b, c)))
    assert d == expected

    # with overwrite, later contributions with matching command ids take precendence.
    e = ContributionPoints(**merge_contributions((a, b, c), overwrite=True))
    expected = ContributionPoints(
        commands=[
            {"id": "plugin.command", "title": "some writer"},
        ],
        writers=[
            {"command": "plugin.command", "layer_types": ["image"]},
        ],
    )
    assert e == a


def test_merge_contributions_duplicate_command_ids_in_single_incoming_slice():
    """Multiple commands in one contribution that share a colliding id.

    ``existing_cmds`` is not updated while processing a single incoming manifest, so
    two commands that both reuse the same colliding id can receive the same renamed
    id (duplicate command ids). This documents current behavior for a later refactor.
    """
    base = ContributionPoints(
        commands=[{"id": "plugin.cmd", "title": "base"}],
    )
    incoming = ContributionPoints(
        commands=[
            {"id": "plugin.cmd", "title": "first"},
            {"id": "plugin.cmd", "title": "second"},
        ],
    )
    merged = merge_contributions((base, incoming))
    assert [c["id"] for c in merged["commands"]] == [
        "plugin.cmd",
        "plugin.cmd_2",
        "plugin.cmd_2",
    ]
    assert [c["title"] for c in merged["commands"]] == [
        "base",
        "first",
        "second",
    ]


def test_merge_contributions_collision_chain_with_existing_numeric_suffixes():
    """When ``out_dict`` already has ``id`` and ``id_2``, a new colliding ``id`` becomes ``id_3``."""
    accumulated = ContributionPoints(
        commands=[
            {"id": "plugin.cmd", "title": "first"},
            {"id": "plugin.cmd_2", "title": "second"},
        ],
    )
    incoming = ContributionPoints(
        commands=[{"id": "plugin.cmd", "title": "incoming"}],
    )
    merged = merge_contributions((accumulated, incoming))
    assert [c["id"] for c in merged["commands"]] == [
        "plugin.cmd",
        "plugin.cmd_2",
        "plugin.cmd_3",
    ]


def test_merge_contributions_menus_dict_coexists_with_command_merge():
    """Non-list contribution values (e.g. ``menus``) are skipped by the list walk.

    Menu items are not updated by the ``"command"`` rename pass (only top-level
    list values are), so menu ``command`` strings stay as the original ids.
    """
    base = ContributionPoints(
        commands=[{"id": "plugin.cmd", "title": "base"}],
        writers=[{"command": "plugin.cmd", "layer_types": ["image"]}],
    )
    incoming = ContributionPoints(
        commands=[{"id": "plugin.cmd", "title": "other"}],
        writers=[{"command": "plugin.cmd", "layer_types": ["labels"]}],
        menus={
            "napari/layer/context": [
                {"command": "plugin.cmd", "group": "navigation"},
            ],
        },
    )
    merged = merge_contributions((base, incoming))
    assert "menus" in merged
    assert merged["commands"][0]["id"] == "plugin.cmd"
    assert merged["commands"][1]["id"] == "plugin.cmd_2"
    assert merged["writers"][0]["command"] == "plugin.cmd"
    assert merged["writers"][1]["command"] == "plugin.cmd_2"
    assert merged["menus"]["napari/layer/context"][0]["command"] == "plugin.cmd"


def test_merge_manifests_collision_chain_matches_merge_contributions():
    """``merge_manifests`` delegates contribution merging to ``merge_contributions``."""
    pm1 = PluginManifest(
        name="plugin",
        contributions={
            "commands": [
                {"id": "plugin.cmd", "title": "first"},
                {"id": "plugin.cmd_2", "title": "second"},
            ],
        },
    )
    pm2 = PluginManifest(
        name="plugin",
        contributions={
            "commands": [{"id": "plugin.cmd", "title": "incoming"}],
        },
    )
    merged = merge_manifests([pm1, pm2])
    cmds = merged.contributions.commands or []
    assert [c.id for c in cmds] == [
        "plugin.cmd",
        "plugin.cmd_2",
        "plugin.cmd_3",
    ]


def test_deep_update():
    a = {"a": {"b": 1, "c": 2}, "e": 2}
    b = {"a": {"d": 4, "c": 3}, "f": 0}
    c = deep_update(a, b, copy=True)
    assert c == {"a": {"b": 1, "d": 4, "c": 3}, "e": 2, "f": 0}
    assert a == {"a": {"b": 1, "c": 2}, "e": 2}

    deep_update(a, b, copy=False)
    assert a == {"a": {"b": 1, "d": 4, "c": 3}, "e": 2, "f": 0}
