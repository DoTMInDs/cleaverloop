import os
import logging
from celery import shared_task
from django.utils import timezone
from django.core.files import File

from apps.editor.models import AssemblyJob
from apps.editor.ffmpeg_service import FFmpegService
from apps.media.models import Media

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def assemble_project_video_task(self, job_id: str):
    """
    Celery task to concatenate project scenes into a unified video.
    """
    try:
        job = AssemblyJob.objects.select_related('project', 'user').get(id=job_id)
    except AssemblyJob.DoesNotExist:
        logger.error(f"AssemblyJob {job_id} not found.")
        return

    job.status = 'rendering'
    job.save(update_fields=['status'])

    project = job.project
    scenes = project.scenes.filter(generated_media__isnull=False).order_by('order')

    if not scenes.exists():
        job.status = 'failed'
        job.render_log = "Cannot assemble video: No completed scene videos found in project."
        job.save(update_fields=['status', 'render_log'])
        return

    scene_media = [s.generated_media for s in scenes]

    try:
        output_file_path = FFmpegService.assemble_scenes(
            scene_media_list=scene_media,
            output_aspect_ratio=job.target_aspect_ratio
        )

        with open(output_file_path, 'rb') as f:
            output_media = Media.objects.create(
                owner=job.user,
                project=project,
                media_type='video',
                file_size=os.path.getsize(output_file_path)
            )
            output_media.file.save(f"assembled_{project.id}.mp4", File(f), save=True)

        job.output_video = output_media
        job.status = 'completed'
        job.completed_at = timezone.now()
        job.save(update_fields=['output_video', 'status', 'completed_at'])

        # Set as project final render
        project.final_render = output_media
        project.status = 'completed'
        project.save(update_fields=['final_render', 'status'])

        # Clean up temp file
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        logger.info(f"Assembly completed successfully for job {job_id}")

    except Exception as exc:
        logger.exception(f"Video assembly failed for job {job_id}: {exc}")
        job.status = 'failed'
        job.render_log = str(exc)
        job.save(update_fields=['status', 'render_log'])
