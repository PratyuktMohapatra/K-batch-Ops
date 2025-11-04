from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

multi_app = Flask(__name__)
CORS(multi_app)

@multi_app.route('/trigger-multiple', methods=['POST'])
def trigger_multiple():
    payloads = [
        {"client_id": "9", "frequency": "15", "batch_id": "1"},
        {"client_id": "25", "frequency": "15", "batch_id": "1"},
        {"client_id": "32", "frequency": "15", "batch_id": "1"}
    ]

    results = []
    for payload in payloads:
        try:
            res = requests.post("http://localhost:5000/run-automation", json=payload)
            results.append({
                "payload": payload,
                "response": res.json()
            })
        except Exception as e:
            results.append({
                "payload": payload,
                "error": str(e)
            })

    return jsonify({"results": results}), 200

if __name__ == '__main__':
    multi_app.run(host='0.0.0.0', port=5001)
