import os, io, csv, time
from datetime import datetime, timedelta, timezone, date
from functools import wraps
from zoneinfo import ZoneInfo
import numpy as np
from flask import Flask, jsonify, request, session, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import face

app = Flask(__name__, static_folder="static")
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///ponto.db").replace("postgres://", "postgresql://", 1),
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-troque-isto"), MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RENDER")), PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
db = SQLAlchemy(app)
TZ = ZoneInfo(os.getenv("TZ_NAME", "America/Sao_Paulo"))
THR = float(os.getenv("FACE_THRESHOLD", "0.45"))
SEM = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
def loc(d): return d.replace(tzinfo=timezone.utc).astimezone(TZ)
def day_range(d):
    s = datetime(d.year, d.month, d.day, tzinfo=TZ); e = s + timedelta(days=1)
    return [x.astimezone(timezone.utc).replace(tzinfo=None) for x in (s, e)]
def iso(d): return d.isoformat() + "Z"

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True); nome = db.Column(db.String(120), nullable=False)
    mat = db.Column(db.String(40), unique=True, nullable=False); senha = db.Column(db.String(255), nullable=False)
    cargo = db.Column(db.String(80), default=""); role = db.Column(db.String(10), default="func")
    def dto(s): return dict(id=s.id, nome=s.nome, mat=s.mat, cargo=s.cargo, role=s.role,
                            face=Face.query.filter_by(user_id=s.id).count())
class Face(db.Model):
    id = db.Column(db.Integer, primary_key=True); user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    emb = db.Column(db.LargeBinary)
class Punch(db.Model):
    id = db.Column(db.Integer, primary_key=True); user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    ts = db.Column(db.DateTime, default=now, index=True); tipo = db.Column(db.Integer)
    score = db.Column(db.Float); foto = db.Column(db.Text)
class Doc(db.Model):
    id = db.Column(db.Integer, primary_key=True); user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    tipo = db.Column(db.String(40)); nome = db.Column(db.String(200)); mime = db.Column(db.String(80))
    dados = db.Column(db.LargeBinary); ts = db.Column(db.DateTime, default=now)
class Msg(db.Model):
    id = db.Column(db.Integer, primary_key=True); user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    de = db.Column(db.String(10)); txt = db.Column(db.Text); ts = db.Column(db.DateTime, default=now)

def j(): return request.get_json(silent=True) or {}
def erro(m, c=400): return jsonify(erro=m), c
def need(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = db.session.get(User, session.get("uid")) if session.get("uid") else None
            if not u: return erro("Sessão expirada", 401)
            if role and u.role != role: return erro("Sem permissão", 403)
            return f(u, *a, **k)
        return w
    return deco
def target(u):  # admin escolhe o funcionário; funcionário só vê o próprio
    return int(request.args.get("uid") or 0) if u.role == "admin" else u.id

fails = {}
@app.post("/api/login")
def login():
    d = j(); mat = str(d.get("mat", "")).strip()
    t = [x for x in fails.get(mat, []) if time.time() - x < 300]
    if len(t) >= 5: return erro("Muitas tentativas. Aguarde 5 minutos.", 429)
    u = User.query.filter_by(mat=mat).first()
    if not u or not check_password_hash(u.senha, str(d.get("senha", ""))):
        fails[mat] = t + [time.time()]; return erro("Matrícula ou senha incorreta", 401)
    session.clear(); session.permanent = True; session["uid"] = u.id
    return jsonify(u.dto())
@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=1)
@app.get("/api/me")
@need()
def me(u): return jsonify(u.dto())

def enroll(u, imgs):
    if not imgs: raise ValueError("Envie as capturas do rosto")
    embs = [face.embed(face.decode(i)) for i in imgs]
    if min(face.score(a, b) for a in embs for b in embs) < 0.4:
        raise ValueError("As capturas parecem de pessoas diferentes. Tente de novo.")
    Face.query.filter_by(user_id=u.id).delete()
    for e in embs: db.session.add(Face(user_id=u.id, emb=e.tobytes()))

@app.get("/api/users")
@need("admin")
def users(u): return jsonify([x.dto() for x in User.query.filter_by(role="func").order_by(User.nome)])
@app.post("/api/users")
@need("admin")
def new_user(u):
    d = j(); nome, mat, senha = (str(d.get(k, "")).strip() for k in ("nome", "mat", "senha"))
    if not (nome and mat and len(senha) >= 4): return erro("Preencha nome, matrícula e senha (mín. 4)")
    if User.query.filter_by(mat=mat).first(): return erro("Matrícula já cadastrada")
    x = User(nome=nome, mat=mat, senha=generate_password_hash(senha), cargo=str(d.get("cargo", ""))[:80])
    try:
        db.session.add(x); db.session.flush(); enroll(x, d.get("images", []))
    except ValueError as m: db.session.rollback(); return erro(str(m))
    db.session.commit(); return jsonify(x.dto())
@app.post("/api/users/<int:i>/face")
@need("admin")
def reface(u, i):
    x = db.get_or_404(User, i)
    try: enroll(x, j().get("images", []))
    except ValueError as m: db.session.rollback(); return erro(str(m))
    db.session.commit(); return jsonify(x.dto())
@app.delete("/api/users/<int:i>")
@need("admin")
def del_user(u, i):
    x = db.get_or_404(User, i)
    if x.role == "admin": return erro("Não é possível remover o admin")
    for M in (Face, Punch, Doc, Msg): M.query.filter_by(user_id=i).delete()
    db.session.delete(x); db.session.commit(); return jsonify(ok=1)

@app.post("/api/punch")
@need()
def punch(u):
    if u.role != "func": return erro("Apenas funcionários batem ponto")
    s, e = day_range(loc(now()).date())
    hoje = Punch.query.filter(Punch.user_id == u.id, Punch.ts >= s, Punch.ts < e).order_by(Punch.ts).all()
    if len(hoje) >= 4: return erro("Jornada de hoje já concluída")
    if hoje and (now() - hoje[-1].ts).seconds < 60: return erro("Aguarde 1 minuto entre as batidas")
    embs = [np.frombuffer(f.emb, np.float32) for f in Face.query.filter_by(user_id=u.id)]
    if not embs: return erro("Rosto não cadastrado. Procure o administrador.")
    try: img = face.decode(j().get("image", "")); emb = face.embed(img)
    except ValueError as m: return erro(str(m))
    sc = max(face.score(emb, x) for x in embs)
    if sc < THR: return erro(f"Rosto não reconhecido (similaridade {sc:.2f})", 403)
    p = Punch(user_id=u.id, tipo=len(hoje), score=round(sc, 3), foto=face.thumb(img))
    db.session.add(p); db.session.commit()
    return jsonify(tipo=p.tipo, ts=iso(p.ts), score=p.score)

@app.get("/api/punches")
@need()
def punches(u):
    q = Punch.query; uid = target(u)
    if uid: q = q.filter_by(user_id=uid)
    if request.args.get("dia"):
        s, e = day_range(date.fromisoformat(request.args["dia"])); q = q.filter(Punch.ts >= s, Punch.ts < e)
    names = {x.id: x.nome for x in User.query}
    return jsonify([dict(id=p.id, uid=p.user_id, nome=names.get(p.user_id, "?"), ts=iso(p.ts), tipo=p.tipo,
                         score=p.score, foto=p.foto) for p in q.order_by(Punch.ts.desc()).limit(300)])

def mirror(uid, mon):
    y, m = map(int, mon.split("-")); a = date(y, m, 1); b = date(y + (m == 12), m % 12 + 1, 1)
    s, e = day_range(a)[0], day_range(b)[0]; by = {}
    for p in Punch.query.filter(Punch.user_id == uid, Punch.ts >= s, Punch.ts < e).order_by(Punch.ts):
        by.setdefault(loc(p.ts).date(), []).append(loc(p.ts))
    rows, tot = [], 0
    for n in range((b - a).days):
        d = a + timedelta(days=n); t = by.get(d, []); w = 0
        if len(t) > 1: w += int((t[1] - t[0]).total_seconds() // 60)
        if len(t) > 3: w += int((t[3] - t[2]).total_seconds() // 60)
        rows.append(dict(dia=d.strftime("%d/%m"), sem=SEM[d.weekday()], bat=[x.strftime("%H:%M") for x in t], min=w)); tot += w
    return rows, tot
@app.get("/api/mirror")
@need()
def mirror_api(u):
    uid = target(u); x = db.get_or_404(User, uid); rows, tot = mirror(uid, request.args["mon"])
    return jsonify(user=x.dto(), rows=rows, total=tot)
@app.get("/api/mirror.csv")
@need()
def mirror_csv(u):
    uid = target(u); x = db.get_or_404(User, uid); rows, tot = mirror(uid, request.args["mon"])
    o = io.StringIO(); w = csv.writer(o, delimiter=";"); w.writerow(["Dia", "Semana", "Entrada", "Saída almoço", "Volta almoço", "Saída", "Minutos"])
    for r in rows: w.writerow([r["dia"], r["sem"]] + (r["bat"] + [""] * 4)[:4] + [r["min"]])
    w.writerow(["Total", "", "", "", "", "", tot])
    return send_file(io.BytesIO(("\ufeff" + o.getvalue()).encode()), mimetype="text/csv", as_attachment=True,
                     download_name=f"espelho_{x.mat}_{request.args['mon']}.csv")

@app.get("/api/docs")
@need()
def docs(u):
    q = Doc.query if u.role == "admin" else Doc.query.filter_by(user_id=u.id)
    names = {x.id: x.nome for x in User.query}
    return jsonify([dict(id=d.id, nome_func=names.get(d.user_id, "?"), tipo=d.tipo, nome=d.nome, ts=iso(d.ts))
                    for d in q.order_by(Doc.ts.desc())])
@app.post("/api/docs")
@need("func")
def up_doc(u):
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")): return erro("Envie PDF, PNG ou JPG")
    d = Doc(user_id=u.id, tipo=request.form.get("tipo", "Outro")[:40], nome=f.filename[:200], mime=f.mimetype, dados=f.read())
    db.session.add(d); db.session.commit(); return jsonify(ok=1)
@app.get("/api/docs/<int:i>/file")
@need()
def doc_file(u, i):
    d = db.get_or_404(Doc, i)
    if u.role != "admin" and d.user_id != u.id: return erro("Sem permissão", 403)
    return send_file(io.BytesIO(d.dados), mimetype=d.mime, download_name=d.nome)
@app.delete("/api/docs/<int:i>")
@need()
def del_doc(u, i):
    d = db.get_or_404(Doc, i)
    if u.role != "admin" and d.user_id != u.id: return erro("Sem permissão", 403)
    db.session.delete(d); db.session.commit(); return jsonify(ok=1)

@app.get("/api/msgs")
@need()
def msgs(u):
    return jsonify([dict(de=m.de, txt=m.txt, ts=iso(m.ts)) for m in Msg.query.filter_by(user_id=target(u)).order_by(Msg.ts)])
@app.post("/api/msgs")
@need()
def send_msg(u):
    d = j(); txt = str(d.get("txt", "")).strip()[:2000]; uid = int(d.get("uid") or 0) if u.role == "admin" else u.id
    if not txt or not uid: return erro("Mensagem vazia")
    db.session.add(Msg(user_id=uid, de=u.role == "admin" and "admin" or "func", txt=txt)); db.session.commit()
    return jsonify(ok=1)

@app.get("/health")
def health(): return "ok"
@app.get("/")
def index(): return send_from_directory("static", "index.html")

with app.app_context():
    db.create_all()
    if not User.query.filter_by(role="admin").first():
        db.session.add(User(nome="Administrador", mat=os.getenv("ADMIN_MAT", "admin"), role="admin",
                            senha=generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123"))))
        db.session.commit()
if __name__ == "__main__": app.run(debug=True)
