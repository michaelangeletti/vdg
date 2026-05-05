# Video Derivative Generator (vdg)
## User Manual — v1.1
**Stanford Media Preservation Lab**
*May 2026*

---

## Table of Contents

1. [Overview](#overview)
2. [Dependencies](#dependencies)
3. [Intake Pipelines](#intake-pipelines)
4. [Output Formats](#output-formats)
5. [Scaling and Resolution Handling](#scaling-and-resolution-handling)
6. [Directory Structure](#directory-structure)
7. [Naming Conventions](#naming-conventions)
8. [Command Reference](#command-reference)
9. [Audio Configuration](#audio-configuration)
10. [Override Flags](#override-flags)
11. [Thumbnails](#thumbnails)
12. [Validation and Logging](#validation-and-logging)
13. [Usage Examples](#usage-examples)
14. [Troubleshooting](#troubleshooting)

---

## Overview

`vdg` (Video Derivative Generator) is a batch video transcoding tool for the Stanford Media Preservation Lab. It processes video files from a source directory, generates one or more derivative formats, produces JPEG 2000 thumbnails alongside H.264 output, and moves completed source files to a finished archive folder. All operations are logged to a per-file process log and a cumulative CSV summary.

The script is designed around two distinct intake pipelines:

- **Tape digitization** — FFV1/MKV preservation masters produced by the SMPL digitization workflow from analog formats (Betacam SP, Digital Betacam, VHS, U-matic, Hi8, DV)
- **Acquired digital content** — born-digital HD deliverables from vendors and distributors

At least one output format flag (`-h264`, `-v210`, `-prores`) must be specified on every invocation.

---

## Dependencies

| Tool | Purpose |
|------|---------|
| `ffmpeg` | All encoding, filtering, and thumbnail generation |
| `ffprobe` | Source file metadata detection |
| Python 3 | Runtime |
| `tqdm` | Progress bar display |

Both `ffmpeg` and `ffprobe` must be present in `PATH`. The script checks for them at startup and exits if either is missing.

**AAC encoder autodetection:** The script probes for AAC encoders at startup in priority order: `aac_at` (macOS AudioToolbox, preferred) → `libfdk_aac` → `aac` (FFmpeg native). The selected encoder is logged and used for all H.264 output in that session.

---

## Intake Pipelines

### Tape Digitization (SD)

Source files are FFV1-encoded MKV containers produced by the SMPL tape digitization workflow. These files follow a strict naming convention using the `_pm` role code suffix. The script is well-tested against this population.

Supported source formats: Betacam SP, Digital Betacam, VHS, U-matic, Hi8, DV

**DV note:** DV content is captured and packaged using dvrescue (MIPoPS). dvrescue-packaged DV-in-MKV files can present unreliable container metadata — in particular, ffprobe may misread the frame rate. Use `--force-fps 29.97` and `--force-scan bff` when processing standard NTSC DV sources from this workflow.

**v210 and ProRes output are restricted to SD sources** (NTSC or PAL video standards). These formats are only applicable to the tape digitization pipeline. Attempting to generate v210 or ProRes from a source that does not resolve to NTSC or PAL will produce an error.

### Acquired Digital Content (HD)

Born-digital deliverables from vendors, distributors, and licensing partners. These files may arrive as H.264 or H.265 in `.mov` or `.mp4` containers, or occasionally as other formats. This population is more variable in its technical attributes. The `-h264` output flag is the appropriate derivative for this pipeline.

---

## Output Formats

### H.264 MP4 (`-h264`)

Two-pass H.264 encode targeting the `main` profile. JPEG 2000 thumbnails are generated alongside every H.264 output.

| Parameter | SD (≤576 lines) | HD (>576 lines) |
|-----------|----------------|----------------|
| Target bitrate | 1000 kbps | 2800 kbps |
| Max bitrate | 1200 kbps | 2900 kbps |
| Buffer size | 2000 kbps | 5800 kbps |
| GOP | 2× output frame rate | 2× output frame rate |
| Profile | Main | Main |
| Pixel format | yuv420p | yuv420p |

Interlaced sources are deinterlaced using `bwdif` before encoding. Progressive sources pass through without deinterlacing.

Audio: AAC stereo, 48 kHz, 128 kbps. See [Audio Configuration](#audio-configuration) for channel routing options.

Output filename: `<base>_sl.mp4`

### v210 QuickTime (`-v210`)

Uncompressed 10-bit 4:2:2 in a QuickTime container. **SD sources only.** A framemd5 lossless validation is performed after encoding, comparing the video stream of the output against the source frame by frame, and comparing audio stream hashes. The output file is deleted if validation fails.

Color metadata is set per standard:

| Standard | Field order | SAR |
|----------|-------------|-----|
| NTSC | BFF | 10:11 |
| PAL | TFF | 12/11 |

Audio: PCM 24-bit little-endian (`pcm_s24le`).

Output filename: `<stem>.mov` (no role code change)

### ProRes 422 HQ QuickTime (`-prores`)

Apple ProRes 422 HQ using the `prores_ks` encoder, profile 3, vendor tag `apl0`. Audio is copied from the source stream without re-encoding.

Output filename: `<base>_sh.mov`

---

## Scaling and Resolution Handling

The script resolves output scale based on source width, height, and DAR. The table below summarizes all handled cases.

| Source dimensions | DAR | Output scale | Notes |
|-------------------|-----|--------------|-------|
| 720×480 or 720×486 (NTSC) | 4:3 | 640×480 | Standard NTSC SD |
| 720×480 or 720×486 (NTSC) | 16:9 | 854×480 | Widescreen NTSC SD |
| 352×480 (NTSC) | 4:3 | 640×480 | Half-D1 NTSC — direct-to-disc DVD recorders |
| 720×576 (PAL) | 4:3 | 640×480 | Standard PAL SD |
| 720×576 (PAL) | 16:9 | 854×480 | Widescreen PAL SD |
| 1440×1080 | 16:9 | 1280×720 | Anamorphic HD (e.g. HDV) |
| 1920×1080 | any | 1280×720 | Full HD downscale |
| 1280×720 | any | 1280×720 | Native 720p passthrough |
| >1920 or >1080 | 16:9 | 1280×720 | Ultra-HD downscale |
| >1920 or >1080 | other | -2:720 | Width calculated to preserve AR |
| All other | any | Source dimensions (mod-2 safe) | Passthrough with dimension rounding |

Frame rate handling: sources with frame rates above the standard threshold for their standard (>30 fps for NTSC, >25 fps for PAL) are halved on output. This handles 50i/60i sources correctly.

---

## Directory Structure

```
<source-dir>/
    source_file_pm.mkv          ← input files processed from here
    finished_sources/           ← source files moved here after successful processing

<output-dir>/
    source_file_sl.mp4          ← H.264 derivative
    source_file_sl.mov          ← v210 derivative
    source_file_sh.mov          ← ProRes derivative
    source_file_thumb_1.jp2     ← thumbnails (alongside H.264 output)
    source_file_thumb_2.jp2
    ...
    transcode_summary.csv       ← cumulative run log
    process_logs/
        source_file_pm_process.log   ← per-file detailed log
        transcode_YYYYMMDD_HHMMSS.log ← session log
```

The `finished_sources` and `process_logs` directories are created automatically. Source files are moved to `finished_sources` on successful completion by default (see `--no-move-finished`).

---

## Naming Conventions

### Role code suffixes

Source files are expected to use a three-character role code suffix:

| Suffix | Role |
|--------|------|
| `_pm` | Preservation master |
| `_sh` | Service high |
| `_sl` | Service low |

### Output filename derivation

The script strips a recognized role code suffix (`_pm`, `_sh`, or `_sl`) from the source stem before constructing output names. If no recognized suffix is present, the full stem is preserved and the output role code is appended directly.

**Examples:**

| Source filename | H.264 output | ProRes output |
|-----------------|-------------|---------------|
| `abc123_pm.mkv` | `abc123_sl.mp4` | `abc123_sh.mov` |
| `abc123_sh.mkv` | `abc123_sl.mp4` | `abc123_sh.mov` |
| `vendor_delivery.mov` | `vendor_delivery_sl.mp4` | `vendor_delivery_sh.mov` |

**Spaces in filenames:** All spaces in source filename stems are replaced with underscores in every output filename. This is applied universally regardless of whether the source filename follows the role code convention.

---

## Command Reference

### Required flags (at least one must be specified)

| Flag | Output |
|------|--------|
| `-h264` | H.264 MP4 with JPEG 2000 thumbnails |
| `-v210` | v210 uncompressed 10-bit 4:2:2 QuickTime (SD only) |
| `-prores` | ProRes 422 HQ QuickTime (SD only) |

### Directory flags

| Flag | Default | Description |
|------|---------|-------------|
| `--source-dir PATH` | (set in script) | Directory containing source video files |
| `--output-dir PATH` | (set in script) | Directory for all output files and logs |

### Processing flags

| Flag | Default | Description |
|------|---------|-------------|
| `--workers N` | `1` | Number of parallel worker processes. `1` = sequential processing |
| `--dry-run` | off | Simulate processing without writing any files or moving sources |
| `--cleanup-only` | off | Delete temporary files only; skip all encoding |
| `--move-finished` | on | Move source files to `finished_sources/` after successful processing |
| `--no-move-finished` | — | Disable source file movement |
| `--skip-validation` | off | Skip post-encode H.264 validation (faster but less safe) |

### Override flags

| Flag | Default | Description |
|------|---------|-------------|
| `--force-scan [progressive\|tff\|bff]` | auto-detect | Override ffprobe scan type detection |
| `--force-fps FLOAT` | auto-detect | Override ffprobe frame rate detection |
| `--thumbs N` | `4` | Override number of thumbnails generated |

---

## Audio Configuration

All audio options apply to H.264 output only. ProRes audio is copied from the source stream. v210 audio is encoded as PCM 24-bit.

### `--audio-stream`

Selects the audio stream to use for H.264 output. Default: `0:a:0` (first audio stream).

```bash
--audio-stream 0:a:0    # first audio stream (default)
--audio-stream 0:a:1    # second audio stream
```

### `--audio-mode`

Controls channel routing. Default: `stereo`.

| Mode | Behavior |
|------|---------|
| `stereo` | Pass the selected stream through as-is |
| `mono-duplicate` | Take channel 0 of the selected stream and duplicate it to both L and R output channels |
| `mono-merge` | Merge streams `0:a:0` and `0:a:1` (both channels summed and center-panned to L+R) |

`mono-merge` overrides `--audio-stream` and always combines the first two audio streams. This is useful for DV sources where left and right channels are packaged as two separate mono streams.

### `--audio-pan-center`

When used with `--audio-mode stereo`, mixes both input channels equally to both output channels (`c0 = 0.5*c0 + 0.5*c1`, same for c1). Useful for content where dialogue and music are split across channels and both should be present at equal level on both sides.

### `--clip-ceiling FLOAT`

Applies a peak ceiling to the audio output at the specified level in dBFS. Accepts a negative float value.

```bash
--clip-ceiling -10    # limit peaks to -10 dBFS
```

Uses `dynaudnorm` configured with a maximum gain factor of 1.0, meaning the filter **only reduces, never boosts**. Quiet passages are left at their original level. Loud passages are brought down toward the ceiling. Response time is fast (100ms analysis frames, 3-frame Gaussian window) to minimize audible level transitions.

This flag is intended for overmodulated camera audio where the source recording level was set too high. It does not remove analog distortion that was introduced at record time — it only prevents peaks in the derivative from exceeding the specified ceiling.

`--clip-ceiling` is compatible with all `--audio-mode` and `--audio-pan-center` combinations.

---

## Override Flags

### `--force-scan`

Overrides ffprobe's field order detection. Choices: `progressive`, `tff`, `bff`.

| Value | Effect |
|-------|--------|
| `progressive` | Skip deinterlacing; treat source as progressive |
| `tff` | Force top-field-first deinterlacing |
| `bff` | Force bottom-field-first deinterlacing |

Standard NTSC DV is bottom-field-first. Use `--force-scan bff` when processing DV sources from dvrescue/dvpackager whose container metadata ffprobe misreads.

### `--force-fps`

Overrides ffprobe's frame rate detection. Accepts a float value.

```bash
--force-fps 29.97
--force-fps 25
```

This flag is applied before video standard detection, so it correctly propagates to GOP calculation, output frame rate, progress bar frame count, and NTSC/PAL classification. Use when processing dvrescue-packaged DV-in-MKV files where ffprobe may misread the frame rate from container metadata (e.g., reporting 30,000 fps).

Both `--force-fps` and `--force-scan` can be used together.

---

## Thumbnails

JPEG 2000 thumbnails (`.jp2`) are generated alongside every H.264 output. They are not generated for v210 or ProRes-only runs.

- **Default:** 4 thumbnails at positions 10%, 40%, 60%, and 90% of the file's duration
- **Override:** `--thumbs N` generates N thumbnails at randomly selected positions between 5% and 95% of duration

Thumbnails are scaled to the same output resolution as the H.264 derivative. Interlaced sources are deinterlaced before thumbnail extraction using the same field order as the H.264 encode.

**Technical specifications:** 8-bit RGB, JPEG 2000 compression, encoded via `libopenjpeg`.

**Naming:** `<base>_thumb_1.jp2`, `<base>_thumb_2.jp2`, etc.

If H.264 encoding fails, all thumbnails for that file are deleted as part of cleanup.

---

## Validation and Logging

### H.264 validation

After pass 2 completes, the output MP4 is decoded end-to-end using `ffmpeg -f null`. Any decode errors cause the file to be flagged as failed. Can be skipped with `--skip-validation`.

### v210 lossless validation

After v210 encoding, a framemd5 comparison is performed:

1. Frame hashes are generated for the source video stream
2. Frame hashes are generated for the output video stream
3. Hashes are compared frame by frame
4. Audio stream hashes (MD5) are generated and compared for source and output

If any mismatch is detected, the output file is deleted and the job is marked as an error. Validation results are written to the per-file process log.

### Log files

**Per-file process log** (`process_logs/<stem>_process.log`): Records ffmpeg command output for all passes, audio configuration, interlacing status, and v210 validation results if applicable.

**Session log** (`process_logs/transcode_YYYYMMDD_HHMMSS.log`): Records all INFO and above events for the session.

**CSV summary** (`transcode_summary.csv`): Appended on every run. Columns: Timestamp, Source File, Status, Audio, Details. Files already present in the CSV with a `Success` status are skipped on subsequent runs unless their output derivatives are missing.

### Skip logic

A file is skipped (not re-processed) if both conditions are true:
- The source filename appears in `transcode_summary.csv` with `Success` status from a previous run
- All expected output files (derivatives + thumbnails) are present on disk

If output files are missing despite a CSV entry, the file will be re-processed.

---

## Usage Examples

### Basic tape digitization — H.264 only

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output -h264
```

### H.264 plus v210 for NTSC tape sources

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output -h264 -v210
```

### All three output formats

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output -h264 -v210 -prores
```

### DV source from dvrescue — override FPS and scan type

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --force-fps 29.97 --force-scan bff -h264
```

### Overmodulated DV audio — apply peak ceiling

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --force-scan bff --clip-ceiling -10 -h264
```

### DV source with two-channel mono audio — merge to stereo

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --audio-mode mono-merge --force-scan bff -h264
```

### DV source with single mono channel — duplicate to L+R

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --audio-mode mono-duplicate --audio-stream 0:a:0 --force-scan bff -h264
```

### Select a specific audio stream

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --audio-stream 0:a:1 -h264
```

### Custom thumbnail count

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --thumbs 6 -h264
```

### Dry run — preview without encoding

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --dry-run -h264
```

### Keep source files in place after processing

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --no-move-finished -h264
```

### Parallel processing (use with care — monitor disk I/O)

```bash
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output \
    --workers 2 -h264
```

---

## Troubleshooting

### "Cannot create v210 output: video is not NTSC or PAL standard"

v210 output is restricted to SD sources that resolve to NTSC (720×480/486, 29.97 fps) or PAL (720×576, 25 fps). HD sources, non-standard frame rates, or non-standard dimensions will not qualify. If the source is a valid SD tape output but the error still occurs, check whether ffprobe is misreading the frame rate — use `--force-fps` to correct it.

### "At least one output format must be specified"

One of `-h264`, `-v210`, or `-prores` must be included in every invocation.

### DV source processes but frame rate / GOP is wrong

dvrescue-packaged DV-in-MKV files can report incorrect frame rates in container metadata. Always use `--force-fps 29.97` for standard NTSC DV sources from this workflow. If you see very large GOP values or unusually fast/slow progress bars, this is the likely cause.

### Audio sounds wrong — only one channel has content

If the source has two discrete mono audio streams (common in DV), the default `stereo` audio mode will pass stream `0:a:0` as the left channel and may result in silence on the right. Use `--audio-mode mono-merge` to combine both streams, or `--audio-mode mono-duplicate` to mirror a single channel to both sides.

### H.264 file exists but job re-processes anyway

The skip logic requires both a `Success` entry in the CSV *and* all output files present on disk. If any thumbnail is missing, the file will be re-processed from scratch. Check that all `_thumb_N.jp2` files are present in the output directory.

### v210 lossless validation fails

Check the process log for the specific frame numbers where the mismatch occurred. Common causes: source file corruption, interrupted encoding run, or disk I/O errors during encoding. Re-run the job; if validation fails consistently on the same file, the source may be damaged.

### Output file has no audio

Confirm the source has an audio stream (`ffprobe <file>`). If the stream exists but uses a non-default stream index, use `--audio-stream 0:a:1` (or the appropriate index). If the source genuinely has no audio, `[No Audio]` will be logged and an audio-free output is expected behavior.

### Output from a DVD-sourced MPEG-2 file is 352×480 instead of 640×480

The source is likely half-D1 NTSC (352×480), a reduced horizontal resolution format used by direct-to-disc DVD recorders. These files use non-square pixels (SAR 20:11) with a 4:3 DAR, which should display at 640×480. The script handles this case explicitly and will scale to 640×480 to match standard NTSC derivative output. If the output is coming out at the wrong resolution, confirm the DAR reported by ffprobe is `4:3` — if the container metadata is incorrect, the passthrough branch may have been triggered instead.

### Low disk space warning at startup

The script checks for a minimum of 10 GB free in the output directory before processing. This is a warning, not a hard stop, but running with insufficient space will cause encoding failures mid-job. Uncompressed v210 output in particular requires significant disk space — a 30-minute NTSC file produces approximately 50–60 GB.

---

*Stanford Media Preservation Lab — Video Derivative Generator v1.1 — May 2026*
