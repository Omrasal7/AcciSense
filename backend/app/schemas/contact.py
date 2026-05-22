from pydantic import BaseModel, EmailStr


class ContactCreate(BaseModel):
    name: str
    phone: str | None = None
    email: EmailStr | None = None
    relation: str | None = None


class ContactRead(ContactCreate):
    id: int
