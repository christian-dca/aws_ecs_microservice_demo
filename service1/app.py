import os
import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

SERVICE2_URL = os.environ.get(
    "SERVICE2_URL", "http://localhost:5001"
)


@app.route("/", methods=["GET"])
def index():
  """Renders the HTML user interface for the client."""
  return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
  """EReceives the text from the form and forwards it to Service 2."""
  data = request.get_json()

  if not data or "text" not in data:
    return jsonify({"error": "Invalid Body. 'text' is required."}), 400

  input_text = data["text"]

  try:
    response = requests.post(
        f"{SERVICE2_URL}/reverse", json={"text": input_text}, timeout=5.0
    )
    response.raise_for_status()
    s2_data = response.json()

    return jsonify({
        "service1_status": "success",
        "original_text": input_text,
        "reversed_text_from_service2": s2_data.get("reversed_text"),
    }), 200

  except requests.RequestException as e:
    return jsonify({
        "error": " Error communicating with Service 2",
        "details": str(e),
    }), 502


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000)