from redis import Redis
from bluenaas.config.settings import settings

redis_client = Redis.from_url(url=settings.CELERY_BROKER_URL)
