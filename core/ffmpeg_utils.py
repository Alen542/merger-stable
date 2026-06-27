import asyncio
import os
import json
import shutil
from config import DEBUG_MODE

# System FFmpeg ebong FFprobe use korbe (Jekono VPS-er jonno universal)
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Branding tag written into output file metadata (container + streams)
METADATA_TAG = "SBRips"

async def _run_cmd(args: list):
    """Run command asynchronously WITHOUT a shell (prevents command injection
    from filenames) and handle errors."""
    if DEBUG_MODE:
        print(f"\n[DEBUG] Running Command: {args}")

    proc = await asyncio.create_subprocess_exec(
        *[str(a) for a in args],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    out = stdout.decode(errors='ignore').strip()
    err = stderr.decode(errors='ignore').strip()

    if DEBUG_MODE:
        if out: print(f"[DEBUG STDOUT]\n{out}")
        if err: print(f"[DEBUG STDERR]\n{err}")

    if proc.returncode != 0:
        # Keep only the tail of stderr so error messages stay readable
        raise Exception(f"FFmpeg error (code {proc.returncode}): {err[-1000:]}")
    return out

async def get_video_properties(file_path: str):
    """Extract duration, width, height, fps, codecs, pix_fmt, and audio channels using ffprobe."""
    # Check if file exists
    if not os.path.exists(file_path):
        raise Exception(f"File not found: {file_path}")

    # Check if ffprobe exists
    if not shutil.which(FFPROBE):
        raise Exception("FFprobe not found on your system! Please install FFmpeg/FFprobe (sudo apt install ffmpeg).")

    cmd = [FFPROBE, "-print_format", "json", "-show_streams", "-show_format", file_path]

    stdout = await _run_cmd(cmd)

    if not stdout:
        raise Exception("FFprobe returned empty output. The file might be corrupted or inaccessible.")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse video info: {str(e)}")

    v_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    a_streams = [s for s in data['streams'] if s['codec_type'] == 'audio']
    a_stream = a_streams[0] if a_streams else None
    audio_count = len(a_streams)

    if not v_stream:
        raise Exception("No video stream found in the file.")

    # Basic properties (fall back to stream duration if container duration is missing)
    raw_duration = data.get('format', {}).get('duration') or v_stream.get('duration') or 0
    try:
        duration = int(float(raw_duration))
    except (TypeError, ValueError):
        duration = 0
    width = int(v_stream.get('width', 1280))
    height = int(v_stream.get('height', 720))

    # FPS calculation
    fps_eval = v_stream.get('avg_frame_rate', '30/1')
    if '/' in fps_eval:
        try:
            num, den = map(int, fps_eval.split('/'))
            fps = num / den if den != 0 else 30.0
        except (ValueError, ZeroDivisionError):
            fps = 30.0
    else:
        try:
            fps = float(fps_eval)
        except (TypeError, ValueError):
            fps = 30.0

    # Advanced properties for perfect matching
    v_codec = v_stream.get('codec_name', 'h264')
    pix_fmt = v_stream.get('pix_fmt', 'yuv420p')
    v_profile = v_stream.get('profile')
    v_level = v_stream.get('level')
    # Codec tag (e.g. hvc1 vs hev1 for HEVC) — must match for glitch-free concat
    v_tag = (v_stream.get('codec_tag_string') or '').strip().lower()
    if v_tag in ('', '[0][0][0][0]'):
        v_tag = None
    a_codec = a_stream.get('codec_name', 'aac') if a_stream else 'aac'
    ar = int(a_stream.get('sample_rate', 48000)) if a_stream else 48000
    ac = int(a_stream.get('channels', 2)) if a_stream else 2

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "v_codec": v_codec,
        "pix_fmt": pix_fmt,
        "v_profile": v_profile,
        "v_level": v_level,
        "v_tag": v_tag,
        "a_codec": a_codec,
        "ar": ar,
        "ac": ac,
        "audio_count": audio_count
    }

_available_encoders: set | None = None

async def _check_encoder(encoder: str):
    """Verify the required encoder exists in this ffmpeg build.
    Gives a clear error instead of a cryptic 'Unknown encoder' merge failure."""
    global _available_encoders
    if _available_encoders is None:
        try:
            out = await _run_cmd([FFMPEG, "-hide_banner", "-encoders"])
            _available_encoders = {
                line.split()[1]
                for line in out.splitlines()
                if line.strip() and len(line.split()) >= 2 and line.lstrip()[0] in "VAS."
            }
        except Exception:
            # Could not list encoders — skip the pre-check and let ffmpeg decide
            _available_encoders = set()
            return
    if _available_encoders and encoder not in _available_encoders:
        raise Exception(
            f"This server's FFmpeg build does not include the `{encoder}` encoder, "
            f"which is required to match your main video's codec. "
            f"Install a full FFmpeg build (e.g. from johnvansickle.com static builds)."
        )

def _metadata_args(title: str | None = None) -> list:
    """Container + per-stream metadata tags (SBRips branding) for the output file."""
    t = title or METADATA_TAG
    return [
        "-map_metadata", "-1",  # Clear all existing global metadata from original files
        "-metadata", f"title={t}",
        "-metadata", f"encoded_by={METADATA_TAG}",
        "-metadata", f"copyright={METADATA_TAG}",
        "-metadata", f"comment={METADATA_TAG}",
        "-metadata", f"publisher={METADATA_TAG}",
        "-metadata", f"artist={METADATA_TAG}",
        "-metadata", f"author={METADATA_TAG}",
        "-metadata", f"description={METADATA_TAG}",
        # Apply to ALL streams (video, audio, subtitle) dynamically without hardcoding stream index
        "-metadata:s", f"title={METADATA_TAG}",
        "-metadata:s", f"handler_name={METADATA_TAG}",
    ]

async def merge_videos(intro_path: str, main_path: str, output_path: str, work_dir: str, title: str | None = None) -> bool:
    """Match Intro to Main Video properties perfectly, then merge.

    Output always gets:
    - SBRips metadata on container, video stream and audio stream
    - moov atom moved to the front (-movflags +faststart) for instant detail/preview loading
    """

    props = await get_video_properties(main_path)
    w, h = props['width'], props['height']
    fps = props['fps']
    v_codec = props['v_codec']
    pix_fmt = props['pix_fmt']
    v_profile = props.get('v_profile')
    v_level = props.get('v_level')
    v_tag = props.get('v_tag')
    a_codec = props['a_codec']
    ar = props['ar']
    ac = props['ac']
    audio_count = props.get('audio_count', 1)

    w = w if w % 2 == 0 else w + 1
    h = h if h % 2 == 0 else h + 1

    matched_intro = os.path.join(work_dir, "matched_intro.mp4")
    vf_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"

    # Encoders
    v_encoder = "libx264"
    if v_codec == "hevc":
        v_encoder = "libx265"
    elif v_codec == "vp9":
        v_encoder = "libvpx-vp9"

    a_encoder = "aac"
    if a_codec == "opus":
        a_encoder = "libopus"
    elif a_codec == "mp3":
        a_encoder = "libmp3lame"

    # Fail early with a clear message if this ffmpeg build lacks the needed encoder
    await _check_encoder(v_encoder)

    # Re-encode Intro to match the main video as closely as possible
    cmd_match = [
        FFMPEG, "-i", intro_path,
        "-vf", vf_scale,
        "-pix_fmt", pix_fmt,
        "-r", f"{fps}",
        "-c:v", v_encoder, "-preset", "superfast",
    ]
    # Match profile/level so that stream-copy concat stays glitch-free
    if v_encoder == "libx264" and v_profile:
        profile_map = {"baseline": "baseline", "main": "main", "high": "high"}
        prof = profile_map.get(str(v_profile).lower())
        if prof:
            cmd_match += ["-profile:v", prof]
        if v_level:
            try:
                lvl = float(v_level) / 10.0
                cmd_match += ["-level:v", f"{lvl:g}"]
            except (TypeError, ValueError):
                pass
    elif v_encoder == "libx265":
        # HEVC profile matching (Main / Main 10 / Main Still Picture)
        hevc_profile_map = {
            "main": "main",
            "main 10": "main10",
            "main still picture": "mainstillpicture",
            "rext": "main",  # range extensions -> closest safe choice
        }
        x265_params = []
        if v_profile:
            prof = hevc_profile_map.get(str(v_profile).lower())
            if prof:
                cmd_match += ["-profile:v", prof]
        if v_level:
            try:
                # ffprobe reports HEVC level as level_idc * 30 (e.g. 123 = 4.1)
                lvl = float(v_level) / 30.0
                x265_params.append(f"level-idc={lvl:g}")
            except (TypeError, ValueError):
                pass
        if x265_params:
            cmd_match += ["-x265-params", ":".join(x265_params)]
        # Match the main video's codec tag (hvc1 vs hev1) — mismatched tags
        # cause black screens on Apple devices / some players after concat
        if v_tag in ("hvc1", "hev1"):
            cmd_match += ["-tag:v", v_tag]
            
    # Map video
    cmd_match += ["-map", "0:v:0"]
    # Duplicate intro audio to match main video audio count
    if audio_count > 0:
        for _ in range(audio_count):
            cmd_match += ["-map", "0:a:0"]

    cmd_match += [
        "-c:a", a_encoder, "-ar", f"{ar}", "-ac", f"{ac}",
        matched_intro, "-y"
    ]
    await _run_cmd(cmd_match)

    meta = _metadata_args(title)
    # Preserve the HEVC codec tag on the merged output as well
    tag_args = ["-tag:v", v_tag] if (v_codec == "hevc" and v_tag in ("hvc1", "hev1")) else []

    if v_codec in ("h264", "hevc"):
        # For H264/HEVC, demuxer directly on MP4 can cause playback freezing due to SPS/PPS headers mismatch.
        # So we use the more reliable MPEG-TS protocol method (v1.0 logic) directly.
        intro_ts = os.path.join(work_dir, "intro.ts")
        main_ts = os.path.join(work_dir, "main.ts")
        bsf = "h264_mp4toannexb" if v_codec == "h264" else "hevc_mp4toannexb"

        # Explicitly map video and audio to avoid PID mismatches from subtitles/data tracks
        await _run_cmd([FFMPEG, "-i", matched_intro, "-map", "0:v:0", "-map", "0:a", "-c", "copy", "-bsf:v", bsf, "-f", "mpegts", intro_ts, "-y"])
        await _run_cmd([FFMPEG, "-i", main_path, "-map", "0:v:0", "-map", "0:a", "-c", "copy", "-bsf:v", bsf, "-f", "mpegts", main_ts, "-y"])

        concat_str = f"concat:{intro_ts}|{main_ts}"
        cmd_merge_fallback = [
            FFMPEG, "-i", concat_str,
            "-map", "0",
            "-c", "copy",
            *meta,
            "-movflags", "+faststart",
            output_path, "-y"
        ]
        await _run_cmd(cmd_merge_fallback)
    else:
        # Concat Logic using Demuxer for other formats
        concat_list = os.path.join(work_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            f.write(f"file '{os.path.abspath(matched_intro)}'\n")
            f.write(f"file '{os.path.abspath(main_path)}'\n")

        cmd_merge = [
            FFMPEG, "-f", "concat", "-safe", "0", "-i", concat_list,
            "-map", "0",
            "-c", "copy",
            *tag_args,
            *meta,
            "-movflags", "+faststart",
            output_path, "-y"
        ]
        await _run_cmd(cmd_merge)

    return True
