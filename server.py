#!/usr/bin/env python3
import os, json, sqlite3, mimetypes, base64, uuid, re
from pathlib import Path
from datetime import date, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; PUBLIC=ROOT/"public"; UPLOADS=DATA/"uploads"; DB=DATA/"tecnologia.db"
DATA.mkdir(exist_ok=True); UPLOADS.mkdir(exist_ok=True)

def conn():
    c=sqlite3.connect(DB, timeout=20)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c

SCHEMA="""
CREATE TABLE IF NOT EXISTS people(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 cedula TEXT, name TEXT NOT NULL, cargo TEXT, cost_center TEXT, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);
CREATE TABLE IF NOT EXISTS equipment(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 asset_tag TEXT UNIQUE, type TEXT NOT NULL DEFAULT 'Equipo',
 brand TEXT, model TEXT, serial TEXT, imei1 TEXT, imei2 TEXT,
 processor TEXT, ram TEXT, storage TEXT, accessories TEXT,
 status TEXT NOT NULL DEFAULT 'DISPONIBLE',
 condition TEXT NOT NULL DEFAULT 'BUENO',
 assigned_person_id INTEGER REFERENCES people(id),
 cost_center TEXT, location TEXT, notes TEXT,
 source TEXT NOT NULL DEFAULT 'APP',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_serial ON equipment(serial) WHERE serial IS NOT NULL AND trim(serial)<>'';
CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_imei1 ON equipment(imei1) WHERE imei1 IS NOT NULL AND trim(imei1)<>'';
CREATE TABLE IF NOT EXISTS movements(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 movement_date TEXT NOT NULL, case_no TEXT,
 person_id INTEGER REFERENCES people(id),
 person_name TEXT NOT NULL, cedula TEXT, cargo TEXT,
 action TEXT NOT NULL, category TEXT, equipment_id INTEGER REFERENCES equipment(id),
 detail TEXT, observations TEXT, source TEXT NOT NULL DEFAULT 'APP',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_movements_date ON movements(movement_date DESC);
CREATE INDEX IF NOT EXISTS idx_movements_person ON movements(person_id);
CREATE TABLE IF NOT EXISTS evidence(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 movement_id INTEGER REFERENCES movements(id) ON DELETE CASCADE,
 filename TEXT NOT NULL, stored_name TEXT NOT NULL, mime TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def norm(s): return re.sub(r"\s+"," ",str(s or "").strip()).casefold()

def init_db():
    c=conn(); c.executescript(SCHEMA)
    imported=c.execute("SELECT COUNT(*) n FROM movements").fetchone()["n"]
    if imported==0 and (DATA/"import.json").exists():
        d=json.loads((DATA/"import.json").read_text(encoding="utf-8"))
        people_map={}
        for p in d.get("persons",[]):
            ced="" if p.get("cedula") is None else str(p.get("cedula"))
            name=str(p.get("name") or "").strip()
            if not name: continue
            key=(norm(name),ced)
            if key in people_map: continue
            cur=c.execute("INSERT INTO people(cedula,name,cargo,cost_center) VALUES(?,?,?,?)",
                (ced or None,name,p.get("cargo"),p.get("cost_center")))
            people_map[key]=cur.lastrowid
        # helper by name
        byname={norm(r["name"]):r["id"] for r in c.execute("SELECT id,name FROM people")}
        for i,e in enumerate(d.get("seed_equipment",[]),1):
            who=e.get("assigned_to"); pid=byname.get(norm(who))
            serial=(e.get("serial") or "").strip() or None
            try:
                c.execute("""INSERT INTO equipment(asset_tag,type,serial,status,assigned_person_id,cost_center,source)
                    VALUES(?,?,?,?,?,?,?)""",(f"TI-{i:04d}","Equipo de cómputo",serial,"ASIGNADO" if pid else "DISPONIBLE",pid,e.get("cost_center"),"EXCEL / EQUIPOS ALLCOM"))
            except sqlite3.IntegrityError:
                pass
        for m in d.get("movements",[]):
            name=str(m.get("person_name") or "").strip() or "Sin nombre"
            pid=byname.get(norm(name))
            c.execute("""INSERT INTO movements(movement_date,case_no,person_id,person_name,cedula,cargo,action,category,detail,observations,source)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(m.get("date") or date.today().isoformat(),str(m.get("case_no") or ""),pid,name,
                None if m.get("cedula") is None else str(m.get("cedula")),m.get("cargo"),m.get("action") or "HISTORICO",
                m.get("category"),m.get("detail"),m.get("observations"),"EXCEL"))
        c.commit()
    c.close()

def rowdict(r): return dict(r) if r else None

def clean(v):
    if v is None: return None
    v=str(v).strip()
    return v or None

def next_tag(c):
    n=c.execute("SELECT COALESCE(MAX(id),0)+1 n FROM equipment").fetchone()["n"]
    return f"TI-{n:04d}"

def next_case(c):
    vals=[r["case_no"] for r in c.execute("SELECT case_no FROM movements WHERE case_no IS NOT NULL")]
    nums=[int(v) for v in vals if str(v).isdigit()]
    return str((max(nums) if nums else 0)+1)

class App(BaseHTTPRequestHandler):
    server_version="GeoSerTecnologia/1.0"
    def log_message(self, fmt,*args): print(datetime.now().isoformat(timespec="seconds"),fmt%args)
    def json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False,default=str).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n=int(self.headers.get("Content-Length","0") or 0)
        if n>12_000_000: raise ValueError("Payload demasiado grande")
        raw=self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8"))
    def do_GET(self):
        p=urlparse(self.path); path=unquote(p.path); q=parse_qs(p.query)
        try:
            if path=="/api/health": return self.json({"ok":True,"app":"tecnologia-geoser"})
            if path=="/api/dashboard":
                c=conn()
                data={
                  "total":c.execute("SELECT COUNT(*) n FROM equipment").fetchone()["n"],
                  "assigned":c.execute("SELECT COUNT(*) n FROM equipment WHERE status='ASIGNADO'").fetchone()["n"],
                  "available":c.execute("SELECT COUNT(*) n FROM equipment WHERE status='DISPONIBLE'").fetchone()["n"],
                  "maintenance":c.execute("SELECT COUNT(*) n FROM equipment WHERE status='MANTENIMIENTO'").fetchone()["n"],
                  "people":c.execute("SELECT COUNT(*) n FROM people WHERE active=1").fetchone()["n"],
                  "movements":c.execute("SELECT COUNT(*) n FROM movements").fetchone()["n"],
                  "recent":[rowdict(r) for r in c.execute("""SELECT m.id,m.movement_date,m.case_no,m.person_name,m.action,m.category,e.asset_tag,e.serial
                      FROM movements m LEFT JOIN equipment e ON e.id=m.equipment_id ORDER BY m.movement_date DESC,m.id DESC LIMIT 8""")]
                }; c.close(); return self.json(data)
            if path=="/api/options":
                c=conn(); res={"next_case":next_case(c),"actions":["ENTREGA","DEVOLUCION"],"categories":[
                  "ENTREGA EQUIPOS MOVILES Y/O ACCESORIOS","ENTREGA EQUIPOS COMPUTO",
                  "DEVOLUCION EQUIPOS MOVILES Y/O ACCESORIOS","DEVOLUCION EQUIPOS COMPUTO","OTRO"],
                  "statuses":["DISPONIBLE","ASIGNADO","MANTENIMIENTO","BAJA"],"conditions":["NUEVO","BUENO","REGULAR","MALO"]}; c.close(); return self.json(res)
            if path=="/api/people":
                term=(q.get("q",[""])[0] or "").strip(); c=conn()
                rows=c.execute("""SELECT p.*, (SELECT COUNT(*) FROM equipment e WHERE e.assigned_person_id=p.id) equipment_count
                    FROM people p WHERE (?='' OR p.name LIKE ? OR COALESCE(p.cedula,'') LIKE ?) ORDER BY p.name LIMIT 1000""",(term,f"%{term}%",f"%{term}%")).fetchall()
                c.close(); return self.json([rowdict(r) for r in rows])
            if path=="/api/equipment":
                term=(q.get("q",[""])[0] or "").strip(); st=(q.get("status",[""])[0] or "").strip(); c=conn()
                rows=c.execute("""SELECT e.*,p.name assigned_to,p.cedula assigned_cedula
                    FROM equipment e LEFT JOIN people p ON p.id=e.assigned_person_id
                    WHERE (?='' OR e.asset_tag LIKE ? OR COALESCE(e.serial,'') LIKE ? OR COALESCE(e.imei1,'') LIKE ? OR COALESCE(e.brand,'') LIKE ? OR COALESCE(e.model,'') LIKE ? OR COALESCE(p.name,'') LIKE ?)
                    AND (?='' OR e.status=?) ORDER BY e.id DESC""",(term,*[f"%{term}%"]*6,st,st)).fetchall()
                c.close(); return self.json([rowdict(r) for r in rows])
            if path=="/api/movements":
                term=(q.get("q",[""])[0] or "").strip(); limit=min(int(q.get("limit",["500"])[0]),2000); c=conn()
                rows=c.execute("""SELECT m.*,e.asset_tag,e.serial,e.type equipment_type
                    FROM movements m LEFT JOIN equipment e ON e.id=m.equipment_id
                    WHERE (?='' OR m.person_name LIKE ? OR COALESCE(m.case_no,'') LIKE ? OR COALESCE(m.detail,'') LIKE ? OR COALESCE(e.serial,'') LIKE ?)
                    ORDER BY m.movement_date DESC,m.id DESC LIMIT ?""",(term,f"%{term}%",f"%{term}%",f"%{term}%",f"%{term}%",limit)).fetchall()
                c.close(); return self.json([rowdict(r) for r in rows])
            m=re.fullmatch(r"/api/movements/(\d+)",path)
            if m:
                c=conn(); r=c.execute("""SELECT m.*,e.asset_tag,e.serial,e.type equipment_type,e.brand,e.model,
                    p.cost_center person_cost_center FROM movements m LEFT JOIN equipment e ON e.id=m.equipment_id
                    LEFT JOIN people p ON p.id=m.person_id WHERE m.id=?""",(int(m.group(1)),)).fetchone()
                ev=[rowdict(x) for x in c.execute("SELECT * FROM evidence WHERE movement_id=? ORDER BY id",(int(m.group(1)),))]
                c.close(); return self.json({"movement":rowdict(r),"evidence":ev} if r else {"error":"No encontrado"},200 if r else 404)
            if path.startswith("/uploads/"):
                f=(UPLOADS/Path(path).name)
                if not f.exists(): return self.send_error(404)
                b=f.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(f.name)[0] or "application/octet-stream"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
            return self.static(path)
        except Exception as e:
            return self.json({"error":str(e)},500)
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            d=self.body(); c=conn()
            if path=="/api/people":
                name=clean(d.get("name"))
                if not name: c.close(); return self.json({"error":"Nombre requerido"},400)
                cur=c.execute("INSERT INTO people(cedula,name,cargo,cost_center) VALUES(?,?,?,?)",(clean(d.get("cedula")),name,clean(d.get("cargo")),clean(d.get("cost_center")))); c.commit()
                r=rowdict(c.execute("SELECT * FROM people WHERE id=?",(cur.lastrowid,)).fetchone()); c.close(); return self.json(r,201)
            if path=="/api/equipment":
                serial=clean(d.get("serial")); imei1=clean(d.get("imei1")); tag=clean(d.get("asset_tag")) or next_tag(c)
                fields=(tag,clean(d.get("type")) or "Equipo",clean(d.get("brand")),clean(d.get("model")),serial,imei1,clean(d.get("imei2")),
                    clean(d.get("processor")),clean(d.get("ram")),clean(d.get("storage")),clean(d.get("accessories")),clean(d.get("status")) or "DISPONIBLE",
                    clean(d.get("condition")) or "BUENO",d.get("assigned_person_id") or None,clean(d.get("cost_center")),clean(d.get("location")),clean(d.get("notes")))
                try:
                    cur=c.execute("""INSERT INTO equipment(asset_tag,type,brand,model,serial,imei1,imei2,processor,ram,storage,accessories,status,condition,assigned_person_id,cost_center,location,notes)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",fields); c.commit()
                except sqlite3.IntegrityError as ex:
                    c.close(); return self.json({"error":"Serial, IMEI o placa ya existe","detail":str(ex)},409)
                r=rowdict(c.execute("SELECT * FROM equipment WHERE id=?",(cur.lastrowid,)).fetchone()); c.close(); return self.json(r,201)
            if path=="/api/movements":
                person_id=int(d.get("person_id") or 0)
                pr=c.execute("SELECT * FROM people WHERE id=?",(person_id,)).fetchone()
                if not pr: c.close(); return self.json({"error":"Selecciona un colaborador"},400)
                action=(clean(d.get("action")) or "").upper()
                if action not in ("ENTREGA","DEVOLUCION"): c.close(); return self.json({"error":"Movimiento inválido"},400)
                eqid=int(d.get("equipment_id") or 0) or None
                eq=c.execute("SELECT * FROM equipment WHERE id=?",(eqid,)).fetchone() if eqid else None
                if action=="ENTREGA" and eq and eq["assigned_person_id"] and eq["assigned_person_id"]!=person_id:
                    c.close(); return self.json({"error":"Este equipo ya está asignado a otra persona. Registra primero la devolución."},409)
                case_no=clean(d.get("case_no")) or next_case(c)
                cur=c.execute("""INSERT INTO movements(movement_date,case_no,person_id,person_name,cedula,cargo,action,category,equipment_id,detail,observations)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(clean(d.get("movement_date")) or date.today().isoformat(),case_no,person_id,pr["name"],pr["cedula"],pr["cargo"],action,
                    clean(d.get("category")),eqid,clean(d.get("detail")),clean(d.get("observations"))))
                if eq:
                    if action=="ENTREGA": c.execute("UPDATE equipment SET assigned_person_id=?,status='ASIGNADO',updated_at=CURRENT_TIMESTAMP WHERE id=?",(person_id,eqid))
                    else: c.execute("UPDATE equipment SET assigned_person_id=NULL,status='DISPONIBLE',updated_at=CURRENT_TIMESTAMP WHERE id=?",(eqid,))
                c.commit(); mid=cur.lastrowid; c.close(); return self.json({"id":mid,"case_no":case_no},201)
            if path=="/api/evidence":
                mid=int(d.get("movement_id") or 0); filename=Path(clean(d.get("filename")) or "evidencia").name
                b64=str(d.get("data") or ""); raw=base64.b64decode(b64.split(",",1)[-1])
                if len(raw)>8_000_000: c.close(); return self.json({"error":"Archivo mayor a 8 MB"},400)
                ext=Path(filename).suffix[:10]; stored=f"{uuid.uuid4().hex}{ext}"; (UPLOADS/stored).write_bytes(raw)
                c.execute("INSERT INTO evidence(movement_id,filename,stored_name,mime) VALUES(?,?,?,?)",(mid,filename,stored,clean(d.get("mime")))); c.commit(); c.close(); return self.json({"ok":True},201)
            c.close(); return self.json({"error":"Ruta no encontrada"},404)
        except Exception as e:
            try: c.close()
            except: pass
            return self.json({"error":str(e)},500)
    def do_PUT(self):
        path=urlparse(self.path).path; m=re.fullmatch(r"/api/equipment/(\d+)",path)
        if not m: return self.json({"error":"Ruta no encontrada"},404)
        try:
            d=self.body(); c=conn(); eid=int(m.group(1))
            vals=[clean(d.get(k)) for k in ["asset_tag","type","brand","model","serial","imei1","imei2","processor","ram","storage","accessories","status","condition","cost_center","location","notes"]]
            pid=d.get("assigned_person_id") or None
            c.execute("""UPDATE equipment SET asset_tag=?,type=?,brand=?,model=?,serial=?,imei1=?,imei2=?,processor=?,ram=?,storage=?,accessories=?,status=?,condition=?,cost_center=?,location=?,notes=?,assigned_person_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",(*vals,pid,eid)); c.commit()
            r=rowdict(c.execute("SELECT * FROM equipment WHERE id=?",(eid,)).fetchone()); c.close(); return self.json(r)
        except sqlite3.IntegrityError as e: return self.json({"error":"Serial, IMEI o placa ya existe","detail":str(e)},409)
        except Exception as e: return self.json({"error":str(e)},500)
    def static(self,path):
        rel="index.html" if path in ("","/") else path.lstrip("/")
        f=(PUBLIC/rel).resolve()
        if not str(f).startswith(str(PUBLIC.resolve())) or not f.exists() or not f.is_file(): f=PUBLIC/"index.html"
        b=f.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(f.name)[0] or "text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)


import profiles
profiles.init()
_original_get=App.do_GET
_original_post=App.do_POST
def profile_get(self):
    route=urlparse(self.path)
    if route.path.startswith('/api/profiles/') or route.path.startswith('/profile-photos/'):
        value=profiles.handle_get(self,route.path,parse_qs(route.query))
        if value is not None or route.path.startswith('/profile-photos/'): return value
    return _original_get(self)
def profile_post(self):
    route=urlparse(self.path)
    if route.path.startswith('/api/profiles/'):
        try: return profiles.handle_post(self,route.path,self.body())
        except Exception as ex: return self.json({'error':str(ex)},400)
    return _original_post(self)
App.do_GET=profile_get
App.do_POST=profile_post

if __name__=="__main__":
    init_db()
    host=os.environ.get("HOST","0.0.0.0"); port=int(os.environ.get("PORT","3014"))
    print(f"Tecnologia GeoSer en http://{host}:{port}")
    ThreadingHTTPServer((host,port),App).serve_forever()