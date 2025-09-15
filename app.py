import os
import requests
from flask import Flask, request, abort, jsonify

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# Render 健康檢查 + LINE verify 測試
@app.route("/", methods=["GET", "HEAD", "POST"])
def index():
    if request.method == "POST":
        return ("OK", 200)
    return ("", 200)

# LINE Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        abort(400)

    print("Received event:", body)

    for event in body.get("events", []):
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].strip()
            reply_token = event["replyToken"]

            # 準備訊息列表：先 echo
            messages = [{"type": "text", "text": f"收到: {user_text}"}]

            # 如果是指令，附加指令回覆
            if user_text.startswith("/"):
                command_reply = handle_command(user_text)
                if command_reply:
                    messages.append({"type": "text", "text": command_reply})

            reply_messages(reply_token, messages)

    return jsonify({"status": "ok"}), 200


def handle_command(text: str) -> str:
    """處理使用者輸入的指令，回傳要顯示的文字"""
    if text == "/hello":
        return "哈囉！很高興見到你 👋"

    elif text.startswith("/add"):
        parts = text[4:].strip()
        if not parts:
            return "格式錯誤，請輸入：/add 日期,類別,描述,金額"
        return f"新增消費紀錄成功：{parts}"

    elif text == "/link":
        return "這是你的消費紀錄連結：https://example.com/records"

    elif text == "/help":
        return (
            "可用指令：\n"
            "/hello：打招呼\n"
            "/add 日期,類別,描述,金額：新增消費紀錄\n"
            "/link：查看消費紀錄連結\n"
            "/help：顯示幫助"
        )

    else:
        return f"未知的指令：{text}"


def reply_messages(reply_token, messages):
    """一次回覆多則訊息"""
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": messages
    }
    response = requests.post(url, headers=headers, json=payload)
    print("LINE API response:", response.status_code, response.text)
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
