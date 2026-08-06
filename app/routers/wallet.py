from fastapi import APIRouter, Depends, Query, Path, Header, Request, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_user, require_role, require_any_role
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole
from app.models.finance import WalletTxStatus, WalletTransaction, PaymentGateway

from app.schemas.finance.wallet import (
    WalletBalanceResponse,
    WalletTransactionResponse,
    WalletTopUpRequest,
    WalletWithdrawRequest,
    WalletActionRequest,
)
from app.services.finance.wallet_service import wallet_service

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get("/me", response_model=ApiResponse[WalletBalanceResponse])
def get_my_wallet(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    balance = wallet_service.get_wallet_balance(db, current_user.id)
    return ApiResponse(
        success=True,
        data=WalletBalanceResponse(user_id=current_user.id, wallet_balance=balance)
    )


@router.get("/transactions/me", response_model=PaginationResponse[WalletTransactionResponse])
def get_my_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = wallet_service.get_my_transactions(db, current_user.id, page, limit)
    total_pages = math.ceil(total / limit) if total > 0 else 1
    
    data = [WalletTransactionResponse.model_validate(x) for x in items]
    
    return PaginationResponse(
        success=True,
        data=data,
        meta=PaginationMetadata(
            total=total,
            limit=limit,
            total_pages=total_pages,
            page=page,
        )
    )


@router.post("/topup/request", response_model=ApiResponse[WalletTransactionResponse])
def request_topup(
    payload: WalletTopUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = wallet_service.request_top_up(
        db=db,
        user_id=current_user.id,
        amount=payload.amount,
        gateway=payload.gateway,
        reference_code=payload.reference_code,
        note=payload.note,
    )
    return ApiResponse(
        success=True,
        data=WalletTransactionResponse.model_validate(tx),
        message="Yêu cầu nạp tiền đã được ghi nhận. Vui lòng thực hiện thanh toán."
    )


@router.post("/withdraw/request", response_model=ApiResponse[WalletTransactionResponse])
def request_withdraw(
    payload: WalletWithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = wallet_service.request_withdrawal(
        db=db,
        user_id=current_user.id,
        amount=payload.amount,
        bank_name=payload.bank_name,
        account_number=payload.account_number,
        account_name=payload.account_name,
        note=payload.note,
    )
    return ApiResponse(
        success=True,
        data=WalletTransactionResponse.model_validate(tx),
        message="Yêu cầu rút tiền thành công. Số dư đã được tạm khấu trừ và chờ Admin duyệt."
    )


# ---------------------------------------------------------------------------
# Public Webhook for top-up simulation
# ---------------------------------------------------------------------------
@router.post("/topup/webhook")
async def topup_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    transaction_id_str = data.get("transaction_id")
    status = data.get("status")

    if not transaction_id_str or status != "success":
        raise HTTPException(status_code=400, detail="Missing transaction_id or status != success")

    try:
        transaction_id = UUID(transaction_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    tx = db.query(WalletTransaction).filter(WalletTransaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx.status == WalletTxStatus.PENDING:
        # Mock approval
        wallet_service.approve_transaction(
            db=db,
            tx_id=tx.id,
            admin_id=tx.user_id,  # Auto-approved
            note="Hệ thống tự động duyệt qua Webhook (Giả lập)"
        )
        return {"status": "success", "message": "Transaction approved"}
    
    return {"status": "ignored", "message": f"Transaction status is {tx.status.value}"}


# ---------------------------------------------------------------------------
# Admin Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/admin/transactions",
    response_model=PaginationResponse[WalletTransactionResponse],
    dependencies=[Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN))],
)
def admin_get_transactions(
    status: Optional[WalletTxStatus] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = wallet_service.get_all_transactions(db, status, page, limit)
    total_pages = math.ceil(total / limit) if total > 0 else 1
    
    data = [WalletTransactionResponse.model_validate(x) for x in items]
    
    return PaginationResponse(
        success=True,
        data=data,
        meta=PaginationMetadata(
            total=total,
            limit=limit,
            total_pages=total_pages,
            page=page,
        )
    )


@router.post(
    "/admin/transactions/{tx_id}/approve",
    response_model=ApiResponse[WalletTransactionResponse],
    dependencies=[Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN))],
)
def admin_approve_transaction(
    tx_id: UUID = Path(...),
    payload: Optional[WalletActionRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = payload.note if payload else None
    tx = wallet_service.approve_transaction(db, tx_id, current_user.id, note)
    return ApiResponse(
        success=True,
        data=WalletTransactionResponse.model_validate(tx),
        message="Đã duyệt giao dịch thành công"
    )


@router.post(
    "/admin/transactions/{tx_id}/reject",
    response_model=ApiResponse[WalletTransactionResponse],
    dependencies=[Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN))],
)
def admin_reject_transaction(
    tx_id: UUID = Path(...),
    payload: Optional[WalletActionRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = payload.note if payload else None
    tx = wallet_service.reject_transaction(db, tx_id, current_user.id, note)
    return ApiResponse(
        success=True,
        data=WalletTransactionResponse.model_validate(tx),
        message="Đã từ chối giao dịch thành công"
    )
