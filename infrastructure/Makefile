SHELL := /bin/bash

TF_DIR := terraform
ANSIBLE_DIR := ansible
MONITORING_ENV_FILE := ../.env.monitoring
MONITORING_COMPOSE_FILE := docker/docker-compose.monitoring.yml
HELM_DIR := helm/mutx

.PHONY: check-tools tf-fmt tf-init tf-init-staging tf-init-production tf-validate tf-plan tf-plan-staging tf-plan-production tf-plan-staging-detailed tf-plan-production-detailed ansible-deps ansible-lint ansible-inventory monitor-up monitor-down monitor-validate helm-install-staging helm-upgrade-staging helm-install-prod helm-lint

check-tools:
	@command -v terraform >/dev/null 2>&1 || { echo "terraform not found"; exit 1; }
	@command -v ansible-lint >/dev/null 2>&1 || { echo "ansible-lint not found"; exit 1; }
	@command -v ansible-galaxy >/dev/null 2>&1 || { echo "ansible-galaxy not found"; exit 1; }

tf-fmt:
	cd $(TF_DIR) && terraform fmt -recursive -check

tf-init:
	cd $(TF_DIR) && terraform init -backend=false

tf-init-staging:
	cd $(TF_DIR) && terraform init -reconfigure -backend-config=environments/staging/backend.hcl

tf-init-production:
	cd $(TF_DIR) && terraform init -reconfigure -backend-config=environments/production/backend.hcl

tf-validate: tf-init
	cd $(TF_DIR) && terraform validate

tf-plan:
	cd $(TF_DIR) && terraform plan

tf-plan-staging: tf-init-staging
	cd $(TF_DIR) && terraform plan -var-file=environments/staging/terraform.tfvars

tf-plan-staging-detailed: tf-init-staging
	cd $(TF_DIR) && terraform plan -detailed-exitcode -var-file=environments/staging/terraform.tfvars

tf-plan-production: tf-init-production
	cd $(TF_DIR) && terraform plan -var-file=environments/production/terraform.tfvars

tf-plan-production-detailed: tf-init-production
	cd $(TF_DIR) && terraform plan -detailed-exitcode -var-file=environments/production/terraform.tfvars

ansible-deps:
	ansible-galaxy collection install -r $(ANSIBLE_DIR)/requirements.yml

ansible-lint:
	ansible-lint $(ANSIBLE_DIR)/playbooks/provision.yml $(ANSIBLE_DIR)/playbooks/deploy-agent.yml

ansible-inventory:
	./scripts/generate-inventory.sh

ansible-provision: ansible-inventory
	cd $(ANSIBLE_DIR) && ansible-playbook -i inventory.generated.ini playbooks/provision.yml

ansible-deploy-agent: ansible-inventory
	cd $(ANSIBLE_DIR) && ansible-playbook -i inventory.generated.ini playbooks/deploy-agent.yml

monitor-up:
	docker compose --env-file $(MONITORING_ENV_FILE) -f $(MONITORING_COMPOSE_FILE) up -d

monitor-down:
	docker compose --env-file $(MONITORING_ENV_FILE) -f $(MONITORING_COMPOSE_FILE) down

monitor-validate:
	docker run --rm --entrypoint promtool -v $(CURDIR)/monitoring/prometheus:/etc/prometheus prom/prometheus:v2.54.1 \
		check config /etc/prometheus/prometheus.yml && \
	docker run --rm --entrypoint promtool -v $(CURDIR)/monitoring/prometheus:/etc/prometheus prom/prometheus:v2.54.1 \
		check rules /etc/prometheus/alerts.yml && \
	docker run --rm --entrypoint amtool -v $(CURDIR)/monitoring/prometheus:/etc/alertmanager prom/alertmanager:v0.27.0 \
		check-config /etc/alertmanager/alertmanager.yml

helm-lint:
	helm lint $(HELM_DIR)

helm-install-staging:
	helm upgrade --install mutx-staging $(HELM_DIR) -f $(HELM_DIR)/values.staging.yaml --namespace staging --create-namespace

helm-upgrade-staging:
	helm upgrade --install mutx-staging $(HELM_DIR) -f $(HELM_DIR)/values.staging.yaml --namespace staging --create-namespace

helm-install-prod:
	helm upgrade --install mutx-prod $(HELM_DIR) -f $(HELM_DIR)/values.prod.yaml --namespace production --create-namespace
