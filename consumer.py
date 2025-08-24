import asyncio
from aiokafka import AIOKafkaConsumer
import json
import os

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_ALERTS = os.getenv("KAFKA_TOPIC_ALERTS", "alerts")

async def consume():
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC_ALERTS,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agent-service",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    try:
        print(f"Consuming from {KAFKA_TOPIC_ALERTS} at {KAFKA_BOOTSTRAP_SERVERS} ...")
        async for msg in consumer:
            payload = json.loads(msg.value.decode("utf-8"))
            print("Event:", payload)
    finally:
        await consumer.stop()

if __name__ == "__main__":
    asyncio.run(consume())