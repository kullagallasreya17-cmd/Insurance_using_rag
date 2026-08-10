from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ClaimRequest(BaseModel):
    question: str = ""
    treatment_details: str | None = None
    diagnosis: str | None = None
    hospital_name: str | None = None
    admission_date: str | None = None
    claim_amount: float | None = None
    bill_amount: float | None = None
    policy_category: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "agent"
