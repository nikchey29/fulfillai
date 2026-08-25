# Azure Container Apps deployment template

This directory contains the infrastructure definition for running the containerized FulfillAI FastAPI service on Azure Container Apps. It does not retrain models or open frozen test partitions.

## Prerequisites

- Azure CLI (`az`)
- Bicep (included with current Azure CLI installations)
- an Azure resource group
- a publicly readable container image, such as a GHCR image produced by the repository container workflow

## Deploy

```bash
az group create --name fulfillai-rg --location westeurope
az deployment group create \
  --resource-group fulfillai-rg \
  --template-file infra/azure/main.bicep \
  --parameters containerImage=ghcr.io/YOUR_GITHUB_USER/fulfillai-api:v1.1.0
```

After deployment, verify the returned URL with `/health` and `/v1/results`.

## Current status

The Bicep template is part of the repository, but this path is intentionally documented as **not yet deployed**. I would rather leave that boundary visible than turn an infrastructure definition into a claim about a runtime I have not verified.
