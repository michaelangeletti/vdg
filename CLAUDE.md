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

- Switch ffprobe `VideoInfo` to use `coded_width`/`coded_height` instead of `width`/`height` — critical fix for macOS FFmpeg 7.x+, which honors QuickTime `clap` clean aperture atoms and crops 720×486 v210 down to 704×480 before encoding, corrupting preservation masters. (Ubuntu with FFmpeg 6.1.1 is unaffected.)
- Add `--clean-aperture` flag for explicit display-dimension mode.
- Log a warning when coded and display dimensions differ.
- Add VFR source detection warning (vendor v210 files that are technically variable frame rate cause frame count discrepancies and false framemd5 failures).
- Add `--keep-failed` flag to retain validation-failed output files, renamed with a `_VALIDATION_FAILED` suffix, instead of deleting them.
- Commit the `--Policy=` MediaConch fix properly to GitHub.

## Key learnings & principles

- **FFmpeg version divergence between macOS and Ubuntu is a recurring source of bugs**, particularly around `clap` atom handling and container behavior. Always consider both platforms when touching video probing/encoding code.
- **framemd5 for video, streamhash for audio.** Audio framemd5 validation fails due to container re-packetization differences between MKV and MOV; streamhash is correct for lossless audio validation.
- **`coded_width`/`coded_height` vs. `width`/`height`.** macOS FFmpeg 7.x+ applies clean aperture cropping to display dimensions; coded dimensions must be used for preservation master encoding.
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
