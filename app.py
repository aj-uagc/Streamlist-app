import os
import sqlite3
import json
import uuid
import time
import bcrypt
import jwt
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.environ.get("DB_PATH", "eztech.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev_secret_change")
JWT_ISS = "eztechmovie"
JWT_AUD = "eztechmovie_app"

app = Flask(name, static_folder="static", template_folder="templates")
CORS(app, supports_credentials=True)

def db():
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
return conn

def init_db():
with db() as conn, open("schema.sql", "r", encoding="utf-8") as f:
conn.executescript(f.read())
cur = conn.execute("SELECT COUNT(*) c FROM movies")
if cur.fetchone()["c"] == 0:
sample = [
("The Matrix", 1999, "R", "A hacker learns truth about reality.", "https://m.media-amazon.com/images/I/51vpnbwFHrL.AC.jpg"),
("Inception", 2010, "PG-13", "A thief enters dreams to steal secrets.", "https://m.media-amazon.com/images/I/51s+EoZl6tL.AC.jpg"),
("Interstellar", 2014, "PG-13", "Explorers travel through a wormhole.", "https://m.media-amazon.com/images/I/71n58bVZ0hL.AC_SL1024.jpg"),
("Spider-Man: Into the Spider-Verse", 2018, "PG", "Miles meets many Spider-heroes.", "https://m.media-amazon.com/images/I/91C0bW2i8jL.AC_SL1500.jpg"),
("Soul", 2020, "PG", "A musician seeks his purpose.", "https://m.media-amazon.com/images/I/81jqf3Tz6oL.AC_SL1500.jpg")
]
conn.executemany(
"INSERT INTO movies (title,year,rating,description,poster) VALUES (?,?,?,?,?)",
sample
)

def token_for_user(user_id, email, name):
now = datetime.utcnow()
payload = {
"sub": str(user_id),
"email": email,
"name": name,
"iss": JWT_ISS,
"aud": JWT_AUD,
"iat": int(now.timestamp()),
"exp": int((now + timedelta(hours=12)).timestamp())
}
return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def auth_required(f):
@wraps(f)
def wrapper(*args, **kwargs):
auth = request.headers.get("Authorization", "")
parts = auth.split(" ")
if len(parts) == 2 and parts[0].lower() == "bearer":
token = parts[1]
try:
payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience=JWT_AUD, issuer=JWT_ISS)
request.user = {"id": int(payload["sub"]), "email": payload["email"], "name": payload["name"]}
return f(*args, **kwargs)
except Exception:
return jsonify({"error": "auth_failed"}), 401
return jsonify({"error": "no_token"}), 401
return wrapper

@app.route("/")
def index():
return send_from_directory("templates", "index.html")

@app.route("/api/auth/register", methods=["POST"])
def register():
data = request.get_json(force=True)
email = data.get("email","").strip().lower()
name = data.get("name","").strip()
pw = data.get("password","")
if not email or not name or not pw:
return jsonify({"error":"missing_fields"}), 400
pw_hash = generate_password_hash(pw)
with db() as conn:
try:
conn.execute("INSERT INTO users (email,name,password_hash) VALUES (?,?,?)",(email,name,pw_hash))
uid = conn.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()["id"]
# start an open cart
conn.execute("INSERT INTO carts (user_id,status) VALUES (?,?)",(uid,"open"))
tok = token_for_user(uid, email, name)
return jsonify({"token": tok})
except sqlite3.IntegrityError:
return jsonify({"error":"email_taken"}), 409

@app.route("/api/auth/login", methods=["POST"])
def login():
data = request.get_json(force=True)
email = data.get("email","").strip().lower()
pw = data.get("password","")
with db() as conn:
row = conn.execute("SELECT id,email,name,password_hash FROM users WHERE email=?",(email,)).fetchone()
if not row:
return jsonify({"error":"invalid_login"}), 401
if not check_password_hash(row["password_hash"], pw):
return jsonify({"error":"invalid_login"}), 401
tok = token_for_user(row["id"], row["email"], row["name"])
return jsonify({"token": tok})

@app.route("/api/profile", methods=["GET","PATCH"])
@auth_required
def profile():
uid = request.user["id"]
with db() as conn:
if request.method == "GET":
row = conn.execute("SELECT id,email,name,plan FROM users WHERE id=?",(uid,)).fetchone()
return jsonify(dict(row))
data = request.get_json(force=True)
plan = data.get("plan")
if plan not in ["individual","friendly","family"]:
return jsonify({"error":"bad_plan"}), 400
conn.execute("UPDATE users SET plan=? WHERE id=?",(plan,uid))
return jsonify({"ok": True})

@app.route("/api/movies", methods=["GET"])
def movies():
q = request.args.get("q","").strip().lower()
with db() as conn:
if q:
rows = conn.execute(
"SELECT * FROM movies WHERE lower(title) LIKE ? ORDER BY title",
(f"%{q}%",)
).fetchall()
else:
rows = conn.execute("SELECT * FROM movies ORDER BY title").fetchall()
return jsonify([dict(r) for r in rows])

@app.route("/api/lists", methods=["GET","POST"])
@auth_required
def lists():
uid = request.user["id"]
with db() as conn:
if request.method == "GET":
rows = conn.execute("SELECT * FROM lists WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
return jsonify([dict(r) for r in rows])
data = request.get_json(force=True)
name = data.get("name","").strip()
visibility = data.get("visibility","private")
if visibility not in ["private","family","public"]:
return jsonify({"error":"bad_visibility"}), 400
if not name:
return jsonify({"error":"name_required"}), 400
cur = conn.execute("INSERT INTO lists (user_id,name,visibility) VALUES (?,?,?)",(uid,name,visibility))
return jsonify({"id": cur.lastrowid, "name": name, "visibility": visibility})

@app.route("/api/lists/int:list_id", methods=["DELETE","PATCH","GET"])
@auth_required
def list_detail(list_id):
uid = request.user["id"]
with db() as conn:
owner = conn.execute("SELECT * FROM lists WHERE id=? AND user_id=?",(list_id,uid)).fetchone()
if not owner:
return jsonify({"error":"not_found"}), 404
if request.method == "GET":
items = conn.execute("""
SELECT li.id, m.id movie_id, m.title, m.year
FROM list_items li JOIN movies m ON m.id=li.movie_id
WHERE li.list_id=? ORDER BY li.id DESC
""",(list_id,)).fetchall()
d = dict(owner)
d["items"] = [dict(i) for i in items]
return jsonify(d)
if request.method == "DELETE":
conn.execute("DELETE FROM lists WHERE id=?",(list_id,))
return jsonify({"ok": True})
data = request.get_json(force=True)
name = data.get("name")
visibility = data.get("visibility")
if visibility and visibility not in ["private","family","public"]:
return jsonify({"error":"bad_visibility"}), 400
if name:
conn.execute("UPDATE lists SET name=? WHERE id=?",(name,list_id))
if visibility:
conn.execute("UPDATE lists SET visibility=? WHERE id=?",(visibility,list_id))
return jsonify({"ok": True})

@app.route("/api/lists/int:list_id/items", methods=["POST","DELETE"])
@auth_required
def list_items(list_id):
uid = request.user["id"]
with db() as conn:
owner = conn.execute("SELECT * FROM lists WHERE id=? AND user_id=?",(list_id,uid)).fetchone()
if not owner:
return jsonify({"error":"not_found"}), 404
if request.method == "POST":
data = request.get_json(force=True)
movie_id = int(data.get("movie_id"))
conn.execute("INSERT INTO list_items (list_id,movie_id) VALUES (?,?)",(list_id,movie_id))
return jsonify({"ok": True})
data = request.get_json(force=True)
item_id = int(data.get("item_id"))
conn.execute("DELETE FROM list_items WHERE id=? AND list_id=?",(item_id,list_id))
return jsonify({"ok": True})

def get_open_cart(conn, uid):
row = conn.execute("SELECT * FROM carts WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
if row: return row
conn.execute("INSERT INTO carts (user_id,status) VALUES (?,?)",(uid,"open"))
return conn.execute("SELECT * FROM carts WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(uid,)).fetchone()

@app.route("/api/cart", methods=["GET","POST","DELETE"])
@auth_required
def cart():
uid = request.user["id"]
with db() as conn:
cart = get_open_cart(conn, uid)
if request.method == "GET":
items = conn.execute("SELECT * FROM cart_items WHERE cart_id=? ORDER BY id",(cart["id"],)).fetchall()
total = sum(r["price_cents"]*r["qty"] for r in items)
return jsonify({"cart_id": cart["id"], "status": cart["status"], "items":[dict(r) for r in items], "total_cents": total})
if request.method == "DELETE":
conn.execute("DELETE FROM cart_items WHERE cart_id=?",(cart["id"],))
return jsonify({"ok": True})
data = request.get_json(force=True)
sku = data.get("sku")
name = data.get("name")
price_cents = int(data.get("price_cents",0))
qty = int(data.get("qty",1))
if not sku or not name or price_cents<=0 or qty<=0:
return jsonify({"error":"bad_item"}), 400
conn.execute("INSERT INTO cart_items (cart_id,sku,name,price_cents,qty) VALUES (?,?,?,?,?)",(cart["id"],sku,name,price_cents,qty))
return jsonify({"ok": True})

@app.route("/api/cart/item/int:item_id", methods=["PATCH","DELETE"])
@auth_required
def cart_item(item_id):
uid = request.user["id"]
with db() as conn:
cart = get_open_cart(conn, uid)
row = conn.execute("SELECT * FROM cart_items WHERE id=? AND cart_id=?",(item_id,cart["id"])).fetchone()
if not row:
return jsonify({"error":"not_found"}), 404
if request.method == "DELETE":
conn.execute("DELETE FROM cart_items WHERE id=?",(item_id,))
return jsonify({"ok": True})
data = request.get_json(force=True)
qty = int(data.get("qty", row["qty"]))
if qty<=0: return jsonify({"error":"bad_qty"}), 400
conn.execute("UPDATE cart_items SET qty=? WHERE id=?",(qty,item_id))
return jsonify({"ok": True})

def luhn_ok(pan):
digits = [int(c) for c in pan if c.isdigit()]
if len(digits) < 12 or len(digits) > 19: return False
s = 0
alt = False
for d in digits[::-1]:
t = d*2 if alt else d
if t>9: t-=9
s += t
alt = not alt
return s % 10 == 0

def brand_for(pan):
if pan.startswith("4"): return "visa"
if pan.startswith(("51","52","53","54","55")): return "mastercard"
if pan.startswith(("34","37")): return "amex"
if pan.startswith("6"): return "discover"
return "card"

@app.route("/api/cards", methods=["GET","POST"])
@auth_required
def cards():
uid = request.user["id"]
with db() as conn:
if request.method == "GET":
rows = conn.execute("SELECT id,brand,last4,exp_month,exp_year,label,created_at FROM cards WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
return jsonify([dict(r) for r in rows])
data = request.get_json(force=True)
pan = data.get("pan","").replace(" ","")
exp_month = int(data.get("exp_month",0))
exp_year = int(data.get("exp_year",0))
label = data.get("label","Primary")
if not luhn_ok(pan):
return jsonify({"error":"invalid_pan"}), 400
if exp_month<1 or exp_month>12 or exp_year<datetime.utcnow().year:
return jsonify({"error":"invalid_exp"}), 400
token = "tok_" + uuid.uuid4().hex
last4 = pan[-4:]
brand = brand_for(pan)
conn.execute(
"INSERT INTO cards (user_id,brand,last4,exp_month,exp_year,token,label) VALUES (?,?,?,?,?,?,?)",
(uid,brand,last4,exp_month,exp_year,token,label)
)
return jsonify({"ok": True})

@app.route("/api/cards/int:card_id", methods=["DELETE","PATCH"])
@auth_required
def card_detail(card_id):
uid = request.user["id"]
with db() as conn:
row = conn.execute("SELECT * FROM cards WHERE id=? AND user_id=?",(card_id,uid)).fetchone()
if not row:
return jsonify({"error":"not_found"}), 404
if request.method == "DELETE":
conn.execute("DELETE FROM cards WHERE id=?",(card_id,))
return jsonify({"ok": True})
data = request.get_json(force=True)
label = data.get("label")
if label:
conn.execute("UPDATE cards SET label=? WHERE id=?",(label,card_id))
return jsonify({"ok": True})

@app.route("/api/checkout", methods=["POST"])
@auth_required
def checkout():
uid = request.user["id"]
data = request.get_json(force=True)
card_id = int(data.get("card_id",0))
with db() as conn:
cart = get_open_cart(conn, uid)
items = conn.execute("SELECT * FROM cart_items WHERE cart_id=?",(cart["id"],)).fetchall()
if not items:
return jsonify({"error":"cart_empty"}), 400
card = conn.execute("SELECT * FROM cards WHERE id=? AND user_id=?",(card_id,uid)).fetchone()
if not card:
return jsonify({"error":"card_required"}), 400
total = sum(r["price_cents"]*r["qty"] for r in items)
order_id = "ord_" + uuid.uuid4().hex[:12]
conn.execute("UPDATE carts SET status='paid' WHERE id=?",(cart["id"],))
conn.execute("INSERT INTO carts (user_id,status) VALUES (?,?)",(uid,"open"))
return jsonify({"order_id": order_id, "total_cents": total})

@app.route("/api/services", methods=["GET"])
def services():
catalog = [
{"sku":"plan_individual","name":"Individual Plan Monthly","price_cents":899},
{"sku":"plan_friendly","name":"Friendly Plan Monthly","price_cents":1299},
{"sku":"plan_family","name":"Family Plan Monthly","price_cents":1799},
{"sku":"streamlist_basic","name":"StreamList Basic","price_cents":199},
{"sku":"streamlist_gold","name":"StreamList Gold","price_cents":399},
{"sku":"streamlist_premium","name":"StreamList Premium","price_cents":699}
]
return jsonify(catalog)

@app.route("/api/db")
def health():
try:
with db() as conn:
conn.execute("SELECT 1")
return jsonify({"ok": True})
except Exception as e:
return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/path:path")
def static_proxy(path):
if os.path.exists(os.path.join("static", path)):
return send_from_directory("static", path)
return send_from_directory("templates", "index.html")

if name == "main":
init_db()
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))