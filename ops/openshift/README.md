# OpenShift Completion Exercise

This exercise deploys FulfillAI using native OpenShift resources instead of reusing the private GCP image.

## What it uses

- OpenShift ImageStream
- OpenShift BuildConfig
- Docker strategy build from the public FulfillAI GitHub branch
- Kubernetes Deployment + Service generated from the ImageStream
- readiness and liveness probes
- OpenShift edge-terminated Route

## Prerequisites

Install the OpenShift CLI on macOS:

```bash
brew install openshift-cli
```

Log in to an OpenShift cluster (for example, a Red Hat Developer Sandbox) using the `oc login ...` command supplied by that cluster.

## Run

```bash
bash scripts/cloudops_openshift.sh
```

The script creates/uses the `fulfillai-dev` project, builds the image inside OpenShift, deploys it, creates a TLS Route, waits for rollout, and verifies `/health`.

Record a successful Route URL and health response before describing OpenShift as completed hands-on deployment.
