import os
import requests
from flask import Flask, request, abort, jsonify

app = Flask(__name__)

# 從 Render 環境變數讀取 LINE Channel Access Token
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# Render 健康檢查 + LINE verify 測試
@app.route("/", methods=["GET", "HEAD", "POST"])
def index():
    if request.method == "POST":
        # LINE 在「Verify Webhook」時，會對 "/" 做 POST 測試
        return ("OK", 200)
    return ("", 200)

# LINE Webhook 事件接收端
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        abort(400)

    print("Received event:", body)

    for event in body.get("events", []):
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"]
            reply_token = event["replyToken"]

            # 回覆 Echo
            reply_message(reply_token, f"你說: {user_text}")

    return jsonify({"status": "ok"}), 200


def reply_message(reply_token, text):
    """呼叫 LINE Messaging API 回覆訊息"""
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {"type": "text", "text": text}
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    print("LINE API response:", response.status_code, response.text)
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
