"""
tests/test_vdg.py

Unit tests for vdg core logic.
Covers pure functions that do not require ffmpeg/ffprobe to be present.
"""

import pytest
from pathlib import Path

from vdg.cli import (
    sanitize_filename,
    strip_role_code,
    calculate_scaling_params,
    detect_video_standard,
    calculate_output_fps,
    get_bitrate_config,
    compute_colliding_stems,
    clean_aperture_input_args,
    VideoStandard,
    ROLE_CODES,
)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_spaces_replaced_with_underscores(self):
        assert sanitize_filename("my file name") == "my_file_name"

    def test_no_spaces_unchanged(self):
        assert sanitize_filename("qp616km4412_pm") == "qp616km4412_pm"

    def test_multiple_spaces(self):
        assert sanitize_filename("vendor  delivery  file") == "vendor__delivery__file"

    def test_empty_string(self):
        assert sanitize_filename("") == ""

    def test_leading_trailing_spaces(self):
        assert sanitize_filename(" file ") == "_file_"


# ---------------------------------------------------------------------------
# strip_role_code
# ---------------------------------------------------------------------------

class TestStripRoleCode:
    def test_strips_pm(self):
        assert strip_role_code("qp616km4412_pm") == "qp616km4412"

    def test_strips_sh(self):
        assert strip_role_code("qp616km4412_sh") == "qp616km4412"

    def test_strips_sl(self):
        assert strip_role_code("qp616km4412_sl") == "qp616km4412"

    def test_no_role_code_unchanged(self):
        assert strip_role_code("vendor_delivery") == "vendor_delivery"

    def test_partial_match_unchanged(self):
        # "_pm" must be a full suffix, not a mid-stem occurrence
        assert strip_role_code("compound_pm_extra") == "compound_pm_extra"

    def test_non_standard_suffix_unchanged(self):
        assert strip_role_code("file_master") == "file_master"

    def test_role_code_only(self):
        # Edge: stem is only the role code
        assert strip_role_code("_pm") == ""

    def test_all_role_codes_covered(self):
        # Ensure ROLE_CODES constant and strip_role_code stay in sync
        for code in ROLE_CODES:
            stem = f"testfile{code}"
            assert strip_role_code(stem) == "testfile"


# ---------------------------------------------------------------------------
# calculate_scaling_params
# ---------------------------------------------------------------------------

class TestCalculateScalingParams:
    def test_ntsc_4x3(self):
        assert calculate_scaling_params(720, 480, "4:3") == "640:480"

    def test_ntsc_16x9(self):
        assert calculate_scaling_params(720, 480, "16:9") == "854:480"

    def test_ntsc_486_4x3(self):
        assert calculate_scaling_params(720, 486, "4:3") == "640:480"

    def test_ntsc_486_16x9(self):
        assert calculate_scaling_params(720, 486, "16:9") == "854:480"

    def test_pal_4x3(self):
        assert calculate_scaling_params(720, 576, "4:3") == "640:480"

    def test_pal_16x9(self):
        assert calculate_scaling_params(720, 576, "16:9") == "854:480"

    def test_anamorphic_1440x1080(self):
        assert calculate_scaling_params(1440, 1080, "16:9") == "1280:720"

    def test_full_hd_1920x1080(self):
        assert calculate_scaling_params(1920, 1080, "16:9") == "1280:720"

    def test_native_720p(self):
        assert calculate_scaling_params(1280, 720, "16:9") == "1280:720"

    def test_ultra_hd_16x9(self):
        assert calculate_scaling_params(3840, 2160, "16:9") == "1280:720"

    def test_ultra_hd_non_169(self):
        result = calculate_scaling_params(3840, 2160, "4:3")
        assert result == "-2:720"

    def test_unknown_dimensions_passthrough(self):
        # Non-standard dimensions should return mod-2 safe passthrough
        result = calculate_scaling_params(800, 600, "4:3")
        assert result == "trunc(iw/2)*2:trunc(ih/2)*2"


# ---------------------------------------------------------------------------
# detect_video_standard
# ---------------------------------------------------------------------------

class TestDetectVideoStandard:
    def test_ntsc_480(self):
        assert detect_video_standard(720, 480, 29.97) == VideoStandard.NTSC

    def test_ntsc_486(self):
        assert detect_video_standard(720, 486, 29.97) == VideoStandard.NTSC

    def test_pal(self):
        assert detect_video_standard(720, 576, 25.0) == VideoStandard.PAL

    def test_unknown_hd(self):
        assert detect_video_standard(1920, 1080, 29.97) == VideoStandard.UNKNOWN

    def test_ntsc_fps_tolerance(self):
        # ffprobe sometimes reports 30.0 for 29.97 — should NOT match NTSC
        assert detect_video_standard(720, 480, 30.0) == VideoStandard.UNKNOWN

    def test_pal_fps_tolerance(self):
        assert detect_video_standard(720, 576, 25.0) == VideoStandard.PAL


# ---------------------------------------------------------------------------
# calculate_output_fps
# ---------------------------------------------------------------------------

class TestCalculateOutputFps:
    def test_ntsc_passthrough(self):
        assert calculate_output_fps(29.97) == pytest.approx(29.97)

    def test_pal_passthrough(self):
        assert calculate_output_fps(25.0) == pytest.approx(25.0)

    def test_60i_halved(self):
        assert calculate_output_fps(60.0) == pytest.approx(30.0)

    def test_50i_halved(self):
        assert calculate_output_fps(50.0) == pytest.approx(25.0)

    def test_59_94_halved(self):
        assert calculate_output_fps(59.94) == pytest.approx(29.97)


# ---------------------------------------------------------------------------
# get_bitrate_config
# ---------------------------------------------------------------------------

class TestGetBitrateConfig:
    def test_sd_profile(self):
        cfg = get_bitrate_config(480)
        assert cfg['bitrate'] == '1000k'
        assert cfg['maxrate'] == '1200k'
        assert cfg['bufsize'] == '2000k'

    def test_sd_576(self):
        cfg = get_bitrate_config(576)
        assert cfg['bitrate'] == '1000k'

    def test_hd_profile(self):
        cfg = get_bitrate_config(720)
        assert cfg['bitrate'] == '2800k'
        assert cfg['maxrate'] == '2900k'
        assert cfg['bufsize'] == '5800k'

    def test_hd_1080(self):
        cfg = get_bitrate_config(1080)
        assert cfg['bitrate'] == '2800k'


# ---------------------------------------------------------------------------
# calculate_scaling_params — force_anamorphic override
# ---------------------------------------------------------------------------

class TestCalculateScalingParamsForceAnamorphic:
    def test_force_overrides_4x3_dar(self):
        # Mistagged 4:3 that is actually anamorphic squeezed 16:9 footage
        assert calculate_scaling_params(720, 480, "4:3", force_anamorphic=True) == "854:480"

    def test_force_486_height(self):
        assert calculate_scaling_params(720, 486, "4:3", force_anamorphic=True) == "854:480"

    def test_force_pal_576_height(self):
        assert calculate_scaling_params(720, 576, "4:3", force_anamorphic=True) == "854:480"

    def test_force_false_uses_detected_dar(self):
        assert calculate_scaling_params(720, 480, "4:3", force_anamorphic=False) == "640:480"

    def test_force_ignored_for_hd_dimensions(self):
        # Flag only applies to SD (720-wide) sources
        result = calculate_scaling_params(1920, 1080, "4:3", force_anamorphic=True)
        assert result != "854:480"


# ---------------------------------------------------------------------------
# compute_colliding_stems
# ---------------------------------------------------------------------------

class TestComputeCollidingStems:
    def test_same_id_different_role_codes_collide(self):
        files = [
            Path("wb824kh0844_At_Home_But_Not_At_Home_2020_pm.mov"),
            Path("wb824kh0844_At_Home_But_Not_At_Home_2020_sh.mp4"),
        ]
        assert compute_colliding_stems(files) == {"wb824kh0844_At_Home_But_Not_At_Home_2020"}

    def test_unique_stems_do_not_collide(self):
        files = [
            Path("file_one_pm.mov"),
            Path("file_two_sh.mp4"),
        ]
        assert compute_colliding_stems(files) == set()

    def test_no_role_code_no_collision(self):
        files = [Path("vendor_delivery.mov")]
        assert compute_colliding_stems(files) == set()

    def test_empty_file_list(self):
        assert compute_colliding_stems([]) == set()


# ---------------------------------------------------------------------------
# clean_aperture_input_args
# ---------------------------------------------------------------------------

class TestCleanApertureInputArgs:
    def test_default_disables_clap_crop(self):
        assert clean_aperture_input_args(False) == ["-flags2", "+ignorecrop"]

    def test_clean_aperture_true_omits_flag(self):
        assert clean_aperture_input_args(True) == []
