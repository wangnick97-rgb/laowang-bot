-- Applied to production pwwbgrplpzthmufydiyh on 2026-10-14.
-- Bot uses the service_role client in db/client.py; no client-side policies needed.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.scheduler_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.consultation_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.group_chat_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_polls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activation_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trade_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.scheduler_logs, public.consultation_bookings,
  public.referrals, public.group_chat_daily, public.daily_polls,
  public.activation_codes, public.trade_signals, public.events
  FROM PUBLIC, anon, authenticated;
COMMIT;
