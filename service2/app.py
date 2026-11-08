from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/reverse", methods=["POST"])
def reverse():
  data = request.get_json()

  if not data or "text" not in data:
    return jsonify({"error": "Ungültiger Body. 'text' erforderlich."}), 400

  original_text = data["text"]
  reversed_text = original_text[::-1]

  return jsonify({
      "service2_status": "success",
      "original_text": original_text,
      "reversed_text": reversed_text,
  }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5001)