# ローカル2フォルダ統合 移行計画

[CLAUDE.md](../CLAUDE.md)の「既知のTODO」記載、ローカル2フォルダ(`analysis`と`GitHub\rz`)統合の詳細調査・移行手順。2026-08-17、ユーザーがエクスポートしたタスクスケジューラ5タスクのXML(`RZ_run_*_daily`)を元に調査。

## 1. 現状整理

- `Z:\Users\suehara\Documents\python\analysis`: 本来の作業フォルダ。`token.pickle`・`python_ss\credentials.json`・`.venv`が実在。**git管理下にはない**。
- `Z:\Users\suehara\Documents\GitHub\rz`: 本リポジトリ(`suehara0511/rz`)のクローン。認証情報・`.venv`は含まれない。

### Step 0(バックアップ)実行時に判明した`analysis`フォルダの実態(2026-08-17)

ユーザーが取得したrobocopyログから、想定より広範囲のファイルが`analysis`直下に存在することが判明した。

- ルート直下・`yojitu`配下に、候補者・企業の実データを含みうる大容量xlsxファイルが多数(`honkosho.xlsx`32MB、`index.xlsx`6MB、`yomi.xlsx`5MBなど)。
- `_pipeline_cache`配下にparquetキャッシュ。
- `python_ss`フォルダがルート直下・`auto`配下・`yojitu`配下の3箇所に重複(CLAUDE.mdの既存記載と一致)、各々に`credentials.json`・`token.pickle`に加え`token.json`(別形式のトークンファイル、従来の`.gitignore`は未対応だった)。
- ルート直下に`★BQ-*.ipynb`など開発用ノートブック多数(CLAUDE.mdが言及する「本来の開発場所」)。
- `.claude/`フォルダ(Claude Code のローカル設定)。

これを受けて`.gitignore`に`*.xlsx`・`*.parquet`・`~$*`・`token.json`・`_pipeline_cache/`を追加済み(2026-08-17、本ドキュメントの更新と同時にpush)。`git checkout`自体はリポジトリに存在しないファイルには触れないため直ちに危険ではないが、この後`git add -A`のような操作で大容量・機密性の高いファイルが誤って追跡・pushされるのを防ぐための事前対応。

**ノートブックの扱いについてはユーザーに確認済み(2026-08-17)**: セル出力に実データが埋め込まれている可能性を提示した上で、「社内限定運用のため気にせずそのまま含める」との判断。よって`*.ipynb`は`.gitignore`に追加しない。ルート直下・`yojitu`配下のノートブック群は、Step 2(`git checkout`)の後、通常の`git add`でリポジトリに取り込む対象とする。

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

## 3. 移行手順(実行版)

当初案(別フォルダに素クローン→robocopyで手動比較→`.git`だけコピー)は、より単純で安全な方法に差し替えた。**`git checkout`は、チェックアウト先に「内容の異なる同名ファイル」が既に存在すると、何も上書きせずにエラーで止まって該当ファイル一覧を教えてくれる**という安全装置を標準で持っている。これを利用し、`analysis`フォルダの中で直接 `git init` → `git checkout` する形にすることで、手動でのファイル突き合わせ作業を省きつつ、内容ベースでの差分検出(タイムスタンプ比較より確実)を行う。

このリポジトリの`.gitignore`は既に`.venv/`・`token.pickle`・`credentials.json`・`client_secret*.json`・`service_account*.json`・`*.env`・`auto/logs/`を除外設定済み(今回のセッションでpush済み)。これらのファイルはリポジトリのコミット履歴に一切含まれていないため、以下の操作でチェックアウト対象になることはなく、`analysis`直下にそのまま置いたままで問題ない。

### Step 0. 事前バックアップ
PowerShellで(Explorerで手動コピーでも可):
```powershell
robocopy "Z:\Users\suehara\Documents\python\analysis" "Z:\Users\suehara\Documents\python\analysis_backup_20260817" /E /XD .venv
```
保険として、対象5タスクの現状設定もテキストで保存(XMLは既にエクスポート済みなので二重の保険):
```powershell
foreach ($t in "RZ_run_shoki_seisansei_daily","RZ_run_rzkpi_update_daily","RZ_run_seiyaku_tanka_update_daily","RZ_run_eigyo_seisansei_daily","RZ_run_tenki_all_update_daily") {
  schtasks /query /tn $t /v /fo list | Out-File "Z:\Users\suehara\Documents\python\analysis_backup_20260817\$t.txt"
}
```
できれば、日次実行の時間帯(8:00〜8:50頃)を避けて作業する。

### Step 1. `analysis`フォルダ内でgitを初期化し、originのmainを取得
```powershell
cd Z:\Users\suehara\Documents\python\analysis
git init
git remote add origin https://github.com/Suehara0511/rz.git
git fetch origin main
```
この時点ではまだ何もチェックアウトしていない(フォルダの中身は一切変化しない)。

### Step 2. チェックアウトを試みる(=内容ベースの差分確認)
```powershell
git checkout -b main origin/main
```
- **成功した場合**: `analysis`の実ファイルは、リポジトリに記録されている内容と完全に一致していたということ。これで`analysis`はそのまま`origin/main`を追跡する通常のgit working treeになる。作業内容を変えず、そのままStep 3へ。
- **`error: The following untracked working tree files would be overwritten by checkout:` のようなエラーで止まった場合**: 一覧に出たファイルだけ、実ファイルの内容がリポジトリ側と食い違っている。何も書き換わっていないので安全に対処できる。ファイルごとに:
  1. `git show origin/main:<相対パス>` でリポジトリ側の内容を確認し、ローカルの実ファイルと見比べる。
  2. リポジトリ側が正しければ、該当ファイルを一時退避(例: `xxx.py.local-bak`にリネーム)してから再度 `git checkout -b main origin/main` を実行する。
  3. ローカル側(analysis実体)が正しければ、同様に一時退避→チェックアウト成功後、退避したファイルの中身を戻す(`git status`で「modified」と出るはずなので、内容を確認の上 `git add` → `git commit` してリポジトリ側にも反映する)。
  - 想定される衝突箇所: CLAUDE.mdに記載のある「root ipynbとauto/.pyの乖離」と同種のもの(auto配下の`.py`がanalysis側でだけ更新されている等)。

### Step 3. 状態の確認

```powershell
git status
git status --ignored
git remote -v
```

- `auto/*.py`・`docs/`・`CLAUDE.md`・`.gitignore`など、既存リポジトリに記録済みのファイルについては、変更なしで表示されること(差分があればStep 2の対処が必要)。
- 一方、**`git status`は「nothing to commit, working tree clean」にはならない**。§1.5で判明した通り、`analysis`にはまだ一度もリポジトリにコミットされていないファイル(ルート・`yojitu`配下のノートブック群、`pyproject.toml`・`poetry.lock`、`.claude/`など)が多数あり、これらは「Untracked files」としてずらっと表示されるのが正常。
- `git status --ignored`で、`token.pickle`・`token.json`・`credentials.json`・`.venv\`・`*.xlsx`・`*.parquet`・`auto\logs\*.log`が「Ignored files」として出ていること(除外設定が効いている確認)。
- `git remote -v`でoriginが`https://github.com/Suehara0511/rz`になっていること。

### Step 4. 新規ファイルの取り込み(この統合で初めてgit管理下に置くもの)

**ここで`git add -A`のような一括追加はしない。** Untracked filesの一覧を見て、意図したものだけを個別に(またはフォルダ単位で)`git add`する。

- 追加してよいもの(既知のTODOにも合致):
  ```powershell
  git add pyproject.toml poetry.lock
  ```
- ノートブック(§1.5でユーザー確認済み、社内限定運用のためそのまま含める方針):
  ```powershell
  git add "★BQ-RZKPI更新.ipynb" "★BQ-RZKPI更新　年収付加.ipynb" "★BQ-SMAP候補者抽出.ipynb" "★BQ-アンタッチャ.ipynb" "★BQ-初期交渉からの生産性.ipynb" "★BQ-営業生産性.ipynb" "★BQ-成約単価更新.ipynb" "★BQ-転機ALLデータ更新.ipynb" "★RZデータ抽出.ipynb" "★事業予測モデル.ipynb" "★自社Sデータ更新.ipynb"
  git add yojitu/
  ```
  (`.bak`・`.backup.ipynb`サフィックスのファイルも、変更前バックアップとして残す運用なのでそのまま追加してよい。`.ipynb_checkpoints/`・`__pycache__/`は`.gitignore`済みなので追加対象に出てこない。)
- `.claude/`(このセッションのClaude Code設定)は、`settings.local.json`の中身を確認し、秘匿情報が含まれていないことを確認してから要否を判断する(必須ではない)。
- 追加した後、忘れず:
  ```powershell
  git status
  git commit -m "analysisフォルダ実体をgit管理下に追加(pyproject.toml/poetry.lock, 開発用ノートブック, yojitu)"
  git push -u origin main
  ```
- **迷ったら一旦保留してよい**。今回の統合の必須条件は「タスクスケジューラ・batが壊れないこと」であり、ノートブック等の取り込みは同じタイミングでなくても後日まとめて行える。

### Step 5. 動作確認
- `run_shoki_seisansei.bat`など1つを手動でダブルクリックし、正常終了することを確認する(パスは何も変えていないので通常通り動くはず)。
- 翌朝、タスクスケジューラの自動実行結果(`auto/logs/run_*.log`、`.gitignore`化済みなのでgit上は汚れない)を確認する。

### Step 6. 重複解消
- Step 4・5が安定していれば、`Z:\Users\suehara\Documents\GitHub\rz`のクローンは削除してよい(`analysis`が正になったため)。
- 削除前に、`GitHub\rz`側だけにある未push差分がないか`git status`で最終確認する。

## 4. 統合作業とは別立てのフォローアップ課題

- `★BQ-*.py`の`credentials.json`絶対パス(`auto\`が抜けている)の実態確認・修正。実際に`python_ss\credentials.json`(analysis直下)に置かれているのか、`auto\python_ss\credentials.json`に置かれているのか、まず現物を確認する。`token.pickle`同様に相対パス化するか、実態に合わせて`auto\`を補うか判断する。
- `転機ALLデータ更新.py`内に残る古い`C:\Users\suehara\Desktop\お転機BOX\ぱいそん練習\python_ss\credentials.json`パス(4箇所)は現状デッドコードの可能性が高いが、要否の確認・整理は別途。
- (2026-08-17解決)`pyproject.toml`/`poetry.lock`未コミットの件はStep 4に組み込み済み。

## 5. ロールバック

Step 2で`git checkout`が失敗している間は、`analysis`フォルダの実ファイルは一切変更されていない(`.git`フォルダが増えているだけ)。取りやめる場合は単純に`.git`フォルダを削除すれば元の(gitなし)状態に戻る。
```powershell
Remove-Item -Recurse -Force "Z:\Users\suehara\Documents\python\analysis\.git"
```
チェックアウト成功後であっても、タスクスケジューラ・`.bat`のパスは一切変更していないため、それ自体が壊れる心配はない。
