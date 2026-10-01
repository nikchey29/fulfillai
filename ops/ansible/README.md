# Ansible Local Linux Target

This exercise runs the existing `ops/ansible/setup.yml` playbook against an Ubuntu container.

## Start target

```bash
docker compose -f ops/ansible/compose.yaml up -d
```

Install the Docker connection collection:

```bash
ansible-galaxy collection install community.docker
```

Run the playbook:

```bash
ansible-playbook   -i ops/ansible/inventory.docker.ini   ops/ansible/setup.yml
```

Run it a second time and compare the changed/ok counts to discuss idempotency.

Stop the target:

```bash
docker compose -f ops/ansible/compose.yaml down
```

Record a successful playbook run before describing Ansible as completed hands-on experience.
