import requests
import csv
import sqlite3
lines =[]
from string import Template
conn = sqlite3.connect("/Users/wangx51/Documents/cpi_data/cpi.db")
cur = conn.cursor()
cur.execute("select *,rowid from mapping where  loaded='n';")

rows = cur.fetchall()
url = "https://ccdi-dev-cpi-neptune-cluster.cluster-cji2s0rgsplw.us-east-1.neptune.amazonaws.com:8182/gremlin"

temp_str = "g.V('$id1').addE('mapping').to(V('$id2')).property('source', 'kf_dataservice_studies_w_cog_usis_duplicates_v2.xlsx').property('status', 'loaded')"

temp_obj = Template(temp_str)
for row in rows:
    line = temp_obj.substitute(id1=row[0]+'-'+row[1], id2=row[2]+'-'+row[3])
    data = {
    "gremlin": line
    } 
    response = requests.post(url, json=data, verify=False)
    if response.status_code == 200:
        sql = ''' UPDATE mapping
              SET loaded = 'y' 
              WHERE rowid = ?'''
        cur.execute(sql, (row[7],))
        conn.commit()
    print("JSON Response ", response.json())




'''
g.V().has('sourceVertexProperty', 'sourceVertexValue')
  .addE('relationshipLabel')
  .property(list, 'multiValuedProperty', 'value1', 'value2', 'value3')
  .to(g.V().has('targetVertexProperty', 'targetVertexValue'))
url = "https://neo4j-qa.bento-tools.org:8182/gremlin"
 
data = {
    "gremlin": 1001,
    "name": "geek",
    "passion": "coding",
}
 
response = requests.post(url, json=data)
 
print("Status Code", response.status_code)
print("JSON Response ", response.json())
      
  '''

 

    

