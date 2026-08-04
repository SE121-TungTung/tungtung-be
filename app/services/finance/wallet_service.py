from sqlalchemy.orm import Session
from typing import List, Tuple, Optional
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import HTTPException

from app.models.finance import (
    WalletTransaction, TransactionType, WalletRefType, WalletTxStatus, PaymentGateway
)
from app.models.user import User


class WalletService:

    def get_wallet_balance(self, db: Session, user_id: UUID) -> Decimal:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        return user.wallet_balance

    def get_my_transactions(
        self, db: Session, user_id: UUID, page: int, limit: int
    ) -> Tuple[List[WalletTransaction], int]:
        query = db.query(WalletTransaction).filter(WalletTransaction.user_id == user_id)
        total = query.count()
        items = (
            query.order_by(WalletTransaction.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    def get_all_transactions(
        self, db: Session, status: Optional[WalletTxStatus], page: int, limit: int
    ) -> Tuple[List[WalletTransaction], int]:
        query = db.query(WalletTransaction)
        if status:
            query = query.filter(WalletTransaction.status == status)
        total = query.count()
        items = (
            query.order_by(WalletTransaction.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    def request_top_up(
        self,
        db: Session,
        user_id: UUID,
        amount: Decimal,
        gateway: PaymentGateway,
        reference_code: Optional[str] = None,
        note: Optional[str] = None,
    ) -> WalletTransaction:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        # Create PENDING CREDIT transaction
        tx = WalletTransaction(
            user_id=user_id,
            type=TransactionType.CREDIT,
            amount=amount,
            balance_after=user.wallet_balance,  # Unchanged until approved
            reference_type=WalletRefType.TOP_UP,
            status=WalletTxStatus.PENDING,
            created_by=user_id,
            note=note,
            extra_metadata={
                "gateway": gateway.value,
                "reference_code": reference_code,
                # Mock transaction ID
                "payment_url": f"https://pay.example.com/topup/{reference_code or 'mock'}"
            }
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx

    def request_withdrawal(
        self,
        db: Session,
        user_id: UUID,
        amount: Decimal,
        bank_name: str,
        account_number: str,
        account_name: str,
        note: Optional[str] = None,
    ) -> WalletTransaction:
        # 1. Lock user row to adjust balance safely
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        if user.wallet_balance < amount:
            raise HTTPException(status_code=400, detail="Số dư ví không đủ để thực hiện yêu cầu rút tiền")

        # 2. Deduct balance immediately
        user.wallet_balance -= amount

        # 3. Create PENDING DEBIT transaction
        tx = WalletTransaction(
            user_id=user_id,
            type=TransactionType.DEBIT,
            amount=amount,
            balance_after=user.wallet_balance,
            reference_type=WalletRefType.WITHDRAWAL,
            status=WalletTxStatus.PENDING,
            created_by=user_id,
            note=note,
            extra_metadata={
                "bank_name": bank_name,
                "account_number": account_number,
                "account_name": account_name,
            }
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx

    def approve_transaction(
        self, db: Session, tx_id: UUID, admin_id: UUID, note: Optional[str] = None
    ) -> WalletTransaction:
        tx = db.query(WalletTransaction).filter(WalletTransaction.id == tx_id).with_for_update().first()
        if not tx:
            raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch")

        if tx.status != WalletTxStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Giao dịch đang ở trạng thái {tx.status.value}, không thể duyệt"
            )

        user = db.query(User).filter(User.id == tx.user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy chủ tài khoản")

        if tx.type == TransactionType.CREDIT:
            user.wallet_balance += tx.amount
            tx.balance_after = user.wallet_balance
        else:
            # Debit withdrawal is already deducted, so balance_after is already user.wallet_balance
            tx.balance_after = user.wallet_balance

        tx.status = WalletTxStatus.APPROVED
        tx.updated_by = admin_id
        if note:
            tx.note = (tx.note + f" | Admin approved: {note}") if tx.note else f"Admin approved: {note}"
        else:
            tx.note = (tx.note + " | Admin approved") if tx.note else "Admin approved"

        db.commit()
        db.refresh(tx)
        return tx

    def reject_transaction(
        self, db: Session, tx_id: UUID, admin_id: UUID, note: Optional[str] = None
    ) -> WalletTransaction:
        tx = db.query(WalletTransaction).filter(WalletTransaction.id == tx_id).with_for_update().first()
        if not tx:
            raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch")

        if tx.status != WalletTxStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Giao dịch đang ở trạng thái {tx.status.value}, không thể từ chối"
            )

        user = db.query(User).filter(User.id == tx.user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy chủ tài khoản")

        if tx.type == TransactionType.DEBIT:
            # Refund the immediate deduction back to the user
            user.wallet_balance += tx.amount
            tx.balance_after = user.wallet_balance
        else:
            tx.balance_after = user.wallet_balance

        tx.status = WalletTxStatus.REJECTED
        tx.updated_by = admin_id
        if note:
            tx.note = (tx.note + f" | Admin rejected: {note}") if tx.note else f"Admin rejected: {note}"
        else:
            tx.note = (tx.note + " | Admin rejected") if tx.note else "Admin rejected"

        db.commit()
        db.refresh(tx)
        return tx


wallet_service = WalletService()
