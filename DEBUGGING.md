# デバッグガイド

## エラーハンドリングの改善

全てのコマンドハンドラーに詳細なエラーハンドリングとデバッグログを追加しました。

### デバッグログの見方

ボットを実行すると、以下のようなログが出力されます：

```
[DEBUG] [/in] user=U123456, text='tue'
[DEBUG] parse_command_text: text='tue', weekday=True, date=False
[DEBUG] parse_weekday_range: tokens=['tue']
[DEBUG]   Weekday found: tue (1)
[DEBUG] get_next_weekday: target=1, from=2026-01-13, result=2026-01-13
[DEBUG] parse_weekday_range result: dates=[datetime.date(2026, 1, 13)], remaining=''
[DEBUG] [/in] parsed: dates=['2026-01-13'], note=''
[DEBUG] [set_status_for_dates] user=Alice, status=in, dates_count=1
[DEBUG]   Set Alice 2026-01-13 = in ()
[DEBUG] [set_status_for_dates] State saved
[DEBUG] [update_board_message] Updating board in channel=C123456
[DEBUG] [update_board_message] Board updated successfully
[DEBUG] [set_status_for_dates] Complete
[DEBUG] [/in] success
```

### エラーが発生した場合

エラーが発生すると、以下のように表示されます：

1. **ユーザーへの通知**:
   ```
   ⚠️ エラーが発生しました: [エラーメッセージ]
   ```

2. **ログ出力**:
   ```
   [DEBUG] [/in] ERROR: [エラーの詳細]
   Traceback (most recent call last):
     ...
   ```

## よくある問題と対処法

### 1. `/in tue` が動かない

**症状**: 特定の曜日だけ反応しない

**原因の可能性**:
- Slackのコマンド設定が不完全
- ボット権限の不足
- APIレート制限

**確認方法**:
1. ログを確認して `[/in] user=...` が出力されているか
2. エラーメッセージが表示されているか
3. `[/in] ERROR:` のログがあるか

### 2. ボードが更新されない

**症状**: コマンドは成功するがボードが更新されない

**原因の可能性**:
- `board_message` の情報が古い
- チャンネルへのアクセス権限がない

**確認方法**:
1. `/setup` を再実行
2. ログで `[update_board_message] ERROR:` を確認

### 3. ユーザー名が取得できない

**症状**: `user_name()` でエラーが発生

**原因**: `users:read` 権限がない

**対処法**: Slackアプリの設定で `users:read` 権限を追加

## デバッグモードの有効化

`.env` ファイルに以下を追加（デフォルトで有効）:

```
DEBUG=1
```

無効化する場合:

```
DEBUG=0
```

## ログの確認

ボットをターミナルで実行している場合、標準出力にログが表示されます：

```bash
python app.py
```

バックグラウンドで実行している場合は、ログをファイルにリダイレクト：

```bash
python app.py > bot.log 2>&1 &
tail -f bot.log
```

## トラブルシューティング手順

### ステップ1: ログを確認

```bash
# リアルタイムでログを表示
tail -f bot.log

# エラーだけを抽出
grep ERROR bot.log

# 特定のコマンドのログを抽出
grep "\[/in\]" bot.log
```

### ステップ2: パーサーのテスト

```bash
python test_parser.py
```

問題のある入力パターンをテストケースに追加して確認できます。

### ステップ3: state.jsonの確認

```bash
cat state.json | python -m json.tool
```

データが正しく保存されているか確認します。

### ステップ4: Slackアプリの設定確認

1. **必要な権限**:
   - `commands` - スラッシュコマンド
   - `chat:write` - メッセージ送信
   - `pins:write` - ピン留め
   - `pins:read` - ピン情報読取
   - `users:read` - ユーザー情報取得
   - `channels:history` - メッセージ履歴（/delete用）

2. **Socket Modeの有効化**

3. **コマンドの登録**: 全てのコマンド（/in, /out, /pm, /home, /maybe, /away, /will, /can, /clear, /lab, /note, /setup, /delete）が登録されているか

## 特定のコマンドが動かない場合

### `/in tue` が動かないが `/in mon` は動く

これは曜日の処理の問題ではなく、Slackの問題の可能性があります：

1. **Slackコマンドの再登録**
   - Slackアプリの設定画面で各コマンドを確認
   - Request URL が正しいか確認

2. **ボットの再起動**
   ```bash
   # 現在のプロセスを停止
   pkill -f "python app.py"
   
   # 再起動
   python app.py
   ```

3. **キャッシュのクリア**
   - Slackアプリをリフレッシュ
   - 別のチャンネルで試してみる

## 問題が解決しない場合

1. `state.json` のバックアップを取る
2. `state.json` を削除して `/setup` を再実行
3. それでも動かない場合は、ログ全体を確認

```bash
python app.py 2>&1 | tee full_debug.log
```

そして、問題のコマンドを実行後、`full_debug.log` を確認します。
