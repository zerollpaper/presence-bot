import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

try:
    from zoneinfo import ZoneInfo              # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo    # Python <=3.8

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from dotenv import load_dotenv
load_dotenv()

import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# デバッグモード
DEBUG = os.environ.get("DEBUG", "1") == "1"

def debug_log(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

ADMIN_USERS = set(
    uid for uid in os.environ.get("ADMIN_USERS", "").split(",") if uid
)

def is_admin(user_id):
    return user_id in ADMIN_USERS

TZ = ZoneInfo("Asia/Tokyo")
DATA_FILE = "state.json"

def load_state():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 古いフォーマットから新しいフォーマットへ移行
            if "board" in data and "schedules" not in data:
                debug_log("Migrating old board format to schedules format")
                schedules = {}
                today = today_key()
                for user, info in data["board"].items():
                    if info.get("status"):
                        schedules[user] = {today: {"status": info["status"], "note": info.get("note", "")}}
                data["schedules"] = schedules
                del data["board"]
                save_state(data)
            return data
    return {"schedules": {}, "board_message": {"channel": None, "ts": None}}

def save_state(state):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def today_key():
    return datetime.now(TZ).strftime("%Y-%m-%d")

def date_to_key(date: datetime) -> str:
    return date.strftime("%Y-%m-%d")

# ========== 日付パーサー ==========

WEEKDAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
    "friday": 4, "saturday": 5, "sunday": 6
}

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12
}

def get_next_weekday(target_weekday: int, from_date: datetime = None) -> datetime:
    """指定した曜日の次の日付を取得（今日から始まる7日間）"""
    if from_date is None:
        from_date = datetime.now(TZ)
    
    current_weekday = from_date.weekday()
    days_ahead = target_weekday - current_weekday
    if days_ahead < 0:
        days_ahead += 7
    
    result = from_date + timedelta(days=days_ahead)
    debug_log(f"get_next_weekday: target={target_weekday}, from={from_date.date()}, result={result.date()}")
    return result

def parse_single_token(token: str) -> Tuple[Optional[List[datetime]], str]:
    """
    単一のトークンをパースして日付リストを返す
    戻り値: (日付リスト or None, トークンの種類)
    トークンの種類: "weekday", "weekday_range", "date", "date_range", "month", "invalid"
    """
    token = token.strip().lower()
    
    if not token:
        return None, "empty"
    
    # 範囲指定（ハイフン含む） - ハイフンの前後にスペースがないことが前提
    if '-' in token:
        parts = token.split('-', 1)
        if len(parts) != 2:
            return None, "invalid"
        
        start_token = parts[0].strip()
        end_token = parts[1].strip()
        
        # 曜日範囲 "mon-fri"
        start_day = WEEKDAY_MAP.get(start_token)
        end_day = WEEKDAY_MAP.get(end_token)
        
        if start_day is not None and end_day is not None:
            debug_log(f"  Weekday range: {start_token}-{end_token}")
            dates = []
            current = start_day
            while True:
                dates.append(get_next_weekday(current))
                if current == end_day:
                    break
                current = (current + 1) % 7
            return dates, "weekday_range"
        
        # 日付範囲 "2/1-2/5" (両方とも月/日形式必須)
        start_match = re.fullmatch(r'(\d{1,2})/(\d{1,2})', start_token)
        end_match = re.fullmatch(r'(\d{1,2})/(\d{1,2})', end_token)
        
        if start_match and end_match:
            now = datetime.now(TZ)
            current_year = now.year
            
            start_month = int(start_match.group(1))
            start_day = int(start_match.group(2))
            end_month = int(end_match.group(1))
            end_day = int(end_match.group(2))
            
            # 年の判定
            start_year = current_year
            if start_month < now.month or (start_month == now.month and start_day < now.day):
                start_year = current_year + 1
            
            end_year = start_year
            if end_month < start_month:
                end_year = start_year + 1
            
            try:
                start_date = datetime(start_year, start_month, start_day, tzinfo=TZ)
                end_date = datetime(end_year, end_month, end_day, tzinfo=TZ)
                
                debug_log(f"  Date range: {start_date.date()} to {end_date.date()}")
                dates = []
                current = start_date
                while current <= end_date:
                    dates.append(current)
                    current += timedelta(days=1)
                
                return dates, "date_range"
            except ValueError:
                # 無効な日付
                return None, "invalid"
        
        # どちらでもない範囲指定は無効
        return None, "invalid"
    
    # 単一トークン（範囲指定なし）
    
    # 曜日
    weekday = WEEKDAY_MAP.get(token)
    if weekday is not None:
        debug_log(f"  Weekday: {token}")
        return [get_next_weekday(weekday)], "weekday"
    
    # 月名
    month_num = MONTH_MAP.get(token)
    if month_num is not None:
        now = datetime.now(TZ)
        current_year = now.year
        
        # 過去の月は来年扱い
        if month_num < now.month:
            year = current_year + 1
        else:
            year = current_year
        
        # その月の全日を追加
        if month_num == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=TZ)
        else:
            next_month = datetime(year, month_num + 1, 1, tzinfo=TZ)
        
        debug_log(f"  Month: {token}")
        dates = []
        current_date = datetime(year, month_num, 1, tzinfo=TZ)
        while current_date < next_month:
            dates.append(current_date)
            current_date += timedelta(days=1)
        
        return dates, "month"
    
    # 日付 "2/1" (月/日形式必須)
    date_match = re.fullmatch(r'(\d{1,2})/(\d{1,2})', token)
    if date_match:
        now = datetime.now(TZ)
        current_year = now.year
        
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        
        # 年の判定
        year = current_year
        if month < now.month or (month == now.month and day < now.day):
            year = current_year + 1
        
        try:
            date = datetime(year, month, day, tzinfo=TZ)
            debug_log(f"  Date: {date.date()}")
            return [date], "date"
        except ValueError:
            # 無効な日付
            return None, "invalid"
    
    # 認識できないトークン
    return None, "invalid"

def parse_command_text(text: str, allow_weekday: bool = True, allow_date: bool = False) -> Tuple[List[datetime], str]:
    """
    コマンドのテキストをパースして日付リストとnoteを返す
    allow_weekday: 曜日指定を許可
    allow_date: 日付指定を許可
    """
    debug_log(f"parse_command_text: text='{text}', weekday={allow_weekday}, date={allow_date}")
    
    if not text:
        # テキストが空なら今日
        return [datetime.now(TZ)], ""
    
    # カンマをスペースに置換
    text = text.replace(',', ' ')
    
    # スペースで分割
    tokens = text.split()
    
    dates = []
    note_tokens = []
    
    for token in tokens:
        parsed_dates, token_type = parse_single_token(token)
        
        if parsed_dates is not None:
            # 曜日パースが許可されているか
            if token_type in ["weekday", "weekday_range"] and not allow_weekday:
                note_tokens.append(token)
                continue
            
            # 日付パースが許可されているか
            if token_type in ["date", "date_range", "month"] and not allow_date:
                note_tokens.append(token)
                continue
            
            dates.extend(parsed_dates)
            debug_log(f"  Token '{token}' parsed as {token_type}: {len(parsed_dates)} date(s)")
        else:
            # パースできなかったトークンはnoteに追加
            note_tokens.append(token)
            debug_log(f"  Token '{token}' added to note ({token_type})")
    
    note = ' '.join(note_tokens)
    
    # 日付が1つもパースできなかった場合は今日+全文がnote
    if not dates:
        debug_log(f"  No dates parsed, treating as note")
        return [datetime.now(TZ)], text
    
    debug_log(f"  Result: {len(dates)} date(s), note='{note}'")
    return dates, note

def render_board(schedules, target_date=None):
    """
    指定日のボードを表示
    schedules: {user_name: {date_key: {"status": "...", "note": "..."}}}
    """
    if target_date is None:
        target_date = datetime.now(TZ)
    
    date_key = date_to_key(target_date)
    lines = [f"【在室ボード】{date_key}"]
    
    # ユーザー毎の状態を集計
    board = {}
    for user_name, user_schedule in schedules.items():
        if date_key in user_schedule:
            info = user_schedule[date_key]
            board[user_name] = info
    
    if not board:
        lines.append("（まだ誰も登録していません）")
    else:
        status_emoji = {
            "in": "✅",
            "pm": "🕒",
            "out": "❌",
            "home": "🏠",
            "maybe": "🤔",
            "trip": "✈️",
            "will": "📅",
            "can": "💡",
        }
        
        for name in sorted(board.keys()):
            s = board[name].get("status", "")
            if not s:
                continue
            note = board[name].get("note", "")
            emoji = status_emoji.get(s, "")
            status_part = f" {emoji} {s}" if emoji else f" {s}"
            tail = f"（{note}）" if note else ""
            lines.append(f"- {name}{status_part}{tail}")
    
    lines.append(f"\n最終更新: {datetime.now(TZ).strftime('%H:%M')}")
    return "\n".join(lines)

def render_board_week(schedules):
    """今日から7日間のボードを表示"""
    lines = ["【在室ボード - 今週】"]
    now = datetime.now(TZ)
    
    # 全ユーザーを収集
    all_users = set()
    for i in range(7):
        date = now + timedelta(days=i)
        date_key = date_to_key(date)
        for user_name, user_schedule in schedules.items():
            if date_key in user_schedule:
                all_users.add(user_name)
    
    if not all_users:
        lines.append("（まだ誰も登録していません）")
        return "\n".join(lines)
    
    status_emoji = {
        "in": "✅",
        "pm": "🕒",
        "out": "❌",
        "home": "🏠",
        "maybe": "🤔",
        "trip": "✈️",
        "will": "📅",
        "can": "💡",
    }
    
    for user_name in sorted(all_users):
        user_line = f"\n**{user_name}**"
        user_schedule = schedules.get(user_name, {})
        
        day_parts = []
        for i in range(7):
            date = now + timedelta(days=i)
            date_key = date_to_key(date)
            weekday = ["月", "火", "水", "木", "金", "土", "日"][date.weekday()]
            
            if date_key in user_schedule:
                info = user_schedule[date_key]
                status = info.get("status", "—")
                note = info.get("note", "")
                emoji = status_emoji.get(status, "➖")
                day_parts.append(f"{date.day}({weekday}){emoji}")
            else:
                day_parts.append(f"{date.day}({weekday})➖")
        
        lines.append(user_line)
        lines.append("  " + " | ".join(day_parts))
    
    lines.append(f"\n最終更新: {datetime.now(TZ).strftime('%H:%M')}")
    return "\n".join(lines)

app = App(token=os.environ["SLACK_BOT_TOKEN"])
state = load_state()

def cleanup_old_dates():
    """過去の日付を削除"""
    today = datetime.now(TZ).date()
    removed_count = 0
    
    for user_name in list(state["schedules"].keys()):
        user_schedule = state["schedules"][user_name]
        for date_key in list(user_schedule.keys()):
            try:
                date_obj = datetime.strptime(date_key, "%Y-%m-%d").date()
                if date_obj < today:
                    debug_log(f"Removing old date: {user_name} {date_key}")
                    del user_schedule[date_key]
                    removed_count += 1
            except:
                pass
        
        # スケジュールが空になったユーザーを削除
        if not user_schedule:
            del state["schedules"][user_name]
    
    if removed_count > 0:
        debug_log(f"Cleaned up {removed_count} old entries")
        save_state(state)
    
    return removed_count

def ensure_board_message(client):
    ch = state["board_message"]["channel"]
    ts = state["board_message"]["ts"]
    if ch and ts:
        return ch, ts
    return None, None

def update_board_message(client):
    """ボードメッセージを更新（今日と今週を表示）"""
    try:
        ch, ts = ensure_board_message(client)
        if not (ch and ts):
            debug_log("[update_board_message] No board message found, skipping update")
            return
        
        # クリーンアップ
        cleanup_old_dates()
        
        # 今日と今週を表示
        today_board = render_board(state["schedules"])
        week_board = render_board_week(state["schedules"])
        
        text = f"{today_board}\n\n{week_board}"
        debug_log(f"[update_board_message] Updating board in channel={ch}")
        client.chat_update(channel=ch, ts=ts, text=text)
        debug_log("[update_board_message] Board updated successfully")
    except Exception as e:
        debug_log(f"[update_board_message] ERROR: {e}")
        import traceback
        traceback.print_exc()

def user_name(client, user_id):
    prof = client.users_info(user=user_id)["user"]["profile"]
    return prof.get("display_name") or prof.get("real_name") or user_id

def normalize_note(text: str) -> str:
    return (text or "").strip()

def set_status_for_dates(client, user_id, status, dates: List[datetime], note: str = ""):
    """指定した日付にステータスを設定"""
    try:
        name = user_name(client, user_id)
        debug_log(f"[set_status_for_dates] user={name}, status={status}, dates_count={len(dates)}")
        
        if name not in state["schedules"]:
            state["schedules"][name] = {}
        
        for date in dates:
            date_key = date_to_key(date)
            state["schedules"][name][date_key] = {
                "status": status,
                "note": note
            }
            debug_log(f"  Set {name} {date_key} = {status} ({note})")
        
        save_state(state)
        debug_log("[set_status_for_dates] State saved")
        update_board_message(client)
        debug_log("[set_status_for_dates] Complete")
    except Exception as e:
        debug_log(f"[set_status_for_dates] ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.command("/setup")
def setup(ack, body, client):
    channel_id = body["channel_id"]

    # If a previous board message is known, unpin it (best-effort).
    prev_ch = state.get("board_message", {}).get("channel")
    prev_ts = state.get("board_message", {}).get("ts")
    if prev_ch and prev_ts:
        try:
            client.pins_remove(channel=prev_ch, timestamp=prev_ts)
        except Exception:
            # Ignore failures (e.g., message deleted, missing permissions, etc.)
            pass

    # Create a new board message and pin it
    text = f"{render_board(state['schedules'])}\n\n{render_board_week(state['schedules'])}"
    msg = client.chat_postMessage(channel=channel_id, text=text)
    ts = msg["ts"]
    client.pins_add(channel=channel_id, timestamp=ts)
    state["board_message"] = {"channel": channel_id, "ts": ts}
    save_state(state)
    ack("在室ボードを作成してピン留めしました。以降 /in /out /pm /home /note /maybe /trip /will /can /clear で更新できます。")

@app.command("/in")
def cmd_in(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/in] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=False)
        debug_log(f"[/in] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"✅ in にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"✅ in にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "in", dates, note)
        debug_log(f"[/in] success")
    except Exception as e:
        debug_log(f"[/in] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/out")
def cmd_out(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/out] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=False)
        debug_log(f"[/out] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"❌ out にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"❌ out にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "out", dates, note)
        debug_log(f"[/out] success")
    except Exception as e:
        debug_log(f"[/out] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/pm")
def cmd_pm(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/pm] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=False)
        debug_log(f"[/pm] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"🕒 pm にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"🕒 pm にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "pm", dates, note)
        debug_log(f"[/pm] success")
    except Exception as e:
        debug_log(f"[/pm] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/home")
def cmd_home(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/home] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=False)
        debug_log(f"[/home] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"🏠 home にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"🏠 home にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "home", dates, note)
        debug_log(f"[/home] success")
    except Exception as e:
        debug_log(f"[/home] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/maybe")
def cmd_maybe(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/maybe] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=True)
        debug_log(f"[/maybe] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"🤔 maybe にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"🤔 maybe にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "maybe", dates, note)
        debug_log(f"[/maybe] success")
    except Exception as e:
        debug_log(f"[/maybe] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/trip")
def cmd_trip(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/trip] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=True)
        debug_log(f"[/trip] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"✈️ trip にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"✈️ trip にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "trip", dates, note)
        debug_log(f"[/trip] success")
    except Exception as e:
        debug_log(f"[/trip] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/will")
def cmd_will(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/will] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=True)
        debug_log(f"[/will] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"📅 will にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"📅 will にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "will", dates, note)
        debug_log(f"[/will] success")
    except Exception as e:
        debug_log(f"[/will] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/can")
def cmd_can(ack, body, client):
    try:
        text = body.get("text", "").strip()
        debug_log(f"[/can] user={body['user_id']}, text='{text}'")
        
        dates, note = parse_command_text(text, allow_weekday=True, allow_date=True)
        debug_log(f"[/can] parsed: dates={[d.strftime('%Y-%m-%d') for d in dates]}, note='{note}'")
        
        date_strs = [d.strftime("%m/%d") for d in dates]
        if len(dates) == 1 and dates[0].date() == datetime.now(TZ).date():
            msg = f"💡 can にしました" + (f"（{note}）" if note else "")
        else:
            msg = f"💡 can にしました: {', '.join(date_strs)}" + (f"（{note}）" if note else "")
        
        ack(msg)
        set_status_for_dates(client, body["user_id"], "can", dates, note)
        debug_log(f"[/can] success")
    except Exception as e:
        debug_log(f"[/can] ERROR: {e}")
        import traceback
        traceback.print_exc()
        ack(f"⚠️ エラーが発生しました: {str(e)}")

@app.command("/clear")
def cmd_clear(ack, body, client):
    text = body.get("text", "").strip().lower()
    name = user_name(client, body["user_id"])
    
    if name not in state["schedules"]:
        ack("🧹 削除するステータスがありません")
        return
    
    user_schedule = state["schedules"][name]
    now = datetime.now(TZ)
    
    if text == "all":
        # 全て削除
        count = len(user_schedule)
        state["schedules"][name] = {}
        if not state["schedules"][name]:
            del state["schedules"][name]
        ack(f"🧹 全てのステータスを削除しました（{count}件）")
    elif text == "week":
        # 今日から7日間
        removed = 0
        for i in range(7):
            date = now + timedelta(days=i)
            date_key = date_to_key(date)
            if date_key in user_schedule:
                del user_schedule[date_key]
                removed += 1
        if not user_schedule:
            del state["schedules"][name]
        ack(f"🧹 今週のステータスを削除しました（{removed}件）")
    elif text == "" or text is None:
        # 今日のみ
        today = today_key()
        if today in user_schedule:
            del user_schedule[today]
            if not user_schedule:
                del state["schedules"][name]
            ack("🧹 今日のステータスを削除しました")
        else:
            ack("🧹 今日のステータスはありません")
    else:
        # "3", "3 week", "3 weeks" のパース
        match = re.match(r'(\d+)\s*(weeks?)?', text)
        if match:
            weeks = int(match.group(1))
            if 1 <= weeks <= 10:
                days = weeks * 7
                removed = 0
                for i in range(days):
                    date = now + timedelta(days=i)
                    date_key = date_to_key(date)
                    if date_key in user_schedule:
                        del user_schedule[date_key]
                        removed += 1
                if not user_schedule:
                    del state["schedules"][name]
                ack(f"🧹 {weeks}週間のステータスを削除しました（{removed}件）")
            else:
                ack("⚠️ 週数は1〜10の範囲で指定してください")
                return
        else:
            ack("⚠️ 使い方: /clear [week|all|数字]")
            return
    
    save_state(state)
    update_board_message(client)

@app.command("/note")
def cmd_note(ack, body, client):
    note = normalize_note(body.get("text"))
    name = user_name(client, body["user_id"])
    today = today_key()
    
    # 今日のステータスがあれば更新、なければin扱い
    if name in state["schedules"] and today in state["schedules"][name]:
        current_status = state["schedules"][name][today].get("status", "in")
    else:
        current_status = "in"
    
    ack(f"📝 note を更新" + (f": {note}" if note else "（空）"))
    set_status_for_dates(client, body["user_id"], current_status, [datetime.now(TZ)], note)

def render_board_range(schedules, days: int):
    """指定日数分のボードを表示（コードブロック形式）"""
    lines = [f"【在室ボード - {days}日間】"]
    now = datetime.now(TZ)
    
    # 全ユーザーを収集
    all_users = set()
    for i in range(days):
        date = now + timedelta(days=i)
        date_key = date_to_key(date)
        for user_name, user_schedule in schedules.items():
            if date_key in user_schedule:
                all_users.add(user_name)
    
    if not all_users:
        lines.append("（まだ誰も登録していません）")
        return "```\n" + "\n".join(lines) + "\n```"
    
    status_emoji = {
        "in": "✅",
        "pm": "🕒",
        "out": "❌",
        "home": "🏠",
        "maybe": "🤔",
        "trip": "✈️",
        "will": "📅",
        "can": "💡",
    }
    
    weeks = (days + 6) // 7  # 切り上げで週数を計算
    
    # 2週間以上の場合は縦に曜日を並べる
    if weeks >= 2:
        for user_name_item in sorted(all_users):
            user_line = f"\n{user_name_item}"
            user_schedule = schedules.get(user_name_item, {})
            
            lines.append(user_line)
            
            # 週ごとに処理
            for week_idx in range(weeks):
                start_day = week_idx * 7
                end_day = min(start_day + 7, days)
                
                if week_idx == 0:
                    # 最初の週だけ曜日ヘッダーを追加
                    header_parts = []
                    day_parts = []
                    for i in range(start_day, end_day):
                        date = now + timedelta(days=i)
                        weekday = ["月", "火", "水", "木", "金", "土", "日"][date.weekday()]
                        # 曜日: 全角1文字(表示幅2) + 前後スペース1ずつ = 表示幅4
                        header_parts.append(f" {weekday} ")
                        
                        date_key = date_to_key(date)
                        if date_key in user_schedule:
                            info = user_schedule[date_key]
                            status = info.get("status", "—")
                            emoji = status_emoji.get(status, "➖")
                            # 日付2桁 + 絵文字(表示幅2) = 表示幅4
                            day_parts.append(f"{date.day:>2}{emoji}")
                        else:
                            day_parts.append(f"{date.day:>2}➖")
                    
                    lines.append("  " + "".join(header_parts))
                    lines.append("  " + "".join(day_parts))
                else:
                    # 2週目以降は日付とステータスのみ
                    day_parts = []
                    for i in range(start_day, end_day):
                        date = now + timedelta(days=i)
                        date_key = date_to_key(date)
                        
                        if date_key in user_schedule:
                            info = user_schedule[date_key]
                            status = info.get("status", "—")
                            emoji = status_emoji.get(status, "➖")
                            day_parts.append(f"{date.day:>2}{emoji}")
                        else:
                            day_parts.append(f"{date.day:>2}➖")
                    
                    lines.append("  " + "".join(day_parts))
    else:
        # 1週間の場合は従来通り
        for user_name_item in sorted(all_users):
            user_line = f"\n{user_name_item}"
            user_schedule = schedules.get(user_name_item, {})
            
            day_parts = []
            for i in range(days):
                date = now + timedelta(days=i)
                date_key = date_to_key(date)
                weekday = ["月", "火", "水", "木", "金", "土", "日"][date.weekday()]
                
                if date_key in user_schedule:
                    info = user_schedule[date_key]
                    status = info.get("status", "—")
                    emoji = status_emoji.get(status, "➖")
                    day_parts.append(f"{date.day}({weekday}){emoji}")
                else:
                    day_parts.append(f"{date.day}({weekday})➖")
            
            lines.append(user_line)
            lines.append("  " + " | ".join(day_parts))
    
    lines.append(f"\n最終更新: {datetime.now(TZ).strftime('%H:%M')}")
    return "```\n" + "\n".join(lines) + "\n```"

def render_user_schedule(schedules, target_user: str):
    """特定ユーザーの全予定を表示"""
    lines = [f"【{target_user} の予定】"]
    now = datetime.now(TZ)
    
    user_schedule = schedules.get(target_user, {})
    
    if not user_schedule:
        lines.append("（予定がありません）")
        return "\n".join(lines)
    
    status_emoji = {
        "in": "✅",
        "pm": "🕒",
        "out": "❌",
        "home": "🏠",
        "maybe": "🤔",
        "trip": "✈️",
        "will": "📅",
        "can": "💡",
    }
    
    # 全ての予定日を取得してソート
    all_dates = []
    for date_key in user_schedule.keys():
        try:
            date_obj = datetime.strptime(date_key, "%Y-%m-%d")
            # 今日以降のみ
            if date_obj.date() >= now.date():
                all_dates.append(date_obj)
        except:
            pass
    
    all_dates.sort()
    
    if not all_dates:
        lines.append("（今後の予定がありません）")
        return "\n".join(lines)
    
    for date in all_dates:
        date_key = date_to_key(date)
        weekday = ["月", "火", "水", "木", "金", "土", "日"][date.weekday()]
        
        info = user_schedule[date_key]
        status = info.get("status", "—")
        note = info.get("note", "")
        emoji = status_emoji.get(status, "")
        
        if emoji:
            status_str = f"{emoji} {status}"
        else:
            status_str = status
        
        note_str = f"（{note}）" if note else ""
        lines.append(f"- {date.month}/{date.day}({weekday}): {status_str}{note_str}")
    
    return "\n".join(lines)

@app.command("/lab")
def cmd_lab(ack, body, client):
    text = body.get("text", "").strip()
    channel_id = body["channel_id"]
    user_id = body["user_id"]
    
    # @ユーザー指定のチェック
    mention_match = re.match(r'<@([A-Z0-9]+)(?:\|[^>]+)?>', text)
    if mention_match:
        target_user_id = mention_match.group(1)
        target_name = user_name(client, target_user_id)
        
        # 全ての予定を表示
        schedule_text = render_user_schedule(state["schedules"], target_name)
        
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=schedule_text
        )
        ack()
        return
    
    # 週数のパース
    text_lower = text.lower()
    if text_lower == "" or text_lower is None:
        # 今日のみ
        board_text = render_board(state["schedules"])
        ack(board_text)
    elif text_lower == "week":
        # 今週（7日間）
        board_text = render_board_range(state["schedules"], 7)
        ack(board_text)
    else:
        # "3", "3 week", "3 weeks"
        match = re.match(r'(\d+)\s*(weeks?)?', text_lower)
        if match:
            weeks = int(match.group(1))
            if 1 <= weeks <= 10:
                days = weeks * 7
                board_text = render_board_range(state["schedules"], days)
                ack(board_text)
            else:
                ack("⚠️ 週数は1〜10の範囲で指定してください")
        else:
            ack("⚠️ 使い方: /lab [week|数字|@ユーザー]")

def delete_bot_messages(client, channel_id):
    bot_user_id = client.auth_test()["user_id"]
    deleted = 0
    cursor = None

    while True:
        resp = client.conversations_history(
            channel=channel_id,
            limit=200,
            cursor=cursor
        )
        for msg in resp.get("messages", []):
            if msg.get("user") == bot_user_id or msg.get("bot_id"):
                try:
                    client.chat_delete(channel=channel_id, ts=msg["ts"])
                    deleted += 1
                except Exception:
                    pass
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    state["board_message"] = {"channel": None, "ts": None}
    save_state(state)
    return deleted

@app.command("/delete")
def cmd_delete(ack, body, client):
    ack("🗑 presence-bot のメッセージを削除中…")

    if not is_admin(body["user_id"]):
        return

    channel_id = body["channel_id"]
    deleted = delete_bot_messages(client, channel_id)

    client.chat_postEphemeral(
        channel=channel_id,
        user=body["user_id"],
        text=f"🗑 削除完了: presence-bot のメッセージ {deleted} 件"
    )


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
