import paho.mqtt.client as mqtt
import json

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f" Topic: {msg.topic:<35} | Src: {payload['source']:<10} | Tag: {payload['tag']:<15} | Val: {payload['value']:<8} | Quality: {payload['quality']}")
    except Exception as e:
        print(f"Error: {e}")

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect("127.0.0.1", 1883, 60)
client.subscribe("plant/#")

print("MQTT Broker listening... data flowing waiting...\n")
client.loop_forever()