# Anti-Fraud Checklist

## Registration
- CAPTCHA + IP throttling
- Max accounts per IP/device
- Email verification before first withdrawal

## Rewarded Ads
- Server-issued session tokens
- Reward only after verified completion
- Per-user cooldowns + daily caps
- Proxy/VPN detection where possible
- Flag abnormal patterns (high velocity, repeated device/IP swaps)

## Withdrawals
- First withdrawal manual review
- Risk score per user
- Wallet reuse detection across accounts
- Delayed processing window (24-72h)

## Monitoring
- Audit log for all balance-impacting actions
- Alerts for suspicious users
- Admin override + notes on decisions
