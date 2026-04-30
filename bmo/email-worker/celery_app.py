import os
from celery import Celery

# Standard AMQP connection string format: amqp://user:password@host:port//
RABBITMQ_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")

# Initialize the Celery application
app = Celery(
    "genai_email_pipeline", 
    broker=RABBITMQ_URL
)

# Optional but recommended configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],  
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # If your GenAI pipeline takes a long time, prevent workers from prematurely killing tasks
    task_acks_late=True,
    worker_prefetch_multiplier=1
)
