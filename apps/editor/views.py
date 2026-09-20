from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from apps.editor.models import AssemblyJob

@login_required
def job_status_api(request, job_id):
    """
    Secure, authenticated job status query scoped strictly to the requesting user.
    Prevents IDOR and unauthorized access to private assembled videos.
    """
    job = get_object_or_404(AssemblyJob, id=job_id, user=request.user)
    return JsonResponse({
        "id": str(job.id),
        "status": job.status,
        "video_url": job.output_video.url if job.output_video else "",
        "render_log": job.render_log if request.user.is_staff else "",
    })
