#!/usr/bin/env python3
"""
表示形式のテスト
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0, '.')
from app import render_board_range, render_user_schedule

TZ = ZoneInfo('Asia/Tokyo')

# テストデータを作成
schedules = {
    'Alice': {},
    'Bob': {}
}

now = datetime.now(TZ)
for i in range(21):  # 3週間分
    date = now + timedelta(days=i)
    date_key = date.strftime('%Y-%m-%d')
    if i % 3 == 0:
        schedules['Alice'][date_key] = {'status': 'in', 'note': 'オフィス'}
    elif i % 3 == 1:
        schedules['Alice'][date_key] = {'status': 'out', 'note': '外出'}
    else:
        schedules['Alice'][date_key] = {'status': 'trip', 'note': '出張'}
    
    if i % 2 == 0:
        schedules['Bob'][date_key] = {'status': 'home', 'note': '在宅'}

print('=== 1週間表示のテスト ===')
result = render_board_range(schedules, 7)
print(result)

print('\n' + '='*60)
print('=== 2週間表示のテスト ===')
result = render_board_range(schedules, 14)
print(result)

print('\n' + '='*60)
print('=== 3週間表示のテスト ===')
result = render_board_range(schedules, 21)
print(result)

print('\n' + '='*60)
print('=== ユーザー予定表示のテスト (Alice) ===')
result = render_user_schedule(schedules, 'Alice')
print(result)

print('\n✅ テスト完了')
