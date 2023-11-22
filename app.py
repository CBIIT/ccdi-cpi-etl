import requests
import csv
import sqlite3


lines =[]
conn = sqlite3.connect("/Users/wangx51/Documents/cpi_data/cpi.db")
cur = conn.cursor()
cur.execute("select * from participant where  loaded='n';")

rows = cur.fetchall()
url = # gremlin url of neptune db
for row in rows:
    line="g.addV('participant').property(id,'"+row[0].replace(".","-")+"').property('participant_id', '"+row[1]+"').property('domain_name', '"+row[2]+"').property('status', 'loaded').property('created_date', '2023-10-06').property('modified_date', '2023-10-06').property('is_private', 'false').as('"+row[0].replace(".","-")+"')"
    print(line)
    data = {
    "gremlin": line
    }
    response = requests.post(url, json=data, verify=False)
    if response.status_code == 200:
        sql = ''' UPDATE participant
              SET loaded = 'y' 
              WHERE id = ?'''
        cur.execute(sql, (row[0],))
        conn.commit()
    print("JSON Response ", response.json())
with open('query.txt', 'w') as f:
    for line in lines:
        f.write(line)
        f.write('\n')


 


