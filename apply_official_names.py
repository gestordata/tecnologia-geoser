import sqlite3,json,sys
sys.path.insert(0,'/opt/geoser/tecnologia-geoser')
import profiles
from collections import Counter
c=profiles.db()
rows=c.execute("SELECT id,source_row,payload FROM source_records WHERE record_type='NOMENCLATURE' ORDER BY id").fetchall()
stats=Counter()
for sr in rows:
 values=json.loads(sr['payload']); hostname=str(values[0] or '').strip()
 if not hostname:continue
 owner=str(values[1] or '').strip(); area=str(values[2] or '').strip()
 av=str(values[3] or '').strip(); system=str(values[4] or '').strip()
 pid,method=profiles.match_person(c,owner)
 existing=c.execute('SELECT id FROM equipment WHERE device_name=?',(hostname,)).fetchone()
 if existing:
  eid=existing['id'];stats['existing']+=1
 else:
  matched=None
  if pid:
   assigned=c.execute("SELECT id FROM equipment WHERE assigned_person_id=? AND (device_name IS NULL OR device_name='')",(pid,)).fetchall()
   if len(assigned)==1: matched=assigned[0]['id'];stats['matched_by_unique_current_owner']+=1
  if matched:eid=matched
  else:
   cur=c.execute("""INSERT INTO equipment(asset_tag,type,status,condition,cost_center,source,device_name,os,antivirus,notes)
    VALUES(?,?,?,?,?,?,?,?,?,?)""",(None,'Computador','POR_VALIDAR','POR_VALIDAR',area or None,'NOMENCLATURA OFICIAL',hostname,system or None,av or None,'Responsable indicado en nomenclatura: '+owner))
   eid=cur.lastrowid
   c.execute("UPDATE equipment SET asset_tag=? WHERE id=?",(f'TEC-{eid:05d}',eid))
   stats['created_hostname_only']+=1
 c.execute("""UPDATE equipment SET device_name=?,os=COALESCE(NULLIF(?,''),os),
  antivirus=COALESCE(NULLIF(?,''),antivirus),
  cost_center=COALESCE(cost_center,NULLIF(?,'')) WHERE id=?""",(hostname,system,av,area,eid))
 c.execute("UPDATE source_records SET person_id=?,equipment_id=?,matching_method=? WHERE id=?",(pid,eid,'OFFICIAL_HOSTNAME / '+method,sr['id']))
 if pid and method in ('DOCUMENT','EXACT_NAME'):
  stats['linked_person_profile']+=1
c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_hostname ON equipment(device_name COLLATE NOCASE) WHERE device_name IS NOT NULL AND trim(device_name)<>''")
c.commit()
print('STATS',dict(stats))
print('EQUIPMENTS',c.execute("SELECT COUNT(*) FROM equipment").fetchone()[0])
print('NAMED',c.execute("SELECT COUNT(*) FROM equipment WHERE device_name IS NOT NULL").fetchone()[0])
print('INTEGRITY',c.execute('PRAGMA integrity_check').fetchone()[0])
c.close()