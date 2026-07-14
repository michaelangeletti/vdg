# Installation — Ubuntu 24.04 LTS

---

## 1. Update package index

```bash
sudo apt update && sudo apt upgrade -y
```

---

## 2. Install FFmpeg

```bash
sudo apt install -y ffmpeg
```

Verify that `libx264` and `libopenjpeg` are present in the build:

```bash
ffmpeg -buildconf 2>&1 | grep -E "libx264|libopenjpeg"
```

If either is missing, build FFmpeg from source or use a PPA with full codec support (e.g., `ppa:savoury1/ffmpeg4`).

> **Note:** `aac_at` (AudioToolbox) is macOS-only. On Ubuntu, `vdg` will automatically fall back to `libfdk_aac` if available, or the built-in `aac` encoder. To install `libfdk_aac`:
>
> ```bash
> sudo apt install -y libfdk-aac-dev
> ```
>
> Then rebuild FFmpeg with `--enable-libfdk-aac`, or use a third-party build that includes it.

---

## 3. Install Python 3.10+

Ubuntu 24.04 ships with Python 3.12. Verify:

```bash
python3 --version
```

Install pip if not present:

```bash
sudo apt install -y python3-pip
```

---

## 4. Clone the repository

```bash
git clone https://github.com/michaelangeletti/vdg.git
cd vdg
```

---

## 5. Install the package

```bash
pip3 install -e .
```

If your user `bin` directory is not in `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add to `~/.bashrc` to make permanent.

---

## 6. Verify installation

```bash
vdg --help
vdg --version
```

---

## 7. Install MediaConch (optional)

MediaConch enables policy conformance checks on `-v210` and `-ffv1` output (Matroska/FFV1 structure, v210 NTSC technical profile). If it's not installed, `vdg` logs a warning at startup and skips the check — it does not fail the run. Ubuntu's default repos don't carry it; install it from the MediaArea repository:

```bash
wget https://mediaarea.net/repo/deb/repo-mediaarea_1.0-27_all.deb
sudo dpkg -i repo-mediaarea_1.0-27_all.deb
sudo apt update
sudo apt install -y mediaconch
```

> If the `.deb` filename above 404s, MediaArea has published a newer repo package — check [mediaarea.net/en/Repos](https://mediaarea.net/en/Repos) for the current version number and substitute it above.

Verify:

```bash
mediaconch --version
```

---

## Running tests

```bash
pip3 install pytest
pytest
```
