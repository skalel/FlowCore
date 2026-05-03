from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
import uuid

class InstallmentCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=100)
    category_id: uuid.UUID
    payment_method: str
    card_id: Optional[uuid.UUID] = None
    
    total_amount: float = Field(..., gt=0) 
    total_installments: int = Field(..., gt=1)
    current_installment: int = Field(..., ge=1)
    
    purchase_date: date 
    current_due_date: date 
    
    generate_retroactive: bool = False