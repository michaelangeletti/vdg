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

At **v1.3.0**, with **v1.4.0** planned as an end-of-month update.

## Queued for v1.4.0

Shipped (untested on Ubuntu/other clap-free sources yet, but macOS-verified — see below):
- `coded_width`/`coded_height` now used by default in `VideoInfo` instead of `width`/`height`.
- `--clean-aperture` flag: default disables automatic clean-aperture cropping via `-apply_cropping 0` (see Key Learnings); passing the flag lets ffmpeg apply its native clap crop instead.
- VFR source detection (`r_frame_rate` vs `avg_frame_rate` divergence) — quarantines the source and skips the transcode instead of producing a corrupt lossless roundtrip.
- Any v210/FFV1 failure (not just VFR) now moves the source into a `QUARANTINE` folder under `output_dir` for review, instead of leaving it mixed in with untried files.
- `--force-anamorphic` flag: forces 854×480 scaling for SD sources mistagged as 4:3 despite being anamorphic squeezed footage.
- Filename disambiguation when the same unique ID has multiple role codes (e.g. `_pm.mov` + `_sh.mp4`) — previously these collided on the same output filename; now the source extension is appended (`_mov_sl.mp4` / `_mp4_sl.mp4`).

Still open:
- Log a warning when coded and display dimensions differ.
- Add `--keep-failed` flag to retain validation-failed output files, renamed with a `_VALIDATION_FAILED` suffix, instead of deleting them.

## Key learnings & principles

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
