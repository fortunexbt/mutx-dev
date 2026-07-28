from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest


CHART = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]


def run_helm(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["helm", *args],
        cwd=REPO,
        check=check,
        capture_output=True,
        text=True,
    )


def template(*args: str) -> str:
    return run_helm("template", "test-release", str(CHART), *args).stdout


class HelmChartTests(unittest.TestCase):
    def test_schema_is_valid_json_and_lint_matrix_passes(self) -> None:
        json.loads((CHART / "values.schema.json").read_text())
        for values_file in (None, "values.staging.yaml", "values.prod.yaml"):
            args = ["lint", str(CHART)]
            if values_file:
                args.extend(["-f", str(CHART / values_file)])
            result = run_helm(*args)
            self.assertIn("0 chart(s) failed", result.stdout)

    def test_default_manifest_matches_next_and_fastapi_contracts(self) -> None:
        rendered = template()

        self.assertEqual(rendered.count("kind: Deployment\n"), 3)
        self.assertEqual(rendered.count("kind: Service\n"), 2)
        self.assertEqual(rendered.count("kind: Job\n"), 1)
        self.assertIn("name: test-release-mutx-api", rendered)
        self.assertIn("name: test-release-mutx-frontend", rendered)
        self.assertIn("name: test-release-mutx-monitor", rendered)
        self.assertIn('image: "mutx-api:1.4.0"', rendered)
        self.assertIn('image: "mutx-frontend:1.4.0"', rendered)
        self.assertIn("containerPort: 8000", rendered)
        self.assertIn("containerPort: 3000", rendered)
        self.assertRegex(rendered, r"startupProbe:\n\s+httpGet:\n\s+path: /health")
        self.assertRegex(rendered, r"readinessProbe:\n\s+httpGet:\n\s+path: /ready")
        self.assertIn('command: ["python", "-m", "src.api.monitor_worker"]', rendered)
        self.assertEqual(
            rendered.count('command: ["python", "-m", "src.api.monitor_worker", "--healthcheck"]'),
            3,
        )
        self.assertIn("name: MONITOR_HEARTBEAT_MAX_AGE_SECONDS", rendered)
        self.assertIn("name: MONITOR_MAX_CONSECUTIVE_FAILURES", rendered)
        self.assertIn("document_worker_enabled=False", rendered)
        self.assertIn("reasoning_worker_enabled=False", rendered)
        self.assertIn("automountServiceAccountToken: false", rendered)
        self.assertIn("readOnlyRootFilesystem: true", rendered)
        self.assertIn("apiVersion: batch/v1\nkind: Job", rendered)
        self.assertIn("test-release-mutx-api:8000/ready", rendered)
        self.assertIn("test-release-mutx-frontend:3000/", rendered)
        self.assertNotIn("kind: Role\n", rendered)
        self.assertNotIn("kind: ClusterRole\n", rendered)
        self.assertNotIn("kind: RoleBinding\n", rendered)
        self.assertNotIn("kind: HorizontalPodAutoscaler\n", rendered)
        self.assertNotIn("kind: Ingress\n", rendered)
        self.assertNotIn("kind: PersistentVolumeClaim\n", rendered)

    def test_production_manifest_has_migration_persistence_and_split_ingress(self) -> None:
        rendered = template("-f", str(CHART / "values.prod.yaml"))

        self.assertEqual(rendered.count("kind: Deployment\n"), 3)
        self.assertEqual(rendered.count("kind: Service\n"), 2)
        self.assertEqual(rendered.count("kind: Job\n"), 2)
        self.assertEqual(rendered.count("kind: PersistentVolumeClaim\n"), 1)
        self.assertEqual(rendered.count("kind: Ingress\n"), 1)
        self.assertNotIn("kind: Secret\n", rendered)
        self.assertIn("name: mutx-prod-api-env", rendered)
        self.assertIn("helm.sh/resource-policy: keep", rendered)
        self.assertIn("helm.sh/hook: pre-install,pre-upgrade", rendered)
        self.assertIn('command: ["alembic"]', rendered)
        self.assertIn('args: ["-c", "/app/alembic.ini", "upgrade", "head"]', rendered)

        for path in ("/v1", "/health", "/ready", "/metrics"):
            self.assertRegex(
                rendered,
                rf"(?s)path: {re.escape(path)}\n\s+pathType: (?:Prefix|Exact).*?name: test-release-mutx-api",
            )
        self.assertRegex(
            rendered,
            r"(?s)path: /\n\s+pathType: Prefix.*?name: test-release-mutx-frontend",
        )

    def test_optional_workers_disable_matching_in_process_consumers(self) -> None:
        rendered = template(
            "--set",
            "features.documents=true",
            "--set",
            "features.reasoning=true",
            "--set",
            "workers.document.enabled=true",
            "--set",
            "workers.reasoning.enabled=true",
            "--set",
            "persistence.enabled=true",
            "--set",
            "persistence.accessModes={ReadWriteMany}",
        )

        self.assertEqual(rendered.count("kind: Deployment\n"), 5)
        self.assertIn('command: ["python", "-m", "src.api.document_worker"]', rendered)
        self.assertIn('command: ["python", "-m", "src.api.reasoning_worker"]', rendered)
        self.assertIn("document_worker_enabled=False", rendered)
        self.assertIn("reasoning_worker_enabled=False", rendered)
        self.assertGreaterEqual(rendered.count("claimName: test-release-mutx-data"), 3)

        embedded = template("--set", "features.documents=true")
        self.assertIn("document_worker_enabled=True", embedded)
        self.assertNotIn('src.api.document_worker"]', embedded)

    def test_inline_secrets_are_split_and_wired_to_the_correct_workloads(self) -> None:
        rendered = template(
            "--set-string",
            "api.secretEnv.DATABASE_URL=postgresql://mutx:test@postgres:5432/mutx",
            "--set-string",
            "frontend.secretEnv.RESEND_API_KEY=test-frontend-key",
        )

        self.assertEqual(rendered.count("kind: Secret\n"), 2)
        self.assertIn("name: test-release-mutx-api-env", rendered)
        self.assertIn("name: test-release-mutx-frontend-env", rendered)
        self.assertIn('DATABASE_URL: "postgresql://mutx:test@postgres:5432/mutx"', rendered)
        self.assertIn('RESEND_API_KEY: "test-frontend-key"', rendered)

    def test_frontend_hpa_targets_only_the_frontend_deployment(self) -> None:
        rendered = template(
            "--set",
            "frontend.autoscaling.enabled=true",
            "--show-only",
            "templates/hpa.yaml",
        )
        self.assertEqual(rendered.count("kind: HorizontalPodAutoscaler\n"), 1)
        self.assertRegex(
            rendered,
            r"(?s)name: test-release-mutx-frontend.*?kind: Deployment\n\s+name: test-release-mutx-frontend",
        )
        self.assertNotIn("name: test-release-mutx-api", rendered)

    def test_unsafe_or_drifted_values_are_rejected(self) -> None:
        invalid_cases = (
            ("--set", "api.env.ENVIRONMENT=production"),
            (
                "--set",
                "features.documents=true",
                "--set",
                "workers.document.enabled=true",
            ),
            ("--set", "api.notARealValue=true"),
            ("--set", "api.autoscaling.enabled=true"),
            (
                "--set",
                "frontend.autoscaling.enabled=true",
                "--set",
                "frontend.autoscaling.minReplicas=7",
                "--set",
                "frontend.autoscaling.maxReplicas=6",
            ),
            (
                "--set",
                "api.existingSecret=external-api-env",
                "--set-string",
                "api.secretEnv.JWT_SECRET=inline-is-ambiguous",
            ),
            (
                "-f",
                str(CHART / "values.prod.yaml"),
                "--set-string",
                "api.env.FORWARDED_ALLOW_IPS=*",
            ),
            (
                "-f",
                str(CHART / "values.prod.yaml"),
                "--set-string",
                "api.env.ALLOWED_HOSTS=*.example.com",
            ),
        )
        for args in invalid_cases:
            result = run_helm("template", "invalid", str(CHART), *args, check=False)
            self.assertNotEqual(result.returncode, 0, msg=(args, result.stdout, result.stderr))

    def test_source_ports_probes_and_worker_entrypoints_cannot_drift_silently(self) -> None:
        frontend_dockerfile = (REPO / "Dockerfile").read_text()
        alternate_frontend_dockerfile = (
            REPO / "infrastructure/docker/Dockerfile.frontend"
        ).read_text()
        api_dockerfile = (REPO / "infrastructure/docker/Dockerfile.api.production").read_text()
        main_source = (REPO / "src/api/main.py").read_text()
        metrics_source = (REPO / "src/api/metrics.py").read_text()
        next_config = (REPO / "next.config.mjs").read_text()
        deployment_template = (CHART / "templates/deployment.yaml").read_text()
        worker_template = (CHART / "templates/workers.yaml").read_text()

        self.assertIn("EXPOSE 3000", frontend_dockerfile)
        self.assertIn("EXPOSE 3000", alternate_frontend_dockerfile)
        self.assertIn("EXPOSE 8000", api_dockerfile)
        self.assertIn('@app.get("/health"', main_source)
        self.assertIn('@app.get("/ready")', main_source)
        self.assertIn('prefix: str | None = "/v1"', main_source)
        self.assertIn('@router.get("/metrics")', metrics_source)
        self.assertIn("process.env.INTERNAL_API_URL", next_config)
        self.assertIn("containerPort: {{ .Values.frontend.port }}", deployment_template)
        self.assertIn("containerPort: {{ .Values.api.port }}", deployment_template)
        self.assertIn("path: /health", deployment_template)
        self.assertIn("path: /ready", deployment_template)

        for module in ("monitor", "document", "reasoning"):
            source = (REPO / f"src/api/{module}_worker.py").read_text()
            self.assertIn('if __name__ == "__main__":', source)
            self.assertIn(f"src.api.{module}_worker", worker_template)

    def test_readme_and_whitepaper_report_current_template_count_and_defaults(self) -> None:
        template_count = sum(1 for path in (CHART / "templates").rglob("*") if path.is_file())
        readme = (CHART / "README.md").read_text()
        whitepaper = (REPO / "docs/whitepaper.md").read_text()

        self.assertEqual(template_count, 13)
        self.assertIn(f"{template_count} template files", readme)
        self.assertIn(f"{template_count} template files", whitepaper)
        for claim in (
            "`api.port` | `8000`",
            "`frontend.port` | `3000`",
            "`api.replicaCount` | `1`",
            "`frontend.replicaCount` | `1`",
            "`persistence.enabled` | `false`",
        ):
            self.assertIn(claim, readme)


if __name__ == "__main__":
    unittest.main()
