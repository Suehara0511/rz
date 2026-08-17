import pandas as pd
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

def get_auth(SCOPES,json_path):
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                json_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('sheets', 'v4', credentials=creds)
    return service

def get_ss(SPREADSHEET_ID,RANGE_NAME,service,value_render_option='FORMATTED_VALUE'):
    # value_render_option: 'FORMATTED_VALUE'(既定、計算後の表示値) / 'UNFORMATTED_VALUE' / 'FORMULA'(数式そのもの)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                range=RANGE_NAME,
                                valueRenderOption=value_render_option).execute()
    values = result.get('values', [])
    df = pd.DataFrame(values)
    df_values = df.iloc[1:]
    df_values.columns = df.iloc[0].tolist()
    return df_values

def get_ss_some(SPREADSHEET_ID,RANGE_LIST,service,value_render_option='FORMATTED_VALUE'):
    result = service.spreadsheets().values().batchGet(
        spreadsheetId=SPREADSHEET_ID, ranges=RANGE_LIST,
        valueRenderOption=value_render_option).execute()
    ranges = result.get('valueRanges', [])
    df = pd.DataFrame()
    for i in ranges:
        df = df.append(pd.DataFrame(i['values'][1:]))
    df.columns = i['values'][0]
    return df

def update_ss(SPREADSHEET_ID,RANGE_NAME,values,service):
    body = {
        'values': values,
    }
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    return

def insert_ss(SPREADSHEET_ID,RANGE_NAME,values,service):
    body = {
        'values': values,
    }
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME,
        valueInputOption="USER_ENTERED",
        body=body,
        insertDataOption = 'INSERT_ROWS',
    ).execute()
    return