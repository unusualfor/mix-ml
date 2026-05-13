# Portfolio Assets

This directory contains documentation intended for portfolio presentation, not for runtime operation.

## Suggested screenshots to capture

### ArgoCD UI
- Application overview showing `Healthy` and `Synced` status
- Resource tree expanded showing all managed resources
- Diff view after a manifest bump, before sync
- History tab showing previous syncs

### OpenShift Pipelines UI
- A successful PipelineRun for `backend-ci` with all steps green
- Step duration breakdown (clone, lint, test, build, push, manifest update)
- The graph visualization showing task dependencies

### Application UI (the mix-ml app itself)
- Home page with cocktails feasible now
- Shopping planner with budget=3, slider at "prefer unforgettable"
- Flavor map with hover tooltip on a cell

### Cluster overview
- `oc get pods,svc,routes -n mix-ml` showing the deployed workloads
- `oc get pipeline,task -n mix-ml-ci` showing CI resources

## Suggested talking points

When walking someone through this project:

1. **The why**: started as a way to systematize bartending knowledge, became a vehicle to demonstrate the full Red Hat-aligned stack (OpenShift, GitOps, Pipelines, Buildah, UBI images).

2. **The architecture decisions**: emphasize the *choices not made* — no Helm because Kustomize was sufficient, no React because HTMX matched the scope, no auto-sync because manual review matched the demo context, no webhooks because CRC isn't internet-exposed.

3. **The technical depth**: ILP solver for shopping optimization (CP-SAT), flavor distance metric with hierarchical clustering for similarity, asymmetric wildcard matching in feasibility query.

4. **The honesty about limits**: this is a single-cluster, single-developer, manual-sync setup. Production would add the items in "Future enhancements". The current scope is a portfolio demonstration of fundamentals, not a production deployment.
