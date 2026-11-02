"""Private pilot support reports. Attachments never live in the public static directory."""
from contextlib import closing
from pathlib import Path
import base64,hashlib,json,re,sqlite3,struct,time,zlib
from urllib.parse import urlsplit
from flask import request,jsonify,Response

def clean_png(raw):
    if len(raw)>2*1024*1024 or raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Choose a PNG screenshot under 2 MB.')
    pos=8;parts=[];seen=[]
    while pos<len(raw):
        if pos+12>len(raw):raise ValueError('Invalid screenshot.')
        size=struct.unpack('>I',raw[pos:pos+4])[0];end=pos+12+size
        if end>len(raw):raise ValueError('Invalid screenshot.')
        kind=raw[pos+4:pos+8];data=raw[pos+8:pos+8+size]
        if zlib.crc32(kind+data)&0xffffffff!=struct.unpack('>I',raw[end-4:end])[0]:raise ValueError('Invalid screenshot.')
        if not seen:
            if kind!=b'IHDR' or size!=13:raise ValueError('Invalid screenshot.')
            w,h=struct.unpack('>II',data[:8])
            if not (0<w<=4096 and 0<h<=4096) or w*h>12000000:raise ValueError('Screenshot is too large.')
        if kind in (b'IHDR',b'PLTE',b'tRNS',b'IDAT',b'IEND'):parts.append(raw[pos:end])
        elif kind[:1].isupper():raise ValueError('Unsupported screenshot.')
        seen.append(kind);pos=end
        if kind==b'IEND':break
    if pos!=len(raw) or seen.count(b'IHDR')!=1 or b'IDAT' not in seen or seen[-1]!=b'IEND':raise ValueError('Invalid screenshot.')
    return raw[:8]+b''.join(parts) # Strip ancillary metadata.

def register(app,context):
    path=Path(context['DB_PATH']).parent/'problem_reports.sqlite3'
    def db():
        c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row;return c
    with closing(db()) as c,c:
        c.execute('''CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,pilot TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,status TEXT NOT NULL,description TEXT NOT NULL,expected TEXT NOT NULL,page TEXT NOT NULL,version TEXT NOT NULL,browser TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',screenshot BLOB,token TEXT NOT NULL,UNIQUE(pilot,token))''')
        c.execute('CREATE INDEX IF NOT EXISTS report_pilot_time ON reports(pilot,created)')
    def reply(data,status=200):
        r=jsonify(data);r.status_code=status;r.headers['Cache-Control']='private, no-store';return r
    def user(staff=False):
        import auth
        p=auth.current()
        if not p:return None,reply({'error':'Please sign in.'},401)
        if staff and not p.get('staff'):return None,reply({'error':'Staff access required.'},403)
        return p,None
    def body():
        if request.headers.get('X-PAC-Report')!='1' or request.headers.get('Sec-Fetch-Site')=='cross-site':raise ValueError('Please submit from the PAC website.')
        origin=request.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=request.host:raise ValueError('Please submit from the PAC website.')
        if not request.content_length or request.content_length>2900000:raise ValueError('Report is too large (screenshot limit 2 MB).')
        b=request.get_json(silent=True)
        if not isinstance(b,dict):raise ValueError('Invalid report.')
        return b
    def text(b,k,maximum,required=False):
        v=b.get(k,'')
        if not isinstance(v,str) or len(v)>maximum or (required and len(v.strip())<5):raise ValueError('Please check the '+k+' field.')
        return v.strip()
    def public(r):
        d=dict(r);d['number']=f"PAC-{d['id']:05d}";return d
    fields='id,pilot,created,updated,status,description,expected,page,version,browser,note,(screenshot IS NOT NULL) AS has_screenshot'
    @app.route('/api/problem-reports',methods=['GET','POST'])
    def problem_reports():
        p,e=user()
        if e is not None:return e
        if request.method=='GET':return listing(p,False)
        try:
            b=body();description=text(b,'description',4000,True);expected=text(b,'expected',2000,True)
            page=text(b,'page',80);version=text(b,'version',100);browser=text(b,'browser',120);token=text(b,'token',64,True)
            if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',token):raise ValueError('Invalid submission token.')
            if not re.fullmatch(r'#[a-z-]+(?:/[a-z-]+)?',page):page='#unknown'
            screenshot=None
            if b.get('screenshot'):
                try:screenshot=clean_png(base64.b64decode(b['screenshot'],validate=True))
                except (ValueError,TypeError):raise ValueError('Invalid PNG screenshot. Please select it again.')
            with closing(db()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                old=c.execute('SELECT id FROM reports WHERE pilot=? AND token=?',(p['id'],token)).fetchone()
                if old:return reply({'id':old['id'],'number':f"PAC-{old['id']:05d}"})
                if c.execute('SELECT COUNT(*) FROM reports WHERE pilot=? AND created>?',(p['id'],time.time()-3600)).fetchone()[0]>=5:return reply({'error':'You have sent five reports this hour. Please try again later.'},429)
                now=time.time();rid=c.execute('INSERT INTO reports(pilot,created,updated,status,description,expected,page,version,browser,screenshot,token) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(p['id'],now,now,'New',description,expected,page,version,browser,screenshot,token)).lastrowid
            return reply({'id':rid,'number':f'PAC-{rid:05d}'},201)
        except ValueError as ex:return reply({'error':str(ex)},400)
    def listing(p,staff):
        try:page=max(1,min(100000,int(request.args.get('page',1))))
        except ValueError:page=1
        where='' if staff else ' WHERE pilot=?';args=() if staff else (p['id'],)
        with closing(db()) as c:
            total=c.execute('SELECT COUNT(*) FROM reports'+where,args).fetchone()[0]
            page=min(page,max(1,(total+19)//20))
            rows=c.execute('SELECT '+fields+' FROM reports'+where+' ORDER BY created DESC,id DESC LIMIT 20 OFFSET ?',args+((page-1)*20,)).fetchall()
        return reply({'reports':[public(r) for r in rows],'page':page,'pages':max(1,(total+19)//20),'total':total})
    @app.get('/api/staff/problem-reports')
    def staff_problem_reports():
        p,e=user(True)
        return e if e is not None else listing(p,True)
    @app.post('/api/staff/problem-reports/<int:rid>')
    def update_problem_report(rid):
        p,e=user(True)
        if e is not None:return e
        try:
            b=body();status=text(b,'status',30);note=text(b,'note',2000)
            if status not in ('New','Investigating','Fixed'):raise ValueError('Invalid status.')
            with closing(db()) as c,c:
                changed=c.execute('UPDATE reports SET status=?,note=?,updated=? WHERE id=?',(status,note,time.time(),rid)).rowcount
            return reply({'ok':True}) if changed else reply({'error':'Report not found.'},404)
        except ValueError as ex:return reply({'error':str(ex)},400)
    @app.get('/api/problem-reports/<int:rid>/screenshot')
    def report_screenshot(rid):
        p,e=user()
        if e is not None:return e
        with closing(db()) as c:r=c.execute('SELECT pilot,screenshot FROM reports WHERE id=?',(rid,)).fetchone()
        if not r or (r['pilot']!=p['id'] and not p.get('staff')) or not r['screenshot']:return reply({'error':'Screenshot not found.'},404)
        return Response(r['screenshot'],mimetype='image/png',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Disposition':f'inline; filename="PAC-{rid:05d}.png"','Content-Security-Policy':"default-src 'none'; sandbox"})
