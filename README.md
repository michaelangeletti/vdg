# vdg

**Video Derivative Generator** — Stanford Media Preservation Lab

`vdg` is a batch video transcoding tool for SMPL digitization and acquisition workflows. It processes video files from a source directory, generates one or more derivative formats (H.264 MP4, v210 uncompressed, ProRes 422 HQ), produces JPEG 2000 thumbnails alongside H.264 output, and maintains a per-file process log and cumulative CSV summary.

---

## Supported output formats

| Flag | Format | Notes |
|------|--------|-------|
| `-h264` | H.264 MP4 + JP2 thumbnails | All sources |
| `-v210` | v210 uncompressed 10-bit 4:2:2 QuickTime | SD sources only |
| `-prores` | ProRes 422 HQ QuickTime | SD sources only |

---

## Quick start

```bash
# H.264 derivatives from a tape digitization batch
vdg --source-dir /Volumes/disk/1/source --output-dir /Volumes/disk/1/output -h264

# DV content from dvrescue — override FPS and scan type
vdg --source-dir /path/to/source --output-dir /path/to/output \
    --force-fps 29.97 --force-scan bff -h264

# Overmodulated camera audio — apply peak ceiling
vdg --source-dir /path/to/source --output-dir /path/to/output \
    --clip-ceiling -10 --force-scan bff -h264
```

---

## Installation

See [INSTALL_MACOS.md](INSTALL_MACOS.md) or [INSTALL_UBUNTU.md](INSTALL_UBUNTU.md).

## Documentation

See [MANUAL.md](MANUAL.md) for the full command reference, flag descriptions, scaling tables, naming conventions, and troubleshooting guide.

---

## Dependencies

- Python 3.10+
- `ffmpeg` and `ffprobe` in `PATH` (must be compiled with `libx264`, `libopenjpeg`, `prores_ks`)
- `tqdm`

---

## Running tests

```bash
pip install pytest
pytest
```
