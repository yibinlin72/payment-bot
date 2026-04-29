import os
import re
import requests
import psycopg2
from flask import Flask, request, abort, jsonify
from datetime import datetime

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Render 健康檢查 + LINE verify 測試
@app.route("/", methods=["GET", "HEAD", "POST"])
def index():
    if request.method == "POST":
        return ("OK", 200)
    return ("", 200)


@app.route("/insert", methods=["POST"])
def insert_payment():
    data = request.get_json()
    pay_dt = data.get("pay_dt")
    category = data.get("category")
    item = data.get("item")
    amount = data.get("amount")

    try:
        insert_payment(pay_dt, category, item, int(amount))
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("Add error:", e)
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/query", methods=["POST"])
def query_payment():
    """依據起訖日期，回傳類別彙整的消費紀錄，並依日期排序"""
    data = request.get_json()
    start_date = data.get("start_date")
    end_date = data.get("end_date")

    if not start_date or not end_date:
        return jsonify({"status": "error", "message": "缺少 start_date 或 end_date"}), 400

    if not validate_date_format(start_date) or not validate_date_format(end_date):
        return jsonify({"status": "error", "message": "日期格式必須為 yyyy-MM-dd"}), 400

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 先撈出符合日期範圍的紀錄
        cur.execute("""
            SELECT pay_dt, category, item, amount
            FROM payment
            WHERE pay_dt BETWEEN %s AND %s
            ORDER BY pay_dt ASC, id ASC
        """, (start_date, end_date))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return jsonify({"status": "success", "data": []}), 200

        # 轉成樹狀結構：category -> list of records
        result = {}
        for pay_dt, category, item, amount in rows:
            if category not in result:
                result[category] = []
            result[category].append({
                "date": pay_dt.strftime("%Y-%m-%d"),
                "item": item,
                "amount": amount
            })

        return jsonify({"status": "success", "data": result}), 200

    except Exception as e:
        print("Query error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# LINE Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        abort(400)

    print("Received event:", body, flush=True)

    for event in body.get("events", []):
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].strip()
            reply_token = event["replyToken"]

            # 預設回覆：echo
            messages = [{"type": "text", "text": f"收到: {user_text}"}]

            if user_text.startswith("/"):
                command_reply = handle_command(user_text)
                if command_reply:
                    messages.append(command_reply)

            reply_messages(reply_token, messages)

    return jsonify({"status": "ok"}), 200


def handle_command(text):
    if text == "/hello":
        return {"type": "text", "text": "哈囉！很高興見到你 👋"}

    elif text.startswith("/insert"):
        parts = re.split(r"[,\s]+", text[4:].strip())

        if len(parts) != 4:
            return {
                "type": "template",
                "altText": "新增消費",
                "template": {
                    "type": "buttons",
                    "title": "新增消費紀錄",
                    "text": "請點擊下方按鈕填寫表單",
                    "actions": [
                        {
                            "type": "uri",
                            "label": "開啟表單",
                            "uri": "https://liff.line.me/2008057774-P62MrMmp"  # 你的 LIFF 頁面
                        }
                    ]
                }
            }

        # if len(parts) != 4:
        #     return {"type": "text", "text": "格式錯誤，請輸入：/add 日期,類別,描述,金額"}
        else:
            try:
                pay_dt, category, item, amount = parts
                amount = int(amount)

                insert_payment(pay_dt, category, item, amount)
                return {"type": "text", "text": f"✅ 新增成功：{pay_dt}, {category}, {item}, {amount}"}

            except ValueError as e:
                return {"type": "text", "text": f"❌ 錯誤：{e}"}
            except Exception as e:
                print("Add error:", e)
                return {"type": "text", "text": "❌ 新增失敗，請檢查格式：/add 日期 類別 描述 金額"}

    elif text == "/list":
        records = get_latest_payments(limit=5)
        if not records:
            return {"type": "text", "text": "目前沒有消費紀錄"}

        # 建立 Flex Message 表格
        contents = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": []
            }
        }

        # 表頭
        contents["body"]["contents"].append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "日期", "weight": "bold", "size": "sm", "flex": 2},
                {"type": "text", "text": "類別", "weight": "bold", "size": "sm", "flex": 2},
                {"type": "text", "text": "描述", "weight": "bold", "size": "sm", "flex": 2},
                {"type": "text", "text": "金額", "weight": "bold", "size": "sm", "flex": 1, "align": "end"}
            ]
        })
        contents["body"]["contents"].append({"type": "separator"})

        # 資料列
        for pay_dt, category, item, amount in records:
            contents["body"]["contents"].append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": pay_dt.strftime("%Y-%m-%d"), "size": "sm", "flex": 2},
                    {"type": "text", "text": category, "size": "sm", "flex": 2},
                    {"type": "text", "text": item, "size": "sm", "flex": 2, "wrap": True},
                    {"type": "text", "text": str(amount), "size": "sm", "flex": 1, "align": "end"}
                ]
            })

        return {
            "type": "flex",
            "altText": "最近 5 筆消費紀錄",
            "contents": contents
        }

    elif text.startswith("/query"):
        parts = re.split(r"[,\s]+", text.strip())

        # case1: 只有 "/query" → 回傳 LIFF 頁面按鈕
        if len(parts) == 1:
            return {
                "type": "template",
                "altText": "查詢消費紀錄",
                "template": {
                    "type": "buttons",
                    "title": "查詢消費紀錄",
                    "text": "請點擊下方按鈕輸入查詢條件",
                    "actions": [
                        {
                            "type": "uri",
                            "label": "開啟查詢頁面",
                            "uri": "https://liff.line.me/2008057774-3klY0YGz"  # 換成查詢用 LIFF ID
                        }
                    ]
                }
            }

        # case2: "/query start_date end_date"
        elif len(parts) == 3:
            _, start_date, end_date = parts

            if not validate_date_format(start_date) or not validate_date_format(end_date):
                return {"type": "text", "text": "❌ 日期格式錯誤，請用 yyyy-MM-dd"}

            try:
                # 查詢資料庫
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                cur.execute("""
                    SELECT pay_dt, category, item, amount
                    FROM payment
                    WHERE pay_dt BETWEEN %s AND %s
                    ORDER BY pay_dt ASC, id ASC
                """, (start_date, end_date))
                rows = cur.fetchall()
                cur.close()
                conn.close()

                if not rows:
                    return {"type": "text", "text": f"查無紀錄 ({start_date} ~ {end_date})"}

                # 分類彙整 → 文字輸出
                result = {}
                for pay_dt, category, item, amount in rows:
                    if category not in result:
                        result[category] = []
                    result[category].append(f"{pay_dt.strftime('%Y-%m-%d')} {item} ${amount}")

                text_result = f"📊 消費紀錄 ({start_date} ~ {end_date})\n"
                for cat, items in result.items():
                    text_result += f"\n【{cat}】\n" + "\n".join(items)

                return {"type": "text", "text": text_result}

            except Exception as e:
                print("Query error:", e)
                return {"type": "text", "text": f"❌ 查詢失敗：{e}"}

        else:
            return {"type": "text", "text": "❌ 格式錯誤，請輸入：\n/query yyyy-MM-dd yyyy-MM-dd"}

    elif text == "/help":
        return {"type": "text", "text": (
            "可用指令：\n"
            "/hello → 打招呼\n"
            "/insert 日期 類別 描述 金額 → 新增消費紀錄\n"
            "/list → 列出最近 5 筆消費紀錄\n"
            "/query → 日期(起) 日期(迄) → 統計消費紀錄\n"
            "/help → 顯示幫助"
        )}

    else:
        return f"未知的指令：{text}"

def validate_date_format(date_str):
    """檢查日期是否符合 yyyy-MM-dd 格式"""
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")  # 驗證日期有效性
        return True
    except ValueError:
        return False


def insert_payment(pay_dt, category, item, amount):
    """寫入 payment 資料表"""

    if not validate_date_format(pay_dt):
        raise ValueError("日期格式錯誤，必須為 yyyy-MM-dd")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO payment (pay_dt, category, item, amount)
        VALUES (%s, %s, %s, %s)
        """,
        (pay_dt, category, item, amount)
    )

    conn.commit()
    cur.close()
    conn.close()


def get_latest_payments(limit=5):
    """查詢最近的消費紀錄"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT pay_dt, category, item, amount
        FROM payment
        ORDER BY pay_dt DESC, id DESC
        LIMIT %s
    """, (limit,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


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
