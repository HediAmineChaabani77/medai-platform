from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    totp_code: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    mfa_verified: bool


class BootstrapAdminResponse(BaseModel):
    username: str
    seeded: bool
    totp_secret: str
    totp_uri: str

