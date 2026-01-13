#!/usr/bin/env python3
"""
新しいパーサー実装（app.pyに移植する前のテスト用）
"""
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tokyo")

WEEKDAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6
}

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
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
        else:
            # パースできなかったトークンはnoteに追加
            note_tokens.append(token)
    
    note = ' '.join(note_tokens)
    
    # 日付が1つもパースできなかった場合は今日+全文がnote
    if not dates:
        return [datetime.now(TZ)], text
    
    return dates, note


# テスト
if __name__ == "__main__":
    test_cases = [
        ("mon tue", True, False),
        ("mon-fri", True, False),
        ("2/1-2/5", True, True),
        ("2/1 2/2 2/5", True, True),
        ("2/1,2/2,2/5", True, True),
        ("2/1 3 4", True, True),  # 月省略形式は無効
        ("2/1-5", True, True),  # 月省略範囲は無効
        ("mon tue 2/1 出張", True, True),
        ("jan", True, True),
    ]
    
    for text, allow_weekday, allow_date in test_cases:
        print(f"\nInput: '{text}'")
        print(f"Options: weekday={allow_weekday}, date={allow_date}")
        dates, note = parse_command_text(text, allow_weekday, allow_date)
        print(f"Dates: {len(dates)}")
        for d in dates[:5]:
            print(f"  - {d.strftime('%Y-%m-%d (%a)')}")
        if len(dates) > 5:
            print(f"  ... (他 {len(dates)-5} 件)")
        print(f"Note: '{note}'")
