# ローカル2フォルダ統合 移行計画

[CLAUDE.md](../CLAUDE.md)の「既知のTODO」記載、ローカル2フォルダ(`analysis`と`GitHub\rz`)統合の詳細調査・移行手順。2026-08-17、ユーザーがエクスポートしたタスクスケジューラ5タスクのXML(`RZ_run_*_daily`)を元に調査。

## 1. 現状整理

- `Z:\Users\suehara\Documents\python\analysis`: 本来の作業フォルダ。`token.pickle`・`python_ss\credentials.json`・`.venv`が実在。**git管理下にはない**。
- `Z:\Users\suehara\Documents\GitHub\rz`: 本リポジトリ(`suehara0511/rz`)のクローン。認証情報・`.venv`は含まれない。

### タスクスケジューラ5タスクの実行パス(XML確認済み)

5タスクとも同一パターンで、Command欄に以下の絶対パスを直書きしている。

| タスク名 | Command |
|---|---|
| RZ_run_shoki_seisansei_daily | `Z:\Users\suehara\Documents\python\analysis\auto\run_shoki_seisansei_scheduled.bat` |
| RZ_run_rzkpi_update_daily | `Z:\Users\suehara\Documents\python\analysis\auto\run_rzkpi_update_scheduled.bat` |
| RZ_run_seiyaku_tanka_update_daily | `Z:\Users\suehara\Documents\python\analysis\auto\run_seiyaku_tanka_update_scheduled.bat` |
| RZ_run_eigyo_seisansei_daily | `Z:\Users\suehara\Documents\python\analysis\auto\run_eigyo_seisansei_scheduled.bat` |
| RZ_run_tenki_all_update_daily | `Z:\Users\suehara\Documents\python\analysis\auto\run_tenki_all_update_scheduled.bat` |

トリガー(毎日8:00〜8:40、10分間隔)・実行条件(`LogonType: InteractiveToken`≒ログオン中のみ実行)は5タスクとも同一で、CLAUDE.mdの記載と一致。

### .bat / .pyファイル側の絶対パス依存(リポジトリ側コードを確認して判明)

タスクスケジューラのCommand欄以外にも、以下2箇所で`analysis`という絶対パスがハードコードされている。

1. **`auto/run_*.bat` と `auto/run_*_scheduled.bat`(手動用・スケジュール用、計10ファイル)**: いずれも
   ```bat
   cd /d "%~dp0"
   "Z:\Users\suehara\Documents\python\analysis\.venv\Scripts\python.exe" run_xxx.py
   ```
   という構造。`cd /d "%~dp0"`(自分自身のあるフォルダに移動)は相対的なのでフォルダを動かしても壊れないが、**Pythonインタプリタの呼び出しパスは`analysis\.venv`という絶対パスに固定**されている。
2. **5パイプラインの`★BQ-*.py`本体**: いずれも
   ```python
   json_path = r"Z:\Users\suehara\Documents\python\analysis\python_ss\credentials.json"
   ```
   というOAuthクライアントシークレットの絶対パスを持つ(`転機ALLデータ更新.py`のみ、未使用と思われる古い`C:\Users\suehara\Desktop\...`パスも複数残存)。
   - ただし`python_ss.get_auth()`の実装上、この`json_path`は**`token.pickle`が存在し有効な間は一切参照されない**(token.pickle不在 or リフレッシュトークン失効時のみ、新規OAuthフローのために使われる)。日次実行が現状問題なく回っている以上、今は「使われていない経路」。統合作業自体の必須対応ではないが、**token.pickleの再認証が将来必要になった際、パスが違うと(`auto\`が抜けている)ここで詰まる**ため、実態確認・修正はフォローアップ課題として残す(§4参照)。
   - `token.pickle`自体は`os.path.exists('token.pickle')`という**相対パス**参照のため、実行時のカレントディレクトリ(`.bat`の`cd /d "%~dp0"`により`auto\`)直下に存在する必要がある。

## 2. 結論:移行方針

**`analysis`フォルダを新しい場所に作り直す(≒`GitHub\rz`の方を主にして`analysis`を再現する)のではなく、`analysis`フォルダをそのままgit管理下に変換する(in-place化)。**

理由: タスクスケジューラのCommand、`.bat`内のPythonパス、`★BQ-*.py`内のcredentials.jsonパスの**3箇所すべてが`Z:\Users\suehara\Documents\python\analysis\...`という同一の絶対パスに依存**している。`analysis`というフォルダの場所・名前を変えなければ、この3箇所は**一切変更不要**になる。逆に、もし`GitHub\rz`側のパスに寄せる(≒新しい場所に統合する)方針を取ると、上記3種×該当ファイル数(タスク5件+`.bat`10件+`.py`5件)すべてに変更が必要になり、1箇所でも直し忘れると本番の日次自動更新が静かに壊れるリスクが高い。

## 3. 移行手順(案)

### Step 0. 事前バックアップ
- `analysis`フォルダ全体をzip等でバックアップ(`.venv`は容量が大きいので除外して可)。
- 保険として、対象5タスクの現状設定を`schtasks /query /tn "RZ_run_shoki_seisansei_daily" /v /fo list`等でテキストにも保存(XMLは既にエクスポート済みなので二重の保険)。

### Step 1. 別フォルダに素クローンして差分確認
- `analysis`とは別の場所(例: `Z:\Users\suehara\Documents\python\rz-check`)に`git clone https://github.com/suehara0511/rz.git`する。
- `auto/`配下の`.py`・`.bat`、`CLAUDE.md`、`docs/`を、`analysis`フォルダの対応ファイルと1つずつ突き合わせる(diffツールでも手動でも可)。
  - CLAUDE.mdの記載上は基本一致している前提だが、実ファイルシステムを直接見比べられるのはユーザーの手元のみなので、ここは必ず実施する。
  - 差分があれば(例: root直下の`★*.ipynb`側だけ更新されている等、CLAUDE.mdの「root ipynbとauto/.pyの乖離」と同種の問題)、どちらが正か判断してから次に進む。

### Step 2. .gitignoreの追加調整(リポジトリ側で先に実施可能)
現在`auto/logs/run_*.log`(5ファイル)が初回アップロード時のスナップショットとしてgit管理下にある。`analysis`フォルダが実行フォルダそのものになると、日次実行のたびにこれらが上書きされ続け、`git status`が常に汚れた状態になってしまう。運用ログは追跡対象から外すのが望ましいため、`auto/logs/`を`.gitignore`に追加し、追跡中の5ログファイルは`git rm --cached`する(本コミットで対応済み、§5参照)。

### Step 3. `analysis`フォルダをgit管理下に変換(実際の統合)
- Step 1で作った一時クローンの`.git`フォルダを、そのまま`analysis`フォルダ直下にコピーする(例: `robocopy Z:\...\rz-check\.git Z:\...\analysis\.git /E`)。
- `analysis`フォルダに移動して`git status`を実行。
  - `token.pickle`・`python_ss\credentials.json`・`.venv\`・(Step 2適用後の)ログファイルが「Untracked」または「Ignored」として出るのは正常(そのままでよい)。
  - `auto/*.py`・`docs/`・`CLAUDE.md`などが「変更なし」であればStep 1での差分確認が取れている証拠。
  - もし差分が残っていれば、必要な分だけ`git add`してコミットする。
- `git remote -v`でoriginが正しいURL(`suehara0511/rz`)になっているか確認。

### Step 4. 動作確認
- 統合後、`run_shoki_seisansei.bat`など1つを手動でダブルクリックし、正常終了することを確認する(パスは何も変えていないので通常通り動くはず)。
- 翌朝、タスクスケジューラの自動実行結果(`auto/logs/run_*.log`、Step 2で`.gitignore`化済みなのでgit上は汚れない)を確認する。

### Step 5. 重複解消
- Step 3・4が安定していれば、`Z:\Users\suehara\Documents\GitHub\rz`のクローンは削除してよい(`analysis`が正になったため)。
- 削除前に、`GitHub\rz`側だけにある未push差分がないか`git status`で最終確認する。

## 4. 統合作業とは別立てのフォローアップ課題

- `★BQ-*.py`の`credentials.json`絶対パス(`auto\`が抜けている)の実態確認・修正。実際に`python_ss\credentials.json`(analysis直下)に置かれているのか、`auto\python_ss\credentials.json`に置かれているのか、まず現物を確認する。`token.pickle`同様に相対パス化するか、実態に合わせて`auto\`を補うか判断する。
- `pyproject.toml`/`poetry.lock`がまだ本リポジトリに存在しない。root `.venv`(Poetry管理)の依存関係を再現可能にするため、統合作業のタイミングで`analysis`直下の実体をコミットするのが望ましい。
- `転機ALLデータ更新.py`内に残る古い`C:\Users\suehara\Desktop\お転機BOX\ぱいそん練習\python_ss\credentials.json`パス(4箇所)は現状デッドコードの可能性が高いが、要否の確認・整理は別途。

## 5. ロールバック

Step 3は`.git`フォルダをコピーするだけの操作なので、問題が起きても`analysis\.git`を削除するだけで元の(gitなし)状態に戻せる。タスクスケジューラ・`.bat`のパスは一切変更していないため、それ自体が壊れる心配はない。
