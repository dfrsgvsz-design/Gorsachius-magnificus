# useSyncEngine — exception-path audit (Item 8 / W3)

**Audited**: `species_monitoring_platform/frontend/src/hooks/useSyncEngine.js`
**Cross-ref**: `tests/e2e/specs/05-reconnect-sync.spec.ts`
**Outcome**: 2 production fixes + 1 e2e hardening, all landed in this batch.

## Catalogue of paths

| # | Path | Trigger | Pre-batch behaviour | Verdict |
|---|---|---|---|---|
| 1 | Network listeners | `online` / `offline` window events | Updates `networkOnline` state | ✅ OK |
| 2 | `refreshQueueFromOutbox` | OUTBOX_CHANGED_EVENT | try/catch → `console.warn` | ⚠️ silent (acceptable: outbox is a cache) |
| 3 | Remote protocol fetch | `networkOnline` flips true | `.catch(() => {})` | ⚠️ silent (acceptable: protocols are a cache) |
| 4 | **`handlePullSync` partial failure** | One of 4 endpoints fails | Promise.all → all fail | 🔴 **BUG, fix below** |
| 5 | `handlePullSync` total failure | All 4 endpoints fail | `setError(getApiErrorMessage(...))` | ✅ OK |
| 6 | `handlePushSync` outbox read fail | SQLite locked / I/O | try/catch → falls back to in-memory queue | ✅ OK |
| 7 | `handlePushSync` push fail | Backend 4xx/5xx | sets `error`, sets `syncMeta.lastStatus='error'`, `lastError` | ✅ OK |
| 8 | `handlePushSync` outbox cleanup fail | SQLite locked after push | try/catch → warn (server upsert is idempotent) | ✅ OK |
| 9 | **`handlePushSync` post-push pull fail** | Push succeeded, follow-up pull throws | Outer catch overwrites the just-set `lastStatus='synced'` with `'error'` | 🔴 **BUG, fix below** |
| 10 | Bootstrap local hydrate fail | SQLite read fail at boot | try/catch → warn, app still boots | ✅ OK |
| 11 | Bootstrap remote pull fail | Same as #4/#5 | Confined to `handlePullSync` | ✅ OK |
| 12 | Bootstrap idempotence | Re-entry from network flip | `hydratedRef.current` guard | ✅ OK |

## Fixes landed in this batch

### Fix A — `handlePullSync` partial-failure resilience (path #4)

`Promise.all` short-circuits on first rejection. If the team A taxonomy
endpoint hiccups, the user loses the entire pull including the survey rows
that fetched successfully. Worse, the survey crew sees a generic error
message and assumes "sync is broken" when actually their observations were
NOT pulled at all.

Switched to `Promise.allSettled` and applied each fulfilled response
independently. The error message now reflects only the endpoints that
genuinely failed, so the user can act on a real diagnosis instead of a
shotgun error.

```diff
- const [pulled, protocolResponse, taxonomyResponse, designAssetResponse] = await Promise.all([
-   pullSurveySync(...),
-   getSurveyProtocols(...),
-   getSurveyTaxonomyPackages(...),
-   currentProjectId ? getSurveyDesignAssets(...) : Promise.resolve({...}),
- ])
+ const results = await Promise.allSettled([...])
+ // unpack with fulfilled? value : null; assemble best-effort mergedPull
+ // report partial failures via setError including which endpoint(s) failed
```

### Fix B — `handlePushSync` post-push pull isolation (path #9)

The trailing `pullSurveySync('')` inside `handlePushSync` shares the outer
`try` block. If push succeeds but pull throws:

1. Outer `catch` fires.
2. `setError(...)` reports "Unable to push queued field data."
3. `setSurveyState` overwrites `syncMeta.lastStatus` to `'error'`,
   wiping the just-applied `'synced'` from `applySyncResult`.
4. The user sees an error suggesting the push failed, when in fact the
   data IS on the server.

Fix: nest the post-push pull in its own try/catch that only warns. The
push success metadata stays intact; the follow-up freshness pull is best-
effort by design.

```diff
- setSurveyState((current) => applySyncResult(current, response.sync_job))
- ...outbox cleanup...
- const pulled = await pullSurveySync('')
- setSurveyState((current) => mergeSyncPull(current, pulled))
+ setSurveyState((current) => applySyncResult(current, response.sync_job))
+ ...outbox cleanup...
+ try {
+   const pulled = await pullSurveySync('')
+   setSurveyState((current) => mergeSyncPull(current, pulled))
+ } catch (pullErr) {
+   console.warn('[useSyncEngine] post-push refresh pull failed', pullErr)
+ }
```

### Fix C — `sync-push` button surfaces last-status for e2e double assertion

Today the e2e 05 spec only asserts that `data-pending-count` reaches 0.
But a queue can drain because:

- The push genuinely succeeded (good — `syncMeta.lastStatus === 'synced'`)
- A failed push was retried with empty payload (bad — `'error'`)
- The user wiped the queue manually (neutral — `'idle'`)

Added `data-status={syncMeta?.lastStatus ?? 'idle'}` to the `sync-push`
button so the spec can assert both invariants and tell apart "drained
because synced" from "drained because failed":

```jsx
<button
  ...
  data-testid="sync-push"
  data-pending-count={surveyState.syncQueue.length}
  data-status={surveyState.syncMeta?.lastStatus || 'idle'}
>
```

### Fix D — e2e 05 double assertion

The spec's existing `toPass` loop only checks `data-pending-count`. Updated
to also assert `data-status === 'synced'` so the regression catches:

- Fix B regression (`lastStatus` overwritten by the post-push pull failure)
- Future regressions where the queue drains via the wrong code path
- Backend regressions where the conflict path returns success but writes
  conflicts (would land `lastStatus === 'conflict'`, which the assertion
  also flags)

```diff
- await expect(async () => {
-   const pending = await pushBtn.getAttribute('data-pending-count');
-   const n = pending != null ? Number(pending) : -1;
-   if (n > 0) {
-     throw new Error(`sync queue still has ${n} pending items`);
-   }
- }).toPass({ timeout: 30_000, intervals: [1_000, 2_000, 5_000] });
+ await expect(async () => {
+   const pending = Number(await pushBtn.getAttribute('data-pending-count'));
+   const status = await pushBtn.getAttribute('data-status');
+   if (pending > 0) throw new Error(`sync queue still has ${pending} pending items`);
+   if (status !== 'synced') throw new Error(`expected synced, got ${status}`);
+ }).toPass({ timeout: 30_000, intervals: [1_000, 2_000, 5_000] });
```

## What was deliberately NOT fixed

- `refreshQueueFromOutbox` silent swallow (#2): the outbox is a cache; the
  in-memory queue still drives the UI. A loud error would be noise.
- Remote protocol fetch silent swallow (#3): same rationale — protocols are
  cached locally; the user can still record observations. Adding a banner
  here would block the field workflow for transient network issues.
- Conflict resolution UX: this is the `OfflineSyncPanel` enhancement in
  P1 W2 (Item from the original work order), tracked separately.

## How to verify (manual + automated)

### Automated
- Vitest sweep stays green after Fix A and Fix B (no behaviour change for
  the happy path).
- E2E 05 with Fix C + Fix D will fail on the pre-batch code path, catching
  regressions of either Fix.

### Manual (with a working backend)
1. **Fix A**: Stub `getSurveyTaxonomyPackages` to throw, leave the other 3
   endpoints healthy. Click pull. Expected: survey rows still arrive, the
   banner says "taxonomy package fetch failed".
2. **Fix B**: Stub `pullSurveySync('')` (no-arg call AFTER push) to throw.
   Click push with one queued observation. Expected: `syncMeta.lastStatus`
   is `'synced'`, NOT `'error'`. The error banner does not appear.
3. **Fix C/D**: Run `tests/e2e/specs/05-reconnect-sync.spec.ts` against a
   backend that returns `conflicts` for the push payload. Expected: the
   double assertion fails because `data-status` is `'conflict'`.
