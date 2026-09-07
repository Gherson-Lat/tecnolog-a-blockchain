from pydantic import BaseModel, Field


class BottleCreate(BaseModel):
    qr_code: str = ""
    product_name: str = Field(..., min_length=1)
    acta_number: str = Field(..., min_length=1)
    unique_code: str = Field(..., min_length=1)
    distributor_company: str = Field(..., min_length=1)
    barcode: str = Field(..., min_length=1)
    consumption_department: str = Field(..., min_length=1)
    alcohol_degree: str = Field(..., min_length=1)
    query_website: str = ""
    acta_date: str = Field(..., min_length=1)
    product_capacity: str = Field(..., min_length=1)
    print_lot_number: str = Field(..., min_length=1)
    print_consecutive: str = Field(..., min_length=1)


class DistributePayload(BaseModel):
    bottle_id: int
    target_user_id: int


class ConsumePayload(BaseModel):
    bottle_id: int
