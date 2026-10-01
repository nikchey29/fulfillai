# Jenkins Lab

The repository contains `ops/jenkins/Jenkinsfile`. This local stack gives Jenkins access to a Docker-in-Docker daemon so the pipeline can verify FulfillAI and build the API image.

## Start

```bash
docker compose -f ops/jenkins/compose.yaml up -d --build
```

Get the initial password:

```bash
docker compose -f ops/jenkins/compose.yaml exec jenkins   cat /var/jenkins_home/secrets/initialAdminPassword
```

Open http://localhost:8082, complete the setup wizard, create a Pipeline job, connect `nikchey29/fulfillai`, select branch `feat/cloudops-platform`, and use `ops/jenkins/Jenkinsfile`.

Record a successful Jenkins run before describing Jenkins as completed hands-on experience.
