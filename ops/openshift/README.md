# OpenShift Completion Exercise

Use the same container image and Helm chart in a Red Hat OpenShift Developer Sandbox.

Typical flow:

```bash
oc new-project fulfillai-dev

helm upgrade --install fulfillai ../../deploy/helm/fulfillai   --namespace fulfillai-dev   --set image.repository=YOUR_IMAGE_REPOSITORY   --set image.tag=YOUR_IMAGE_TAG

oc apply -f route.yaml -n fulfillai-dev
oc get pods,svc,route -n fulfillai-dev
```

Record a successful Route URL and health request before describing OpenShift as completed hands-on deployment.
