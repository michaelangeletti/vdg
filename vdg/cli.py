"""
vdg.cli — core logic for the Video Derivative Generator.

Stanford Media Preservation Lab
Video Derivative Generator - v1.1
May 2026
"""

import os
import sys
import subprocess
import json
import math
import csv
import shutil
import re
import random
import argparse
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

SCRIPT_TITLE = "Stanford Media Preservation Lab"
SCRIPT_NAME = "Video Derivative Generator, v1.1, May 2026"
SCRIPT_SEPARATOR = "----"

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

class ProcessStatus(Enum):
    SUCCESS = "Success"
    ERROR = "Error"
    SKIPPED = "Skipped"
    INCOMPLETE = "Incomplete"

class VideoStandard(Enum):
    NTSC = "ntsc"
    PAL = "pal"
    UNKNOWN = "unknown"

VIDEO_EXTENSIONS = (
    '.mp4', '.mov', '.mkv', '.mxf', '.avi', '.mpg', '.mpeg', '.m2v', '.ts',
    '.vob', '.wmv', '.asf', '.flv', '.f4v', '.rm', '.rmvb', '.dv', '.dif',
    '.webm', '.ogg', '.ogv', '.3gp', '.3g2', '.m4v'
)

BITRATE_CONFIG = {
    'sd': {'bitrate': '1000k', 'maxrate': '1200k', 'bufsize': '2000k'},
    'hd': {'bitrate': '2800k', 'maxrate': '2900k', 'bufsize': '5800k'}
}

THUMBNAIL_POSITIONS = [0.10, 0.40, 0.60, 0.90]
GOP_MULTIPLIER = 2
VALIDATION_TIMEOUT = 300

@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    fps: float
    dar: str
    has_audio: bool
    total_frames: int
    codec: str
    interlaced: bool

@dataclass
class ProcessingResult:
    source_file: str
    status: ProcessStatus
    audio_status: str
    message: str
    timestamp: str

@dataclass
class ProcessingStats:
    total: int = 0
    success: int = 0
    error: int = 0
    skipped: int = 0
    failed_files: List[str] = None
    
    def __post_init__(self):
        if self.failed_files is None:
            self.failed_files = []

class Config:
    def __init__(self, args: argparse.Namespace):
        self.source_dir = Path(args.source_dir)
        self.output_dir = Path(args.output_dir)
        self.finished_dir = self.source_dir / "finished_sources"
        self.log_dir = self.output_dir / "process_logs"
        self.csv_log = self.output_dir / "transcode_summary.csv"
        self.cleanup_only = args.cleanup_only
        self.move_finished = args.move_finished
        self.dry_run = args.dry_run
        self.workers = args.workers
        self.skip_validation = args.skip_validation
        self.output_h264 = args.h264
        self.output_v210 = args.v210
        self.output_prores = args.prores
        self.audio_stream = args.audio_stream
        self.audio_mode = args.audio_mode
        self.audio_pan_center = args.audio_pan_center
        self.force_scan = args.force_scan
        self.force_fps = args.force_fps
        self.thumb_count = args.thumbs
        self.clip_ceiling = args.clip_ceiling
        self.aac_encoder = detect_aac_encoder()
        
        if not (self.output_h264 or self.output_v210 or self.output_prores):
            raise ValueError("At least one output format must be specified (-h264, -v210, or -prores)")
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {self.source_dir}")
        for directory in [self.output_dir, self.log_dir, self.finished_dir]:
            directory.mkdir(parents=True, exist_ok=True)
def setup_logging(log_dir: Path, dry_run: bool) -> logging.Logger:
    logger = logging.getLogger('video_transcoder')
    logger.setLevel(logging.DEBUG)
    
    class ColoredFormatter(logging.Formatter):
        FORMATS = {
            logging.DEBUG: Colors.CYAN + '%(levelname)s: %(message)s' + Colors.RESET,
            logging.INFO: Colors.GREEN + '%(levelname)s: %(message)s' + Colors.RESET,
            logging.WARNING: Colors.YELLOW + '%(levelname)s: %(message)s' + Colors.RESET,
            logging.ERROR: Colors.RED + '%(levelname)s: %(message)s' + Colors.RESET,
            logging.CRITICAL: Colors.RED + Colors.BOLD + '%(levelname)s: %(message)s' + Colors.RESET,
        }
        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)
    
    if not dry_run:
        log_file = log_dir / f"transcode_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
        with open(log_file, 'a') as f:
            f.write(SCRIPT_TITLE + "\n" + SCRIPT_NAME + "\n" + SCRIPT_SEPARATOR + "\n" + SCRIPT_SEPARATOR + "\n\n")
    return logger

def detect_aac_encoder() -> str:
    for encoder in ['aac_at', 'libfdk_aac', 'aac']:
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=10
            )
            if f' {encoder} ' in result.stdout:
                return encoder
        except Exception:
            continue
    return 'aac'

def check_dependencies() -> bool:
    logger = logging.getLogger('video_transcoder')
    for tool in ['ffmpeg', 'ffprobe']:
        if shutil.which(tool) is None:
            logger.error(f"Required tool '{tool}' not found in PATH")
            return False
    logger.info("All required dependencies found")
    return True

def check_disk_space(output_dir: Path, required_gb: float = 10.0) -> bool:
    logger = logging.getLogger('video_transcoder')
    stat = shutil.disk_usage(output_dir)
    available_gb = stat.free / (1024 ** 3)
    if available_gb < required_gb:
        logger.warning(f"Low disk space: {available_gb:.2f} GB available (recommended: {required_gb} GB)")
        return False
    logger.info(f"Disk space OK: {available_gb:.2f} GB available")
    return True

def get_completed_files(csv_path: Path) -> Set[str]:
    completed = set()
    if not csv_path.exists():
        return completed
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Status') == ProcessStatus.SUCCESS.value:
                    completed.add(row.get('Source File'))
    except Exception as e:
        logging.getLogger('video_transcoder').warning(f"Error reading CSV log: {e}")
    return completed

def log_to_csv(csv_path: Path, result: ProcessingResult, dry_run: bool):
    if dry_run:
        return
    file_exists = csv_path.exists()
    try:
        with open(csv_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Source File', 'Status', 'Audio', 'Details'])
            writer.writerow([result.timestamp, result.source_file, result.status.value, result.audio_status, result.message])
    except Exception as e:
        logging.getLogger('video_transcoder').error(f"Error writing to CSV: {e}")

def format_file_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours > 0 else f"{minutes:02d}:{secs:02d}"

def get_file_info_for_display(file_path: Path) -> Tuple[int, float]:
    try:
        size = file_path.stat().st_size
        info = get_video_info(file_path)
        return size, info.duration
    except Exception:
        return 0, 0.0

def get_video_info(file_path: Path) -> VideoInfo:
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', str(file_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise Exception("ffprobe timeout - file may be corrupt")
    except json.JSONDecodeError:
        raise Exception("Failed to parse ffprobe output")
    except Exception as e:
        raise Exception(f"ffprobe failed: {e}")
    
    v_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    a_stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)
    if not v_stream:
        raise Exception("No video stream found")
    duration = float(data['format'].get('duration', 0))
    if duration == 0:
        raise Exception("Invalid or zero duration")
    fps_str = v_stream.get('avg_frame_rate', '30/1')
    try:
        fps = eval(fps_str)
    except:
        fps = 30.0
    total_frames = int(v_stream.get('nb_frames', 0))
    if total_frames == 0:
        total_frames = int(duration * fps)
    
    # Detect interlacing
    field_order = v_stream.get('field_order', 'progressive')
    interlaced = field_order not in ['progressive', 'unknown']
    
    return VideoInfo(
        width=int(v_stream['width']), height=int(v_stream['height']), duration=duration,
        fps=fps, dar=v_stream.get('display_aspect_ratio', '4:3'), has_audio=a_stream is not None,
        total_frames=total_frames, codec=v_stream.get('codec_name', 'unknown'),
        interlaced=interlaced
    )

def detect_video_standard(width: int, height: int, fps: float) -> VideoStandard:
    if width == 720 and height in [486, 480] and abs(fps - 29.97) < 0.1:
        return VideoStandard.NTSC
    if width == 720 and height == 576 and abs(fps - 25) < 0.1:
        return VideoStandard.PAL
    return VideoStandard.UNKNOWN

def calculate_scaling_params(width: int, height: int, dar: str) -> str:
    if height == 576 and width == 720:
        return "854:480" if dar == "16:9" else "640:480"
    elif height in [480, 486] and width == 720:
        return "854:480" if dar == "16:9" else "640:480"
    elif height == 480 and width == 352:
        # Half-D1 NTSC (352x480, SAR 20:11) — direct-to-disc DVD recorders.
        # Non-square pixels; DAR 4:3 displays at 640x480. Matches standard NTSC output.
        return "640:480"
    elif width == 1440 and height == 1080 and dar == "16:9":
        return "1280:720"
    elif width >= 1280 and height >= 720:
        if (width == 1920 and height == 1080) or (width == 1280 and height == 720):
            return "1280:720"
        elif width > 1920 or height > 1080:
            return "1280:720" if dar == "16:9" else "-2:720"
    return "trunc(iw/2)*2:trunc(ih/2)*2"

def get_bitrate_config(height: int) -> Dict[str, str]:
    return BITRATE_CONFIG['sd'] if height <= 576 else BITRATE_CONFIG['hd']

def calculate_output_fps(fps: float) -> float:
    is_pal = (abs(fps - 50) < 1 or abs(fps - 25) < 1)
    threshold = 25 if is_pal else 30
    return fps / 2 if fps > threshold else fps

def build_audio_filter_and_mapping(config: Config, info: VideoInfo) -> Tuple[List[str], List[str], str]:
    if not info.has_audio:
        return [], ["-an"], "No Audio"
    
    # Build ceiling filter string if requested.
    # Uses dynaudnorm with m=1 (max gain = 1.0, so it never boosts — only reduces)
    # targeting the specified peak level. This eliminates the slow level-riding
    # effect of default dynaudnorm settings: quiet passages are left completely
    # unchanged, and loud passages are reduced quickly (f=100ms frames, g=3
    # Gaussian window vs. the 500ms/31-frame defaults).
    clip_filter = ""
    clip_desc = ""
    if config.clip_ceiling is not None:
        clip_level = 10 ** (config.clip_ceiling / 20)
        clip_filter = f"dynaudnorm=p={clip_level:.4f}:m=1:f=100:g=3"
        clip_desc = f" [ceiling: {config.clip_ceiling:.0f} dBFS]"
    
    audio_mapping, audio_filter_args, audio_description = [], [], ""
    if config.audio_mode == 'stereo':
        audio_mapping = ["-map", config.audio_stream]
        if config.audio_pan_center:
            pan = "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"
            af = f"{pan},{clip_filter}" if clip_filter else pan
            audio_filter_args = ["-af", af]
            audio_description = f"Stereo {config.audio_stream} (center-panned){clip_desc}"
        elif clip_filter:
            audio_filter_args = ["-af", clip_filter]
            audio_description = f"Stereo {config.audio_stream}{clip_desc}"
        else:
            audio_description = f"Stereo {config.audio_stream}"
    elif config.audio_mode == 'mono-duplicate':
        audio_mapping = ["-map", config.audio_stream]
        pan = "pan=stereo|c0=c0|c1=c0"
        af = f"{pan},{clip_filter}" if clip_filter else pan
        audio_filter_args = ["-af", af]
        audio_description = f"Mono {config.audio_stream} (duplicated to L+R){clip_desc}"
    elif config.audio_mode == 'mono-merge':
        audio_mapping = []
        base_fc = "[0:a:0][0:a:1]amerge=inputs=2,pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"
        fc = f"{base_fc},{clip_filter}[aout]" if clip_filter else f"{base_fc}[aout]"
        audio_filter_args = ["-filter_complex", fc, "-map", "[aout]"]
        audio_description = f"Mono 0:a:0+0:a:1 (merged and center-panned){clip_desc}"
    return audio_mapping, audio_filter_args, audio_description

def validate_output(file_path: Path, timeout: int = VALIDATION_TIMEOUT) -> Tuple[bool, str]:
    cmd = ['ffmpeg', '-v', 'error', '-i', str(file_path), '-f', 'null', '-']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (result.returncode == 0 and len(result.stderr) == 0), result.stderr
    except subprocess.TimeoutExpired:
        return False, "Validation timeout"
    except Exception as e:
        return False, str(e)

def run_validation_command_with_spinner(cmd: List[str], description: str) -> Tuple[bool, str]:
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    result_container = {'result': None, 'done': False}
    def run_command():
        result = subprocess.run(cmd, capture_output=True, text=True)
        result_container['result'] = result
        result_container['done'] = True
    thread = threading.Thread(target=run_command)
    thread.daemon = True
    thread.start()
    idx = 0
    sys.stdout.write(f"    {description} ")
    sys.stdout.flush()
    while not result_container['done']:
        sys.stdout.write(f"\r    {description} {spinner[idx % len(spinner)]}")
        sys.stdout.flush()
        time.sleep(0.1)
        idx += 1
    sys.stdout.write(f"\r    {description} ✓\n")
    sys.stdout.flush()
    thread.join()
    result = result_container['result']
    return (result.returncode == 0), result.stdout
def validate_v210_lossless(source_path: Path, output_path: Path, process_log: Path) -> Tuple[bool, str]:
    logger = logging.getLogger('video_transcoder')
    try:
        temp_dir = output_path.parent / "temp_framemd5"
        temp_dir.mkdir(exist_ok=True)
        source_video_md5 = temp_dir / f"{source_path.stem}_source_video.framemd5"
        output_video_md5 = temp_dir / f"{output_path.stem}_output_video.framemd5"
        logger.info(f"Validating v210 lossless conversion for {source_path.name}...")
        with open(process_log, 'a') as log_f:
            log_f.write("\n" + "=" * 70 + "\n" + "FRAMEMD5 LOSSLESS VALIDATION\n" + "=" * 70 + "\n\n")
        
        logger.info("  → Generating framemd5 for source video stream...")
        cmd_source_video = ['ffmpeg', '-i', str(source_path), '-map', '0:v:0', '-f', 'framemd5', str(source_video_md5)]
        success, _ = run_validation_command_with_spinner(cmd_source_video, "Hashing source video")
        if not success:
            return False, "Failed to generate source video framemd5"
        with open(process_log, 'a') as log_f:
            log_f.write("Source video framemd5 generated successfully\n")
        
        logger.info("  → Generating framemd5 for output video stream...")
        cmd_output_video = ['ffmpeg', '-i', str(output_path), '-map', '0:v:0', '-f', 'framemd5', str(output_video_md5)]
        success, _ = run_validation_command_with_spinner(cmd_output_video, "Hashing output video")
        if not success:
            return False, "Failed to generate output video framemd5"
        with open(process_log, 'a') as log_f:
            log_f.write("Output video framemd5 generated successfully\n")
        
        logger.info("  → Comparing video framemd5 checksums...")
        with open(source_video_md5, 'r') as f:
            source_video_lines = f.readlines()
        with open(output_video_md5, 'r') as f:
            output_video_lines = f.readlines()
        source_video_hashes = [line.strip() for line in source_video_lines if not line.startswith('#')]
        output_video_hashes = [line.strip() for line in output_video_lines if not line.startswith('#')]
        if source_video_hashes != output_video_hashes:
            mismatch_msg = f"Video framemd5 mismatch: {len(source_video_hashes)} source frames vs {len(output_video_hashes)} output frames"
            with open(process_log, 'a') as log_f:
                log_f.write(f"ERROR: {mismatch_msg}\n")
                for i, (src, out) in enumerate(zip(source_video_hashes[:10], output_video_hashes[:10])):
                    if src != out:
                        log_f.write(f"  Frame {i} mismatch:\n    Source: {src}\n    Output: {out}\n")
            return False, mismatch_msg
        logger.info(f"  ✓ Video validation passed: {len(source_video_hashes)} frames match")
        with open(process_log, 'a') as log_f:
            log_f.write(f"Video validation PASSED: {len(source_video_hashes)} frames verified\n\n")
        
        logger.info("  → Generating hash for source audio stream(s)...")
        cmd_source_audio = ['ffmpeg', '-i', str(source_path), '-map', '0:a', '-f', 'streamhash', '-hash', 'md5', '-']
        success, source_audio_hash_value = run_validation_command_with_spinner(cmd_source_audio, "Hashing source audio")
        if not success:
            audio_error = "No audio stream or failed to generate source audio hash"
            logger.warning(f"  ⚠ {audio_error}")
            with open(process_log, 'a') as log_f:
                log_f.write(f"Audio validation skipped: {audio_error}\n")
        else:
            source_audio_hash_value = source_audio_hash_value.strip()
            with open(process_log, 'a') as log_f:
                log_f.write(f"Source audio hash generated: {source_audio_hash_value}\n")
            logger.info("  → Generating hash for output audio stream(s)...")
            cmd_output_audio = ['ffmpeg', '-i', str(output_path), '-map', '0:a', '-f', 'streamhash', '-hash', 'md5', '-']
            success, output_audio_hash_value = run_validation_command_with_spinner(cmd_output_audio, "Hashing output audio")
            if not success:
                return False, "Failed to generate output audio hash"
            output_audio_hash_value = output_audio_hash_value.strip()
            with open(process_log, 'a') as log_f:
                log_f.write(f"Output audio hash generated: {output_audio_hash_value}\n")
            logger.info("  → Comparing audio stream hashes...")
            if source_audio_hash_value != output_audio_hash_value:
                mismatch_msg = f"Audio streamhash mismatch:\nSource: {source_audio_hash_value}\nOutput: {output_audio_hash_value}"
                with open(process_log, 'a') as log_f:
                    log_f.write(f"ERROR: {mismatch_msg}\n")
                return False, mismatch_msg
            logger.info(f"  ✓ Audio validation passed: stream hashes match")
            with open(process_log, 'a') as log_f:
                log_f.write(f"Audio validation PASSED: {source_audio_hash_value}\n")
        
        try:
            source_video_md5.unlink()
            output_video_md5.unlink()
            temp_dir.rmdir()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp validation files: {e}")
        with open(process_log, 'a') as log_f:
            log_f.write("\n" + "=" * 70 + "\n" + "LOSSLESS VALIDATION: PASSED\n" + "=" * 70 + "\n\n")
        logger.info(f"  ✓ v210 lossless validation PASSED for {source_path.name}")
        return True, "Validation passed"
    except subprocess.TimeoutExpired:
        return False, "Validation timeout"
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False, f"Validation error: {e}"

def run_ffmpeg_with_progress(cmd: List[str], total_frames: int, description: str, log_file: Optional[Path] = None) -> Tuple[bool, str]:
    if total_frames <= 0:
        total_frames = 1
    pbar = tqdm(total=total_frames, desc=description, unit="fr", leave=False, dynamic_ncols=True, colour='cyan')
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
    frame_pattern = re.compile(r'frame=\s*(\d+)')
    full_output, last_frame = [], 0
    try:
        for line in process.stdout:
            full_output.append(line)
            match = frame_pattern.search(line)
            if match:
                current_frame = int(match.group(1))
                diff = current_frame - last_frame
                if diff > 0:
                    pbar.update(diff)
                    last_frame = current_frame
        process.wait()
    except Exception as e:
        process.kill()
        raise e
    finally:
        pbar.close()
    output_text = "".join(full_output)
    if log_file:
        try:
            with open(log_file, 'a') as f:
                f.write(output_text)
        except Exception as e:
            logging.getLogger('video_transcoder').warning(f"Failed to write log: {e}")
    return (process.returncode == 0), output_text

def generate_thumbnail(source_path: Path, output_path: Path, timestamp: float, scale_string: str, index: int, total: int, interlaced: bool, parity: int = -1, log_file: Optional[Path] = None) -> bool:
    # Only deinterlace thumbnails if source is interlaced
    if interlaced:
        vf_filter = f"bwdif=mode=0:parity={parity}:deint=all,scale={scale_string},format=rgb24"
    else:
        vf_filter = f"scale={scale_string},format=rgb24"
    
    # Use libopenjpeg encoder rather than the native jpeg2000 encoder.
    # The native encoder maps to sYCC color space at 9-bit regardless of input format.
    # libopenjpeg with rgb24 input produces standard 8-bit sRGB JP2 output.
    cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(source_path),
           "-vf", vf_filter,
           "-frames:v", "1", "-update", "1", "-c:v", "libopenjpeg", "-pix_fmt", "rgb24", str(output_path)]
    desc = f"Thumbnail {index}/{total}"
    success, output = run_ffmpeg_with_progress(cmd, 1, desc, log_file)
    return success

def cleanup_temp_files(prefix: Path):
    for ext in ["-0.log", "-0.log.mbtree"]:
        temp_file = Path(str(prefix) + ext)
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as e:
                logging.getLogger('video_transcoder').warning(f"Failed to delete {temp_file}: {e}")

def verify_derivatives_exist(output_paths: Dict[str, Path], thumbnail_prefix: str, num_thumbs: int = 4) -> bool:
    for output_path in output_paths.values():
        if output_path and not output_path.exists():
            return False
    if 'h264' in output_paths and output_paths['h264']:
        for i in range(1, num_thumbs + 1):
            thumb_path = output_paths['h264'].parent / f"{thumbnail_prefix}_thumb_{i}.jp2"
            if not thumb_path.exists():
                return False
    return True

def process_h264_output(source_path: Path, output_path: Path, info: VideoInfo, config: Config, process_log: Path, stats_log_prefix: Path, thumbnail_prefix: str) -> bool:
    try:
        out_fps = calculate_output_fps(info.fps)
        gop = math.ceil(out_fps * GOP_MULTIPLIER)
        scale_string = calculate_scaling_params(info.width, info.height, info.dar)
        bitrate_cfg = get_bitrate_config(info.height)
        
        # Build filter chain - only deinterlace if source is interlaced
        if info.interlaced:
            if config.force_scan == 'tff':
                parity = 0
            elif config.force_scan == 'bff':
                parity = 1
            else:
                parity = -1
            vf_chain = f"bwdif=mode=0:parity={parity}:deint=all,scale={scale_string},format=yuv420p"
        else:
            parity = -1
            vf_chain = f"scale={scale_string},format=yuv420p"
        
        audio_mapping, audio_filter_args, audio_description = build_audio_filter_and_mapping(config, info)
        with open(process_log, 'a') as log_f:
            log_f.write(f"Audio Configuration: {audio_description}\n")
            log_f.write(f"AAC Encoder: {config.aac_encoder}\n")
            log_f.write(f"Interlaced: {info.interlaced}\n")
        
        video_mapping = ["-map", "0:v:0"]
        video_codec_args = ["-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-fps_mode", "cfr",
                           "-r", f"{out_fps:.3f}", "-g", str(gop), "-sc_threshold", "0", "-vf", vf_chain,
                           "-b:v", bitrate_cfg['bitrate'], "-maxrate", bitrate_cfg['maxrate'], "-bufsize", bitrate_cfg['bufsize']]
        audio_codec_args = ["-c:a", config.aac_encoder, "-ac", "2", "-ar", "48000", "-b:a", "128k"] if info.has_audio else ["-an"]
        
        pass1_cmd = ["ffmpeg", "-y", "-i", str(source_path)] + video_mapping + video_codec_args + ["-pass", "1", "-passlogfile", str(stats_log_prefix), "-an", "-f", "mp4", os.devnull]
        success, _ = run_ffmpeg_with_progress(pass1_cmd, info.total_frames, f"H264 Pass 1: {source_path.name[:20]}", process_log)
        if not success:
            return False
        
        pass2_cmd = ["ffmpeg", "-y", "-i", str(source_path)] + video_mapping
        pass2_cmd += audio_mapping
        if audio_filter_args:
            pass2_cmd += audio_filter_args
        pass2_cmd += video_codec_args + ["-pass", "2", "-passlogfile", str(stats_log_prefix), "-tune", "film"] + audio_codec_args + ["-movflags", "faststart", str(output_path)]
        success, _ = run_ffmpeg_with_progress(pass2_cmd, info.total_frames, f"H264 Pass 2: {source_path.name[:20]}", process_log)
        if not success:
            return False
        
        if not config.skip_validation:
            is_valid, err_msg = validate_output(output_path)
            if not is_valid:
                logging.getLogger('video_transcoder').error(f"H264 validation failed: {err_msg}")
                return False
        
        if config.thumb_count is not None:
            num_thumbs = config.thumb_count
            positions = sorted([random.uniform(0.05, 0.95) for _ in range(num_thumbs)])
        else:
            num_thumbs = len(THUMBNAIL_POSITIONS)
            positions = THUMBNAIL_POSITIONS
        time_points = [info.duration * pos for pos in positions]
        for idx, timestamp in enumerate(time_points, 1):
            thumb_path = output_path.parent / f"{thumbnail_prefix}_thumb_{idx}.jp2"
            success = generate_thumbnail(source_path, thumb_path, timestamp, scale_string, idx, len(time_points), info.interlaced, parity, process_log)
            if not success:
                return False
        return True
    except Exception as e:
        logging.getLogger('video_transcoder').error(f"H264 processing error: {e}")
        return False

def process_v210_output(source_path: Path, output_path: Path, info: VideoInfo, video_standard: VideoStandard, process_log: Path) -> bool:
    logger = logging.getLogger('video_transcoder')
    try:
        setfield = "bff" if video_standard == VideoStandard.NTSC else "tff"
        setsar = "10/11" if video_standard == VideoStandard.NTSC else "12/11"
        cmd = ["ffmpeg", "-y", "-i", str(source_path), "-movflags", "write_colr", "-c:v", "v210",
               "-color_primaries", "smpte170m", "-color_trc", "bt709", "-colorspace", "smpte170m",
               "-color_range", "mpeg", "-metadata:s:v:0", "encoder=Uncompressed 10-bit 4:2:2",
               "-vf", f"setfield={setfield},setsar={setsar},setdar=4/3",
               "-c:a", "pcm_s24le", "-map", "0:v", "-map", "0:a", "-f", "mov", str(output_path)]
        success, _ = run_ffmpeg_with_progress(cmd, info.total_frames, f"v210: {source_path.name[:20]}", process_log)
        if not success:
            return False
        logger.info(f"Starting framemd5 lossless validation for {source_path.name}")
        is_valid, validation_msg = validate_v210_lossless(source_path, output_path, process_log)
        if not is_valid:
            logger.error(f"v210 lossless validation FAILED: {validation_msg}")
            if output_path.exists():
                output_path.unlink()
            return False
        return True
    except Exception as e:
        logger.error(f"v210 processing error: {e}")
        return False

def process_prores_output(source_path: Path, output_path: Path, info: VideoInfo, process_log: Path) -> bool:
    try:
        cmd = ["ffmpeg", "-y", "-i", str(source_path), "-codec:v", "prores_ks", "-profile:v", "3",
               "-vtag", "apch", "-metadata:s", "encoder=Apple ProRes 422 HQ", "-vendor", "apl0",
               "-codec:a", "copy", "-map", "0:v", "-map", "0:a", str(output_path)]
        success, _ = run_ffmpeg_with_progress(cmd, info.total_frames, f"ProRes: {source_path.name[:20]}", process_log)
        return success
    except Exception as e:
        logging.getLogger('video_transcoder').error(f"ProRes processing error: {e}")
        return False

ROLE_CODES = ('_pm', '_sh', '_sl')

def sanitize_filename(name: str) -> str:
    """Replace spaces with underscores in a filename stem."""
    return name.replace(' ', '_')

def strip_role_code(stem: str) -> str:
    """Strip a 3-character role code suffix (_pm, _sh, _sl) if present.
    If no recognized role code is found, return the stem unchanged."""
    for code in ROLE_CODES:
        if stem.endswith(code):
            return stem[:-3]
    return stem

def process_single_video(source_path: Path, config: Config, completed_set: Set[str]) -> ProcessingResult:
    logger = logging.getLogger('video_transcoder')
    base_name, root_name = source_path.name, sanitize_filename(source_path.stem)
    base_stem = strip_role_code(root_name)
    output_paths = {}
    if config.output_h264:
        output_paths['h264'] = config.output_dir / f"{base_stem}_sl.mp4"
    else:
        output_paths['h264'] = None
    if config.output_v210:
        output_paths['v210'] = config.output_dir / f"{root_name}.mov"
    else:
        output_paths['v210'] = None
    if config.output_prores:
        output_paths['prores'] = config.output_dir / f"{base_stem}_sh.mov"
    else:
        output_paths['prores'] = None
    
    thumbnail_prefix = base_stem if config.output_h264 else None
    num_thumbs = config.thumb_count if config.thumb_count is not None else len(THUMBNAIL_POSITIONS)
    derivatives_exist = verify_derivatives_exist(output_paths, thumbnail_prefix if thumbnail_prefix else "", num_thumbs)
    if base_name in completed_set and derivatives_exist:
        return ProcessingResult(base_name, ProcessStatus.SKIPPED, "N/A", "Already processed", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    process_log = config.log_dir / f"{root_name}_process.log"
    stats_log_prefix = config.log_dir / f"stats_{root_name}"
    audio_status = "Unknown"
    
    try:
        info = get_video_info(source_path)
        audio_status = "Stereo" if info.has_audio else "No Audio"
        
        # Apply FPS override if specified (before video standard detection)
        if config.force_fps is not None:
            logger.info(f"FPS override: {info.fps:.3f} -> {config.force_fps:.3f}")
            info.fps = config.force_fps
            info.total_frames = int(info.duration * info.fps)
        
        video_standard = detect_video_standard(info.width, info.height, info.fps)
        
        # Apply scan type override if specified
        if config.force_scan == 'progressive':
            info.interlaced = False
            logger.info(f"Scan override: forcing progressive (ignoring detected field order)")
        elif config.force_scan in ('tff', 'bff'):
            info.interlaced = True
            logger.info(f"Scan override: forcing {config.force_scan.upper()} field dominance")
        
        # Log interlacing status to terminal
        interlace_status = "interlaced" if info.interlaced else "progressive"
        logger.info(f"Source: {info.width}x{info.height} @ {info.fps:.2f}fps ({interlace_status})")
        
        with open(process_log, 'w') as log_f:
            log_f.write(SCRIPT_TITLE + "\n" + SCRIPT_NAME + "\n" + SCRIPT_SEPARATOR + "\n" + SCRIPT_SEPARATOR + "\n\n")
            log_f.write(f"Processing: {base_name}\nSource: {info.width}x{info.height} @ {info.fps:.2f}fps\n")
            log_f.write(f"Video Standard: {video_standard.value}\nOutput Formats: {', '.join([k for k, v in output_paths.items() if v])}\n\n")
        
        if config.output_h264:
            logger.info(f"Encoding H.264 for {base_name}")
            if not process_h264_output(source_path, output_paths['h264'], info, config, process_log, stats_log_prefix, thumbnail_prefix):
                raise Exception("H.264 encoding failed")
        if config.output_v210:
            logger.info(f"Encoding v210 for {base_name}")
            if video_standard == VideoStandard.UNKNOWN:
                raise Exception("Cannot create v210 output: video is not NTSC or PAL standard")
            if not process_v210_output(source_path, output_paths['v210'], info, video_standard, process_log):
                raise Exception("v210 encoding failed")
        if config.output_prores:
            logger.info(f"Encoding ProRes for {base_name}")
            if not process_prores_output(source_path, output_paths['prores'], info, process_log):
                raise Exception("ProRes encoding failed")
        
        if config.move_finished and not config.dry_run:
            shutil.move(str(source_path), str(config.finished_dir / base_name))
        formats_created = [k for k, v in output_paths.items() if v]
        return ProcessingResult(base_name, ProcessStatus.SUCCESS, audio_status, f"Completed successfully ({', '.join(formats_created)})", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.error(f"Error processing {base_name}: {e}")
        for output_path in output_paths.values():
            if output_path and output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
        if config.output_h264 and thumbnail_prefix:
            for i in range(1, num_thumbs + 1):
                thumb_path = config.output_dir / f"{thumbnail_prefix}_thumb_{i}.jp2"
                if thumb_path.exists():
                    try:
                        thumb_path.unlink()
                    except Exception:
                        pass
        return ProcessingResult(base_name, ProcessStatus.ERROR, audio_status, str(e), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    finally:
        if config.output_h264:
            cleanup_temp_files(stats_log_prefix)

def collect_video_files(source_dir: Path, finished_dir: Path) -> List[Path]:
    files = []
    for root, _, filenames in os.walk(source_dir):
        root_path = Path(root)
        if root_path.resolve() == finished_dir.resolve():
            continue
        for filename in filenames:
            if filename.lower().endswith(VIDEO_EXTENSIONS):
                files.append(root_path / filename)
    return sorted(files)

def print_file_list(files: List[Path], file_index_map: Dict[str, int] = None):
    print("\n" + "=" * 100 + f"\nFILES FOUND ({len(files)} total):\n" + "-" * 100)
    total_size, total_duration = 0, 0.0
    print(f"{'#':>4}  {'Filename':<50}  {'Size':>12}  {'Duration':>10}\n" + "-" * 100)
    for i, file_path in enumerate(files, 1):
        status = ""
        if file_index_map and file_path.name in file_index_map:
            status = " ✓"
        size, duration = get_file_info_for_display(file_path)
        total_size += size
        total_duration += duration
        display_name = file_path.name if len(file_path.name) <= 50 else file_path.name[:47] + "..."
        size_str = format_file_size(size) if size > 0 else "N/A"
        duration_str = format_duration(duration) if duration > 0 else "N/A"
        print(f"{i:4}. {display_name:<50}  {size_str:>12}  {duration_str:>10}{status}")
    print("-" * 100 + f"\n{'TOTAL:':<56}  {format_file_size(total_size):>12}  {format_duration(total_duration):>10}\n" + "=" * 100 + "\n")

def print_live_status(files: List[Path], session_completed: Set[str], stats: ProcessingStats):
    status_lines = ["\n" + "=" * 70, f"STATUS UPDATE ({len(session_completed)}/{len(files)} completed)", "-" * 70]
    for i, file_path in enumerate(files):
        status_icon = f"{Colors.GREEN}✓{Colors.RESET}" if file_path.name in session_completed else "⋯"
        status_lines.append(f"{i+1:4}. {status_icon} {file_path.name}")
    status_lines.append("-" * 70)
    success_str = f"{Colors.GREEN}Success: {stats.success}{Colors.RESET}"
    skipped_str = f"{Colors.YELLOW}Skipped: {stats.skipped}{Colors.RESET}" if stats.skipped > 0 else f"Skipped: {stats.skipped}"
    error_str = f"{Colors.RED}Errors: {stats.error}{Colors.RESET}" if stats.error > 0 else f"Errors: {stats.error}"
    status_lines.append(f"{success_str} | {skipped_str} | {error_str}")
    status_lines.append("=" * 70 + "\n")
    for line in status_lines:
        tqdm.write(line)

def print_summary(stats: ProcessingStats, start_time: datetime):
    logger = logging.getLogger('video_transcoder')
    duration = datetime.now() - start_time
    print("\n" + "=" * 70 + f"\n{Colors.BOLD}PROCESSING SUMMARY{Colors.RESET}\n" + "=" * 70)
    print(f"Total files:      {stats.total}\n{Colors.GREEN}Successful:       {stats.success}{Colors.RESET}")
    skipped_line = f"{Colors.YELLOW}Skipped:          {stats.skipped}{Colors.RESET}" if stats.skipped > 0 else f"Skipped:          {stats.skipped}"
    error_line = f"{Colors.RED}Errors:           {stats.error}{Colors.RESET}" if stats.error > 0 else f"Errors:           {stats.error}"
    print(f"{skipped_line}\n{error_line}")
    print(f"Processing time:  {duration}\n" + "=" * 70)
    if stats.failed_files:
        print(f"\n{Colors.RED}FAILED FILES:{Colors.RESET}")
        for failed in stats.failed_files:
            print(f"  {Colors.RED}✗{Colors.RESET} {failed}")
        print()
    logger.info("=" * 70 + "\nPROCESSING SUMMARY\n" + "=" * 70)
    logger.info(f"Total files:      {stats.total}\nSuccessful:       {stats.success}\nSkipped:          {stats.skipped}\nErrors:           {stats.error}\nProcessing time:  {duration}\n" + "=" * 70)
    if stats.failed_files:
        logger.error("FAILED FILES:")
        for failed in stats.failed_files:
            logger.error(f"  - {failed}")
    if stats.error == 0:
        logger.info("JOB COMPLETED SUCCESSFULLY - All files processed without errors")
    elif stats.success > 0:
        logger.warning(f"JOB COMPLETED WITH ERRORS - {stats.success} succeeded, {stats.error} failed")
    else:
        logger.error("JOB FAILED - No files were successfully processed")

def process_batch(config: Config) -> ProcessingStats:
    logger = logging.getLogger('video_transcoder')
    stats, start_time = ProcessingStats(), datetime.now()
    files = collect_video_files(config.source_dir, config.finished_dir)
    stats.total = len(files)
    if not files:
        logger.warning("No video files found to process")
        return stats
    print_file_list(files)
    completed_set = get_completed_files(config.csv_log)
    logger.info(f"Found {len(completed_set)} previously completed files")
    session_completed = set()
    mode = "CLEANUP" if config.cleanup_only else "PROCESSING"
    print(f"--- Starting {mode} MODE ---\n")
    
    if config.workers > 1 and not config.cleanup_only:
        with ProcessPoolExecutor(max_workers=config.workers) as executor:
            futures = {executor.submit(process_single_video, f, config, completed_set): f for f in files}
            with tqdm(total=len(files), unit="file", desc="Total Progress", position=0) as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    log_to_csv(config.csv_log, result, config.dry_run)
                    if result.status == ProcessStatus.SUCCESS:
                        stats.success += 1
                        session_completed.add(result.source_file)
                    elif result.status == ProcessStatus.SKIPPED:
                        stats.skipped += 1
                        session_completed.add(result.source_file)
                    else:
                        stats.error += 1
                        stats.failed_files.append(f"{result.source_file}: {result.message}")
                    pbar.set_postfix_str(f"✓ {len(session_completed)}/{len(files)} | ✗ {stats.error}")
                    pbar.update(1)
                    if len(session_completed) % 1 == 0 or result.status == ProcessStatus.ERROR:
                        print_live_status(files, session_completed, stats)
    else:
        with tqdm(total=len(files), unit="file", desc="Total Progress", position=0) as pbar:
            for file_path in files:
                result = process_single_video(file_path, config, completed_set)
                log_to_csv(config.csv_log, result, config.dry_run)
                if result.status == ProcessStatus.SUCCESS:
                    stats.success += 1
                    session_completed.add(result.source_file)
                elif result.status == ProcessStatus.SKIPPED:
                    stats.skipped += 1
                    session_completed.add(result.source_file)
                else:
                    stats.error += 1
                    stats.failed_files.append(f"{result.source_file}: {result.message}")
                pbar.set_postfix_str(f"✓ {len(session_completed)}/{len(files)} | ✗ {stats.error}")
                pbar.update(1)
                print_live_status(files, session_completed, stats)
    print_summary(stats, start_time)
    return stats

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Video Transcoding and Archival Pipeline', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--source-dir', type=str, default='/Users/mangelet/Desktop/In_Progress/1/source', help='Source directory containing video files')
    parser.add_argument('--output-dir', type=str, default='/Users/mangelet/Desktop/In_Progress/1/output', help='Output directory for processed files')
    parser.add_argument('--workers', type=int, default=1, help='Number of parallel workers (1 = sequential)')
    parser.add_argument('--cleanup-only', action='store_true', help='Only cleanup temporary files, do not process')
    parser.add_argument('--move-finished', action='store_true', default=True, help='Move source files to finished_sources after processing')
    parser.add_argument('--no-move-finished', dest='move_finished', action='store_false', help='Do not move source files after processing')
    parser.add_argument('--dry-run', action='store_true', help='Simulate processing without making changes')
    parser.add_argument('--skip-validation', action='store_true', help='Skip output file validation (faster but less safe)')
    parser.add_argument('--force-scan', type=str, choices=['progressive', 'tff', 'bff'], default=None,
                        help='Override scan type detection: progressive (skip deinterlace), tff (top field first), bff (bottom field first)')
    parser.add_argument('--force-fps', type=float, default=None,
                        help='Override detected frame rate (e.g. 29.97). Use when ffprobe misreads FPS from the container')
    parser.add_argument('--thumbs', type=int, default=None,
                        help='Number of thumbnails to generate (default: 4 at standard positions, override uses random positions)')
    parser.add_argument('-h264', action='store_true', help='Generate H.264 MP4 output with thumbnails (_sl.mp4)')
    parser.add_argument('-v210', action='store_true', help='Generate v210 uncompressed 10-bit 4:2:2 QuickTime output (.mov)')
    parser.add_argument('-prores', action='store_true', help='Generate ProRes 422 HQ QuickTime output (_sh.mov)')
    audio_group = parser.add_argument_group('Audio Configuration (H.264 only)')
    audio_group.add_argument('--audio-stream', type=str, default='0:a:0', help='Audio stream to use (default: 0:a:0). Examples: 0:a:0, 0:a:1')
    audio_group.add_argument('--audio-mode', type=str, choices=['stereo', 'mono-duplicate', 'mono-merge'], default='stereo', help='Audio processing mode: stereo (default), mono-duplicate, mono-merge')
    audio_group.add_argument('--audio-pan-center', action='store_true', help='Pan/mix stereo channels to center (music+dialogue to both L+R)')
    audio_group.add_argument('--clip-ceiling', type=float, default=None,
                             help='Apply a peak ceiling to audio output at the specified level in dBFS (e.g. -10). '
                                  'Uses dynaudnorm with max gain = 1.0 so it only reduces, never boosts — '
                                  'quiet passages are left unchanged. Fast response (100ms frames, 3-frame window). '
                                  'Default: disabled.')
    return parser.parse_args()

def main():
    args = parse_arguments()
    print(f"\n{Colors.BOLD}{Colors.CYAN}{SCRIPT_TITLE}{Colors.RESET}")
    print(f"{Colors.BOLD}{SCRIPT_NAME}{Colors.RESET}")
    print(SCRIPT_SEPARATOR)
    print(SCRIPT_SEPARATOR + "\n")
    try:
        config = Config(args)
        logger = setup_logging(config.log_dir, config.dry_run)
        if not check_dependencies():
            logger.error("Missing required dependencies. Exiting.")
            sys.exit(1)
        if not config.dry_run:
            check_disk_space(config.output_dir)
        logger.info("Starting video transcoding pipeline")
        logger.info(f"AAC encoder: {config.aac_encoder}")
        stats = process_batch(config)
        if stats.error > 0:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nProcessing interrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.getLogger('video_transcoder').critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

