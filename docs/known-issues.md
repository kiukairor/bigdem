# PULSE — Known Issues & Fixes

Running log of significant bugs, build failures, and their resolutions.
Re-read this before debugging CI, K8s, or dependency issues.

---

## CI

### pulse-profile arm64 build failure — enhanced-resolve native bindings
**Status:** Fixed (workaround in place)  
**Symptom:** `npm ci` or `next build` fails on arm64 with a native binding error from `enhanced-resolve`.  
**Root cause:** `enhanced-resolve` versions above 5.20.0 include native binaries that don't build cleanly for linux/arm64 in the `@module-federation/nextjs-mf` dependency tree.  
**Fix:** Pin `enhanced-resolve` to `5.20.0` via the `overrides` field in `package.json`:
```json
"overrides": {
  "enhanced-resolve": "5.20.0"
}
```
**Watch for:** Any upgrade of `@module-federation/nextjs-mf` may pull in a newer `enhanced-resolve` and reintroduce the failure. Check this first if `next build` fails on arm64 for pulse-profile or pulse-feed.

---

### pulse-profile CI permanently queued — no self-hosted runner registered
**Status:** Mitigated (switched to ubuntu-latest + cross-compile)  
**Symptom:** pulse-profile workflow stays in `queued` indefinitely. `gh api repos/.../actions/runners` returns `total_count: 0`.  
**Root cause:** Workflow used `runs-on: [self-hosted, linux, arm64]` but no runner was ever registered (or was deregistered). The self-hosted runner host is `piworker`.  
**Fix applied:** Switched `build` job to `runs-on: ubuntu-latest` with `platforms: linux/arm64` in the buildx step (cross-compile, same approach as pulse-feed). Local cache steps removed (not available on ephemeral runners).  
**Fallback (Option A):** If cross-compile fails, register `piworker` as a self-hosted runner:  
  - Go to github.com/kiukairor/bigdem → Settings → Actions → Runners → New self-hosted runner (Linux/ARM64)  
  - Run the install steps on `piworker`  
  - Revert `runs-on` back to `[self-hosted, linux, arm64]`

---

### pulse-profile GHCR push 403 — package never initialised
**Status:** ⚠ Blocked — awaiting manual fix  
**Symptom:** Build succeeds (Next.js compiles, arm64 cross-compile works) but push to GHCR fails:  
`403 Forbidden on HEAD request to ghcr.io/kiukairor/pulse-profile`  
**Root cause:** The `pulse-profile` GHCR package has never been pushed before (self-hosted runner never ran). `GITHUB_TOKEN` with `packages: write` can push to existing packages but cannot always initialise a brand-new one.  
**Fix (one-time manual step):**
```bash
# From any machine with Docker and your GHCR credentials
echo $GITHUB_PAT | docker login ghcr.io -u kiukairor --password-stdin
docker pull hello-world
docker tag hello-world ghcr.io/kiukairor/pulse-profile:init
docker push ghcr.io/kiukairor/pulse-profile:init
```
Then go to **github.com → Packages → pulse-profile → Package settings**:  
- Set visibility to Public, OR link it to the `bigdem` repository  

Then re-trigger the workflow:
```bash
gh workflow run pulse-profile.yml --repo kiukairor/bigdem
```
**Alternative fix:** GitHub Settings → Actions → General → Workflow permissions → set to "Read and write permissions" (blocks GHCR writes for new packages if set to read-only).  
**Context:** The build step (cross-compile, enhanced-resolve, npm) is confirmed working as of run `25216472008` (sha `fcc6744`). This is purely a GHCR package initialisation issue, not a build issue.

---

### pulse-profile package-lock.json out of sync
**Status:** Fixed  
**Symptom:** `npm ci` fails with "package-lock.json does not match package.json".  
**Fix:** Run `npm install` locally in `frontends/pulse-profile/` and commit the updated `package-lock.json`.  
**Watch for:** Adding new dependencies (like `@newrelic/browser-agent`) without regenerating the lock file.

---

### pulse-feed CI workflow path mismatch
**Status:** Fixed  
**Symptom:** Pushing changes to `frontends/pulse-feed/` did not trigger the CI workflow.  
**Root cause:** Workflow `paths:` trigger pointed at the wrong directory (stale `versus-era` path).  
**Fix:** Updated `paths:` in `.github/workflows/pulse-feed.yml` to `frontends/pulse-feed/**`.

---

## Kubernetes / Infrastructure

### PostgreSQL + Redis PVCs stuck in Pending
**Status:** Fixed  
**Symptom:** `kubectl get pvc -n pulse-prod` shows PVCs in `Pending` state, pods stuck in `Init`.  
**Root cause:** Helm charts referenced `storageClass: standard` which doesn't exist on the Pi cluster.  
**Fix:** Changed to `storageClass: local-path` (provided by `rancher/local-path-provisioner`). Ensure local-path-provisioner is installed before applying Helm charts:
```bash
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.26/deploy/local-path-storage.yaml
```

---

## Frontends

### NR Browser MicroAgent — credentials must be baked at build time
**Status:** By design (documented here to avoid re-investigation)  
**Symptom:** `process.env.NEXT_PUBLIC_NR_*` is undefined at runtime in pulse-feed / pulse-profile.  
**Root cause:** Next.js inlines `NEXT_PUBLIC_*` values at webpack build time. Runtime env injection (K8s secrets, `getServerSideProps`) does not work for these variables in MFE remote bundles.  
**Fix:** NR credentials for pulse-feed and pulse-profile must be passed as `build-args` in the CI workflow (`.github/workflows/pulse-feed.yml`, `.github/workflows/pulse-profile.yml`). To rotate credentials, update the build-args and push — a new image build is required.  
**Exception:** pulse-shell uses the full SPA agent injected server-side via `getServerSideProps`, so it CAN read NR credentials from K8s secrets at runtime.
