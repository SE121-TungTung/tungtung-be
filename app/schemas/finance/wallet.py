from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.models.finance import TransactionType, WalletRefType, WalletTxStatus, PaymentGateway


class WalletBalanceResponse(BaseModel):
    user_id: UUID
    wallet_balance: Decimal

    model_config = {"from_attributes": True}


class WalletTransactionResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: TransactionType
    amount: Decimal
    balance_after: Decimal
    reference_type: WalletRefType
    reference_id: Optional[UUID] = None
    status: WalletTxStatus
    created_by: Optional[UUID] = None
    note: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WalletTopUpRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Số tiền cần nạp")
    gateway: PaymentGateway = Field(..., description="Cổng/Phương thức nạp (ví dụ MOMO, VNPAY, BANK_TRANSFER)")
    note: Optional[str] = None
    reference_code: Optional[str] = None


class WalletWithdrawRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Số tiền cần rút")
    bank_name: str = Field(..., description="Tên ngân hàng nhận")
    account_number: str = Field(..., description="Số tài khoản nhận")
    account_name: str = Field(..., description="Tên chủ tài khoản nhận")
    note: Optional[str] = None


class WalletActionRequest(BaseModel):
    note: Optional[str] = None
