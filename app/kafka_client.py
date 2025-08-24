import asyncio
import json
from aiokafka import AIOKafkaProducer
from .config import settings

_producer: AIOKafkaProducer | None = None

async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
        await _producer.start()
    return _producer

async def send_alert_event(event_type: str, payload: dict):
    producer = await get_producer()
    message = json.dumps({"event": event_type, "data": payload}).encode("utf-8")
    await producer.send_and_wait(settings.KAFKA_TOPIC_ALERTS, message)

async def close_producer():
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None