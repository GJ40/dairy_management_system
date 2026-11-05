import { useCallback, useEffect, useState } from 'react';

// The backend owns the cooldown; it is derived from persisted failed-attempt
// state, so it keeps running while the tab is closed. This hook only mirrors
// the deadline in localStorage so a reopened tab shows the remaining pause
// instead of an apparently usable form.
const STORAGE_PREFIX = 'dairy:login-cooldown';

function storageKeyFor(scope) {
  return `${STORAGE_PREFIX}:${scope}`;
}

function readStored(key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const until = Number(parsed?.until);
    if (!Number.isFinite(until)) return null;
    if (until <= Date.now()) {
      window.localStorage.removeItem(key);
      return null;
    }
    const minutes = Number(parsed?.minutes);
    // Only the deadline and the configured pause length are restored. The
    // server's prose is not: its "try again in ..." sentence would be stale
    // after a reopen, while the live countdown never is.
    return {
      until,
      minutes: Number.isFinite(minutes) && minutes > 0 ? minutes : null,
    };
  } catch {
    // Private mode or a corrupted entry: fall back to a normal form, the
    // server still refuses early attempts.
    return null;
  }
}

function persist(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Display-only convenience; failing to persist must never block sign-in.
  }
}

function forget(key) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
}

function formatClock(totalSeconds) {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function useLoginCooldown(scope = 'staff') {
  const storageKey = storageKeyFor(scope);
  const [cooldown, setCooldown] = useState(() => readStored(storageKey));
  const [now, setNow] = useState(() => Date.now());

  const until = cooldown?.until ?? 0;
  const remainingSeconds = until > now ? Math.ceil((until - now) / 1000) : 0;

  useEffect(() => {
    if (!until) return undefined;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= until) {
        clearInterval(timer);
        forget(storageKey);
        setCooldown(null);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [until, storageKey]);

  const start = useCallback(
    (seconds, minutes = null) => {
      const pause = Number(seconds);
      if (!Number.isFinite(pause) || pause <= 0) return;
      const deadline = Date.now() + pause * 1000;
      const storedMinutes =
        Number(minutes) > 0 ? Math.round(Number(minutes)) : null;
      setNow(Date.now());
      setCooldown({ until: deadline, minutes: storedMinutes });
      persist(storageKey, { until: deadline, minutes: storedMinutes });
    },
    [storageKey]
  );

  const clear = useCallback(() => {
    forget(storageKey);
    setCooldown(null);
  }, [storageKey]);

  return {
    isBlocked: remainingSeconds > 0,
    remainingSeconds,
    clock: formatClock(remainingSeconds),
    pauseMinutes: cooldown?.minutes ?? null,
    start,
    clear,
  };
}

export default useLoginCooldown;
