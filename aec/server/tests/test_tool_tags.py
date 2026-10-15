"""Unit tests for blender_tool_tags.py: the qgis-documented 'stranded preset'
trap (an untagged tool, or a tag no preset includes, is unreachable once
enable(only=True) applies) must not be possible here.
"""
from blender_tool_tags import ESCAPE, PRESETS, TOOL_TAGS, preset_tags

REQUIRED_ESCAPE_TOOLS = {
    "ping", "get_blender_info", "execute_code", "search_tools",
    "describe_tool", "run_tool", "set_toolset", "search_rules",
}

REQUIRED_PRESET_NAMES = {
    "full", "generic_blender", "bim_authoring", "bim_costing",
    "rendering", "minimal",
}


def test_all_required_presets_exist():
    assert REQUIRED_PRESET_NAMES <= set(PRESETS)


def test_every_required_escape_tool_is_tagged_escape():
    for name in REQUIRED_ESCAPE_TOOLS:
        assert TOOL_TAGS.get(name) == "escape", f"{name} must be tagged escape"


def test_every_preset_includes_the_escape_tag():
    for preset, tags in PRESETS.items():
        if tags is None:  # 'full': sentinel for everything, escape included trivially
            continue
        assert ESCAPE <= tags, f"preset {preset!r} does not include escape: {tags}"


def test_orphaned_tags_are_still_reachable_through_escape():
    """Some BIM sub-domain tags (clash, BCF, structural, drawings,
    validation, systems) aren't named by any preset but 'full' — same shape
    as qgis-mcp's own PRESETS, where 'annotations'/'settings'/'editing'/
    'temporal' are likewise full-only. Not a stranding: every preset carries
    'escape', and search_tools/run_tool reach any tool regardless of its
    tag, which is the entire point of that tag. This just documents the
    gap instead of silently growing it unnoticed."""
    covered = set()
    for tags in PRESETS.values():
        if tags is not None:
            covered |= tags
    orphaned = set(TOOL_TAGS.values()) - covered
    assert orphaned == {
        "bim_structural", "bim_clash", "bim_drawings", "bim_systems", "bim_bcf",
        "bim_validation",
    }, f"orphaned-tag set changed, update this test deliberately: {orphaned}"


def test_preset_tags_helper_matches_dict():
    for preset in PRESETS:
        assert preset_tags(preset) == PRESETS[preset]
    assert preset_tags("not-a-real-preset") is None


def test_known_tool_count_is_147_plus_5_wave1_meta_tools():
    # Ground-truthed count (aec/server/blender_mcp_server.py has exactly 147
    # @qtool sites from wave 0) plus the 5 discovery/control tools wave 1
    # adds (search_tools, describe_tool, run_tool, set_toolset, search_rules)
    # — all 5 are themselves tagged (escape), so they belong in this dict too.
    assert len(TOOL_TAGS) == 147 + 5
