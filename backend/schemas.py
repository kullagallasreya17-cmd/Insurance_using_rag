import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str


class WebSearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=10)


class ClaimRequest(BaseModel):
    question: str = ""
    mode: str = "auto"
    analysis_mode: str | None = None
    treatment_details: str | None = None
    diagnosis: str | None = None
    hospital_name: str | None = None
    hospital_location: str | None = None
    admission_date: str | None = None
    discharge_date: str | None = None
    claim_amount: float | None = None
    bill_amount: float | None = None
    policy_category: str | None = None
    policy_document_id: int | None = None
    claim_document_ids: list[int] = Field(default_factory=list)
    uploaded_document_types: list[str] = Field(default_factory=list)
    enable_web_search: bool = True


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str = "customer"


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    email: str
    role: Literal["customer"] = "customer"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Please enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8 or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must be at least 8 characters and include a letter and a number.")
        return value


class ForgotPasswordRequest(BaseModel):
    email: str


class TokenRequest(BaseModel):
    token: str = Field(min_length=32)


class ResetPasswordRequest(TokenRequest):
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8 or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must be at least 8 characters and include a letter and a number.")
        return value
