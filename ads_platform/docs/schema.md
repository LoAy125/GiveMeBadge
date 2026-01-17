# Database Schema (Draft)

## users
- id (uuid, pk)
- email (unique)
- username
- password_hash
- status (active, suspended, banned)
- created_at
- updated_at

## auth_accounts
- id (uuid, pk)
- user_id (fk users)
- provider (google)
- provider_id
- created_at

## devices
- id (uuid, pk)
- user_id (fk users)
- fingerprint
- last_ip
- last_seen_at

## ad_units
- id (uuid, pk)
- name
- status
- reward_min
- reward_max
- cooldown_seconds
- daily_cap

## ad_views
- id (uuid, pk)
- user_id (fk users)
- ad_unit_id (fk ad_units)
- session_token
- started_at
- completed_at
- rewarded_amount
- status (started, completed, rejected)

## balances
- user_id (pk, fk users)
- available
- pending
- updated_at

## transactions
- id (uuid, pk)
- user_id (fk users)
- type (earn, spend, adjust)
- source (ad_view, withdrawal, admin)
- amount
- occurred_at

## withdrawals
- id (uuid, pk)
- user_id (fk users)
- amount
- fee
- payout_method
- destination
- status (pending, approved, rejected, paid)
- created_at
- reviewed_at
- review_notes

## audit_logs
- id (uuid, pk)
- actor_id (nullable)
- action
- metadata (json)
- created_at
