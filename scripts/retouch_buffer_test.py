import json

import requests

SEND_URL = "http://127.0.0.1:5000/processing/send-to-retouch"
BUFFER_URL = "http://127.0.0.1:5000/processing/retouch-buffer"


def run():
    with open("test_debug.png", "rb") as fh:
        files = {"file": ("test_debug.png", fh, "image/png")}
        r = requests.post(SEND_URL, files=files)
        print("POST", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2)[:4000])
        except Exception as e:
            print("POST json parse error", e)
    r2 = requests.get(BUFFER_URL)
    print("GET", r2.status_code)
    try:
        print(json.dumps(r2.json(), indent=2)[:4000])
    except Exception as e:
        print("GET json parse error", e)


if __name__ == "__main__":
    run()
