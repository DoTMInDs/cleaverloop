from django.urls import path
from django.http import JsonResponse
from apps.editor.models import AssemblyJob

def job_status_api(request, job_id):
    job = AssemblyJob.objects.filter(id=job_id).first()
    if not job:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse({
        "id": str(job.id),
        "status": job.status,
        "video_url": job.output_video.url if job.output_video else "",
        "render_log": job.render_log
    })

app_name = 'editor'

urlpatterns = [
    path('jobs/<uuid:job_id>/status/', job_status_api, name='job_status'),
]
