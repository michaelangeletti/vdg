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
git clone https://github.com/michaelangeletti/smpl-vdg.git
cd smpl-vdg
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
```

---

## Running tests

```bash
pip3 install pytest
pytest
```
