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
    compute_filename_disambiguation,
    clean_aperture_input_args,
    collect_video_files,
    handle_failed_lossless_output,
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
# compute_filename_disambiguation
# ---------------------------------------------------------------------------

class TestComputeFilenameDisambiguation:
    def test_same_id_different_extensions(self):
        files = [
            Path("wb824kh0844_At_Home_But_Not_At_Home_2020_pm.mov"),
            Path("wb824kh0844_At_Home_But_Not_At_Home_2020_sh.mp4"),
        ]
        result = compute_filename_disambiguation(files)
        assert result == {
            "wb824kh0844_At_Home_But_Not_At_Home_2020_pm.mov": "mov",
            "wb824kh0844_At_Home_But_Not_At_Home_2020_sh.mp4": "mp4",
        }

    def test_same_id_same_extension_falls_back_to_role_code(self):
        # Regression: bm994hd4640_pm.mov + bm994hd4640_sh.mov both .mov —
        # extension alone collided and silently overwrote one output.
        # Must fall back to role_code + extension for the whole group.
        files = [
            Path("bm994hd4640_pm.mov"),
            Path("bm994hd4640_sh.mov"),
            Path("bm994hd4640_sl.mp4"),
        ]
        result = compute_filename_disambiguation(files)
        assert result == {
            "bm994hd4640_pm.mov": "pm_mov",
            "bm994hd4640_sh.mov": "sh_mov",
            "bm994hd4640_sl.mp4": "sl_mp4",
        }
        # Confirm every disambiguated stem is actually unique.
        assert len(set(result.values())) == 3

    def test_unique_stems_do_not_collide(self):
        files = [
            Path("file_one_pm.mov"),
            Path("file_two_sh.mp4"),
        ]
        assert compute_filename_disambiguation(files) == {}

    def test_no_role_code_no_collision(self):
        files = [Path("vendor_delivery.mov")]
        assert compute_filename_disambiguation(files) == {}

    def test_empty_file_list(self):
        assert compute_filename_disambiguation([]) == {}


# ---------------------------------------------------------------------------
# clean_aperture_input_args
# ---------------------------------------------------------------------------

class TestCleanApertureInputArgs:
    def test_default_disables_clap_crop(self):
        assert clean_aperture_input_args(False) == ["-apply_cropping", "0"]

    def test_clean_aperture_true_omits_flag(self):
        assert clean_aperture_input_args(True) == []


# ---------------------------------------------------------------------------
# collect_video_files — hidden-file / AppleDouble filtering
# ---------------------------------------------------------------------------

class TestCollectVideoFiles:
    def test_excludes_appledouble_sidecar(self, tmp_path):
        (tmp_path / "real_pm.mov").touch()
        (tmp_path / "._real_pm.mov").touch()
        files = collect_video_files(tmp_path, tmp_path / "finished_sources")
        assert [f.name for f in files] == ["real_pm.mov"]

    def test_excludes_other_hidden_files(self, tmp_path):
        (tmp_path / "real_pm.mov").touch()
        (tmp_path / ".DS_Store").touch()
        files = collect_video_files(tmp_path, tmp_path / "finished_sources")
        assert [f.name for f in files] == ["real_pm.mov"]

    def test_excludes_finished_dir_contents(self, tmp_path):
        finished = tmp_path / "finished_sources"
        finished.mkdir()
        (tmp_path / "real_pm.mov").touch()
        (finished / "already_done_pm.mov").touch()
        files = collect_video_files(tmp_path, finished)
        assert [f.name for f in files] == ["real_pm.mov"]


# ---------------------------------------------------------------------------
# handle_failed_lossless_output — --keep-failed behavior
# ---------------------------------------------------------------------------

class TestHandleFailedLosslessOutput:
    def test_deletes_by_default(self, tmp_path):
        output_path = tmp_path / "failed_pm.mkv"
        output_path.touch()
        handle_failed_lossless_output(output_path, keep_failed=False)
        assert not output_path.exists()

    def test_keep_failed_renames_with_suffix(self, tmp_path):
        output_path = tmp_path / "failed_pm.mkv"
        output_path.touch()
        handle_failed_lossless_output(output_path, keep_failed=True)
        assert not output_path.exists()
        assert (tmp_path / "failed_pm_VALIDATION_FAILED.mkv").exists()

    def test_missing_output_is_a_no_op(self, tmp_path):
        output_path = tmp_path / "does_not_exist_pm.mkv"
        # Should not raise even though the file was never created.
        handle_failed_lossless_output(output_path, keep_failed=True)
        handle_failed_lossless_output(output_path, keep_failed=False)
