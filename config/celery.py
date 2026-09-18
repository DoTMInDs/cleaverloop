import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

app = Celery('cleaverloop')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Routing Queues
app.conf.task_routes = {
    'apps.generations.tasks.generate_video_task': {'queue': 'video'},
    'apps.generations.tasks.generate_image_task': {'queue': 'image'},
    'apps.editor.tasks.assemble_project_video_task': {'queue': 'render'},
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Celery Debug Request: {self.request!r}')
