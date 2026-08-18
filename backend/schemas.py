from pydantic import BaseModel, Field


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
    policy_document_id: int | None = None
    claim_document_ids: list[int] = Field(default_factory=list)
    uploaded_document_types: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str = "customer"


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "customer"
