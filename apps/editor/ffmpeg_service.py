import os
import shutil
import subprocess
import tempfile
import logging
from typing import List
from django.core.files import File
from apps.media.models import Media

logger = logging.getLogger(__name__)

class FFmpegService:
    """Video assembly, concatenation, and encoding pipeline."""

    @classmethod
    def get_ffmpeg_binary(cls) -> str:
        """
        Locates the FFmpeg executable across system PATH, local virtualenv,
        workspace bin directory, imageio-ffmpeg, and common Windows/Linux OS directories.
        """
        # 1. System PATH
        system_bin = shutil.which("ffmpeg")
        if system_bin and os.path.exists(system_bin):
            return system_bin

        from django.conf import settings
        base_dir = str(getattr(settings, 'BASE_DIR', ''))

        # 2. Workspace bin directory (e.g. project_root/bin/ffmpeg.exe)
        workspace_candidates = [
            os.path.join(base_dir, "bin", "ffmpeg.exe"),
            os.path.join(base_dir, "bin", "ffmpeg"),
            os.path.join(base_dir, ".venv", "Scripts", "ffmpeg.exe"),
            os.path.join(base_dir, "venv", "Scripts", "ffmpeg.exe"),
        ]
        for candidate in workspace_candidates:
            if os.path.isfile(candidate):
                return candidate

        # 3. Check imageio_ffmpeg Python module
        try:
            import imageio_ffmpeg
            img_exe = imageio_ffmpeg.get_ffmpeg_exe()
            if img_exe and os.path.isfile(img_exe):
                return img_exe
        except Exception:
            pass

        # 4. Standard Windows Installation Paths
        windows_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\ffmpeg\bin\ffmpeg.exe"),
            os.path.expandvars(r"%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        ]
        import glob
        for wp in windows_paths:
            if '*' in wp:
                for match in glob.glob(wp):
                    if os.path.isfile(match):
                        return match
            elif os.path.isfile(wp):
                return wp

        # Check WinGet packages dynamically
        winget_pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\*\bin\ffmpeg.exe")
        for match in glob.glob(winget_pattern):
            if os.path.isfile(match):
                return match

        # 5. Check if local workspace bin has manually provisioned binary
        bin_dir = os.path.join(base_dir, "bin")
        target_exe = os.path.join(bin_dir, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if os.path.isfile(target_exe):
            return target_exe

        logger.debug("FFmpeg executable not detected across standard system PATH or workspace bin.")
        return ""

    @classmethod
    def get_ffprobe_binary(cls) -> str:
        """Locates the FFprobe executable corresponding to FFmpeg."""
        ffmpeg_bin = cls.get_ffmpeg_binary()
        if ffmpeg_bin:
            probe_candidate = ffmpeg_bin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
            if os.path.isfile(probe_candidate):
                return probe_candidate

        probe_which = shutil.which("ffprobe")
        if probe_which and os.path.isfile(probe_which):
            return probe_which
        return ""

    @classmethod
    def is_ffmpeg_available(cls) -> bool:
        return bool(cls.get_ffmpeg_binary())

    @classmethod
    def probe_clip(cls, video_path: str) -> dict:
        """
        Extract video and audio technical specifications:
        width, height, duration, has_audio, and framerate.
        """
        default_meta = {
            'width': 1920,
            'height': 1080,
            'duration': 5.0,
            'has_audio': False,
            'fps': 30.0,
        }
        if not video_path or not os.path.exists(video_path):
            return default_meta

        ffprobe_bin = cls.get_ffprobe_binary()
        if ffprobe_bin:
            try:
                cmd = [
                    ffprobe_bin,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    video_path
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
                if result.returncode == 0 and result.stdout:
                    import json
                    data = json.loads(result.stdout)
                    streams = data.get('streams', [])
                    format_info = data.get('format', {})

                    v_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
                    a_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

                    if v_stream:
                        default_meta['width'] = int(v_stream.get('width', 1920))
                        default_meta['height'] = int(v_stream.get('height', 1080))
                        r_fps = v_stream.get('r_frame_rate', '30/1')
                        if '/' in r_fps:
                            num, den = r_fps.split('/')
                            default_meta['fps'] = float(num) / float(den) if float(den) > 0 else 30.0
                        else:
                            default_meta['fps'] = float(r_fps)

                    default_meta['has_audio'] = a_stream is not None
                    dur = format_info.get('duration') or (v_stream.get('duration') if v_stream else None)
                    if dur:
                        default_meta['duration'] = max(0.5, float(dur))
                    return default_meta
            except Exception as exc:
                logger.debug(f"FFprobe extraction exception: {exc}")

        # Fallback inspection via ffmpeg -i
        ffmpeg_bin = cls.get_ffmpeg_binary()
        if ffmpeg_bin:
            try:
                res = subprocess.run([ffmpeg_bin, "-i", video_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                text = res.stderr
                import re
                dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", text)
                if dur_match:
                    h, m, s = dur_match.groups()
                    default_meta['duration'] = float(h)*3600 + float(m)*60 + float(s)
                res_match = re.search(r",\s*(\d{3,4})x(\d{3,4})", text)
                if res_match:
                    default_meta['width'] = int(res_match.group(1))
                    default_meta['height'] = int(res_match.group(2))
                default_meta['has_audio'] = "Audio:" in text
            except Exception:
                pass

        return default_meta

    @classmethod
    def normalize_clip(
        cls,
        input_path: str,
        output_path: str,
        target_aspect_ratio: str = "16:9",
        conforming_mode: str = "smart_blur"
    ) -> bool:
        """
        Standardizes any video clip to a uniform canvas, constant 30fps,
        yuv420p color format, and 48kHz stereo AAC with loudness normalization.
        If clip lacks audio, injects synchronized silent stereo audio.
        """
        ffmpeg_bin = cls.get_ffmpeg_binary()
        if not ffmpeg_bin or not os.path.exists(input_path):
            return False

        dimensions = {
            '16:9': (1920, 1080),
            '9:16': (1080, 1920),
            '1:1': (1080, 1080),
            '4:3': (1440, 1080),
            '21:9': (2560, 1080),
        }
        tw, th = dimensions.get(target_aspect_ratio, (1920, 1080))
        meta = cls.probe_clip(input_path)
        has_audio = meta['has_audio']

        # Construct video conforming filter
        if conforming_mode == "smart_blur":
            # Silky blurred pillarbox/letterbox for mismatched ratios
            v_filter = (
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=15:2[bg];"
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,setsar=1[vout]"
            )
        else:
            # Clean black matte letterboxing
            v_filter = (
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,setsar=1[vout]"
            )

        if has_audio:
            cmd = [
                ffmpeg_bin, "-y",
                "-i", input_path,
                "-filter_complex", f"{v_filter};[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,dynaudnorm=f=150:g=15[aout]",
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart",
                output_path
            ]
        else:
            cmd = [
                ffmpeg_bin, "-y",
                "-i", input_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-filter_complex", v_filter,
                "-map", "[vout]",
                "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-shortest",
                "-movflags", "+faststart",
                output_path
            ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            logger.warning(f"Clip normalization error: {res.stderr[:200]}")
            return False
        return True

    @classmethod
    def assemble_scenes(
        cls,
        scene_media_list: List[Media],
        output_aspect_ratio: str = "16:9",
        conforming_mode: str = "smart_blur",
        background_music_path: str = None,
        bgm_volume: float = 0.25
    ) -> str:
        """
        Intelligently compiles multiple scene videos into a unified film.
        Normalizes all clips to standard 1080p canvas, aligns 30fps & 48kHz audio,
        prevents desync, and optionally mixes background soundtrack.
        """
        if not scene_media_list:
            raise ValueError("No scene media provided for assembly.")

        ffmpeg_bin = cls.get_ffmpeg_binary()

        # Fallback if FFmpeg binary is absent
        if not ffmpeg_bin:
            logger.warning("FFmpeg binary not found. Using fallback copy mechanism.")
            first_media = scene_media_list[0]
            if first_media.file and os.path.exists(first_media.file.path):
                temp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                shutil.copyfile(first_media.file.path, temp_out.name)
                return temp_out.name
            else:
                temp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                temp_out.write(b"MOCK_RENDER_MP4_CONTENT")
                temp_out.close()
                return temp_out.name

        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_paths = []
            for idx, media in enumerate(scene_media_list):
                if media.file and os.path.exists(media.file.path):
                    norm_out = os.path.join(temp_dir, f"norm_scene_{idx:03d}.mp4")
                    success = cls.normalize_clip(
                        input_path=media.file.path,
                        output_path=norm_out,
                        target_aspect_ratio=output_aspect_ratio,
                        conforming_mode=conforming_mode
                    )
                    if success and os.path.exists(norm_out):
                        normalized_paths.append(norm_out)
                    else:
                        # Fallback copy if direct normalization encounters quirk
                        normalized_paths.append(media.file.path)

            if not normalized_paths:
                raise RuntimeError("No valid scene files could be pre-processed for assembly.")

            concat_txt_path = os.path.join(temp_dir, "scenes.txt")
            raw_assembled_path = os.path.join(temp_dir, "raw_assembled.mp4")

            with open(concat_txt_path, "w", encoding="utf-8") as f:
                for path in normalized_paths:
                    clean_path = path.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{clean_path}'\n")

            # Stitch all standardized scenes
            concat_cmd = [
                ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_txt_path,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                raw_assembled_path
            ]
            logger.info(f"Running FFmpeg scene concatenation: {' '.join(concat_cmd)}")
            res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                logger.error(f"FFmpeg assembly error: {res.stderr}")
                raise RuntimeError(f"FFmpeg assembly failed: {res.stderr[:300]}")

            final_stage_path = raw_assembled_path

            # Optional: mix background soundtrack with ducking
            if background_music_path and os.path.exists(background_music_path):
                music_mixed_path = os.path.join(temp_dir, "film_with_score.mp4")
                mix_cmd = [
                    ffmpeg_bin, "-y",
                    "-i", raw_assembled_path,
                    "-stream_loop", "-1", "-i", background_music_path,
                    "-filter_complex",
                    f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    "-movflags", "+faststart",
                    music_mixed_path
                ]
                mix_res = subprocess.run(mix_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if mix_res.returncode == 0 and os.path.exists(music_mixed_path):
                    final_stage_path = music_mixed_path

            # Copy to persistent output
            persistent_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            shutil.copyfile(final_stage_path, persistent_out.name)
            return persistent_out.name

    @classmethod
    def merge_video_and_audio(cls, video_path: str, audio_path: str, output_path: str = None) -> str:
        """
        Mux audio track directly into MP4 video container with 48kHz AAC encoding.
        Ensures downloaded/exported videos natively have sound without separate tracks.
        """
        if not video_path or not os.path.exists(video_path):
            raise ValueError(f"Video file not found at {video_path}")
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found at {audio_path}")

        ffmpeg_bin = cls.get_ffmpeg_binary()

        if not ffmpeg_bin:
            logger.warning("FFmpeg binary not found on PATH or local paths. Skipping audio merge and returning original video.")
            return video_path

        out_file = output_path
        if not out_file:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            out_file = temp_file.name
            temp_file.close()

        # 1. Try fast stream copy for video + 48kHz AAC for audio
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-movflags", "+faststart",
            out_file
        ]

        logger.info(f"Running FFmpeg audio-video merge: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # 2. Fallback: If copy mode fails due to timescale or format mismatch, re-encode video fast
        if result.returncode != 0:
            logger.warning(f"Fast stream copy failed ({result.stderr[:150]}), retrying with fast re-encode...")
            fallback_cmd = [
                ffmpeg_bin,
                "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                "-movflags", "+faststart",
                out_file
            ]
            fb_res = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if fb_res.returncode != 0:
                logger.error(f"FFmpeg audio-video merge re-encode failed: {fb_res.stderr}")
                return video_path

        return out_file
