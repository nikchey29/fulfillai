# Azure Container Apps deployment

This is the deployment layer for the containerized FastAPI service. It does not retrain models or open frozen test partitions.

## Prerequisites

- Azure CLI (`az`)
- Bicep (included with current Azure CLI installations)
- a resource group
- a publicly readable container image (for example a GHCR image created by the repository container workflow)

## Deploy

```bash
az group create --name fulfillai-rg --location westeurope
az deployment group create \
  --resource-group fulfillai-rg \
  --template-file infra/azure/main.bicep \
  --parameters containerImage=ghcr.io/YOUR_GITHUB_USER/fulfillai-api:v1.1.0
```

After successful deployment, use the output URL and verify `/health` and `/v1/results`.

Only after completing this real deployment should Azure Container Apps be claimed as a deployed FulfillAI skill on the resume.
