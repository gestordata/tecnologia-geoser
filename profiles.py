import sqlite3, json, unicodedata, re, os, base64, uuid, mimetypes
from pathlib import Path
from urllib.parse import urlparse,parse_qs

BASE=Path(__file__).resolve().parent
DB=BASE/'data'/'tecnologia.db'
PHOTOS=BASE/'data'/'photos'
PHOTOS.mkdir(exist_ok=True)
def db():
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
def init():
 c=db()
 for sql in [
 "ALTER TABLE people ADD COLUMN email TEXT",
 "ALTER TABLE people ADD COLUMN photo TEXT",
 "ALTER TABLE people ADD COLUMN phone TEXT",
 "ALTER TABLE people ADD COLUMN external_sales_key TEXT",
 "ALTER TABLE equipment ADD COLUMN photo TEXT",
 "ALTER TABLE equipment ADD COLUMN device_name TEXT",
 "ALTER TABLE equipment ADD COLUMN os TEXT",
 "ALTER TABLE equipment ADD COLUMN antivirus TEXT",
 "ALTER TABLE equipment ADD COLUMN renting TEXT",
 "ALTER TABLE equipment ADD COLUMN external_sales_key TEXT"
 ]:
  try:c.execute(sql)
  except sqlite3.OperationalError:pass
 c.executescript("""
 CREATE TABLE IF NOT EXISTS source_records(
  id INTEGER PRIMARY KEY,source_file TEXT NOT NULL,source_sheet TEXT,
  source_row INTEGER NOT NULL,record_type TEXT NOT NULL,payload TEXT NOT NULL,
  person_id INTEGER REFERENCES people(id),equipment_id INTEGER REFERENCES equipment(id),
  matching_method TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(source_file,source_sheet,source_row));
 CREATE TABLE IF NOT EXISTS asset_assignments(
  id INTEGER PRIMARY KEY,equipment_id INTEGER NOT NULL REFERENCES equipment(id),
  person_id INTEGER REFERENCES people(id),recipient_raw TEXT,started_at TEXT,
  ended_at TEXT,source_record_id INTEGER REFERENCES source_records(id),
  movement_id INTEGER REFERENCES movements(id),status TEXT DEFAULT 'HISTORICAL',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS idx_assignment_equipment ON asset_assignments(equipment_id);
 CREATE INDEX IF NOT EXISTS idx_assignment_person ON asset_assignments(person_id);
 CREATE TABLE IF NOT EXISTS identity_review(id INTEGER PRIMARY KEY,entity_type TEXT,raw_value TEXT,
  source_file TEXT,source_sheet TEXT,source_row INTEGER,candidates TEXT,
  status TEXT DEFAULT 'PENDING',resolved_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 """)
 c.commit();c.close()
def normal(x):
 s=unicodedata.normalize('NFKD',str(x or '').casefold())
 return re.sub(r'[^a-z0-9]','', ''.join(ch for ch in s if not unicodedata.combining(ch)))
def match_person(c,raw,cedula=None):
 ced=str(cedula or '').strip()
 if ced:
  hits=c.execute('SELECT id FROM people WHERE cedula=?',(ced,)).fetchall()
  if len(hits)==1:return hits[0]['id'],'DOCUMENT'
 nm=normal(raw)
 if not nm:return None,'EMPTY'
 hits=[r['id'] for r in c.execute('SELECT id,name FROM people') if normal(r['name'])==nm]
 return (hits[0],'EXACT_NAME') if len(hits)==1 else (None,'AMBIGUOUS' if hits else 'UNMATCHED')
def match_eq(c,serial):
 s=normal(serial)
 if not s:return None,'EMPTY'
 matches=[r['id'] for r in c.execute('SELECT id,serial FROM equipment WHERE serial IS NOT NULL') if normal(r['serial'])==s]
 return (matches[0],'SERIAL') if len(matches)==1 else (None,'AMBIGUOUS' if matches else 'UNMATCHED')
def source(c,file,sheet,row,typ,payload,pid=None,eid=None,method='PENDING'):
 cur=c.execute("""INSERT OR IGNORE INTO source_records(source_file,source_sheet,source_row,record_type,payload,person_id,equipment_id,matching_method)
  VALUES(?,?,?,?,?,?,?,?)""",(file,sheet,row,typ,json.dumps(payload,ensure_ascii=False),pid,eid,method))
 return cur.rowcount
def import_seed(d):
 c=db();counts={}
 def record(file,sheet,row,typ,payload,pid=None,eid=None,method='PENDING'):
  counts[typ]=counts.get(typ,0)+source(c,file,sheet,row,typ,payload,pid,eid,method)
 def strv(x):
  x=str(x).strip() if x is not None else ''
  return None if x in ('','None','nan','-') else x
 # Corporate directory: only document-level or exact name matches.
 for n,r in enumerate(d.get('directory',[]),2):
  ced,name,email=(r+[None]*3)[:3]
  if not name:continue
  pid,method=match_person(c,name,ced)
  if pid:
   c.execute('UPDATE people SET email=COALESCE(email,?),cedula=COALESCE(cedula,?) WHERE id=?',(strv(email),strv(ced),pid))
  else:
   cur=c.execute('INSERT INTO people(name,cedula,email) VALUES(?,?,?)',(str(name),strv(ced),strv(email)));pid=cur.lastrowid;method='CREATED_DOCUMENT'
  record('Base de datos 6_10_2026.xlsx','Hoja1',n,'DIRECTORY',r,pid,None,method)
 # Asset master, unmatched owner stays raw in source and gets review.
 for n,r in enumerate(d.get('assets',[]),2):
  typ,brand,model,serial,owner,cost,status=(r+[None]*7)[:7]
  condition='USADO';state='Activo';area=None;notes=None
  serial=strv(serial)
  if not serial:continue
  eid,em=match_eq(c,serial)
  pid,pm=match_person(c,owner)
  if not eid:
   cur=c.execute("""INSERT INTO equipment(asset_tag,type,brand,model,serial,status,condition,cost_center,notes,source)
    VALUES(?,?,?,?,?,?,?,?,?,?)""",(None,strv(typ) or 'Equipo',strv(brand),strv(model),serial,
    'POR_VALIDAR' if strv(owner) else 'DISPONIBLE',strv(condition) or 'USADO',strv(cost),strv(notes),'ALLCOM'))
   eid=cur.lastrowid; c.execute('UPDATE equipment SET asset_tag=? WHERE id=?',(f'TEC-{eid:05d}',eid));em='CREATED_SERIAL'
  else:
   c.execute("""UPDATE equipment SET type=COALESCE(?,type),brand=COALESCE(brand,?),
    model=COALESCE(model,?),cost_center=COALESCE(cost_center,?),notes=COALESCE(notes,?) WHERE id=?""",
    (strv(typ),strv(brand),strv(model),strv(cost),strv(notes),eid))
  record('Equipos ALLCOM (version 1).xlsb','Control Activos',n,'ASSET',r,pid,eid,em+' / '+pm)
  if strv(owner) and strv(status)=='Asignado' and pid:
   exists=c.execute('SELECT 1 FROM asset_assignments WHERE equipment_id=? AND person_id=? AND status="IMPORTED" LIMIT 1',(eid,pid)).fetchone()
   if not exists:
    c.execute('INSERT INTO asset_assignments(equipment_id,person_id,recipient_raw,status) VALUES(?,?,?,?)',(eid,pid,strv(owner),'IMPORTED'))
  if strv(owner) and not pid:
   c.execute('INSERT INTO identity_review(entity_type,raw_value,source_file,source_sheet,source_row) VALUES(?,?,?,?,?)',('PERSON',str(owner),'Equipos ALLCOM','Control Activos',n))
 # Renting is separate source ledger, never forcibly overrides owner.
 for n,r in enumerate(d.get('renting',[]),2):
  serial,typ,brand,owner,location,cost,state=(r+[None]*7)[:7]
  notes=None;substatus=None
  eid,em=match_eq(c,serial);pid,pm=match_person(c,owner)
  if not eid and strv(serial):
   cur=c.execute('INSERT INTO equipment(asset_tag,type,brand,serial,status,source,renting,location,cost_center) VALUES(?,?,?,?,?,?,?,?,?)',
    (None,strv(typ) or 'Portatil',strv(brand),strv(serial),'POR_VALIDAR' if strv(owner) else 'DISPONIBLE','RENTING','SI',strv(location),strv(cost)))
   eid=cur.lastrowid;c.execute('UPDATE equipment SET asset_tag=? WHERE id=?',(f'TEC-{eid:05d}',eid));em='CREATED_SERIAL'
  if eid:c.execute('UPDATE equipment SET renting=?,location=COALESCE(location,?) WHERE id=?',('SI',strv(location),eid))
  record('Equipos ALLCOM (version 1).xlsb','DB Renting',n,'RENTING',r,pid,eid,em+' / '+pm)
  if not pid and strv(owner):
   c.execute('INSERT INTO identity_review(entity_type,raw_value,source_file,source_sheet,source_row) VALUES(?,?,?,?,?)',('PERSON',str(owner),'Equipos ALLCOM','DB Renting',n))
 # Device names, Bitdefender; device names do not equal serials.
 for n,r in enumerate(d.get('names',[]),2):
  hostname,owner,area,renting,os_=(r+[None]*5)[:5]
  antivirus=None
  record('Nomenclatura_Computadores_GEOSER.xlsx','EQUIPOS GEOSER',n,'NOMENCLATURE',r,*((match_person(c,owner)[0]),None),'HOSTNAME_ONLY')
 for n,r in enumerate(d.get('antivirus',[]),3):
  record('Nomenclatura_Computadores_GEOSER.xlsx','Licencias Asignadas BitDefender',n,'ANTIVIRUS',r,None,None,'HOSTNAME_ONLY')
 for n,r in enumerate(d.get('staff',[]),2):
  first,last,area,cargo,phone=(r+[None]*5)[:5]
  name=' '.join(filter(None,[strv(first),strv(last)]))
  pid,method=match_person(c,name)
  if pid:c.execute('UPDATE people SET phone=COALESCE(phone,?),cargo=COALESCE(cargo,?) WHERE id=?',(strv(phone),strv(cargo),pid))
  record('Equipos ALLCOM (version 1).xlsb','DB Personal Geoser',n,'PERSONNEL',r,pid,None,method)
 c.commit();c.close();return counts
def handle_get(app,path,q):
 c=db()
 if path=='/api/profiles/summary':
  x={k:c.execute('SELECT COUNT(*) FROM '+k).fetchone()[0] for k in ('people','equipment','source_records','asset_assignments','identity_review')}
  c.close();return app.json(x)
 if path=='/api/profiles/review':
  rows=[dict(r) for r in c.execute('SELECT * FROM identity_review WHERE status="PENDING" ORDER BY id DESC LIMIT 500')]
  c.close()
  return app.json(rows)
 if path=='/api/profiles/people':
  term=(q.get('q',[''])[0] or '').lower()
  arr=[dict(r) for r in c.execute('SELECT p.*,(SELECT COUNT(*) FROM equipment e WHERE e.assigned_person_id=p.id) AS equipment_count FROM people p ORDER BY p.name')]
  c.close();return app.json([r for r in arr if term in (r['name'] or '').lower() or term in (r['cedula'] or '').lower() or term in (r['email'] or '').lower()][:1500])
 if path=='/api/profiles/equipment':
  term=(q.get('q',[''])[0] or '').lower()
  arr=[dict(r) for r in c.execute('SELECT e.*,p.name assigned_to FROM equipment e LEFT JOIN people p ON p.id=e.assigned_person_id ORDER BY e.id DESC')]
  c.close();return app.json([r for r in arr if any(term in str(r.get(k) or '').lower() for k in ('asset_tag','serial','type','brand','model','device_name','assigned_to'))][:3000])
 m=re.fullmatch(r'/api/profiles/(people|equipment)/(\d+)',path)
 if m:
  typ,pk=m.group(1),int(m.group(2));pcol='person_id' if typ=='people' else 'equipment_id'
  tab='people' if typ=='people' else 'equipment'
  obj=c.execute(f'SELECT * FROM {tab} WHERE id=?',(pk,)).fetchone()
  if not obj:c.close();return app.json({'error':'No encontrado'},404)
  ass=[dict(r) for r in c.execute(f"""SELECT a.*,e.asset_tag,e.serial,e.type equipment_type,
    p.name person_name FROM asset_assignments a JOIN equipment e ON e.id=a.equipment_id
    LEFT JOIN people p ON p.id=a.person_id WHERE a.{pcol}=? ORDER BY a.id DESC""",(pk,))]
  mov=[dict(r) for r in c.execute(f"""SELECT m.*,e.asset_tag,e.serial FROM movements m LEFT JOIN equipment e ON e.id=m.equipment_id
   WHERE m.{pcol}=? ORDER BY m.movement_date DESC,m.id DESC LIMIT 200""",(pk,))]
  refs=[dict(r) for r in c.execute(f'SELECT source_file,source_sheet,source_row,record_type,matching_method,payload FROM source_records WHERE {pcol}=? ORDER BY id DESC LIMIT 200',(pk,))]
  current=[dict(r) for r in (c.execute('SELECT * FROM equipment WHERE assigned_person_id=?',(pk,)) if typ=='people' else [])]
  c.close();return app.json({'profile':dict(obj),'assignments':ass,'movements':mov,'sources':refs,'current_equipment':current})
 if path.startswith('/profile-photos/'):
  filename=Path(path).name;f=PHOTOS/filename
  if not f.is_file():return app.send_error(404)
  content=f.read_bytes();app.send_response(200)
  app.send_header('Content-Type',mimetypes.guess_type(f.name)[0] or 'image/jpeg')
  app.send_header('Content-Length',str(len(content)));app.end_headers();app.wfile.write(content);c.close();return
 c.close();return None
def handle_post(app,path,d):
 if path=='/api/profiles/import':
  return app.json({'error':'Carga masiva administrativa deshabilitada desde API pública'},403)
 m=re.fullmatch(r'/api/profiles/(people|equipment)/(\d+)/photo',path)
 if not m:return None
 kind,pk=m.group(1),int(m.group(2))
 payload=str(d.get('data') or '')
 raw=base64.b64decode(payload.split(',',1)[-1])
 if len(raw)>3000000:return app.json({'error':'La imagen supera 3 MB'},400)
 mime=payload.split(';')[0]
 allowed={'data:image/jpeg':'.jpg','data:image/png':'.png','data:image/webp':'.webp'}
 if mime not in allowed:return app.json({'error':'Formato inválido: JPG, PNG o WEBP'},400)
 file=uuid.uuid4().hex+allowed[mime]
 (PHOTOS/file).write_bytes(raw)
 c=db();tab='people' if kind=='people' else 'equipment'
 c.execute(f'UPDATE {tab} SET photo=? WHERE id=?',(file,pk));c.commit();c.close()
 return app.json({'photo':file})
 return None