# Architecture Decision Records

Key decisions made during the mix-ml project, with rationale.

## ADR-001: Mono-repo structure

**Decision**: Single repository for backend, frontend, manifests, scripts, and data.

**Rationale**: Simplifies CI (single clone), atomic commits across app + manifest, easier to demonstrate the full stack. The project is single-developer; the coordination overhead of multi-repo is unjustified.

**Trade-off**: Larger clone size, coarser-grained access control. Acceptable for portfolio scope.

## ADR-002: Kustomize over Helm

**Decision**: Use Kustomize for all manifest management. No Helm charts.

**Rationale**: Kustomize is built into `kubectl`/`oc`, requires no extra tooling, and the project doesn't need Helm's templating engine. Overlays handle the single environment difference (CRC). Image tag overrides via `images:` section are cleaner than Helm value files for this use case.

**Trade-off**: Less ecosystem of pre-built charts. Not a concern — all manifests are custom.

## ADR-003: HTMX + Jinja2 over React/Vue SPA

**Decision**: Server-rendered frontend with HTMX for dynamic behavior.

**Rationale**: No JavaScript build step, no Node.js dependency, no API versioning between frontend and backend. FastAPI serves both API and rendered HTML. HTMX provides sufficient interactivity (partial page updates, infinite scroll, search-as-you-type) without a full SPA framework.

**Trade-off**: Less client-side state management capability. Not needed — all state lives in the backend or URL parameters.

## ADR-004: Manual ArgoCD sync (no auto-sync)

**Decision**: ArgoCD Application uses manual sync policy.

**Rationale**: Keeps a human in the loop between "image built" and "image deployed". Appropriate for a portfolio demo where you want to show the diff review step. One-line change (`automated: {}` in syncPolicy) to enable auto-sync for production.

**Trade-off**: Extra click required for every deployment. Acceptable for demo/learning context.

## ADR-005: ghcr.io over Quay.io or internal registry

**Decision**: Push images to GitHub Container Registry (ghcr.io).

**Rationale**: Tightly integrated with GitHub (same PAT), public packages are free, no separate account needed. CRC's internal registry has storage constraints and isn't accessible outside the cluster for debugging.

**Trade-off**: External dependency for image hosting. Acceptable — images are also tagged immutably so they can be mirrored.

## ADR-006: Manual pipeline trigger (no webhooks)

**Decision**: Pipelines triggered via `tkn pipeline start` from the developer's machine.

**Rationale**: CRC runs on a local laptop, not exposed to the internet. GitHub webhooks can't reach it. Manual trigger is the pragmatic choice. The pipeline itself is fully automated once started.

**Trade-off**: Extra manual step. Would add Tekton Triggers with an EventListener if the cluster had ingress.

## ADR-007: Immutable SHA tags + Kustomize images override

**Decision**: Every build produces `git-<7-char-sha>` tag. Manifests reference SHA tags via Kustomize `images:` section, never hardcoded in Deployment YAML.

**Rationale**: Immutable tags enable reliable rollback (revert the kustomization.yaml commit). The `images:` override is the Kustomize-native way to manage tags without editing Deployment files directly.

**Trade-off**: Slightly more complex kustomization.yaml. Worth it for auditability and rollback.

## ADR-008: Reusable Tekton Tasks across apps

**Decision**: Tasks are parameterized with `app-path` to work for both backend and frontend pipelines.

**Rationale**: DRY principle. Both apps are Python/FastAPI with identical build patterns (pip install, ruff, pytest, Buildah, git push). Duplicating Tasks would mean maintaining two copies of identical logic.

**Trade-off**: Tasks are slightly more complex with extra params. All params have sensible defaults for backwards compatibility.

## ADR-009: Secrets managed out-of-band (setup scripts)

**Decision**: Kubernetes Secrets are created by `setup-secrets.sh` and `setup-ci-secrets.sh`, not stored in Git.

**Rationale**: Storing secrets in Git (even base64-encoded) is a security anti-pattern. Sealed Secrets or External Secrets Operator would be production-grade, but add operator dependencies. Setup scripts are the minimal viable approach for a single-developer CRC environment.

**Trade-off**: Secrets not version-controlled, manual rotation. Documented as a future enhancement.

## ADR-010: UBI9 base images

**Decision**: All container images use Red Hat UBI9 (Universal Base Image) as base.

**Rationale**: Red Hat alignment for portfolio credibility. UBI images are freely redistributable, regularly patched, and compatible with OpenShift's security context constraints. Pinned to digest for reproducibility.

**Trade-off**: Larger image size than Alpine. Acceptable — security and compatibility outweigh size.
