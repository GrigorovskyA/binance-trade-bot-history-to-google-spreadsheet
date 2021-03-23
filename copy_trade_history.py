from __future__ import print_function
import os.path
import platform
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient import discovery
import sqlite3
import pandas as pd
from variables import *

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

if platform.system() == "Windows":
    dbfile = windows_db_path
elif platform.system() == "Linux":
    dbfile = linux_db_path

#get creds to google spreadsheet
creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
service = build('sheets', 'v4', credentials=creds)

#get current spreadsheet
request = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id,
                                              range=current_scope)
#formatting current data
current_data = pd.DataFrame(request.execute()['values'], columns = request.execute()['values'][0])
current_data = current_data.iloc[1:].reset_index()
current_data['datetime_ts'] = pd.to_datetime(current_data['datetime'])

#get trade history from database
con = sqlite3.connect(dbfile)
new_data = pd.read_sql_query("SELECT th1.alt_coin_id AS coin, "
                       "th1.alt_trade_amount AS amount, "
                       "th1.crypto_trade_amount AS priceInUSD, "
                       "(th1.alt_trade_amount - (SELECT th2.alt_trade_amount FROM trade_history th2 "
                       "WHERE th2.alt_coin_id = th1.alt_coin_id AND "
                       "th1.datetime > th2.datetime AND "
                       "th2.selling = 0 ORDER BY th2.datetime DESC LIMIT 1)) AS change, "
                       "th1.datetime FROM trade_history th1 "
                       "WHERE th1.state = 'COMPLETE' AND "
                       "th1.selling = 0 ORDER BY th1.datetime;", con).fillna(0)
#format db data
new_data = new_data[['datetime', 'coin', 'amount', 'priceInUSD', 'change']]
new_data['datetime_ts'] = pd.to_datetime(new_data['datetime'])
new_data['datetime_ts'] = new_data['datetime_ts'].dt.round('1s')
con.close()
#merge data to append only new data with uniq timestamp
ultimate_new_rows = pd.merge(new_data,
                             current_data,
                             how='left',
                             on=('datetime_ts', 'coin')).fillna(-9999)
ultimate_new_rows = ultimate_new_rows[ultimate_new_rows['amount_y'] == -9999][['datetime_x', 'coin', 'amount_x', 'priceInUSD_x', 'change_x']]

#append new data to spreadsheet
body = {
    'values': ultimate_new_rows.values.tolist()
}
result = service.spreadsheets().values().append(
    spreadsheetId=spreadsheet_id, range=current_scope,
    valueInputOption="USER_ENTERED", body=body).execute()
print('{0} cells appended.'.format(result \
                                   .get('updates') \
                                   .get('updatedCells')))

