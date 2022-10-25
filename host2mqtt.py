import json
import platform
from os import environ
from socket import gethostname
from time import sleep

import paho.mqtt.client
import psutil

DEBUG = environ.get('DEBUG', '1') == '1'
HOMEASSISTANT_ENABLED = environ.get('HOMEASSISTANT_ENABLED', '1') == '1'
HOMEASSISTANT_PREFIX = environ.get('HOMEASSISTANT_PREFIX', 'homeassistant')
HOST2MQTT_HOSTNAME = environ.get('HOST2MQTT_HOSTNAME', gethostname()).replace(" ", "")
MQTT_CLIENT_ID = environ.get('MQTT_CLIENT_ID', 'host2mqtt')
MQTT_USER = environ.get('MQTT_USER', '')
MQTT_PASSWD = environ.get('MQTT_PASSWD', '')
MQTT_HOST = environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(environ.get('MQTT_PORT', '1883'))
MQTT_TIMEOUT = int(environ.get('MQTT_TIMEOUT', '30'))
MQTT_TOPIC_PREFIX = environ.get('MQTT_TOPIC_PREFIX', 'host2mqtt')
MQTT_QOS = int(environ.get('MQTT_QOS', 1))
STATS_DELAY_SECONDS = environ.get('STATS_DELAY', 5)

topics = {
    "cpu_usage": f"{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/cpu_usage",
    "cpu_usage_attrs": f"{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/cpu_usage_attrs",
    "memory_usage": f"{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/memory_usage",
    "memory_usage_attrs": f"{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/memory_usage_attrs",
    "disk_usage": f"{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/disk_{{}}/usage",
    "disk_usage_attrs": f"{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/disk_{{}}/disk_attrs",
    "home_assistant": {
        "cpu_usage": f"{HOMEASSISTANT_PREFIX}/sensor/host2mqtt-{HOST2MQTT_HOSTNAME}/cpu_usage/config",
        "memory_usage": f"{HOMEASSISTANT_PREFIX}/sensor/host2mqtt-{HOST2MQTT_HOSTNAME}/memory_usage/config",
        "disk_usage": f"{HOMEASSISTANT_PREFIX}/sensor/host2mqtt-{HOST2MQTT_HOSTNAME}/disk_{{}}/config"
    }
}

base_config = {
    'availability_topic': f'{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/status',
    'qos': MQTT_QOS,
    'device': {
        "name": HOST2MQTT_HOSTNAME,
        "manufacturer": f"{platform.system()}",
        "model": f"{platform.machine()}",
        "identifiers": f"{gethostname()}",
        "sw_version": f"{platform.system()} {platform.release()} ({platform.version()})",
        "via_device": "host2mqtt",
    },
}

mqtt = paho.mqtt.client.Client()
connected_to_mqtt = False

'''
MQTT CALLBACKS
'''
def on_mqtt_connect(client, userdata, flags, rc):
    global connected_to_mqtt

    if rc == 0:
        connected_to_mqtt = True

        print(f'Connected to MQTT server at {MQTT_HOST}:{MQTT_PORT}')

        if HOMEASSISTANT_ENABLED:
            ha_register_host()
        else:
            print("HA not enabled")
    else:
        connected_to_mqtt = False
        print(f'Failed to connect to MQTT server at {MQTT_HOST}:{MQTT_PORT} reason: {rc}')


def on_mqtt_message(client, userdata, msg):
    print("Message received->" + msg.topic + " > " + str(msg.payload.decode()))
    command = msg.payload.decode()


def on_mqtt_disconnect(client, userdata, rc):
    global connected_to_mqtt

    print(f'Disconnected from MQTT server (reason:{rc})')
    connected_to_mqtt = False


'''
MQTT MANAGEMENT
'''
def setup_mqtt():
    global mqtt

    mqtt = paho.mqtt.client.Client()
    mqtt.username_pw_set(username=MQTT_USER, password=MQTT_PASSWD)
    mqtt.will_set(f'{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/status', 'offline', qos=MQTT_QOS, retain=True)
    mqtt.on_connect = on_mqtt_connect
    mqtt.on_disconnect = on_mqtt_disconnect
    mqtt.on_message = on_mqtt_message


def mqtt_connect(exit_on_fail=False):
    global mqtt, connected_to_mqtt

    try:
        print(f'Attempting to connect to MQTT server at {MQTT_HOST}:{MQTT_PORT}')
        mqtt.connect(MQTT_HOST, MQTT_PORT, MQTT_TIMEOUT)
        connected_to_mqtt = True

        # mqtt.subscribe(topics['commands'].format("+"))

        mqtt.loop_start()
        mqtt_send(f'{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/status', 'online', retain=True)
        return True
    except ConnectionRefusedError as e:
        print(f'Failed to connect to MQTT server at {MQTT_HOST}:{MQTT_PORT}')
        print(e)
        connected_to_mqtt = False

        if exit_on_fail:
            exit(0)

        return False


def mqtt_disconnect():
    global connected_to_mqtt

    print(f'Disconnecting from MQTT voluntarily')
    connected_to_mqtt = False
    mqtt.publish(f'{MQTT_TOPIC_PREFIX}/{HOST2MQTT_HOSTNAME}/status', 'offline', qos=MQTT_QOS, retain=True)
    mqtt.disconnect()
    sleep(1)
    mqtt.loop_stop()


def mqtt_send(topic, payload, retain=False):
    global connected_to_mqtt

    if connected_to_mqtt:
        try:
            if DEBUG:
                print(f'Sending to MQTT: {topic}: {payload}')
            mqtt.publish(topic, payload=payload, qos=MQTT_QOS, retain=retain)
        except Exception as e:
            print(f'MQTT Publish Failed: {e}')


def ha_register_host():
    global base_config

    cpu_usage_config = base_config | {
        "state_topic": topics['cpu_usage'],
        "json_attributes_topic": topics['cpu_usage_attrs'],
        "name": f"{HOST2MQTT_HOSTNAME} CPU Usage",
        "unique_id": f"{HOST2MQTT_HOSTNAME}.cpu_usage",
        "unit_of_measurement": "%",
        "entity_category": "diagnostic",
        "icon": "mdi:cpu-64-bit"
    }
    mqtt_send(topics['home_assistant']['cpu_usage'], json.dumps(cpu_usage_config), retain=True)

    memory_usage_config = base_config | {
        "state_topic": topics['memory_usage'],
        "json_attributes_topic": topics['memory_usage_attrs'],
        "name": f"{HOST2MQTT_HOSTNAME} Memory Usage",
        "unique_id": f"{HOST2MQTT_HOSTNAME}.memory_usage",
        "unit_of_measurement": "%",
        "entity_category": "diagnostic",
        "icon": "mdi:memory"
    }
    mqtt_send(topics['home_assistant']['memory_usage'], json.dumps(memory_usage_config), retain=True)


def format_disk_name(name):
    return name\
        .replace("\\", "")\
        .replace("/", "_")\
        .replace(":", "")\
        .lower()\
        .replace("__", "_")


def register_device_disk(disk, diskname = "none"):
    disk_config = base_config | {
        "state_topic": topics['disk_usage'].format(diskname),
        "json_attributes_topic": topics['disk_usage_attrs'].format(diskname),
        "name": f"{disk.device} Disk Usage",
        "unique_id": f"{HOST2MQTT_HOSTNAME}_{diskname}.cpu_usage",
        "unit_of_measurement": "%",
        "entity_category": "diagnostic",
        "icon": "mdi:harddisk"
    }

    mqtt_send(topics['home_assistant']['disk_usage'].format(diskname), json.dumps(disk_config), retain=True)


def sizeof_humanreadable(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def update_sensors():
    mqtt_send(topics['cpu_usage'], psutil.cpu_percent())
    mqtt_send(topics['memory_usage'], psutil.virtual_memory().percent)

    cpu_freq = psutil.cpu_freq()
    mqtt_send(topics['cpu_usage_attrs'], json.dumps({
        "cpu_count": psutil.cpu_count(),
        "cpu_freq_min": cpu_freq.min,
        "cpu_freq_max": cpu_freq.max,
        "cpu_freq_current": cpu_freq.current
    }))

    memory = psutil.virtual_memory()
    mqtt_send(topics['memory_usage_attrs'], json.dumps({
        "memory_total": sizeof_humanreadable(memory.total),
        "memory_available": sizeof_humanreadable(memory.available),
        "memory_used": sizeof_humanreadable(memory.used)
    }))

    parts = psutil.disk_partitions()

    for part in parts:
        disk_name = format_disk_name(part.device)
        register_device_disk(part, disk_name)

        disk_data = psutil.disk_usage(part.mountpoint)

        percent = disk_data.percent

        mqtt_send(topics['disk_usage'].format(disk_name), percent)

        mqtt_send(topics['disk_usage_attrs'].format(disk_name), json.dumps({
            "total": sizeof_humanreadable(disk_data.total),
            "free": sizeof_humanreadable(disk_data.free),
            "used": sizeof_humanreadable(disk_data.used),
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
        }))


if __name__ == '__main__':
    setup_mqtt()

    mqtt_connect(True)

    while True:
        update_sensors()
        sleep(STATS_DELAY_SECONDS)