const API = {
async get(path) { return req("GET", path) },
async post(path, body) { return req("POST", path, body) },
async patch(path, body) { return req("PATCH", path, body) },
async del(path, body) { return req("DELETE", path, body) },
};

function token() { return localStorage.getItem("jwt") || ""; }
function setToken(t) { localStorage.setItem("jwt", t); syncAuthBar(); }
function clearToken() { localStorage.removeItem("jwt"); syncAuthBar(); }

async function req(method, path, body) {
const headers = {"Content-Type":"application/json"};
if (token()) headers["Authorization"] = "Bearer " + token();
const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
if (!res.ok) {
const e = await res.json().catch(()=>({error:"request_failed"}));
throw e;
}
return res.json();
}

const view = document.getElementById("view");
const who = document.getElementById("who");
document.getElementById("nav-home").onclick = showHome;
document.getElementById("nav-movies").onclick = showMovies;
document.getElementById("nav-lists").onclick = showLists;
document.getElementById("nav-services").onclick = showServices;
document.getElementById("nav-cart").onclick = showCart;
document.getElementById("nav-cards").onclick = showCards;
document.getElementById("btn-login").onclick = showLogin;
document.getElementById("btn-logout").onclick = () => { clearToken(); showHome(); };

function el(tag, attrs={}, children=[]) {
const e = document.createElement(tag);
for (const k in attrs) {
if (k === "class") e.className = attrs[k];
else if (k.startsWith("on")) e.addEventListener(k.slice(2), attrs[k]);
else e.setAttribute(k, attrs[k]);
}
for (const c of children) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
return e;
}

async function syncAuthBar() {
if (!token()) {
who.textContent = "";
document.getElementById("btn-login").style.display = "inline-block";
document.getElementById("btn-logout").style.display = "none";
return;
}
try {
const me = await API.get("/api/profile");
who.textContent = ${me.name} • ${me.plan};
document.getElementById("btn-login").style.display = "none";
document.getElementById("btn-logout").style.display = "inline-block";
} catch (_) {
clearToken();
}
}

function showHome() {
view.innerHTML = "";
view.appendChild(el("div",{class:"card"},[
el("h2",{},["Welcome"]),
el("p",{},["Use the nav to log in, browse movies, manage StreamList, select services, manage cards, and checkout."]),
]));
}

function showLogin() {
view.innerHTML = "";
const email = el("input",{class:"input",placeholder:"Email",type:"email"});
const name = el("input",{class:"input",placeholder:"Name"});
const pw = el("input",{class:"input",placeholder:"Password",type:"password"});
const wrap = el("div",{class:"card"},[
el("h2",{},["Login / Register"]),
el("div",{class:"row"},[
el("div",{style:"flex:1"},[el("label",{},["Email"]), email]),
el("div",{style:"flex:1"},[el("label",{},["Name (register)"]), name]),
el("div",{style:"flex:1"},[el("label",{},["Password"]), pw]),
]),
el("div",{class:"row"},[
el("button",{onclick:async()=>{
try {
const r = await API.post("/api/auth/login",{email:email.value,password:pw.value});
setToken(r.token); showHome();
} catch(e){ alert(e.error || "login_failed"); }
}},["Login"]),
el("button",{onclick:async()=>{
try {
const r = await API.post("/api/auth/register",{email:email.value,name:name.value,password:pw.value});
setToken(r.token); showHome();
} catch(e){ alert(e.error || "register_failed"); }
}},["Register"])
])
]);
view.appendChild(wrap);
}

async function showMovies() {
view.innerHTML = "";
const q = el("input",{class:"input",placeholder:"Search title"});
const grid = el("div",{class:"grid"},[]);
const box = el("div",{class:"card"},[
el("h2",{},["Movies"]),
q,
el("div",{},[grid])
]);
view.appendChild(box);
async function load() {
const list = await API.get("/api/movies"+(q.value??q=${encodeURIComponent(q.value)}:""));
grid.innerHTML="";
list.forEach(m=>{
const card = el("div",{class:"card"},[
el("div",{class:"row"},[
el("img",{src:m.poster,alt:m.title,style:"width:80px;height:120px;object-fit:cover;border-radius:8px;border:1px solid #1f2a37"}),
el("div",{},[
el("h3",{},[m.title]),
el("div",{},[Year: ${m.year} • Rated: ${m.rating}]),
el("p",{},[m.description]),
el("div",{class:"row"},[
el("button",{onclick:()=>addToListPrompt(m.id)},["Add to StreamList"])
])
])
])
]);
grid.appendChild(card);
});
}
q.addEventListener("input",()=>load());
await load();
}

async function ensureAuth() { if (!token()) { showLogin(); throw new Error("noauth"); } }

async function addToListPrompt(movie_id) {
try { await ensureAuth(); } catch(_) { return; }
const lists = await API.get("/api/lists");
const name = prompt("List name for new one, or leave empty to pick existing");
if (name && name.trim()) {
const created = await API.post("/api/lists",{name, visibility:"private"});
await API.post(/api/lists/${created.id}/items,{movie_id});
alert("Added");
return;
}
if (!lists.length) { alert("No lists"); return; }
const pick = prompt("Pick list id:\n"+lists.map(l=>${l.id}: ${l.name}).join("\n"));
const id = parseInt(pick||"",10);
if (!id) return;
await API.post(/api/lists/${id}/items,{movie_id});
alert("Added");
}

async function showLists() {
try { await ensureAuth(); } catch(_) { return; }
view.innerHTML = "";
const wrap = el("div",{class:"card"},[
el("h2",{},["StreamList"]),
el("div",{class:"row"},[
el("button",{onclick:async()=>{
const name = prompt("List name");
if (!name) return;
await API.post("/api/lists",{name,visibility:"private"});
load();
}},["New List"])
]),
el("div",{id:"lists"})
]);
view.appendChild(wrap);
async function load() {
const holder = document.getElementById("lists");
holder.innerHTML = "";
const lists = await API.get("/api/lists");
for (const l of lists) {
const detail = await API.get(/api/lists/${l.id});
const card = el("div",{class:"card"},[
el("div",{class:"row",style:"justify-content:space-between;align-items:center"},[
el("h3",{},[l.name," ",el("span",{class:"tag"},[l.visibility])]),
el("div",{class:"action"},[
el("button",{onclick:async()=>{
const v = prompt("visibility: private | family | public", l.visibility);
if (!v) return;
await API.patch(/api/lists/${l.id},{visibility:v});
load();
}},["Visibility"]),
el("button",{onclick:async()=>{ await API.del(/api/lists/${l.id}); load(); }},["Delete"])
])
]),
el("div",{},[
detail.items.length? "" : "Empty",
...detail.items.map(it=>el("div",{class:"row",style:"justify-content:space-between"},[
el("div",{},[${it.title} (${it.year})]),
el("button",{onclick:async()=>{ await API.del(/api/lists/${l.id}/items,{item_id:it.id}); load(); }},["Remove"])
]))
])
]);
holder.appendChild(card);
}
}
load();
}

async function showServices() {
view.innerHTML = "";
const list = await API.get("/api/services");
const grid = el("div",{class:"grid"},[]);
list.forEach(s=>{
const card = el("div",{class:"card"},[
el("h3",{},[s.name]),
el("p",{},[SKU: ${s.sku}]),
el("strong",{},[$${(s.price_cents/100).toFixed(2)}]),
el("div",{class:"row"},[
el("button",{onclick:async()=>{
try { await ensureAuth(); } catch(_) { return; }
await API.post("/api/cart",{sku:s.sku,name:s.name,price_cents:s.price_cents,qty:1});
alert("Added to cart");
}},["Add to cart"])
])
]);
grid.appendChild(card);
});
const planBox = el("div",{class:"card"},[
el("h3",{},["Manage Plan"]),
el("div",{class:"row"},[
el("button",{onclick:()=>updatePlan("individual")},["Individual"]),
el("button",{onclick:()=>updatePlan("friendly")},["Friendly"]),
el("button",{onclick:()=>updatePlan("family")},["Family"]),
]),
el("small",{},["Plan affects simultaneous streams."])
]);
view.appendChild(planBox);
view.appendChild(el("div",{},[grid]));
}

async function updatePlan(plan) {
try { await ensureAuth(); } catch(_) { return; }
await API.patch("/api/profile",{plan});
await syncAuthBar();
alert("Plan updated");
}

async function showCart() {
try { await ensureAuth(); } catch(_) { return; }
view.innerHTML = "";
const data = await API.get("/api/cart");
const items = data.items;
const tbl = el("table",{class:"table"},[
el("thead",{},[el("tr",{},[
el("th",{},["SKU"]), el("th",{},["Name"]), el("th",{},["Price"]), el("th",{},["Qty"]), el("th",{},["Actions"])
])]),
el("tbody",{},items.map(it=>el("tr",{},[
el("td",{},[it.sku]),
el("td",{},[it.name]),
el("td",{},[$${(it.price_cents/100).toFixed(2)}]),
el("td",{},[String(it.qty)]),
el("td",{},[
el("button",{onclick:async()=>{ await API.patch(/api/cart/item/${it.id},{qty:it.qty+1}); showCart(); }},["+"]),
el("button",{onclick:async()=>{
if (it.qty>1) { await API.patch(/api/cart/item/${it.id},{qty:it.qty-1}); }
else { await API.del(/api/cart/item/${it.id}); }
showCart();
}},["-"])
])
])))
]);
const total = el("h3",{},[Total: $${(data.total_cents/100).toFixed(2)}]);
const cardPicker = await buildCardPicker();
const actions = el("div",{class:"row"},[
el("button",{onclick:async()=>{ await API.del("/api/cart"); showCart(); }},["Clear Cart"]),
el("button",{onclick:async()=>{
const sel = cardPicker.querySelector("select");
if (!sel.value) { alert("Select card"); return; }
const r = await API.post("/api/checkout",{card_id: parseInt(sel.value,10)});
alert(Paid. Order ${r.order_id}.);
showCart();
}},["Checkout"])
]);
view.appendChild(el("div",{class:"card"},[
el("h2",{},["Cart"]),
tbl, total, cardPicker, actions
]));
}

async function buildCardPicker() {
const wrap = el("div",{class:"card"},[
el("h3",{},["Payment"]),
el("div",{class:"row"},[
el("div",{style:"flex:1"},[
el("label",{},["Cards"]),
el("select",{id:"card_sel",class:"input"},[])
]),
el("button",{onclick:showCards},["Manage Cards"])
])
]);
const sel = wrap.querySelector("select");
const cards = await API.get("/api/cards");
sel.appendChild(el("option",{value:""},["Select..."]))
cards.forEach(c=>{
const txt = ${c.label || c.brand} •••• ${c.last4} • ${String(c.exp_month).padStart(2,"0")}/${String(c.exp_year).slice(-2)};
sel.appendChild(el("option",{value:String(c.id)},[txt]));
});
return wrap;
}

async function showCards() {
try { await ensureAuth(); } catch(_) { return; }
view.innerHTML = "";
const listWrap = el("div",{id:"cards"});
const addWrap = el("div",{class:"card"},[
el("h2",{},["Cards"]),
el("div",{class:"row"},[
el("input",{class:"input",id:"pan",placeholder:"Card number"}),
el("input",{class:"input",id:"expm",placeholder:"MM"}),
el("input",{class:"input",id:"expy",placeholder:"YYYY"}),
el("input",{class:"input",id:"label",placeholder:"Label"})
]),
el("div",{class:"row"},[
el("button",{onclick:async()=>{
const pan = document.getElementById("pan").value.trim();
const expm = parseInt(document.getElementById("expm").value,10);
const expy = parseInt(document.getElementById("expy").value,10);
const label = document.getElementById("label").value.trim() || "Primary";
try {
await API.post("/api/cards",{pan,exp_month:expm,exp_year:expy,label});
showCards();
} catch(e){ alert(e.error || "card_error"); }
}},["Add Card"])
])
]);
view.appendChild(addWrap);
view.appendChild(listWrap);

async function load() {
listWrap.innerHTML = "";
const cards = await API.get("/api/cards");
if (!cards.length) {
listWrap.appendChild(el("div",{class:"card"},["No cards"]));
return;
}
cards.forEach(c=>{
const row = el("div",{class:"card"},[
el("div",{class:"row",style:"justify-content:space-between;align-items:center"},[
el("div",{},[${c.brand} •••• ${c.last4} • ${String(c.exp_month).padStart(2,"0")}/${String(c.exp_year).slice(-2)} • ${c.label||""}]),
el("div",{class:"action"},[
el("button",{onclick:async()=>{
const v = prompt("Label", c.label||"");
if (v==null) return;
await API.patch(/api/cards/${c.id},{label:v});
load();
}},["Label"]),
el("button",{onclick:async()=>{ await API.del(/api/cards/${c.id}); load(); }},["Delete"])
])
])
]);
listWrap.appendChild(row);
});
}
load();
}

(async function boot(){
await syncAuthBar();
showHome();
})();