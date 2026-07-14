# VDG — Claude Code Context

Context for continuing development on this project. For usage/install docs see [README.md](README.md), [MANUAL.md](MANUAL.md), [INSTALL_MACOS.md](INSTALL_MACOS.md), [INSTALL_UBUNTU.md](INSTALL_UBUNTU.md).

## What this is

VDG (Video Derivative Generator, package `smpl-vdg`) is a batch video transcoding tool for the Stanford Media Preservation Lab's (SMPL) digitization and acquisition workflows. Michael is the primary developer/maintainer.

Two intake pipelines feed it:
1. **Digitized analog tape** (Betacam SP, Digital Betacam, VHS, U-matic, Hi8, DV) captured via `vrecord`/`dvrescue`, producing FFV1/MKV preservation masters.
2. **Born-digital HD deliverables** from vendors, often v210 QuickTime.

Three derivative types, each with a strict three-character suffix convention:

| Flag | Format | Suffix | Notes |
|---|---|---|---|
| `-h264` | H.264 MP4 + JP2 thumbnails | `_sl` | All sources |
| `-v210` | v210 uncompressed 10-bit 4:2:2 QuickTime | `_pm` | SD sources only |
| `-prores` | ProRes 422 HQ QuickTime | `_sh` | SD sources only |

**Lab infrastructure:** seven Apple Silicon Macs, two-plus Ubuntu 24.04 workstations (including a Threadripper), varying FFmpeg builds. Homebrew-managed Python is the preferred macOS baseline.

## Current state

At **v1.4.0**.

## Shipped in v1.4.0

- `coded_width`/`coded_height` now used by default in `VideoInfo` instead of `width`/`height`.
- `--clean-aperture` flag: default disables automatic clean-aperture cropping via `-apply_cropping 0` (see Key Learnings); passing the flag lets ffmpeg apply its native clap crop instead. Verified against a real clap-tagged v210 source (macOS, FFmpeg 8.1.2) — MediaInfo confirmed 720x486 preserved by default, 704x480 with `--clean-aperture`.
- VFR source detection (`r_frame_rate` vs `avg_frame_rate` divergence) — quarantines the source and skips the transcode instead of producing a corrupt lossless roundtrip.
- Any v210/FFV1 failure (not just VFR) now moves the source into a `QUARANTINE` folder under `output_dir` for review, instead of leaving it mixed in with untried files.
- `--force-anamorphic` flag: forces 854×480 scaling for SD sources mistagged as 4:3 despite being anamorphic squeezed footage. Required a `setsar=1` fix to actually take effect — see Key Learnings.
- Filename disambiguation when the same unique ID has multiple role codes (e.g. `_pm.mov` + `_sh.mp4`) — previously these collided on the same output filename; now the source extension is appended (`_mov_sl.mp4` / `_mp4_sl.mp4`). Extension alone isn't always enough — see Key Learnings.
- Every ffmpeg/MediaConch command (encode, framemd5/streamhash hashing, policy check) is now logged verbatim to the process log for troubleshooting.

## Queued for next release

- Log a warning when coded and display dimensions differ.
- Add `--keep-failed` flag to retain validation-failed output files, renamed with a `_VALIDATION_FAILED` suffix, instead of deleting them.

## Key learnings & principles

- **Whole-file average frame rate (`avg_frame_rate` vs `r_frame_rate`) is too coarse to detect real-world VFR.** A production file was found with only a *local* dip to 14.985fps (a handful of held/duplicated frames out of 84,603 total) — the overall average still rounded to the nominal 29.970fps, so the average-based check missed it entirely and the file transcoded and validated as if it were clean. Fixed by also checking actual per-packet durations directly from the container index (`ffprobe -show_entries packet=duration_time`, no decode needed) — catches VFR regardless of how small a fraction of frames is affected. Both checks are kept (OR'd together); the packet-duration check is gated to only run when `-v210`/`-ffv1` is requested, since it's more expensive than the average check.
- **AppleDouble sidecar files (`._filename`) get created automatically by macOS on non-native filesystems** (exFAT/NTFS external drives) and match `VIDEO_EXTENSIONS` by extension alone. `collect_video_files()` now skips any filename starting with `.` during discovery — without this, a `._foo.mov` sidecar gets treated as a real source, fails ffprobe, and gets quarantined instead of (or in addition to) the actual file needing review.
- **Filename disambiguation by extension alone isn't always unique.** A real test case had `bm994hd4640_pm.mov` + `bm994hd4640_sh.mov` + `bm994hd4640_sl.mp4` sharing one ID — two of the three shared the `.mov` extension, so both resolved to the same disambiguated stem and the second silently overwrote the first's H.264 output and thumbnails. `compute_filename_disambiguation()` now tries extension alone first, and falls back to `role_code + extension` for the whole ID group if extension alone isn't unique across it. Always verify disambiguation fixes by listing the actual output directory, not just the run summary — a per-file "Success" doesn't reveal a same-batch overwrite.
- **`scale=WxH` alone doesn't change display aspect ratio — it silently gets reverted.** FFmpeg's `scale` filter, when given only literal width/height with no explicit `sar`, recalculates the output SAR to *preserve the source's original DAR*. So `--force-anamorphic`'s `scale=854:480` produced 854x480 pixels but FFmpeg re-tagged it with a narrow SAR that forced playback right back to the source's (wrong) 4:3 — completely negating the override. This was invisible in the two pre-existing (non-forced) scaling cases only because their target dimensions were already chosen to be DAR-correct as square pixels. Fixed by adding `setsar=1` after every `scale=` in both the H.264 encode filter chain and the thumbnail filter chain — confirmed via `ffprobe -show_entries stream=...,sample_aspect_ratio,display_aspect_ratio` on both the forced and normal paths.
- **FFmpeg version divergence between macOS and Ubuntu is a recurring source of bugs**, particularly around `clap` atom handling and container behavior. Always consider both platforms when touching video probing/encoding code.
- **framemd5 for video, streamhash for audio.** Audio framemd5 validation fails due to container re-packetization differences between MKV and MOV; streamhash is correct for lossless audio validation.
- **`coded_width`/`coded_height` vs. `width`/`height`.** On FFmpeg 8.1.2 (macOS), ffprobe's `width`/`height` were observed equal to `coded_width`/`coded_height` for a clap-tagged v210 source — the crop instead showed up as stream-level `Side data: Frame Cropping` (crop_top/bottom/left/right). Using coded dimensions is still correct/harmless, but the real crop mechanism at transcode time is separate — see next point.
- **The actual clean-aperture crop is controlled by the generic decoder option `-apply_cropping`** (boolean, default `true`), not `-flags2 +ignorecrop` (that only affects codec-level SPS conformance-window cropping, not container-derived `clap` side data). Confirmed empirically on a real file (`bm994hd4640_pm.mov`, 720x486 with clap crop 8/8/3/3 → 704x480 display): `-flags2 +ignorecrop` had **no effect** (still cropped to 704x480 either way via MediaInfo), while `-apply_cropping 0` is the correct flag to preserve the full coded frame for lossless FFV1/v210 masters. `vdg`'s `--clean-aperture` flag toggles this (default off = `-apply_cropping 0` = full frame preserved).
- **framemd5 validation only proves internal self-consistency, not true losslessness against the original.** If the source-hash command and the encode command don't use identical crop-handling flags, framemd5 can pass while silently comparing two equally-wrong (or two equally-right) results — it can't catch a crop that's applied consistently to both sides. Always verify actual pixel dimensions (MediaInfo/ffprobe on the output) when testing crop-related fixes, not just the framemd5 PASS.
- **VFR sources break frame count assumptions.** Vendor-delivered v210 files may technically be variable frame rate, causing false validation failures on round-trip transcoding.
- **Standard Homebrew FFmpeg bottles omit `libopenjpeg`.** Machines needing correct JP2 output need the `homebrew-ffmpeg/ffmpeg` tap built `--with-openjpeg`.
- **Preserve all existing logic when adding features.** Changes should be surgical — only modify what's necessary.
- **Source and output directories must always be separate.** Resume logic incorrectly picks up derivative files as sources when directories are shared; this is a workflow convention, not a code-level filter.
- **Audio mapping must always be appended before conditional audio filter args.** Past bug: `audio_mapping` was omitted when `audio_filter_args` was present, causing silent audio failures.
- **`mono-merge` mode** uses `amerge` + `pan` to center-pan both mono streams equally onto left and right.

## Development approach

- Iterative, incremental — preserve existing behavior with each change.
- Features are driven by real production problems (specific tape formats, vendor file quirks, platform FFmpeg differences), not speculative design.
- Verbose terminal output is preferred: processing status, interlacing detection, and validation results should appear both in the terminal and in process logs.
- Log files include a consistent header banner identifying the lab and script version.
- Resume capability via CSV tracking is a core workflow feature.
- Per-machine default source/output paths are hardcoded by editing the installed `cli.py` directly (located via `grep -n "mangelet"`); on pipx installs, shell aliases in `.zshrc` are used instead.

## Tools & ecosystem

- **FFmpeg / ffprobe** — core transcoding/inspection engine; needs `libx264`, `libopenjpeg`, `prores_ks`. Version varies by machine.
- **vrecord** — analog tape capture on macOS workstations.
- **dvrescue** — DV tape capture and packaging.
- **MediaConch** — policy-based validation for FFV1/MKV and v210; CLI flag syntax is `--Policy=` (capital P, equals sign) for cross-platform compatibility.
- **MediaInfo (MediaArea)** — technical metadata inspection, used for manual QC alongside VDG output.
- **QCTools** — video QC analysis (signal metrics, filter scopes) for reviewing derivatives.
- **VLC** — manual playback review of derivatives.
- **Homebrew** — preferred macOS package manager; Homebrew-managed Python is the clean baseline.
