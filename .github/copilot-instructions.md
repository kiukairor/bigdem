# VERSUS — AI Coding Agent Instructions

## Architecture Overview

This is a **microservices-based preference tournament app** with Module Federation frontends, deployed on bare-metal Kubernetes (Raspberry Pi) via GitOps.

**Service Boundaries:**
- `versus-shell` — Next.js host app, loads MFEs via Module Federation
- `versus-duel` / `versus-profile` — Next.js MFEs (game and soul reveal)
- `duel-svc` — Go backend: question pool, bracket generation
- `session-svc` — Python/FastAPI: tracks session state & user answers
- `soul-svc` — Python/FastAPI: generates AI personality profiles via Claude API
- `postgresql` / `redis` — shared data layer across Python services

**Directory Structure:**
- `frontend/{service-name}/` — Next.js frontends (shell, duel, profile)
- `services/{service-name}/` — Backend services (Go, Python)
- `infra/helm/{service-name}/` — Helm charts per service
- `argocd/apps/` — ArgoCD application definitions

**Data Flow:**
Frontend (shell) → loads MFEs → calls services → shared PostgreSQL/Redis state → soul-svc calls Anthropic Claude.

## Critical Patterns & Conventions

### 1. GitOps Deployment Flow

**The golden rule:** Changes to `main` trigger CI → Docker build → image push to GHCR → Helm values update → ArgoCD auto-syncs.

- Each service/frontend has its own workflow: `.github/workflows/{service-name}.yml`
- On merge to `main`, GitHub Actions builds ARM64 images, pushes to `ghcr.io/YOUR_ORG/{service-name}:{sha-tag}`
- Same workflow commits new image tag to `infra/helm/{service-name}/values.yaml` with `[skip ci]`
- ArgoCD detects drift and deploys to `versus-prod` namespace on K8s

**Never manually edit image tags** — the CI pipeline handles it. Manual edits break sync.

### 2. Helm Chart Structure (Every Service Follows This)

- Charts live in `infra/helm/{service-name}/`
- Minimal chart: `Chart.yaml`, `values.yaml`, `templates/deployment.yaml`, `templates/service.yaml`
- All deployments mount secrets: `ghcr-secret` (registry), `postgres-secret`, `newrelic-secret`
- Health checks required: `/health` endpoint for liveness and readiness probes
- Resource limits defined: `resources.requests` and `resources.limits` (Pi has limited RAM)

**Example from [duel-svc/values.yaml](infra/helm/duel-svc/values.yaml):**
```yaml
env:
  DB_HOST: "postgresql"
  DB_PORT: "5432"
  DB_NAME: "versus"
```
All services reference `postgresql` / `redis` by K8s service name (DNS).

### 3. Dockerfile Conventions

**Go Services:**
- Multi-stage: `golang:1.22-alpine` → `alpine:3.19`
- Build for ARM64: `GOARCH=arm64`
- Binary lives in `/cmd/main.go`, outputs to `./duel-svc`
- Example: [services/duel-svc/Dockerfile](services/duel-svc/Dockerfile)

**Python Services:**
- Base: `python:3.12-slim`
- Use `requirements.txt` (no Poetry/pipenv)
- FastAPI + uvicorn, New Relic agent required
- Example: [services/session-svc/Dockerfile](services/session-svc/Dockerfile)

**Next.js MFEs:**
- Multi-stage: `node:20-alpine` deps → builder → runner
- Output mode: `standalone` (see `next.config.js`)
- Copies `.next/standalone`, `.next/static`, `public/`
- Example: [frontend/versus-shell/Dockerfile](frontend/versus-shell/Dockerfile)

### 4. Secrets Management

**Three K8s secrets required** (create manually per [docs/phase1-infra.md](docs/phase1-infra.md)):
- `ghcr-secret` — GitHub Container Registry pull credentials
- `postgres-secret` — keys: `username`, `password`
- `newrelic-secret` — key: `license-key`

All deployments reference these in `env` via `secretKeyRef`. Missing secrets = crashloop.

### 5. Observability

- **New Relic** integrated: Go uses `go-agent/v3`, Python uses `newrelic` package
- All deployments have annotation: `newrelic.io/scrape: "true"`
- App names: `NEW_RELIC_APP_NAME` env var matches service name

### 6. Local Development vs Deployment

**There is no docker-compose.** Services run in K8s only.

- To test locally: `kubectl port-forward svc/{service-name} {local-port}:{service-port}`
- For Python: use `pip install -r requirements.txt` + `uvicorn main:app --reload`
- For Go: `go run ./cmd/main.go`
- For frontends: `npm run dev` (but Module Federation only works when deployed)

**DO NOT create docker-compose.yml** — it conflicts with the K8s-first strategy.

## Common Workflows

### Adding a New Service

1. Create `services/{new-svc}/` with Dockerfile + code
2. Create Helm chart: `infra/helm/{new-svc}/` (copy from `duel-svc` template)
3. Create ArgoCD app: `argocd/apps/{new-svc}.yaml` (copy from existing)
4. Create GitHub Actions workflow: `.github/workflows/{new-svc}.yml`
5. Update `YOUR_ORG` placeholders if they exist

### Updating Dependencies

- **Go:** Edit `go.mod`, run `go mod tidy`, commit both `go.mod` and `go.sum`
- **Python:** Edit `requirements.txt`, rebuild image (no lock file)
- **Node:** `npm install {pkg}` updates `package-lock.json`, commit both

### Troubleshooting Deployments

```bash
# Check ArgoCD app status
kubectl get applications -n argocd

# Force ArgoCD sync
kubectl patch application {service-name} -n argocd --type merge -p '{"metadata": {"annotations": {"argocd.argoproj.io/refresh": "hard"}}}'

# View pod logs
kubectl logs -n versus-prod deployment/{service-name} -f

# Check secret exists
kubectl get secret {secret-name} -n versus-prod
```

### Running Setup Script

`./setup.sh` is **one-time only** — it replaces `YOUR_ORG` placeholders with your GitHub org/username. After running, commit changes immediately. If you run it twice, you'll break references.

## Architecture Decisions (The "Why")

- **Module Federation:** Allows independent deployment of frontends while sharing runtime bundles. Shell lazy-loads MFEs.
- **ArgoCD App-of-Apps:** Single `kubectl apply -f argocd/app-of-apps.yaml` deploys all services. No manual Helm commands.
- **Plain K8s (no k3s):** Pi cluster uses kubeadm for learning purposes. Production would use managed K8s.
- **ARM64 builds:** Pi architecture. All Dockerfiles and CI workflows build for `linux/arm64`.
- **GitOps-only updates:** No manual `kubectl apply` for app changes. Commit to `main` → CI → ArgoCD. Infrastructure as code.

## Quick Reference

| Task | Command |
|------|---------|
| Access ArgoCD UI | `kubectl port-forward svc/argocd-server -n argocd 8080:443` |
| Get ArgoCD password | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" \| base64 -d` |
| Apply app-of-apps | `kubectl apply -f argocd/app-of-apps.yaml` |
| Port-forward service | `kubectl port-forward -n versus-prod svc/duel-svc 8080:8080` |
| View all apps | `kubectl get applications -n argocd` |
| Restart deployment | `kubectl rollout restart -n versus-prod deployment/{service-name}` |

## What NOT to Do

- ❌ Manually edit image tags in `values.yaml` (CI pipeline owns this)
- ❌ Use `kubectl apply -f` for service deployments (use ArgoCD)
- ❌ Create `docker-compose.yml` (conflicts with K8s-first design)
- ❌ Commit secrets to git (use K8s secrets, reference in Helm)
- ❌ Run `setup.sh` more than once (it's idempotent only if `YOUR_ORG` is unchanged)
