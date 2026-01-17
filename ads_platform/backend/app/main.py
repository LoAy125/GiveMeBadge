from datetime import datetime, timedelta
import random
from typing import List
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import AdUnit, AdView, AuthAccount, Balance, Transaction, User, Withdrawal

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="Rewarded Ads Platform MVP")
ADMIN_TOKEN = "admin_demo"


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    username: str = Field(min_length=3, max_length=32)


class AuthRegisterResponse(BaseModel):
    message: str
    user_id: str
    verification_required: bool


class GoogleAuthRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class BalanceResponse(BaseModel):
    balance: float
    pending: float
    currency: str = "USD"


class AdStartRequest(BaseModel):
    ad_unit_id: str


class AdStartResponse(BaseModel):
    session_token: str
    cooldown_seconds: int


class AdCompleteRequest(BaseModel):
    session_token: str


class AdCompleteResponse(BaseModel):
    reward: float
    new_balance: float


class EarningsItem(BaseModel):
    transaction_id: str
    amount: float
    occurred_at: datetime
    source: str


class EarningsHistoryResponse(BaseModel):
    items: List[EarningsItem]


class WithdrawRequest(BaseModel):
    amount: float
    payout_method: str
    destination: str


class WithdrawResponse(BaseModel):
    withdrawal_id: str
    status: str
    queued_at: datetime


class AdminWithdrawalReviewRequest(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    review_notes: str | None = None


class AdminUserSummary(BaseModel):
    user_id: str
    email: EmailStr
    username: str
    balance: float
    pending: float


class AdminWithdrawalSummary(BaseModel):
    withdrawal_id: str
    user_id: str
    amount: float
    status: str
    created_at: datetime


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user(
    user_id: str = Query(..., description="User ID from auth token"),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def require_admin(admin_token: str = Query(..., description="Admin token")) -> None:
    if admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not db.query(AdUnit).first():
            db.add(
                AdUnit(
                    name="Rewarded Video",
                    reward_min=0.002,
                    reward_max=0.01,
                    cooldown_seconds=60,
                    daily_cap=30,
                )
            )
            db.commit()


@app.get("/")
def root() -> dict:
    return {"status": "ok", "message": "MVP backend running"}


@app.post("/api/auth/register", response_model=AuthRegisterResponse)
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)) -> AuthRegisterResponse:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already used")

    user = User(
        email=payload.email,
        username=payload.username,
        password_hash=pwd_context.hash(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(Balance(user_id=user.id, available=0.0, pending=0.0))
    db.commit()

    return AuthRegisterResponse(
        message="Registered successfully",
        user_id=user.id,
        verification_required=True,
    )


@app.post("/api/auth/google", response_model=TokenResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not payload.id_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    auth_account = (
        db.query(AuthAccount)
        .filter(AuthAccount.provider == "google", AuthAccount.provider_id == payload.id_token)
        .first()
    )
    if auth_account:
        user = db.get(User, auth_account.user_id)
    else:
        user = User(
            email=f"google_{payload.id_token[:8]}@example.com",
            username=f"google_{payload.id_token[:8]}",
            password_hash=pwd_context.hash(uuid4().hex),
        )
        db.add(user)
        db.flush()
        db.add(Balance(user_id=user.id, available=0.0, pending=0.0))
        db.add(AuthAccount(user_id=user.id, provider="google", provider_id=payload.id_token))
        db.commit()

    return TokenResponse(access_token=uuid4().hex, user_id=user.id)


@app.post("/api/ads/start", response_model=AdStartResponse)
def ads_start(
    payload: AdStartRequest,
    user: User = Depends(get_user),
    db: Session = Depends(get_db),
) -> AdStartResponse:
    ad_unit = db.get(AdUnit, payload.ad_unit_id)
    if not ad_unit or not ad_unit.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad unit not found")

    recent_view = (
        db.query(AdView)
        .filter(AdView.user_id == user.id)
        .order_by(AdView.started_at.desc())
        .first()
    )
    if recent_view:
        elapsed = datetime.utcnow() - recent_view.started_at
        if elapsed < timedelta(seconds=ad_unit.cooldown_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Cooldown active",
            )

    start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = (
        db.query(AdView)
        .filter(
            AdView.user_id == user.id,
            AdView.status == "completed",
            AdView.started_at >= start_of_day,
        )
        .count()
    )
    if daily_count >= ad_unit.daily_cap:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Daily cap reached")

    session_token = uuid4().hex
    db.add(AdView(user_id=user.id, ad_unit_id=ad_unit.id, session_token=session_token))
    db.commit()

    return AdStartResponse(session_token=session_token, cooldown_seconds=ad_unit.cooldown_seconds)


@app.post("/api/ads/complete", response_model=AdCompleteResponse)
def ads_complete(
    payload: AdCompleteRequest,
    user: User = Depends(get_user),
    db: Session = Depends(get_db),
) -> AdCompleteResponse:
    ad_view = db.query(AdView).filter(AdView.session_token == payload.session_token).first()
    if not ad_view or ad_view.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if ad_view.status != "started":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already completed")

    ad_unit = db.get(AdUnit, ad_view.ad_unit_id)
    reward = random.uniform(ad_unit.reward_min, ad_unit.reward_max) if ad_unit else 0.0
    ad_view.status = "completed"
    ad_view.completed_at = datetime.utcnow()
    ad_view.rewarded_amount = reward

    balance = user.balance
    balance.available += reward
    balance.updated_at = datetime.utcnow()
    db.add(
        Transaction(
            user_id=user.id,
            type="earn",
            source="ad_view",
            amount=reward,
        )
    )
    db.commit()

    return AdCompleteResponse(reward=reward, new_balance=balance.available)


@app.get("/api/me/balance", response_model=BalanceResponse)
def get_balance(user: User = Depends(get_user)) -> BalanceResponse:
    balance = user.balance
    return BalanceResponse(balance=balance.available, pending=balance.pending)


@app.get("/api/me/history", response_model=EarningsHistoryResponse)
def get_history(user: User = Depends(get_user), db: Session = Depends(get_db)) -> EarningsHistoryResponse:
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.occurred_at.desc())
        .limit(20)
        .all()
    )
    items = [
        EarningsItem(
            transaction_id=transaction.id,
            amount=transaction.amount,
            occurred_at=transaction.occurred_at,
            source=transaction.source,
        )
        for transaction in transactions
    ]
    return EarningsHistoryResponse(items=items)


@app.post("/api/withdraw/request", response_model=WithdrawResponse)
def request_withdraw(
    payload: WithdrawRequest,
    user: User = Depends(get_user),
    db: Session = Depends(get_db),
) -> WithdrawResponse:
    if payload.amount < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum is $10")

    balance = user.balance
    if balance.available < payload.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")

    balance.available -= payload.amount
    balance.pending += payload.amount
    balance.updated_at = datetime.utcnow()

    withdrawal = Withdrawal(
        user_id=user.id,
        amount=payload.amount,
        fee=0.2,
        payout_method=payload.payout_method,
        destination=payload.destination,
    )
    db.add(withdrawal)
    db.add(
        Transaction(
            user_id=user.id,
            type="spend",
            source="withdrawal",
            amount=-payload.amount,
        )
    )
    db.commit()

    return WithdrawResponse(
        withdrawal_id=withdrawal.id,
        status=withdrawal.status,
        queued_at=withdrawal.created_at,
    )


@app.get("/api/withdraw/list", response_model=List[WithdrawResponse])
def list_withdrawals(user: User = Depends(get_user)) -> List[WithdrawResponse]:
    return [
        WithdrawResponse(
            withdrawal_id=withdrawal.id,
            status=withdrawal.status,
            queued_at=withdrawal.created_at,
        )
        for withdrawal in user.withdrawals
    ]


@app.get("/api/admin/users", response_model=List[AdminUserSummary], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)) -> List[AdminUserSummary]:
    users = db.query(User).all()
    return [
        AdminUserSummary(
            user_id=user.id,
            email=user.email,
            username=user.username,
            balance=user.balance.available,
            pending=user.balance.pending,
        )
        for user in users
    ]


@app.get(
    "/api/admin/withdrawals",
    response_model=List[AdminWithdrawalSummary],
    dependencies=[Depends(require_admin)],
)
def list_withdrawals_admin(db: Session = Depends(get_db)) -> List[AdminWithdrawalSummary]:
    withdrawals = db.query(Withdrawal).order_by(Withdrawal.created_at.desc()).all()
    return [
        AdminWithdrawalSummary(
            withdrawal_id=withdrawal.id,
            user_id=withdrawal.user_id,
            amount=withdrawal.amount,
            status=withdrawal.status,
            created_at=withdrawal.created_at,
        )
        for withdrawal in withdrawals
    ]


@app.post(
    "/api/admin/withdrawals/{withdrawal_id}/review",
    response_model=WithdrawResponse,
    dependencies=[Depends(require_admin)],
)
def review_withdrawal(
    withdrawal_id: str,
    payload: AdminWithdrawalReviewRequest,
    db: Session = Depends(get_db),
) -> WithdrawResponse:
    withdrawal = db.get(Withdrawal, withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Withdrawal not found")

    withdrawal.status = payload.status
    withdrawal.reviewed_at = datetime.utcnow()
    withdrawal.review_notes = payload.review_notes
    db.commit()

    return WithdrawResponse(
        withdrawal_id=withdrawal.id,
        status=withdrawal.status,
        queued_at=withdrawal.created_at,
    )
