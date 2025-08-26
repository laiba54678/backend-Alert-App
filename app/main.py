# TOP OF FILE
from datetime import datetime, timedelta, timezone

from bson.errors import InvalidId

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from bson import ObjectId
from .db import get_db
from .utils import hash_password, verify_password, to_str_id
from . import schemas
from .kafka_client import send_alert_event, close_producer

from pydantic import BaseModel, EmailStr
from typing import Optional, List

from typing import Optional, List
from pydantic import BaseModel

app = FastAPI(title="Panic Backend", version="1.0.0")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"],
#     allow_credentials=True,
# )

ALLOWED_ORIGINS = [
       "https://alert-app-2-kjzee36pr-laiba54678s-projects.vercel.app",  # your frontend URL,  # your frontend URL
    "http://localhost:5173",             # local dev (Vite)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

@app.get("/ping")
async def ping():
    db = get_db()
    collections = await db.list_collection_names()
    return {"status": "ok", "collections": collections}

@app.on_event("shutdown")
async def shutdown_event():
    await close_producer()



# -------- AUTH --------

@app.post("/register", response_model=schemas.RegisterOut, status_code=201)
async def register(body: schemas.RegisterIn):
    db = get_db()
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    doc = {
        "name": body.name,
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "usertype": body.usertype,
    }
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    out = to_str_id(doc)
    return {
        "id": out["id"],
        "name": out["name"],
        "email": out["email"],
        "usertype": out["usertype"],
    }



@app.post("/login", response_model=schemas.LoginOut)
async def login(body: schemas.LoginIn):
    db = get_db()
    user = await db.users.find_one({"email": body.email.lower()})
    if not user:
        return {"exists": False, "usertype": None}
    if not verify_password(body.password, user["password_hash"]):
        # exists but wrong password -> do not reveal usertype
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return {"exists": True, "usertype": user.get("usertype")}



# -------- ALERTS --------

@app.post("/alerts", response_model=schemas.AlertOut, status_code=201)
async def create_alert(body: schemas.AlertCreateIn):
    db = get_db()
    # ensure sender exists
    sender = await db.users.find_one({"email": body.sender_email.lower()})
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    alert_doc = {
        "sender_email": body.sender_email.lower(),
        "location": {"lat": body.location.lat, "lng": body.location.lng},
        "alert_type": body.alert_type,
        "status": "pending",
        "accepted_by": None,
        "created_at": datetime.now(timezone.utc),
        "accepted_at": None,                  
        "resolved_at": None                   
    }

    res = await db.alerts.insert_one(alert_doc)
    alert_doc["_id"] = res.inserted_id
    out = to_str_id(alert_doc)
    # send Kafka event
    await send_alert_event("alert_created", out)
    return {
        "id": out["id"],
        "sender_email": out["sender_email"],
        "location": out["location"],
        "alert_type": out["alert_type"],
        "status": out["status"],
        "accepted_by": out["accepted_by"],
    }

from pydantic import BaseModel

class AcceptAlertIn(BaseModel):
    agent_email: str

@app.post("/alerts/{alert_id}/accept", response_model=schemas.AlertOut)
async def accept_alert(alert_id: str, body: AcceptAlertIn):
    db = get_db()
    agent = await db.users.find_one({"email": body.agent_email.lower(), "usertype": "agent"})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    alert = await db.alerts.find_one({"_id": ObjectId(alert_id)})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.get("status") == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")
    update = {"$set": {"status": "accepted", "accepted_by": body.agent_email.lower()}}
    await db.alerts.update_one({"_id": ObjectId(alert_id)}, update)
    alert.update({"status": "accepted", "accepted_by": body.agent_email.lower()})
    out = to_str_id(alert)
    await send_alert_event("alert_accepted", out)
    return {
        "id": out["id"],
        "sender_email": out["sender_email"],
        "location": out["location"],
        "alert_type": out["alert_type"],
        "status": out["status"],
        "accepted_by": out["accepted_by"],
        "accepted_at": datetime.now(timezone.utc)  # <-- consistent with resolved_at
    }






@app.post("/alerts/{alert_id}/resolve", response_model=schemas.AlertOut)
async def resolve_alert(alert_id: str):
    db = get_db()
    alert = await db.alerts.find_one({"_id": ObjectId(alert_id)})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    update = {"$set": {"status": "resolved"}}
    await db.alerts.update_one({"_id": ObjectId(alert_id)}, update)
    alert.update({"status": "resolved"})
    out = to_str_id(alert)
    await send_alert_event("alert_resolved", out)
    return {
        "id": out["id"],
        "sender_email": out["sender_email"],
        "location": out["location"],
        "alert_type": out["alert_type"],
        "status": out["status"],
        "accepted_by": out["accepted_by"],
        "resolved_at": datetime.now(timezone.utc)  # <-- consistent with accepted_at
    }

@app.get("/alerts/{alert_id}", response_model=schemas.AlertOut)
async def get_alert(alert_id: str):
    db = get_db()
    alert = await db.alerts.find_one({"_id": ObjectId(alert_id)})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    out = to_str_id(alert)
    return {
        "id": out["id"],
        "sender_email": out["sender_email"],
        "location": out["location"],
        "alert_type": out["alert_type"],
        "status": out["status"],
        "accepted_by": out["accepted_by"],
    }

@app.get("/alerts/user/{email}")
async def list_user_alerts(email: str):
    db = get_db()
    cursor = db.alerts.find({"sender_email": email.lower()}).sort([("_id", -1)])
    items = []
    async for a in cursor:
        items.append({
            "id": str(a["_id"]),
            "sender_email": a["sender_email"],
            "location": a["location"],
            "alert_type": a["alert_type"],
            "status": a["status"],
            "accepted_by": a.get("accepted_by"),
        })
    return {"items": items}

@app.get("/alerts")
async def list_alerts():
    db = get_db()
    #  Only return alerts where status == "pending"
    cursor = db.alerts.find({"status": "pending"}).sort([("_id", -1)])
    items = []
    async for a in cursor:
        items.append({
            "id": str(a["_id"]),
            "sender_email": a["sender_email"],
            "location": a["location"],
            "alert_type": a["alert_type"],
            "status": a["status"],
            "accepted_by": a.get("accepted_by"),
        })
    return {"items": items}

@app.get("/alerts/agent/{email}")
async def list_agent_alerts(email: str):
    db = get_db()
    cursor = db.alerts.find({"accepted_by": email.lower(), "status": "accepted"}).sort([("_id", -1)])
    items = []
    async for a in cursor:
        items.append({
            "id": str(a["_id"]),
            "sender_email": a["sender_email"],
            "location": a["location"],
            "alert_type": a["alert_type"],
            "status": a["status"],
            "accepted_by": a.get("accepted_by"),
        })
    return {"items": items}


@app.get("/alerts/agent/{email}/resolved")
async def list_resolved_alerts(email: str):
    db = get_db()
    cursor = db.alerts.find(
        {"accepted_by": email.lower(), "status": "resolved"}
    ).sort([("_id", -1)])
    items = []
    async for a in cursor:
        items.append({
            "id": str(a["_id"]),
            "sender_email": a["sender_email"],
            "location": a["location"],
            "alert_type": a["alert_type"],
            "status": a["status"],
            "accepted_by": a.get("accepted_by"),
        })
    return {"items": items}


#dashboard apis



def _iso_date(s: Optional[str]):
    if not s: return None
    # supports "2024-01-15" or full ISO
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

@app.get("/stats/overview")
async def stats_overview(from_: Optional[str] = None, to: Optional[str] = None):
    """Cards: Total Users, Total Agents, Active Alerts (pending+accepted), Resolved Alerts"""
    db = get_db()
    f = _iso_date(from_); t = _iso_date(to)
    time_filter = {}
    if f or t:
        rng = {}
        if f: rng["$gte"] = f
        if t: rng["$lte"] = t
        time_filter["created_at"] = rng

    total_users   = await db.users.count_documents({})
    total_agents  = await db.users.count_documents({"usertype": "agent"})
    pending_count = await db.alerts.count_documents({**time_filter, "status": "pending"})
    accepted_ct   = await db.alerts.count_documents({**time_filter, "status": "accepted"})
    resolved_ct   = await db.alerts.count_documents({**time_filter, "status": "resolved"})
    active_ct     = pending_count + accepted_ct

    return {
        "total_users": total_users,
        "total_agents": total_agents,
        "active_alerts": active_ct,
        "resolved_alerts": resolved_ct,
    }

@app.get("/stats/alert-trends")
async def stats_alert_trends(days: int = 7):
    """Line chart: daily counts for Active(accepted+pending) and Resolved"""
    db = get_db()
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    since = since - timedelta(days=days-1)

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$project": {
            "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "status": 1
        }},
        {"$group": {
            "_id": "$day",
            "pending": {"$sum": {"$cond":[{"$eq":["$status","pending"]},1,0]}},
            "accepted": {"$sum": {"$cond":[{"$eq":["$status","accepted"]},1,0]}},
            "resolved": {"$sum": {"$cond":[{"$eq":["$status","resolved"]},1,0]}},
        }},
        {"$sort": {"_id": 1}}
    ]
    out = []
    async for r in db.alerts.aggregate(pipeline):
        out.append({
            "day": r["_id"],
            "active": r["pending"] + r["accepted"],
            "resolved": r["resolved"]
        })
    return {"items": out}

@app.get("/stats/alert-types")
async def stats_alert_types(days: int = 7):
    """Donut chart: count per alert_type in recent N days"""
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$alert_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    items = []
    async for r in db.alerts.aggregate(pipeline):
        items.append({"alert_type": r["_id"], "count": r["count"]})
    return {"items": items}

@app.get("/stats/agent-activity")
async def stats_agent_activity(limit: int = 10):
    """Right card: recent agent activity / leaderboard (resolved counts)"""
    db = get_db()
    pipeline = [
        {"$match": {"status": "resolved", "accepted_by": {"$ne": None}}},
        {"$group": {"_id": "$accepted_by", "resolved": {"$sum": 1}}},
        {"$sort": {"resolved": -1}},
        {"$limit": limit}
    ]
    items = []
    async for r in db.alerts.aggregate(pipeline):
        items.append({"agent_email": r["_id"], "resolved": r["resolved"]})
    return {"items": items}


#user management 



class UserAdminIn(BaseModel):
    name: str
    email: EmailStr
    role: str = "user"      # alias of usertype if you prefer
    department: Optional[str] = None
    phone: Optional[str] = None
    status: str = "active"  # active/inactive

class UserAdminUpdateIn(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None

@app.get("/users")
async def list_users(q: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None,
                     limit: int = 50, offset: int = 0):
    db = get_db()
    filt = {}
    if q:
        filt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
        ]
    if role:   filt["usertype"] = role
    if status: filt["status"] = status
    cursor = db.users.find(filt).sort([("name", 1)]).skip(offset).limit(min(limit, 200))
    items = []
    async for u in cursor:
        items.append({
            "id": str(u["_id"]), "name": u.get("name"), "email": u.get("email"),
            "role": u.get("usertype"), "status": u.get("status","active"),
            "created": u.get("created_at")
        })
    return {"items": items}

@app.post("/users", status_code=201)
async def create_user_admin(body: UserAdminIn):
    db = get_db()
    exists = await db.users.find_one({"email": body.email.lower()})
    if exists: raise HTTPException(409, "Email already exists")
    doc = {
        "name": body.name, "email": body.email.lower(),
        "usertype": body.role, "department": body.department,
        "phone": body.phone, "status": body.status, "created_at": datetime.utcnow()
    }
    res = await db.users.insert_one(doc)
    return {"id": str(res.inserted_id)}

@app.put("/users/{email}")
async def update_user_admin(email: str, body: UserAdminUpdateIn):
    db = get_db()
    u = await db.users.find_one({"email": email.lower()})
    if not u: raise HTTPException(404, "User not found")
    to_set = {k:v for k,v in body.model_dump(exclude_unset=True).items()}
    if "role" in to_set:
        to_set["usertype"] = to_set.pop("role")
    if not to_set: return {"updated": False}
    await db.users.update_one({"_id": u["_id"]}, {"$set": to_set})
    return {"updated": True}

@app.delete("/users/{email}")
async def delete_user_admin(email: str):
    db = get_db()
    u = await db.users.find_one({"email": email.lower()})
    if not u: raise HTTPException(404, "User not found")
    # soft delete
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"status": "inactive"}})
    return {"deleted": True}



#agent managment 

class AgentUpdateIn(BaseModel):
    name: Optional[str] = None
    specialization: Optional[str] = None
    location: Optional[str] = None     # e.g., "North District"
    phone: Optional[str] = None
    rating: Optional[float] = None

class AgentStatusIn(BaseModel):
    status: str   # "available" | "on-call" | "unavailable"

@app.get("/agents")
async def list_agents(q: Optional[str] = None, status: Optional[str] = None):
    db = get_db()
    filt = {"usertype": "agent"}
    if q:
        filt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"specialization": {"$regex": q, "$options": "i"}},
            {"location": {"$regex": q, "$options": "i"}},
        ]
    if status:
        filt["status"] = status
    cursor = db.users.find(filt).sort([("name", 1)])
    items = []
    async for a in cursor:
        items.append({
            "id": str(a["_id"]), "name": a.get("name"), "email": a.get("email"),
            "specialization": a.get("specialization"), "status": a.get("status", "available"),
            "rating": a.get("rating", 0), "phone": a.get("phone"), "location": a.get("location")
        })
    return {"items": items}


@app.put("/agents/{email}")
async def update_agent(email: str, body: AgentUpdateIn):
    db = get_db()
    a = await db.users.find_one({"email": email.lower(), "usertype": "agent"})
    if not a: raise HTTPException(404, "Agent not found")
    to_set = body.model_dump(exclude_unset=True)
    if not to_set: return {"updated": False}
    await db.users.update_one({"_id": a["_id"]}, {"$set": to_set})
    return {"updated": True}

@app.put("/agents/{email}/status")
async def set_agent_status(email: str, body: AgentStatusIn):
    db = get_db()
    a = await db.users.find_one({"email": email.lower(), "usertype": "agent"})
    if not a: raise HTTPException(404, "Agent not found")
    await db.users.update_one({"_id": a["_id"]}, {"$set": {"status": body.status, "last_status_at": datetime.now(timezone.utc)}})
    return {"email": email.lower(), "status": body.status}



#report management

@app.get("/reports/alerts/summary")
async def report_alerts_summary(from_: Optional[str] = None, to: Optional[str] = None):
    """Used by Reports page cards + allows CSV/Excel export on frontend."""
    db = get_db()
    f = _iso_date(from_); t = _iso_date(to)
    match = {}
    if f or t:
        rng = {}
        if f: rng["$gte"] = f
        if t: rng["$lte"] = t
        match["created_at"] = rng

    total = await db.alerts.count_documents(match)
    resolved = await db.alerts.count_documents({**match, "status": "resolved"})

    # avg response time = resolved_at - created_at (minutes)
    pipeline = [
        {"$match": {"status": "resolved", **match}},
        {"$project": {"diffMin": {"$divide": [{"$subtract": ["$resolved_at", "$created_at"]}, 1000*60]}}},
        {"$group": {"_id": None, "avgMin": {"$avg": "$diffMin"}}}
    ]
    avg_minutes = None
    agg = db.alerts.aggregate(pipeline)
    async for row in agg:
        avg_minutes = row.get("avgMin")
    return {
        "total_alerts": total,
        "resolved": resolved,
        "avg_response_minutes": round(avg_minutes, 1) if avg_minutes is not None else None
    }




# --- replace your current SettingsIn with this ---
class SettingsIn(BaseModel):
    # General
    system_name: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    alert_types: Optional[List[str]] = None

    # Alert Settings
    critical_threshold: Optional[int] = None
    high_threshold: Optional[int] = None
    medium_threshold: Optional[int] = None
    low_threshold: Optional[int] = None

    # Notifications
    email_notifications: Optional[bool] = None
    sms_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    sound_alerts: Optional[bool] = None

    # System
    auto_backup: Optional[bool] = None
    backup_frequency: Optional[str] = None       # "hourly" | "daily" | "weekly" | "monthly"
    retention_days: Optional[int] = None
    max_concurrent_users: Optional[int] = None

    # Security
    session_timeout: Optional[int] = None
    require_mfa: Optional[bool] = None
    password_policy: Optional[str] = None        # "basic" | "strong" | "very-strong"
    ip_whitelist: Optional[str] = None

    # Integrations
    webhook_url: Optional[str] = None
    api_rate_limit: Optional[int] = None
    enable_webhooks: Optional[bool] = None


# --- replace your current GET /settings with this ---
@app.get("/settings")
async def get_settings():
    db = get_db()
    doc = await db.settings.find_one({"_id": "global"}) or {}

    return {
        # General
        "system_name":         doc.get("system_name", "Panic Alert System"),
        "timezone":            doc.get("timezone", "UTC"),
        "language":            doc.get("language", "English"),
        "alert_types":         doc.get("alert_types", ["medical", "fire", "police", "utility"]),

        # Alert Settings
        "critical_threshold":  doc.get("critical_threshold", 30),
        "high_threshold":      doc.get("high_threshold", 60),
        "medium_threshold":    doc.get("medium_threshold", 120),
        "low_threshold":       doc.get("low_threshold", 300),

        # Notifications
        "email_notifications": doc.get("email_notifications", True),
        "sms_notifications":   doc.get("sms_notifications", False),
        "push_notifications":  doc.get("push_notifications", True),
        "sound_alerts":        doc.get("sound_alerts", True),

        # System
        "auto_backup":         doc.get("auto_backup", True),
        "backup_frequency":    doc.get("backup_frequency", "daily"),
        "retention_days":      doc.get("retention_days", 90),
        "max_concurrent_users":doc.get("max_concurrent_users", 1000),

        # Security
        "session_timeout":     doc.get("session_timeout", 30),
        "require_mfa":         doc.get("require_mfa", True),
        "password_policy":     doc.get("password_policy", "strong"),
        "ip_whitelist":        doc.get("ip_whitelist", ""),

        # Integrations
        "webhook_url":         doc.get("webhook_url", ""),
        "api_rate_limit":      doc.get("api_rate_limit", 1000),
        "enable_webhooks":     doc.get("enable_webhooks", False),
    }


# --- keep your PUT as-is (works with the expanded model) ---
@app.put("/settings")
async def put_settings(body: SettingsIn):
    db = get_db()
    update = {"$set": {k: v for k, v in body.model_dump(exclude_unset=True).items()}}
    await db.settings.update_one({"_id": "global"}, update, upsert=True)
    return {"updated": True}




