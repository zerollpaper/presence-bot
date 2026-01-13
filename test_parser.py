#!/usr/bin/env python3
"""
パーサーのテストスクリプト（app.pyから実装をインポート）
"""
import sys
sys.path.insert(0, '.')

from app import parse_command_text, TZ
from datetime import datetime

# テストケース
test_cases = [
    # 曜日テスト
    ("mon tue", True, False, 2, "複数曜日"),
    ("mon-fri", True, False, 5, "曜日範囲"),
    ("wed afternoon", True, False, 1, "曜日+note"),
    ("thu 午後", True, False, 1, "曜日+日本語note"),
    
    # 日付テスト（厳格な形式）
    ("2/1-2/5", True, True, 5, "日付範囲"),
    ("2/1 2/2 2/5", True, True, 3, "複数日付"),
    ("2/1,2/2,2/5", True, True, 3, "カンマ区切り日付"),
    ("2/1-2/5 出張", True, True, 5, "日付範囲+note"),
    
    # 月名テスト
    ("jan", True, True, 31, "1月全日"),
    ("feb", True, True, 28, "2月全日"),
    
    # 複合テスト
    ("mon tue 2/1 出張", True, True, 3, "曜日+日付+note"),
    
    # 無効な形式（noteとして扱われる）
    ("2/1 3 4", True, True, 1, "月省略形式は無効→今日+note"),
    ("2/1-5", True, True, 1, "月省略範囲は無効→今日+note"),
    ("random text", True, False, 1, "認識できないテキスト→今日+note"),
]

def run_tests():
    now = datetime.now(TZ)
    print(f"今日: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})")
    print(f"現在時刻: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    passed = 0
    failed = 0
    
    for test_input, allow_weekday, allow_date, expected_count, description in test_cases:
        print("=" * 60)
        print(f"TEST: {description}")
        print(f"Input: '{test_input}'")
        print(f"Options: weekday={allow_weekday}, date={allow_date}")
        print("=" * 60)
        
        try:
            dates, note = parse_command_text(test_input, allow_weekday=allow_weekday, allow_date=allow_date)
            
            print(f"結果:")
            print(f"  日付数: {len(dates)}")
            for date in sorted(dates)[:5]:
                print(f"    - {date.strftime('%Y-%m-%d (%a)')}")
            if len(dates) > 5:
                print(f"    ... (他 {len(dates)-5} 件)")
            print(f"  Note: '{note}'")
            
            if len(dates) == expected_count:
                print(f"  ✅ PASS (expected {expected_count} dates)")
                passed += 1
            else:
                print(f"  ❌ FAIL (expected {expected_count} dates, got {len(dates)})")
                failed += 1
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        
        print()
    
    print("=" * 60)
    print(f"✅ {passed} passed, ❌ {failed} failed")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
