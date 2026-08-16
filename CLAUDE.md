# CLAUDE.md

## このリポジトリについて

株式会社ロンザン(シニアエグゼクティブ層のスカウト・ヘッドハンティング事業)の経営企画業務を自動化するためのコード群。役割は「企業開拓」と「候補者集客」の2軸KPIについて事業計画を作成し、スプレッドシートで予実管理を行い、計画未達KPIの原因を仮説立てて経営陣へ提言すること。

事業構造・組織・KPIファネルの定義は [docs/business-structure.md](docs/business-structure.md) を参照。経営会議の議事録から抽出した内容であり、KPI悪化の原因仮説を立てる際の背景知識として使う(特に「本当の業務悪化」か「集計ロジック・締め日の違いによる見かけ上のズレ」かを切り分ける視点)。転機(候補者集客チャネルの1つ、WEB広告運用)側のKPI体系は取得できておらずTODO(6章参照)。

現場の業務手順(初期交渉・再交渉・マッチングなどの実施マニュアル)は [docs/manuals/](docs/manuals/) 配下に、社内ポータル「ロンザンポータル」(Google Sites)の内容を1トピック1ファイルの形で蓄積している(現状: [初期交渉](docs/manuals/初期交渉.md)、[マッチング/再交渉のポイント割り振りルール](docs/manuals/マッチング_再交渉.md))。KPIのどのステップが崩れているかを具体的な業務手順・ポイント配分ルールのレベルで仮説立てる際に参照する。ロンザンポータル自体はGoogle Sitesで社内限定公開のため直接クロールはできず(認証なしのWebFetchはログイン画面にリダイレクトされ、認証済みのGoogle Drive連携でもSitesのファイル形式は非対応)、ユーザーからページ本文やリンク先のドキュメント/スプレッドシートのURLを個別に共有してもらう形で蓄積している。

## 現在の作業フロー

1. BigQueryでローデータを抽出する
2. スプレッドシートにローデータを出力し、スプレッドシート関数で集計する
3. 場合により、BigQueryから取得したデータをPythonで加工してからスプレッドシートにローデータとして出力し、その後はスプレッドシート関数で集計する

これらの自動化が目的。作業対象のスプレッドシートはローカルではなく基本的にGoogle Drive上にある。

## 環境構成

- 依存管理はルートの `pyproject.toml`(Poetry)。`.venv` がルートに存在。
- `auto/` 配下には本番運用中のBigQuery連携ノートブック(`★BQ-*.ipynb`)とそれをスクリプト化した同名 `.py` があり、独自の `auto/.venv` を持つ(ルートの venv とは別環境。pyproject.toml はauto/にはないので依存関係の一元管理はされていない点に注意)。
- ルート直下の `★*.ipynb` は開発中/個別分析用のノートブック。`.backup.ipynb` / `.bak` サフィックスのファイルは変更前のバックアップなので、削除や上書きをする前に必ず内容を確認する。

## 自動化パイプライン(auto/)

`auto/` 配下の各 `★BQ-*.py` を、手動でのセル実行から「1コマンド/1クリックで完結」させる形に整備していく。現在の方針・注意点は以下の通り。

- **root ipynbとauto/.pyの乖離に注意**: root直下の `★BQ-*.ipynb` が実際の開発・改修が行われる場所で、`auto/★BQ-*.py` はそれを元にしたスクリプト版だが、**自動で同期される仕組みはなく手動コピーのため乖離しうる**。実績として、2026/08時点で `★BQ-初期交渉からの生産性` は、root ipynb側だけが後日リファクタリング(重複認証コードの削除・関数化・BigQueryクライアントの使い回し等)されており、auto/.pyは数週間分古いままだった。**auto/配下のパイプラインに手を入れる前に、必ずroot直下に対応するipynbがないか、あればどちらが新しいか(更新日時・内容diff)を確認すること。**
- **実行環境はrootの`.venv`(Poetry管理)に統一していく方針**。`auto/.venv` は過去の実行環境として残っているが、新規/更新したパイプラインはroot `.venv` から実行する。
- **1クリック実行**: `auto/run_<パイプライン名>.bat` を用意し、ダブルクリックで `cd /d auto\` → root `.venv` のpythonで対応する `.py` を実行、という形にする(token.pickle・python_ssパッケージの相対パス解決のため、実行時のカレントディレクトリは必ず `auto/` にする)。
- **.batファイル名・内容は必ずASCII文字のみにする(重要)**: `★BQ-*.py` のような日本語ファイル名を `.bat` ファイルの中に直接書くと、cmd.exeがバッチファイルを規定のANSIコードページ(日本語版Windowsでは932=Shift-JIS)で読み込むため、UTF-8で保存された日本語部分が文字化けし、「指定されたパスが見つかりません」等のエラーになる(`chcp 65001` を先頭に追加しても解消しないことを確認済み、2026-08-14)。回避策として、`.bat` からは日本語を含まないASCII名の中継用Pythonスクリプト(例: `run_shoki_seisansei.py`。中身は `runpy.run_path("★BQ-....py")` のように日本語ファイル名をPythonの文字列リテラルとして持つ)を呼び出す構成にする。Pythonのソースコードは既定でUTF-8として読まれるため、コンソールのコードページに左右されず日本語ファイル名を正しく扱える。

**現状(2026-08-14時点で5パイプラインすべて1コマンド化対応済み)**:

| パイプライン | root ipynbとauto/.pyの乖離 | ランチャー(ダブルクリック対象) | 実行確認 |
|---|---|---|---|
| 初期交渉からの生産性 | 乖離あり→auto/.py再生成済み | [auto/run_shoki_seisansei.bat](auto/run_shoki_seisansei.bat) | ✅ 本番4シート(shoki/hon/hon_nin/hon_sha)への書き込みまで確認済み |
| RZKPI更新 | 実質一致(差分なし) | [auto/run_rzkpi_update.bat](auto/run_rzkpi_update.bat) | 構文チェックのみ、未実行 |
| 成約単価更新 | 完全一致 | [auto/run_seiyaku_tanka_update.bat](auto/run_seiyaku_tanka_update.bat) | 構文チェックのみ、未実行 |
| 営業生産性 | 乖離あり→auto/.py再生成済み(不要な認証取得コード削除、BigQueryクライアント使い回し、ヘルパー関数化などroot ipynb側の整理を反映) | [auto/run_eigyo_seisansei.bat](auto/run_eigyo_seisansei.bat) | 構文チェックのみ、未実行 |
| 転機ALLデータ更新 | 完全一致 | [auto/run_tenki_all_update.bat](auto/run_tenki_all_update.bat) | 構文チェックのみ、未実行 |

2026-08-14に5パイプラインすべて、ユーザーが手元で`run_*.bat`をダブルクリックして実行し、問題なく更新されることを確認済み。

### スケジュール実行(Windows タスクスケジューラ)

5パイプラインとも、Windowsタスクスケジューラで毎日自動実行するよう登録済み(2026-08-14)。

- **トリガー**: 毎日、8:00から10分間隔で5つを順次実行(BigQuery/Sheets APIのレート制限回避のため同時実行を避けている)
- **実行条件**: 「ログオン中のみ実行」(`Logon Mode: Interactive only`)。PCがログオフ/スリープ中は実行されない
- **実行対象**: 手動実行用の`run_*.bat`(`pause`で結果表示のまま待機する)とは別に、無人実行用の`run_*_scheduled.bat`(`pause`なし、標準出力・エラーを`auto/logs/run_*.log`にリダイレクト)を作成し、こちらをタスクに登録している。**手動実行用の`.bat`をそのままタスクスケジューラに登録すると`pause`でキー入力待ちのまま止まってしまうため、必ず`_scheduled.bat`版を使うこと。**

| タスク名 | 実行時刻 | 対象 |
|---|---|---|
| RZ_run_shoki_seisansei_daily | 8:00 | 初期交渉からの生産性 |
| RZ_run_rzkpi_update_daily | 8:10 | RZKPI更新 |
| RZ_run_seiyaku_tanka_update_daily | 8:20 | 成約単価更新 |
| RZ_run_eigyo_seisansei_daily | 8:30 | 営業生産性 |
| RZ_run_tenki_all_update_daily | 8:40 | 転機ALLデータ更新 |

確認・変更・削除は `schtasks /query /tn "<タスク名>" /v /fo list` / `schtasks /delete /tn "<タスク名>" /f`、またはWindows標準の「タスクスケジューラ」GUIから行う。実行結果は各タスク実行後に `auto/logs/run_*.log` で確認できる(次回実行時に上書きされるので、失敗した場合はその日のうちに確認すること)。

## Google Sheets/Driveとの連携

作業対象がGoogle Drive上にあっても、以下の2つの経路を使い分けることで読み書き・数式の検査/修正まで対応できる。

### 経路A: 既存のPython + Google Sheets API(数式の読み書きが必要な作業はこちら)

`auto/python_ss/python_ss.py` に、OAuth(`token.pickle`、InstalledAppFlow)経由でSheets API v4に接続するヘルパーがある。

- `get_ss` / `get_ss_some`: 指定範囲の値を取得。第4引数 `value_render_option` で `'FORMATTED_VALUE'`(既定、表示上の計算済み値)/ `'UNFORMATTED_VALUE'` / `'FORMULA'`(セルの数式そのもの、例: `"=SUM(A1:A10)"`) を切り替えられる(2026-08-14実装、root/auto/yojituの3箇所にある`python_ss.py`すべてに同一変更を反映済み)。既存の呼び出し元は引数省略時の既定値が従来と同じ計算済み値のため影響を受けない。数式の検証・修正を行う際は `value_render_option='FORMULA'` で読み取り、`update_ss` で修正後の数式文字列(`"=..."`)を書き込む。
- `update_ss`: `valueInputOption="USER_ENTERED"` で書き込むため、文字列で `"=SUM(...)"` のように渡せばSheets側で数式として解釈される。既存の数式を修正する用途にそのまま使える。
- `insert_ss`: 行追加

このtoken.pickleはSheets APIのスコープのみで発行されている。Google Docsなど別APIを読み書きしたい場合は、この既存の認証情報を流用せず、別のtoken/認証情報を発行して使うこと(本番のBigQuery連携パイプラインに影響を与えないため)。

### 経路B: Claude Code接続のGoogle Driveコネクタ(調査・下読み用途、書き込み不可)

`search_files` / `read_file_content` / `download_file_content` などが使えるが、**既存ファイルの中身を直接更新する機能はない**(読み取り・コピー・新規作成のみ)。また、数百KBを超える大きめのGoogleドキュメントは `read_file_content` / `download_file_content` の両方が高確率でタイムアウトする(実績: 831KBのドキュメントで、text/plain・PDFエクスポートともに計7回試行して全滅)。この経路は「小〜中規模ファイルの内容確認」「ファイル一覧の把握」に限定して使い、実際の修正・大容量ファイルの全文取得は経路Aのローカル実行に切り替える。

## 既知のTODO

- 転機(候補者集客チャネル)MTGの議事録(Google Docs、831KB、複数回分の生VTTが1ドキュメントに連結)は経路Bでは取得不可。経路A方式(ローカルPython + Docs API、新規スコープでの認証)での取得を検討中。取得できたら `docs/tenki-kpi.md` を作成し、本ファイルから参照を追加する。
