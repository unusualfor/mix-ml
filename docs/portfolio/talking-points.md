# Talking Points — Interview Guide

Personal notes for walking through mix-ml in a technical interview or portfolio review.

## Opening (30 seconds)

- "This is a cocktail intelligence platform built on 102 official IBA recipes."
- "It's also a vehicle to demonstrate a complete GitOps workflow on OpenShift — from code push to production deployment, with Tekton CI and ArgoCD."

## Architecture walkthrough (2 minutes)

- Three-tier: FastAPI backend, HTMX/Jinja frontend, PostgreSQL
- All running on OpenShift Local (CRC), deployed via ArgoCD
- Two Tekton pipelines (backend + frontend) build and push images, update manifests
- Single mono-repo, Kustomize-only (no Helm)

## Technical depth highlights (pick 2-3)

- **Shopping optimizer**: ILP solver (Google OR-Tools CP-SAT) that finds the minimum set of bottles to buy given a budget and preference weights
- **Flavor distance**: hierarchical ingredient classification with custom distance metric for flavor similarity between cocktails
- **Feasibility engine**: asymmetric wildcard matching — "any whiskey" in a recipe matches "Bourbon" in your bar
- **GitOps pipeline**: immutable SHA tags, Kustomize image overrides, Tekton → ghcr.io → Git commit → ArgoCD sync
- **No-JS frontend**: HTMX for dynamic behavior, zero JavaScript files, server-rendered templates

## What I'd change for production

- External Secrets Operator instead of setup scripts
- Auto-sync with health checks and rollback
- Multi-environment overlays (dev → staging → prod)
- Image scanning in pipeline (Trivy or ACS)
- Webhook triggers instead of manual `tkn start`

## Questions I'm prepared for

- "Why not Helm?" → Kustomize was sufficient for the scope; no need for templating engine when overlays handle environment differences
- "Why manual sync?" → Deliberate: keeps a human gate for a portfolio demo. One-line change to enable auto-sync.
- "Why HTMX?" → Server-rendered is simpler for this scope. No API versioning needed, no build step, no Node.js dependency.
- "How would you scale this?" → Horizontal pod autoscaling, read replicas for Postgres, CDN for static assets, multi-cluster with ApplicationSet
