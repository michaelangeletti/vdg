# Installation — macOS (Apple Silicon)

Tested on macOS 13+ with M1/M2/M3/M4 processors.

---

## 1. Install Homebrew

If not already installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

---

## 2. Install FFmpeg

Install the full-featured FFmpeg tap, which includes `libx264`, `libopenjpeg`, and AudioToolbox (`aac_at`) support:

```bash
brew install ffmpeg
```

Verify:

```bash
ffmpeg -version
ffprobe -version
```

---

## 3. Install Python 3.10+

macOS ships with Python 3, but it is recommended to use a Homebrew-managed version:

```bash
brew install python@3.12
```

---

## 4. Clone the repository

```bash
git clone https://github.com/michaelangeletti/smpl-vdg.git
cd smpl-vdg
```

---

## 5. Install the package

Install in editable mode so that changes to the source are reflected immediately:

```bash
pip3 install -e .
```

This installs the `vdg` command into your Python environment's `bin` directory. If it is not in your `PATH`, add it:

```bash
export PATH="$(python3 -m site --user-base)/bin:$PATH"
```

Add the above line to your `~/.zshrc` to make it permanent.

---

## 6. Verify installation

```bash
vdg --help
```

---

## Optional: run directly from bin/

The `bin/vdg` script can also be run directly without installation, as long as the repository root is in your `PYTHONPATH`:

```bash
export PYTHONPATH=/path/to/smpl-vdg
python3 bin/vdg --help
```

---

## Running tests

```bash
pip3 install pytest
pytest
```
