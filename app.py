#  CREATE (epl:League { name:"English Premier League",nickname: "EPL"})
'''
g.addV("League").
    property(id,'EPL-2019-20').
    property("name", "English Premier League").
    property("nickname", "EPL").
    as("epl").
https://neo4j-qa.bento-tools.org:8182/openCypher?query=MATCH%20(t:participant)%20RETURN%20t%20AS%20Team_Info
    curl -X POST "https://neo4j-qa.bento-tools.org:8182/gremlin" -H "Content-Type: application/json" -d '{
	"gremlin": "g.addV('Person').property('name', 'John').property('age', 30)"
}'

'''
import requests
import csv
import sqlite3


lines =[]
conn = sqlite3.connect("/Users/wangx51/Documents/cpi_data/cpi.db")
cur = conn.cursor()
cur.execute("select * from participant where  loaded='n';")

rows = cur.fetchall()
url = "https://ccdi-dev-cpi-neptune-cluster.cluster-cji2s0rgsplw.us-east-1.neptune.amazonaws.com:8182/gremlin"
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
'''
with open('/Users/wangx51/Documents/cpi_data/export_participant.csv', newline='') as csvfile:
    spamreader = csv.reader(csvfile, delimiter=',', quotechar='|')
    next(spamreader)
    for row in spamreader:
        line="g.addV('participant').property(id,'"+row[0].replace(".","-")+"').property('participant_id', '"+row[1]+"').property('domain_name', '"+row[2]+"').property('status', 'loaded').property('created_date', '2023-10-06').property('modified_date', '2023-10-06').property('is_private', 'false').as('"+row[0].replace(".","-")+"')"
        print(line)
        lines.append(line)
'''
'''
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
 

 


