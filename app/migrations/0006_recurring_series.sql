-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Phase 4.3: recurring appointment series (appointments.series_id).
-- Column is added idempotently by app.db._ensure_columns().

CREATE INDEX IF NOT EXISTS idx_appt_series ON appointments(series_id);
