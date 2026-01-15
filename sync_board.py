#!/usr/bin/env python3
"""
state.jsonの内容で固定メッセージを即座に更新するスクリプト
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# app.pyと同じ設定を使う
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# app.pyから必要な関数をインポート
from app import state, render_board, render_board_week
from slack_sdk import WebClient

def sync_board():
    """state.jsonの内容でボードメッセージを更新"""
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    
    ch = state["board_message"]["channel"]
    ts = state["board_message"]["ts"]
    
    if not (ch and ts):
        print("❌ board_messageが設定されていません")
        print(f"   channel={ch}, ts={ts}")
        return False
    
    print(f"📋 Updating board message...")
    print(f"   Channel: {ch}")
    print(f"   Timestamp: {ts}")
    
    # ボードをレンダリング
    today_board = render_board(state["schedules"])
    week_board = render_board_week(state["schedules"])
    text = f"{today_board}\n\n{week_board}"
    
    # 更新
    try:
        client.chat_update(channel=ch, ts=ts, text=text)
        print("✅ ボードメッセージを更新しました")
        return True
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

if __name__ == "__main__":
    success = sync_board()
    sys.exit(0 if success else 1)
