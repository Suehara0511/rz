# %%
import ast
import datetime

import numpy as np
import pandas as pd

import db_dtypes  # BigQueryのDATE/TIME列をpandasで扱うために必要(直接は使わない)
from google.cloud import bigquery
from google.cloud import secretmanager
from google.oauth2 import service_account

import python_ss.python_ss as ps

pd.set_option('display.max_rows', 50)
pd.set_option('display.max_columns', None)


# %%
def access_secret_version(project_id, secret_id, version_id='latest'):
    client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    return ast.literal_eval(payload)


# %%
# BigQuery / スプレッドシートの認証はここで1回だけ行い、以降すべてのセルで再利用する。
# (以前は各セクションで get_auth() / bigquery.Client() を都度呼び直しており、
#  OAuth・API discoveryの通信が発生する分だけ無駄に時間がかかっていた)
credentials = service_account.Credentials.from_service_account_info(
    access_secret_version('r-group-bigdata', 'CREDENTIALS_SECRET_KEY_WORKER'),
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
bq_client = bigquery.Client(credentials=credentials, project=credentials.project_id)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"Z:\Users\suehara\Documents\python\analysis\python_ss\credentials.json"
service = ps.get_auth(SCOPES, json_path)


# %%
# 書き込み先スプレッドシートID(通知先マスタ)。IDを各セルに直書きすると同じIDが
# 何十回も重複するので、ここに集約する。
SS_LINE_ADMASTER = '14vXxjcdlyY463QjrtEnCw7pJ0oLStXZD8Q42IdW2Zd4'   # 候補者マスタ/広告費の取得元
SS_NEO = '1Mvqe8nLhdiT9acCMA4cP-4MH5X4GmYPiC9OSqHTEHtk'             # 成約単価管理表【NEO】
SS_NM = '1d1uYQMCIhJGMlUe4S8m56Bd_ZS4_V-FUEtPjUlgpn9Y'              # 成約単価管理表【NM】
SS_ZEALS = '1EglGY_Lf1kvHqZTpow4F2ksD20xD9J8G1oaMIjtyj78'           # 成約単価管理表【ZEALS】
SS_CA = '1fVbpOYwIRsbW69EDsbJlTJwJVPTexi8RoMd3ahiO-IA'              # 成約単価管理表【CA】
SS_YOMIHYO = '1qtTngN03WSZ_JjZovhNVh6bd1uc_Eh8tRP5Hp9yWSNc'         # 読み表(成約データ取得元)
SS_NM_SUMMARY = '1YRjsfJ76yfAnhoyTlsvcXVKZhmmcvkNwpApf9iubByc'      # NMサマリー/データセット1
SS_GAX = '1JxBS0dT8nR_o_ehqVdlKYx3iD1jEMIaQPXWl6wJIXJk'             # GAX手上げデータ


# %%
def to_sheet_values(df, date_cols=None):
    """DataFrameをスプレッドシート書き込み用の list-of-lists に変換する共通処理。

    以前は各セクションで
      ・inf -> NaN -> fillna('') -> values.tolist()
      ・マージ後に文字列化された 'NaN' / 'None' / 'NaT' / '<NA>' の個別カラムごとの str.replace
    をほぼ同じ形でコピペしていたのを1関数に集約した。
    """
    df = df.copy()
    for col in date_cols or []:
        df[col] = df[col].astype(str)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna('')
    df = df.replace(['NaN', 'None', 'NaT', '<NA>'], '')
    return df.values.tolist()


def write_to_sheets(data, targets, service):
    """同じデータを複数の (spreadsheet_id, range_name) へ書き込む共通処理。"""
    for spreadsheet_id, range_name in targets:
        ps.update_ss(spreadsheet_id, range_name, data, service)


def find_row_index(df, id_col, target_id):
    """id_col が target_id と一致する行の「シート上の行番号(1始まり)」を返す。見つからなければNone。"""
    matches = df[df[id_col] == target_id].index
    return int(matches[0]) + 1 if len(matches) > 0 else None


# %% [markdown]
# ## 広告情報取得

# %%
# 候補者マスタを取得(このデータは後続の複数セクションで使い回す)
RANGE_NAME = '候補者マスタ!A:M'
adinfo = ps.get_ss(SS_LINE_ADMASTER, RANGE_NAME, service)


# %%
# 【主要媒体別】成約単価管理表【NEO/NM/ZEALS】にコピペ
adinfoA = adinfo.copy()
adinfoA_values = to_sheet_values(adinfoA)

write_to_sheets(adinfoA_values, [
    (SS_NEO, 'user!A2'),
    (SS_NM, 'user!A2'),
    (SS_ZEALS, 'user!A2'),
], service)


# %% [markdown]
# ## 広告費

# %%
# LINE広告費を取得する
RANGE_NAME = '広告費!A:T'
adcost = ps.get_ss(SS_LINE_ADMASTER, RANGE_NAME, service)
adcost_nm = adcost.copy()
adcost_nm_values = to_sheet_values(adcost_nm)


# %%
# LINE/NM/CAシートへコピペ
write_to_sheets(adcost_nm_values, [
    (SS_ZEALS, '広告費!A2'),
    (SS_NM, 'adcost!A2'),
    (SS_CA, '広告費!A2'),
], service)


# %% [markdown]
# ## 初期交渉情報取得

# %%
rzshokikosho_query = """
WITH
-- ステップ1: 必要なテーブルをJOINし、各レコードの基本情報を計算
base_data AS (
  SELECT
    s.kohosha_id,
    k.tenki_id,
    s.kosho_setteibi,
    s.kosho_yoteibi,
    s.kosho_jisshibi,
    s.kosho_seq,
    s.cxl_riyu,
    -- APsource: 複数の名称を'その他'にまとめるなど、カテゴリを整形
    CASE
      WHEN consts1.name IN ('HP反響', '上場企業役員DM', 'Gアポ') THEN 'その他'
      WHEN consts1.name = '社外取締役名鑑　候補者' THEN '顧問名鑑登録　解放者'
      ELSE consts1.name
    END AS APsource,
    syi2.sei_plus AS ap_kakutokusha,
    -- 面談担当者: syainテーブルに存在すればsei_plusを、なければ元のIDを使用
    COALESCE(syi1.sei_plus, s.mendan_tanto) AS mendan_tanto,
    -- 実施ステータス: フラグ値などを元に分かりやすい文字列に変換
    CASE
      WHEN s.kosho_yoteibi >= CURRENT_DATE('Asia/Tokyo') THEN '実施前'
      WHEN s.jisshi_flag = 2 AND s.deleted = 2 THEN 'CXL'
      WHEN s.jisshi_flag = 0 AND s.deleted = 0 AND s.nittei_chosei = 1 THEN '日程調整中'
      WHEN s.jisshi_flag = 1 THEN '実施'
      WHEN s.jisshi_flag = 0 THEN '未報告'
      ELSE CAST(s.jisshi_flag AS STRING)
    END AS jisshi,
    -- 移籍意欲: 新しい値があれば優先し、なければ古い値を使用
    COALESCE(consts2.name, consts3.name) AS iseki_iyoku,
    -- 前回実施日からの経過日数: LAG関数で候補者ごとに前回交渉の実施日を取得して計算
    DATE_DIFF(s.kosho_setteibi, LAG(s.kosho_jisshibi) OVER (PARTITION BY s.kohosha_id ORDER BY s.kosho_jisshibi), DAY) AS keikabi
  FROM
    `r-group-bigdata..live_rhs.shokikoshos` AS s
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS k ON s.kohosha_id = k.id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON s.mendan_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON s.ap_kakutoku = syi2.user_id
    -- sys_constsテーブルへのJOINを最適化。必要なgroup_codeごとにJOINを分ける
    LEFT JOIN `r-group-bigdata.live_rhs.sys_consts` AS consts1 ON s.ap_source = consts1.code AND consts1.group_code = 19
    LEFT JOIN `r-group-bigdata.live_rhs.sys_consts` AS consts2 ON k.iseki_iyoku_new = consts2.code AND consts2.group_code = 5100
    LEFT JOIN `r-group-bigdata.live_rhs.sys_consts` AS consts3 ON s.iseki_iyoku = consts3.code AND consts3.group_code = 5100
),

-- ステップ2: ステップ1で計算したAPsourceを元に、前回からの変更を検知
final_data AS (
  SELECT
    *,
    -- APsourceが前回から変更されたかのフラグを計算
    CASE
      -- LAG関数で取得した1つ前のAPsourceと比較
      WHEN APsource != LAG(APsource) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) THEN 1
      ELSE 0
    END AS APS_change
  FROM
    base_data
)

-- 最終的なアウトプット: 必要なカラムを選択し、最終的なフラグを計算
SELECT
  kohosha_id,
  tenki_id,
  APsource,
  ap_kakutokusha,
  mendan_tanto,
  kosho_setteibi,
  kosho_yoteibi,
  kosho_jisshibi,
  jisshi,
  kosho_seq,
  APS_change,
  -- 再フラグ: 複数の条件に基づいてフラグを立てる
  CASE
    WHEN kosho_seq = 1 THEN 1       -- 最初の交渉
    WHEN APS_change = 1 THEN 1     -- APsourceが変更された場合
    WHEN keikabi > 90 THEN 2       -- 前回の交渉から90日以上経過した場合
    ELSE 0
  END AS sai_flg,
  cxl_riyu,
  iseki_iyoku
FROM
  final_data
WHERE
  -- 元のクエリと同じフィルタ条件
  APsource = '転機社長名鑑'
  AND kosho_setteibi >= DATE '2019-09-30'
ORDER BY
  kosho_setteibi ASC;
"""

rzshokikosho = bq_client.query(rzshokikosho_query).result().to_dataframe()


# %%
adinfoB = adinfo.copy().rename(columns={"ID": "tenki_id"})
rzshokikosho["tenki_id"] = rzshokikosho["tenki_id"].astype(str)
shokikosho = pd.merge(rzshokikosho, adinfoB, on="tenki_id", how="left")

shokikosho = shokikosho[['tenki_id', '登録日時', 'kosho_setteibi', 'kosho_jisshibi',
                          '参照元/メディア', 'キャンペーン', '広告ID', 'KWD', 'sai_flg']]
shokikosho = shokikosho.sort_values(by='kosho_setteibi')
shokikosho_values = to_sheet_values(shokikosho, date_cols=['kosho_setteibi', 'kosho_jisshibi'])


# %%
# NEO/ZEALS/CAのシートにコピペ(NMシートは対象外)
write_to_sheets(shokikosho_values, [
    (SS_NEO, 'rzdata!A3'),
    (SS_ZEALS, 'rzdata!A3'),
    (SS_CA, 'data!A3'),
], service)


# %% [markdown]
# ## 本交渉情報取得

# %%
rzhonkosho_query = """
with HONS as (
with SHOKIS as (
with shoki_base3 as (
with shoki_base2 as (
with shoki_base as (
SELECT
  shk.id,
  shk.tenki_id,
  shk.kohosha_id,
  shk.ap_source,
  layer.name as layer,
  shk.annual_income,
  CASE WHEN syi1.sei_plus IS NULL THEN shk.mendan_tanto
       ELSE syi1.sei_plus END AS mendan_tanto,
  syi2.sei_plus AS ap_kakutokusha,
  shk.kosho_setteibi,
  shk.kosho_yoteibi,
  shk.kosho_jisshibi,
  shk.kosho_seq,
  shk.saikosho_kaisu,
  saikosho_seq,
  valid_flag,
  shk.initial_contact_date,
  DATE_DIFF(shk.kosho_setteibi, LAG(shk.kosho_jisshibi) OVER (PARTITION BY shk.kohosha_id ORDER BY shk.kosho_jisshibi), DAY) AS keikabi
FROM (
  SELECT *,
    FIRST_VALUE(kosho_jisshibi IGNORE NULLS) OVER (PARTITION BY kohosha_id ORDER BY kosho_jisshibi) AS initial_contact_date
  FROM `r-group-bigdata.live_rhs.shokikoshos`
) shk
LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` koho ON shk.kohosha_id = koho.id
LEFT JOIN `r-group-bigdata.live_company.syain` syi1 ON shk.mendan_tanto = syi1.user_id
LEFT JOIN `r-group-bigdata.live_company.syain` syi2 ON shk.ap_kakutoku = syi2.user_id
LEFT JOIN (SELECT
    code,
    name
  FROM `r-group-bigdata.live_rhs.sys_consts`
  WHERE group_code = 19) consts ON shk.ap_source = consts.code
left join (SELECT
            group_code,
             code,
             name
            FROM `r-group-bigdata.live_rhs.sys_consts`
            where group_code = 25) layer on shk.max_bushoyakushoku = layer.code
ORDER BY shk.kosho_setteibi
)

  select *,
    LAG(ap_source) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) AS prev_APsource,
  from shoki_base)

  select *,
   CASE WHEN ap_source != prev_APsource THEN 1 ELSE 0
        END AS APS_change
  from shoki_base2)

  select *,
  case when kosho_seq = 1 then 1
        when APS_change = 1 then 1
        when keikabi > 90 then 2
        else 0 end as sai_flg
  from shoki_base3
  order by kosho_setteibi desc
)

SELECT
  hon.id as honkosho_id,
  hon.anken_id as anken_id,
  an.kohosha_id as kohosha_id,
  koho.tenki_id,
  an.linked_shokikosho_id,
  kgy.tsr_code as tsr_code,
  kgy.name,
  case when consts.name is null then consts2.name
       else consts.name end as AP_source,
  shoki.annual_income,
  shoki.layer,
  initial_contact_date,
  format_date('%Y/%m/%d',shoki.kosho_setteibi) as shoki_setteibi,
  format_date('%Y/%m/%d',shoki.kosho_jisshibi) as shoki_jisshibi,
  format_date('%Y/%m/%d',hon.kosho_setteibi) as hon_setteibi,
  format_date('%Y/%m/%d',hon.kosho_yoteibi) as hon_yoteibi,
  format_date('%Y/%m/%d',hon.kosho_jisshibi) as hon_jisshibi,
  case when syi1.sei_plus is null then hon.kohosha_tanto
  else syi1.sei_plus end as kohosha_tanto,
  syi2.sei_plus as kigyo_tanto,
  hon.kosho_seq as hon_seq,
  shoki.kosho_seq,
  shoki.sai_flg,
  DATE_DIFF(hon.kosho_setteibi, shoki.kosho_jisshibi, DAY) as jisshibi_sa,
  yomi.name as yomi,
  case when yomi2.name is null then yomi.name
       when yomi2.name = yomi.name then yomi2.name
       else yomi2.name end as yomi_final,
  ROUND(tokikessan_uriagedaka/100000,0)as URIAGE,
  consts3.name as yakushoku_class,
  first_mendan.mendan_tanto as first_mendan_tanto
FROM `r-group-bigdata.live_rhs.honkoshos` hon
LEFT JOIN `r-group-bigdata.live_rhs.ankens` an on hon.anken_id = an.id
left join (with yomis_base as (
           SELECT *,
           row_number() over (partition by anken_id order by yomi_torokubi desc) as rn
           FROM `r-group-bigdata.live_rhs.honkosho_yomis`)
           select *
          from yomis_base
          where rn = 1) yomis on an.id = yomis.anken_id
LEFT JOIN SHOKIS shoki on an.linked_shokikosho_id = shoki.id
LEFT JOIN `r-group-bigdata.live_rhs.kigyos` kgy on an.kigyo_id = kgy.id
left join `r-group-bigdata.tsr.company_info` tsr on kgy.tsr_code = tsr.tsr_code
LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` koho on an.kohosha_id = koho.id
LEFT JOIN `r-group-bigdata.live_company.syain` syi1 on hon.kohosha_tanto = syi1.user_id
LEFT JOIN `r-group-bigdata.live_company.syain` syi2 on an.kigyo_tanto = syi2.user_id
left join (select
              shoki.id,
              shoki.kohosha_id,
              case when syi3.sei_plus is null then shoki.mendan_tanto
                   else syi3.sei_plus end as mendan_tanto,
              shoki.kosho_jisshibi
             from `r-group-bigdata.live_rhs.shokikoshos` shoki
             left join `r-group-bigdata.live_company.syain` syi3 on shoki.mendan_tanto = syi3.user_id
             where kosho_seq = 1) first_mendan on an.kohosha_id = first_mendan.kohosha_id
LEFT JOIN (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts`
             where group_code = 19) consts on shoki.ap_source = consts.code
LEFT JOIN (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts`
             where group_code = 19) consts2 on koho.ap_source = consts2.code
left join (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts`
             where group_code = 9) yomi on hon.yomi = yomi.code
left join (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts`
             where group_code = 9) yomi2 on yomis.yomi = yomi2.code
left join (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts`
             where group_code = 10) consts3 on hon.yakushoku_class = consts3.code
-- where hon.kosho_seq = 1
)

select *,
  case when AP_source = '転機社長名鑑' then '転機'
       when AP_source = '人事部経由' then '人事部紹介'
       when AP_source = '顧問名鑑登録　解放者' then '顧問名鑑登録者'
       when AP_source = 'HP反響' then 'その他'
       when AP_source = '上場企業役員DM' then 'その他'
       when AP_source = '社外取締役名鑑　候補者' then '顧問名鑑登録者'
       when AP_source = 'Gアポ' then 'その他'
       else AP_source end as APsource,

  case when shoki_jisshibi is null then 2
       when jisshibi_sa > 90 then 2
       else sai_flg end as sai_flg2
from HONS
where AP_source = "転機社長名鑑"
-- and hon_setteibi >= "2025/03/27"
order by anken_id
"""
honkosho = bq_client.query(rzhonkosho_query).result().to_dataframe()


# %%
honkosho["tenki_id"] = honkosho["tenki_id"].astype(str)
honkosho = pd.merge(honkosho, adinfoB, how="left", on="tenki_id")
honkosho = honkosho[["tenki_id", "登録日時", "hon_setteibi", "hon_jisshibi",
                      "参照元/メディア", "キャンペーン", "広告ID", "KWD", "sai_flg2"]]
honkosho_values = to_sheet_values(honkosho)


# %%
# 成約単価シート(NEO/NM/ZEALS/CA)にコピペ
write_to_sheets(honkosho_values, [
    (SS_NEO, 'rzdata!J3'),
    (SS_NM, 'rzdata!J3'),
    (SS_ZEALS, 'rzdata!J3'),
    (SS_CA, 'data!J3'),
], service)


# %% [markdown]
# ## SCKPI

# %%
sckpi_query = """
WITH
-- =================================================================
-- データ結合と基本加工セクション
-- 必要なテーブルを結合し、基本的なカラムを計算する
-- =================================================================
base_data AS (
  SELECT
    rc.tenki_id,
    can.ap_kakutoku AS shokikosho_setteibi,
    rc.first_nmen_date AS first_jisshi_date,
    can.nmen_zisshi AS shokikosho_jisshibi,
    -- COALESCE関数を使い、繰り返しが多いCASE文を簡潔に書き換え
    COALESCE(
      com.settei8, com.settei7, com.settei6, com.settei5,
      com.settei4, com.settei3, com.settei2, com.settei1
    ) AS honkosho_setteibi,
    COALESCE(
      com.zisshi8, com.zisshi7, com.zisshi6, com.zisshi5,
      com.zisshi4, com.zisshi3, com.zisshi2, com.zisshi1
    ) AS honkosho_jissibi,
    com.seiyaku,
    can.kouhosya_tantou AS kohosha_tanto,
    can.client_tantou AS kigyo_tanto,
    can.mendan_tantou AS mendan_tanto,
    can.ap_source,
    CASE
      WHEN can.zisshi LIKE 'キャンセル%' THEN 'CXL'
      WHEN can.zisshi LIKE '%実施%' THEN '実施'
      ELSE '-'
    END AS CXL_status
  FROM
    `r-group-bigdata.live_sugarcrm52.rc_race_candidate_management` AS rc
    LEFT JOIN `r-group-bigdata.live_saltcrm.candidate` AS can ON can.sugarid = rc.candidate_no
    LEFT JOIN `r-group-bigdata.live_saltcrm.company` AS com ON com.candidate_id = can.id
  WHERE
    rc.tenki_id IS NOT NULL
    AND rc.deleted = 0
)

-- =================================================================
-- 最終的な集計と出力
-- ウィンドウ関数を用いて登場回数をカウントする
-- =================================================================
SELECT
  *,
  -- tenki_idごとに、shokikosho_setteibi(設定日)の昇順で登場回数をカウント
  ROW_NUMBER() OVER (PARTITION BY tenki_id ORDER BY shokikosho_setteibi) AS sai_flg
FROM
  base_data
where shokikosho_setteibi >= "2019-10-01"
and (ap_source = "転機" or ap_source = "マッチング")
ORDER BY
  shokikosho_setteibi;

"""
sckpi = bq_client.query(sckpi_query).result().to_dataframe()


# %%
adinfoC = adinfo.copy()
adinfoC = adinfoC.query('フリ先 == "レイノス"')
adinfoC = adinfoC[["tenki_id", "登録日時", "フリ先", "手上げ日付", "参照元/メディア", "キャンペーン", "広告ID", "KWD"]]

# tenki_idはマージのキーになるため、マージ前に文字列型へ揃える
sckpi["tenki_id"] = sckpi["tenki_id"].astype(str)
sckpi = pd.merge(sckpi, adinfoC, how="left", on="tenki_id")


# %%
sckpi_nm = sckpi.drop(columns=['kohosha_tanto', 'kigyo_tanto', 'mendan_tanto', 'CXL_status'])

DATE_COLS = ['shokikosho_setteibi', 'first_jisshi_date', 'shokikosho_jisshibi',
             'honkosho_setteibi', 'honkosho_jissibi', 'seiyaku']
sckpi_values = to_sheet_values(sckpi, date_cols=DATE_COLS)
sckpi_nm_values = to_sheet_values(sckpi_nm, date_cols=DATE_COLS)


# %%
# 成約単価シートにコピペ(NEOのみ担当者/CXL_statusの列を含むフル版を書き込む)
write_to_sheets(sckpi_values, [
    (SS_NEO, 'scdata!A2'),
], service)

# NM/CAには担当者列を除いた版を書き込む
write_to_sheets(sckpi_nm_values, [
    (SS_NM, 'scdata!A2'),
    (SS_CA, 'scdata!A3'),
], service)


# %% [markdown]
# ## 成約データ

# %%
RANGE_NAME = 'yomihyo!A:T'
seiyaku = ps.get_ss(SS_YOMIHYO, RANGE_NAME, service)

adinfoB_seiyaku = adinfoB.rename(columns={"tenki_id": "転機ID"})
seiyaku = pd.merge(seiyaku, adinfoB_seiyaku, how="left", on="転機ID")

seiyaku["移籍年収"] = ""
seiyaku = seiyaku[["転機ID", "登録日", "計上日", "獲得P", "参照元/メディア", "キャンペーン",
                    "広告ID", "KWD", "前職年収", "移籍年収", "売上金額", "sai_flg"]]
seiyaku_values = to_sheet_values(seiyaku)


# %%
# 成約単価シート(NEO/NM/ZEALS/CA)にコピペ
write_to_sheets(seiyaku_values, [
    (SS_NEO, 'rzdata!S3'),
    (SS_NM, 'rzdata!S3'),
    (SS_ZEALS, 'rzdata!S3'),
    (SS_CA, 'data!S3'),
], service)


# %% [markdown]
# ### CR別パフォーマンスを更新

# %%
# 当月の初日、およびその30日前を取得
def get_first_date(year, month):
    return datetime.date(year, month, 1)


now = datetime.datetime.now()
firstday = get_first_date(now.year, now.month)
firstday_minus_60 = (firstday - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
firstday_minus_60


# %% [markdown]
# ## 登録情報取得(直近60日分に絞り込み)

# %%
# 候補者マスタは冒頭で取得済みの adinfo を再利用する(同じ範囲を再取得しない)
adinfoA = adinfo.copy()

# IDのデータ型をint64に変換
adinfoA['tenki_id'] = pd.to_numeric(adinfoA['tenki_id'], errors='coerce').fillna(0).astype('int64')

# `登録日時`列をdatetime形式に変換
adinfoA['登録日時'] = pd.to_datetime(adinfoA['登録日時'])

# 直近60日分のデータのみを抽出
adinfoA = adinfoA[adinfoA['登録日時'] >= firstday_minus_60]

# 'フリ先'が'ロンザン'または'レイノス'と一致する場合、'1'に変換
adinfoA.loc[adinfoA['フリ先'].isin(['ロンザン', 'レイノス']), 'フリ先'] = '1'

# 'フリ先'が'送信NG'と一致する場合、空白に変換
adinfoA.loc[adinfoA['フリ先'] == '送信NG', 'フリ先'] = ''

# '本手上げ'が'TRUE'なら'1'、'FALSE'なら'0'に変換
adinfoA.loc[adinfoA['本手上げ'] == 'TRUE', '本手上げ'] = '1'
adinfoA.loc[adinfoA['本手上げ'] == 'FALSE', '本手上げ'] = '0'


# %%
tkuserinfo_query = f"""
select
	inf.id,
	format_date('%Y/%m/%d',inf.created_at) as created_at,
	concat(trim(replace(inf.shi,'　',' ')),trim(replace(inf.mei,'　',' '))) as name,
	inf.seibetu,
  concat(inf.birth_year,"/",inf.birth_month,"/",inf.birth_day) as birthday,
  extract(year from inf.created_at)-inf.birth_year as age,
	inf.email,
	inf.mob_tel,
	inf.comp_name,
	inf.gyousyu1,
	inf.jobcat,
	inf.syokusyu1,
	inf.layer,
	inf.income,
  inf.management_num1,
	inf.change_job,
	concat(corp_from_year1,"/",corp_from_month1,"~",
	       ifnull(cast(corp_to_year1 as string),""),"/",ifnull(cast(corp_to_month1 as string),"")) as zaiseki_kikan,
  inf.pref,
	inf.work_pref,
	inf.wish_pref,
	inf.moving,
	inf.kanou_jiki,
	format_date('%Y/%m/%d',dt.keireki_ja_date) as shokureki_upload_date
from
	`r-group-bigdata.live_tenki.user_info` inf
left join `r-group-bigdata.live_tenki.user_detail` dt on inf.id = dt.id
where
    created_at >= date '{firstday_minus_60}'
order by id
"""
tkuserinfo = bq_client.query(tkuserinfo_query).result().to_dataframe()
tkuserinfo = tkuserinfo.rename(columns={"id": "ID"})


# %%
adinfoA = adinfoA.rename(columns={"tenki_id": "ID"})
ALL_data = pd.merge(adinfoA, tkuserinfo, how='left', on='ID')
ALL_data = ALL_data[["ID", "登録日時", "フリ先", "手上げ日付", "本手上げ", "参照元/メディア", "キャンペーン",
                      "広告ID", "KWD", "年齢", "income", "役職", "pref", "gyousyu1", "jobcat", "syokusyu1", "change_job"]]


# %% [markdown]
# ## 各種シートに貼り付け

# %%
# NM/CA/GAXそれぞれの「サマリー」「手上げデータ」シートを取得
recentID_NM = ps.get_ss(SS_NM_SUMMARY, 'サマリー!A:A', service)
recentID_CA = ps.get_ss(SS_CA, 'サマリー!A:A', service)
recentID_GAX = ps.get_ss(SS_GAX, '手上げデータ!A:A', service)


# %%
# 書き込み先のセル(行)を特定
recentID_NM['転機ID'] = recentID_NM['転機ID'].astype('int64')
recentID_CA['ID'] = recentID_CA['ID'].astype('int64')
recentID_GAX['ID'] = recentID_GAX['ID'].astype('int64')

target_id = ALL_data['ID'][0]
row_NM = find_row_index(recentID_NM, "転機ID", target_id)
row_CA = find_row_index(recentID_CA, "ID", target_id)
row_GAX = find_row_index(recentID_GAX, "ID", target_id)


# %%
ALL_data["ID"] = ALL_data["ID"].astype(str)
ALL_data["登録日時"] = ALL_data["登録日時"].astype(str)

# infをNaNに、NaNをNoneに置き換え(このシートは空欄をNoneで表現する仕様のため、
# 他セクションの to_sheet_values とは別処理にしている)
ALL_data = ALL_data.replace([np.inf, -np.inf], np.nan)
ALL_data = ALL_data.where(pd.notnull(ALL_data), None)
ALL_data_values = ALL_data.values.tolist()


# %%
# NM/CA/GAXシートへの書き込み処理。一致する行が無ければスキップする。
for row, spreadsheet_id, sheet_range, label in [
    (row_NM, SS_NM_SUMMARY, 'サマリー!A', 'NM'),
    (row_CA, SS_CA, 'サマリー!A', 'CA'),
    (row_GAX, SS_GAX, '手上げデータ!A', 'GAX'),
]:
    if row is not None:
        ps.update_ss(spreadsheet_id, f'{sheet_range}{row}', ALL_data_values, service)
        print(f"{label}シートの更新が完了しました。")
    else:
        print(f"スキップ: {label}の条件に一致するデータが見つかりませんでした。")


# %% [markdown]
# ## 媒体の広告を抽出する

# %%
adinfoB_fb = adinfo.copy()[["tenki_id", "登録日時", "キャンペーン", "広告ID"]]
adinfoB_fb = adinfoB_fb[adinfoB_fb["キャンペーン"] == "nm_facebook"]
adinfoB_fb['登録日時'] = pd.to_datetime(adinfoB_fb['登録日時'])
adinfoB_fb = adinfoB_fb[adinfoB_fb['登録日時'] >= firstday_minus_60]
adinfoB_fb['tenki_id'] = adinfoB_fb['tenki_id'].astype('int64')


# %%
recentID_NM_ds1 = ps.get_ss(SS_NM_SUMMARY, 'データセット1!A:B', service)
recentID_NM_ds1['ID'] = recentID_NM_ds1['ID'].astype('int64')

if len(adinfoB_fb) > 0:
    target_id = adinfoB_fb['tenki_id'].iloc[0]
    row_NM_ds1 = find_row_index(recentID_NM_ds1, "ID", target_id)
else:
    row_NM_ds1 = None
    print("adinfoBに条件に一致するデータが存在しませんでした。")


# %%
adinfoB_fb = adinfoB_fb[["広告ID", "tenki_id"]]
adinfoB_fb["tenki_id"] = adinfoB_fb["tenki_id"].astype(str)
adinfoB_fb_values = to_sheet_values(adinfoB_fb)


# %%
# NMシートにコピペ(元のノートブックでも意図的にコメントアウトされていたため維持)
# if row_NM_ds1 is not None:
#     ps.update_ss(SS_NM_SUMMARY, f'データセット1!A{row_NM_ds1}', adinfoB_fb_values, service)



