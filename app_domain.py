import requests
import csv
import sqlite3
lines =[]
from string import Template
conn = sqlite3.connect("/Users/wangx51/Documents/cpi_data/cpi.db")
cur = conn.cursor()
cur.execute("select *,rowid from domain where  loaded='n';")

rows = cur.fetchall()
url = # gremlin url of neptune db
for row in rows:
    line="g.addV('domain').property(id,'"+row[0]+"').property('domain_name', '"+row[0]+"').property('domain_description', '"+row[1]+"').property('status', 'loaded').property('created_date', '2023-10-06').property('modified_date', '2023-10-06').property('is_private', 'false').as('"+row[0]+"')"
    print(line)
    data = {
    "gremlin": line
    } 
    response = requests.post(url, json=data, verify=False)
    if response.status_code == 200:
        sql = ''' UPDATE domain
              SET loaded = 'y' 
              WHERE rowid = ?'''
        cur.execute(sql, (row[3],))
        conn.commit()
    print("JSON Response ", response.json())




    

