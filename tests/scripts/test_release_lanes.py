"""The stable release lanes: what a lane set builds, tests, and records in its claim."""
import pytest

from scripts.releases import lanes as lane_set


def test_the_default_builds_everything_but_macos_intel_and_termux():
    assert lane_set.DEFAULT == set(lane_set.NAMES) - {"macos-intel", "termux"}
    assert lane_set.select() == lane_set.DEFAULT


@pytest.mark.parametrize("kwargs,expected", [
    # The request that motivated lanes: only the macOS Intel package and the image, no tests.
    ({"only": ["macos-intel", "docker"]}, {"macos-intel", "docker"}),
    ({"with_": ["macos-intel", "termux"]}, set(lane_set.NAMES)),
    ({"without": ["macos-arm64", "upgrade"]}, set(lane_set.DEFAULT) - {"macos-arm64", "upgrade"}),
    ({"only": ["macos-intel"], "with_": ["smoke"], "without": ["macos-intel"]}, {"smoke"}),
    ({"only": []}, set()),
])
def test_select_edits_the_default_or_replaces_it(kwargs, expected):
    assert lane_set.select(**kwargs) == expected


def test_select_refuses_unknown_and_contradictory_lanes():
    with pytest.raises(ValueError, match="unknown lane intel"):
        lane_set.select(with_=["intel"])
    with pytest.raises(ValueError, match="both name ci"):
        lane_set.select(with_=["ci"], without=["ci"])


def test_options_flatten_repeats_and_commas():
    assert lane_set.parse_list(["macos-intel, docker", "ci"]) == ["macos-intel", "docker", "ci"]
    assert lane_set.parse_list(None) is None


def test_every_job_names_real_lanes():
    for job, needs in lane_set.JOB_LANES.items():
        assert needs <= {*lane_set.NAMES, *lane_set.DERIVED}, job
    for target, lane in lane_set.TARGET_LANE.items():
        assert lane in lane_set.NAMES, target
    for handoff, lane in lane_set.HANDOFF_LANE.items():
        assert lane in {*lane_set.NAMES, *lane_set.DERIVED}, handoff


def test_a_job_runs_only_when_every_lane_it_needs_is_on():
    native_only = lane_set.jobs_to_run(["macos-intel", "docker"])
    assert {job for job, runs in native_only.items() if runs} == {
        "docker", "publish-docker", "candidates-darwin-x64", "candidate-manifest", "publish-bundles"}
    # A test lane for something that is not built is inert.
    assert not lane_set.jobs_to_run(["upgrade", "macos-intel"])["transitions-darwin-arm64"]
    assert lane_set.jobs_to_run(["upgrade", "macos-intel"])["transitions-darwin-x64"]
    # termux-checks needs both the check and the package.
    assert not lane_set.jobs_to_run(["termux-checks"])["termux-checks"]
    assert lane_set.jobs_to_run(["termux-checks", "termux"])["termux-checks"]
    assert not any(lane_set.jobs_to_run([]).values())




def test_flags_round_trip_and_refuse_anything_loose():
    flags = lane_set.flags(["macos-intel", "docker"])
    assert flags["bundles"] is True and flags["macos-arm64"] is False
    assert flags["desktop-channel"] is False
    assert lane_set.flags(lane_set.DEFAULT)["desktop-channel"] is True
    assert lane_set.from_flags(flags) == {"macos-intel", "docker"}
    assert lane_set.flags(["docker"])["bundles"] is False
    for bad in (None, {}, {**flags, "extra": True}, {**flags, "ci": "true"},
                {name: flags[name] for name in flags if name != "ci"}):
        with pytest.raises(ValueError, match="boolean for every lane"):
            lane_set.from_flags(bad)




def test_targets_and_handoffs_follow_the_build_lanes():
    assert lane_set.targets(["macos-intel", "termux"]) == {"macos/x64", "termux/aarch64"}
    assert lane_set.handoffs(["macos-intel"], ("darwin-x64", "darwin-arm64", "termux")) == \
        ("darwin-x64",)


def test_smokes_run_only_for_a_built_desktop_package():
    assert lane_set.runs_smokes(lane_set.DEFAULT)
    assert not lane_set.runs_smokes(["smoke", "docker", "termux"])
    assert not lane_set.runs_smokes(["macos-intel"])


def test_the_desktop_channel_moves_only_for_the_full_desktop_set():
    assert lane_set.advances_desktop(lane_set.DEFAULT)
    assert not lane_set.advances_desktop(["macos-intel", "docker"])
    assert lane_set.advances_desktop(["macos-arm64"])
    # A release that moves no channel is finished once public.
    assert lane_set.moves_channels(["docker"]) and lane_set.moves_channels(["macos-intel", "macos-arm64"])
    assert not lane_set.moves_channels(["macos-intel"]) and not lane_set.moves_channels([])
