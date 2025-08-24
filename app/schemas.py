from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal, Any, Dict

UserType = Literal["user", "agent"]
AlertStatus = Literal["pending", "accepted", "resolved"]

class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    usertype: UserType

class RegisterOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    usertype: UserType

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class LoginOut(BaseModel):
    exists: bool
    usertype: Optional[UserType] = None

class Location(BaseModel):
    lat: float
    lng: float

class AlertCreateIn(BaseModel):
    sender_email: EmailStr
    location: Location
    alert_type: str

class AlertOut(BaseModel):
    id: str
    sender_email: EmailStr
    location: Dict[str, float]
    alert_type: str
    status: AlertStatus
    accepted_by: Optional[str] = None