-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Expand appointment.status beyond active|cancelled.
-- Allowed values (enforced in app): active, arrived, no_show, completed, cancelled.
-- Existing rows keep their values; no DDL rewrite needed for the TEXT column.
SELECT 1;
