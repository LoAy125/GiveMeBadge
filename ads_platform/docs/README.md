# Rewarded Ads Platform MVP

This folder contains the initial MVP scaffolding for the rewarded-ads project. It focuses on the
core loop, anti-fraud considerations, and the baseline API surface needed to ship quickly.

## Core Loop
1. User registers (email or Google OAuth).
2. User lands in dashboard and requests a rewarded ad.
3. Server issues a session token for the ad view.
4. Client completes ad and calls back for verification.
5. Server records the completed view and rewards the account.
6. At $10 balance, user can request withdrawal.

## MVP Scope
- Authentication (email + Google)
- Rewarded ads flow (start/complete)
- Ledger-driven balance tracking
- Withdrawals with pending review
- Admin review flow (manual in MVP)

## Local API Notes
- The MVP uses SQLite locally and auto-creates tables on startup.
- Endpoints that require a user accept a `user_id` query parameter to keep the MVP stateless.
- Admin endpoints require an `admin_token` query parameter (default: `admin_demo`).
- Rewarded ads enforce cooldowns and daily caps per user.

## Next Steps
- Replace the `user_id` query parameter with JWT auth.
- Wire the API to production persistence (PostgreSQL).
- Add device fingerprinting + risk scoring.
- Add admin panel and reporting dashboards.
