import json
import os

from ltcli import color


json_path = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'string.json'
)

with open(json_path) as json_file:
    json_data = json.load(json_file)


def get(key):
    try:
        return json_data[key]
    except KeyError:
        print(color.red("Message not found: '{}'".format(key)))
        return ""
