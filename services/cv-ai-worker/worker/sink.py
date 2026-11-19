import json


class JsonlSink:
    def __init__(self, path):
        self.f = open(path, "w")

    def send(self, event):
        self.f.write(json.dumps(event) + "\n")

    def close(self):
        self.f.close()


class KafkaSink:
    def __init__(self, brokers, topic):
        from confluent_kafka import Producer
        self.p = Producer({"bootstrap.servers": brokers, "linger.ms": 5})
        self.topic = topic

    def send(self, event):
        self.p.produce(self.topic, key=event["run_id"], value=json.dumps(event))
        self.p.poll(0)

    def close(self):
        self.p.flush(5)
