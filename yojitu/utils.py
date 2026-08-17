#!/usr/bin/python3
# coding: utf-8
import pandas as pd
import pymysql


# 接続情報を記載
conn = pymysql.connect(
                    host="10.228.16.7",
                    user="capybara",
                    password="qU5nZbzj",
                    db="db",
                    port=3306,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor)

conn2 = pymysql.connect(
                    host="192.168.5.110",
                    user="y-nishi",
                    password="D8giPu7S",
                    db="rms_contract",
                    port=3306,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor)

conn3 = pymysql.connect(
                    host="192.168.5.124",
                    user="eigyou_kikaku",
                    password="As6hV2K!k",
                    db="eigyou_kikaku",
                    port=3306,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor)

def sqlserver_reconnect():
    conn.ping(reconnect=True)
    conn.cursor()

def get_data(sql,conn_info):
#     # sqlを実行する度にmysqlに再接続する
    sqlserver_reconnect()
    try:
        with conn_info.cursor() as cursor:
            cursor.execute(sql)
            result = cursor.fetchall()
    finally:
        conn.close()
    return result

def connect_mysql():
    con = pymysql.connect(host="10.228.16.7",user="capybara",password="qU5nZbzj",database="db",port=3306)
    cur = con.cursor(pymysql.cursors.DictCursor)
    return con,cur

def to_datetime(df, col):
    df[col] = pd.to_datetime(df[col], errors='coerce')
    return df