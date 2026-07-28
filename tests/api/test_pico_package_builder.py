"""Tests for pico_package_builder — real ZIP package generation and OnboardingState readiness."""

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from src.api.models.pico_onboarding import OnboardingState
from src.api.services.pico_package_builder import build_onboarding_package


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_zip(zip_bytes: bytes) -> dict[str, str]:
    """Extract a ZIP archive into a {filename: content} dict."""
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


KNOWLEDGE_ROOT = (
    Path(__file__).resolve().parents[2] / "src" / "api" / "knowledge" / "pico-builder-pack"
)
STACK_KB_DOCS = {
    "hermes": "HERMES.md",
    "openclaw": "OPENCLAW.md",
    "nanoclaw": "NANOCLAW.md",
    "picoclaw": "PICOCLAW.md",
}


def _read_knowledge_doc(name: str) -> str:
    return (KNOWLEDGE_ROOT / name).read_text("utf-8")


# ---------------------------------------------------------------------------
# OnboardingState readiness logic
# ---------------------------------------------------------------------------


class TestOnboardingStateReadiness:
    """Test the model_validator that syncs the ready flag."""

    def test_ready_when_all_required_fields_set(self):
        state = OnboardingState(stack="hermes", os="macos", provider="openai", goal="install")
        assert state.ready is True

    def test_not_ready_when_stack_missing(self):
        state = OnboardingState(os="macos", provider="openai", goal="install")
        assert state.ready is False

    def test_not_ready_when_os_missing(self):
        state = OnboardingState(stack="hermes", provider="openai", goal="install")
        assert state.ready is False

    def test_not_ready_when_provider_missing(self):
        state = OnboardingState(stack="hermes", os="macos", goal="install")
        assert state.ready is False

    def test_not_ready_when_goal_missing(self):
        state = OnboardingState(stack="hermes", os="macos", provider="openai")
        assert state.ready is False

    def test_not_ready_when_all_missing(self):
        state = OnboardingState()
        assert state.ready is False

    def test_ready_even_without_optional_fields(self):
        """Optional fields (channels, networking, hardware, skill_level) should not block readiness."""
        state = OnboardingState(stack="openclaw", os="linux", provider="anthropic", goal="install")
        assert state.channels == []
        assert state.networking is None
        assert state.hardware is None
        assert state.skill_level is None
        assert state.ready is True

    def test_ready_with_all_optional_fields(self):
        state = OnboardingState(
            stack="hermes",
            os="macos",
            provider="openai",
            goal="install",
            channels=["telegram", "discord"],
            networking="tailscale",
            hardware="laptop",
            skill_level="intermediate",
        )
        assert state.ready is True

    def test_compute_ready_matches_validator(self):
        state = OnboardingState(stack="hermes", os="linux", provider="local", goal="repair")
        assert state.compute_ready() is True
        assert state.ready == state.compute_ready()


# ---------------------------------------------------------------------------
# Hermes stack — full state
# ---------------------------------------------------------------------------


class TestHermesPackage:
    """Hermes stack with full state including channels and tailscale networking."""

    @pytest.fixture()
    def state(self):
        return OnboardingState(
            stack="hermes",
            os="macos",
            provider="openai",
            goal="install",
            channels=["telegram", "discord"],
            networking="tailscale",
        )

    @pytest.fixture()
    def files(self, state):
        zip_bytes, filename = build_onboarding_package(state)
        assert filename == "hermes-setup.zip"
        return _extract_zip(zip_bytes)

    def test_does_not_guess_hermes_runtime_config(self, files):
        assert "config.yaml" not in files

    def test_contains_agents_md(self, files):
        assert "AGENTS.md" in files
        assert "Hermes" in files["AGENTS.md"]

    def test_contains_env_template(self, files):
        assert ".env.template" in files
        assert "OPENAI_API_KEY" in files[".env.template"]

    def test_contains_install_sh(self, files):
        assert "install.sh" in files
        assert len(files["install.sh"]) > 0

    def test_contains_readme(self, files):
        assert "README.md" in files
        readme = files["README.md"]
        assert "Hermes" in readme
        assert "macOS" in readme
        assert "OpenAI" in readme

    def test_contains_channel_configs(self, files):
        assert not any(name.startswith("channels/") for name in files)
        assert "telegram, discord" in files["README.md"]
        assert "does not emit guessed cross-stack YAML" in files["README.md"]

    def test_contains_tailscale_setup(self, files):
        assert "tailscale-setup.sh" in files
        assert "tailscale" in files["tailscale-setup.sh"]
        assert "install.sh |" not in files["tailscale-setup.sh"]

    def test_env_template_has_channel_tokens(self, files):
        env = files[".env.template"]
        assert "TELEGRAM_BOT_TOKEN" in env
        assert "DISCORD_BOT_TOKEN" in env

    def test_contains_current_builder_kb_docs(self, files):
        assert files["kb/INSTALL_FLOW.md"] == _read_knowledge_doc("INSTALL_FLOW.md")
        assert files["kb/UPDATE_NOTES.md"] == _read_knowledge_doc("UPDATE_NOTES.md")
        assert files["kb/HERMES.md"] == _read_knowledge_doc("HERMES.md")
        assert files["kb/TAILSCALE_PLAYBOOK.md"] == _read_knowledge_doc("TAILSCALE_PLAYBOOK.md")

    def test_readme_points_to_included_builder_kb(self, files):
        readme = files["README.md"]
        assert "kb/INSTALL_FLOW.md" in readme
        assert "kb/HERMES.md" in readme
        assert "kb/UPDATE_NOTES.md" in readme
        assert "kb/TAILSCALE_PLAYBOOK.md" in readme


# ---------------------------------------------------------------------------
# OpenClaw stack
# ---------------------------------------------------------------------------


class TestOpenClawPackage:
    """OpenClaw stack — linux + anthropic, no tailscale, no channels."""

    @pytest.fixture()
    def state(self):
        return OnboardingState(
            stack="openclaw",
            os="linux",
            provider="anthropic",
            goal="install",
        )

    @pytest.fixture()
    def files(self, state):
        zip_bytes, filename = build_onboarding_package(state)
        assert filename == "openclaw-setup.zip"
        return _extract_zip(zip_bytes)

    def test_does_not_guess_openclaw_runtime_config(self, files):
        assert "openclaw.json" not in files

    def test_pins_current_openclaw_release_and_runtime(self, files):
        lock = json.loads(files["upstream.lock.json"])
        assert lock["repository"] == "https://github.com/openclaw/openclaw"
        assert lock["ref"] == "v2026.7.1"
        assert lock["version"] == "2026.7.1"
        assert lock["runtime"] == "Node >=22.22.3,<23 or >=24.15.0,<25 or >=25.9.0"
        assert "$OPENCLAW_INSTALL_COMMIT/scripts/install.sh" in files["install.sh"]
        assert "--install-method npm" in files["install.sh"]
        assert '--version "$OPENCLAW_VERSION"' in files["install.sh"]
        assert "--no-onboard" not in files["install.sh"]
        assert "--no-prompt" not in files["install.sh"]
        assert "\nopenclaw onboard" not in files["install.sh"]
        assert "openclaw@latest" not in files["install.sh"]
        assert "command -v node" not in files["install.sh"]
        assert "command -v npm" not in files["install.sh"]

    def test_no_tailscale_script(self, files):
        assert "tailscale-setup.sh" not in files

    def test_no_channels_dir(self, files):
        channel_files = [f for f in files if f.startswith("channels/")]
        assert channel_files == []

    def test_env_template_has_anthropic_key(self, files):
        assert ".env.template" in files
        assert "ANTHROPIC_API_KEY" in files[".env.template"]

    def test_readme_mentions_stack_os_provider(self, files):
        readme = files["README.md"]
        assert "OpenClaw" in readme
        assert "Linux" in readme
        assert "Anthropic" in readme

    def test_install_sh_non_empty(self, files):
        assert "install.sh" in files
        assert len(files["install.sh"].strip()) > 0


# ---------------------------------------------------------------------------
# NanoClaw stack
# ---------------------------------------------------------------------------


class TestNanoClawPackage:
    """NanoClaw stack — windows_wsl2 + local provider."""

    @pytest.fixture()
    def state(self):
        return OnboardingState(
            stack="nanoclaw",
            os="windows_wsl2",
            provider="local",
            goal="install",
        )

    @pytest.fixture()
    def files(self, state):
        zip_bytes, filename = build_onboarding_package(state)
        assert filename == "nanoclaw-setup.zip"
        return _extract_zip(zip_bytes)

    def test_does_not_ship_a_fantasy_latest_compose(self, files):
        assert "docker-compose.yml" not in files
        assert "nanoclaw/agent:latest" not in "\n".join(files.values())

    def test_pins_canonical_nanoclaw_v2_release(self, files):
        lock = json.loads(files["upstream.lock.json"])
        assert lock["repository"] == "https://github.com/nanocoai/nanoclaw"
        assert lock["ref"] == "v2.1.17"
        assert "github.com/nanocoai/nanoclaw.git" in files["install.sh"]
        assert "NANOCLAW_REF='v2.1.17'" in files["install.sh"]
        assert "bash nanoclaw.sh" in files["install.sh"]

    def test_readme_mentions_stack_os_provider(self, files):
        readme = files["README.md"]
        assert "NanoClaw" in readme
        assert "Windows (WSL2)" in readme
        # Local provider is rendered as "Local (LM Studio/Ollama)"
        assert "Local" in readme

    def test_env_template_has_local_url(self, files):
        assert ".env.template" in files
        assert "LOCAL_MODEL_URL" in files[".env.template"]

    def test_no_tailscale_without_networking(self, files):
        assert "tailscale-setup.sh" not in files


# ---------------------------------------------------------------------------
# PicoClaw stack
# ---------------------------------------------------------------------------


class TestPicoClawPackage:
    """PicoClaw stack — android + google provider."""

    @pytest.fixture()
    def state(self):
        return OnboardingState(
            stack="picoclaw",
            os="android",
            provider="google",
            goal="install",
        )

    @pytest.fixture()
    def files(self, state):
        zip_bytes, filename = build_onboarding_package(state)
        assert filename == "picoclaw-setup.zip"
        return _extract_zip(zip_bytes)

    def test_does_not_guess_picoclaw_runtime_config(self, files):
        assert "config.json" not in files
        assert ".security.yml.template" not in files

    def test_pins_current_android_release_and_checksum_instructions(self, files):
        lock = json.loads(files["upstream.lock.json"])
        assert lock["repository"] == "https://github.com/sipeed/picoclaw"
        assert lock["ref"] == "v0.3.1"
        android_release = lock["android_distribution"]
        assert android_release["repository"] == "https://github.com/sipeed/picoclaw_fui"
        assert android_release["ref"] == "picoclaw_fui-v0.1.4"
        assert android_release["commit"] == "d689c94c1b67f625f70ec4111a9aa3f01be9cbb3"
        assert android_release["asset"] == "picoclaw_fui-android-universal.apk"
        assert (
            android_release["sha256"]
            == "7700b209deffb26008c5296c6467e9f6426538f162d978a153bc8313cc25c373"
        )
        assert "picoclaw_fui-android-universal.apk" in files["install.sh"]
        assert "picoclaw-android-universal.zip" not in files["install.sh"]

    def test_android_helper_cannot_report_a_false_install_success(self, files):
        install_script = files["install.sh"]
        result = subprocess.run(
            ["bash"],
            input=install_script,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 2
        assert "no runtime was installed and setup is not complete" in result.stdout
        assert "Setup complete" not in install_script

        readme = files["README.md"]
        assert "information-only helper" in readme
        assert "exits with status 2" in readme
        assert "https://docs.picoclaw.io/docs/installation/android/" in readme

    def test_android_verification_uses_the_app_service_instead_of_a_desktop_path(self, files):
        readme = files["README.md"]
        assert "Tap **Start Service**" in readme
        assert "http://127.0.0.1:18800" in readme
        assert 'export PATH="$HOME/.local/bin:$PATH"' not in readme
        assert "picoclaw --version" not in readme

    def test_desktop_package_preserves_the_complete_release_toolset(self):
        state = OnboardingState(
            stack="picoclaw",
            os="linux",
            provider="google",
            goal="install",
        )
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        install_script = files["install.sh"]

        assert "for binary in picoclaw picoclaw-launcher" in install_script
        assert 'install -m 0755 "$TMP_DIR/$binary" "$HOME/.local/bin/$binary"' in install_script
        assert 'export PATH="$HOME/.local/bin:$PATH"' in install_script
        assert '"$HOME/.local/bin/picoclaw" onboard' in install_script

        readme = files["README.md"]
        assert 'export PATH="$HOME/.local/bin:$PATH"' in readme
        assert "picoclaw version && picoclaw status" in readme
        assert "picoclaw --version" not in readme

        bundled_kb = files["kb/PICOCLAW.md"]
        assert "picoclaw-launcher`" in bundled_kb
        assert "do not ship `picoclaw-launcher-tui`" in bundled_kb
        assert "\npicoclaw-launcher-tui\n" not in bundled_kb

    def test_linux_package_maps_every_published_release_architecture(self):
        state = OnboardingState(
            stack="picoclaw",
            os="linux",
            provider="google",
            goal="install",
        )
        zip_bytes, _ = build_onboarding_package(state)
        install_script = _extract_zip(zip_bytes)["install.sh"]

        expected_mappings = {
            "x86_64|amd64": "x86_64",
            "arm64|aarch64": "arm64",
            "armv6|armv6l": "armv6",
            "armv7|armv7l": "armv7",
            "loong64|loongarch64": "loong64",
            "mipsle|mipsel": "mipsle",
            "riscv64": "riscv64",
            "s390x": "s390x",
        }
        for uname_values, release_arch in expected_mappings.items():
            assert f"{uname_values}) PICOCLAW_ARCH='{release_arch}'" in install_script

    def test_macos_package_does_not_offer_linux_only_release_architectures(self):
        state = OnboardingState(
            stack="picoclaw",
            os="macos",
            provider="google",
            goal="install",
        )
        zip_bytes, _ = build_onboarding_package(state)
        install_script = _extract_zip(zip_bytes)["install.sh"]

        assert "x86_64|amd64) PICOCLAW_ARCH='x86_64'" in install_script
        assert "arm64|aarch64) PICOCLAW_ARCH='arm64'" in install_script
        for linux_only_arch in ("armv6", "armv7", "loong64", "mipsle", "riscv64", "s390x"):
            assert f"PICOCLAW_ARCH='{linux_only_arch}'" not in install_script

    def test_readme_mentions_stack_os_provider(self, files):
        readme = files["README.md"]
        assert "PicoClaw" in readme
        assert "Android" in readme
        assert "Google" in readme

    def test_env_template_has_google_key(self, files):
        assert ".env.template" in files
        assert "GOOGLE_API_KEY" in files[".env.template"]


# ---------------------------------------------------------------------------
# Cross-stack validation
# ---------------------------------------------------------------------------


class TestCrossStackValidation:
    """Checks that apply to all stacks."""

    @pytest.mark.parametrize(
        "stack,os_name,provider",
        [
            ("hermes", "macos", "openai"),
            ("openclaw", "linux", "anthropic"),
            ("nanoclaw", "windows_wsl2", "local"),
            ("picoclaw", "android", "google"),
        ],
    )
    def test_install_sh_non_empty(self, stack, os_name, provider):
        state = OnboardingState(stack=stack, os=os_name, provider=provider, goal="install")
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        assert "install.sh" in files
        assert len(files["install.sh"].strip()) > 0
        subprocess.run(
            ["bash", "-n"],
            input=files["install.sh"],
            text=True,
            check=True,
        )

    @pytest.mark.parametrize(
        "stack,expected_ref,expected_commit",
        [
            ("hermes", "v2026.7.20", "3ef6bbd201263d354fd83ec55b3c306ded2eb72a"),
            ("openclaw", "v2026.7.1", "2d2ddc43d0dcf71f31283d780f9fe9ff4cc04fe4"),
            ("nanoclaw", "v2.1.17", "ee7f891698760f21b9e79a850d64c7f633cd95ef"),
            ("picoclaw", "v0.3.1", "2cf030d2fd3b871d7ec17e3be34c24688aac76da"),
        ],
    )
    def test_every_package_records_a_verified_upstream_ref(
        self,
        stack,
        expected_ref,
        expected_commit,
    ):
        state = OnboardingState(stack=stack, os="linux", provider="openai", goal="install")
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        lock = json.loads(files["upstream.lock.json"])

        assert lock["schema_version"] == 1
        assert lock["ref"] == expected_ref
        assert lock["commit"] == expected_commit
        assert lock["verified_at"] == "2026-07-22"
        assert "@latest" not in files["install.sh"]
        assert "install.sh | bash" not in files["install.sh"]

    @pytest.mark.parametrize(
        "stack,os_name,provider",
        [
            ("hermes", "macos", "openai"),
            ("openclaw", "linux", "anthropic"),
            ("nanoclaw", "windows_wsl2", "local"),
            ("picoclaw", "android", "google"),
        ],
    )
    def test_readme_mentions_correct_details(self, stack, os_name, provider):
        state = OnboardingState(stack=stack, os=os_name, provider=provider, goal="install")
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        readme = files["README.md"]

        stack_names = {
            "hermes": "Hermes",
            "openclaw": "OpenClaw",
            "nanoclaw": "NanoClaw",
            "picoclaw": "PicoClaw",
        }
        os_names = {
            "macos": "macOS",
            "linux": "Linux",
            "windows_wsl2": "Windows (WSL2)",
            "android": "Android",
        }
        provider_names = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "google": "Google",
            "local": "Local",
        }

        assert stack_names[stack] in readme
        assert os_names[os_name] in readme
        assert provider_names[provider] in readme

    @pytest.mark.parametrize(
        "stack,os_name,provider,expected_key",
        [
            ("hermes", "macos", "openai", "OPENAI_API_KEY"),
            ("openclaw", "linux", "anthropic", "ANTHROPIC_API_KEY"),
            ("nanoclaw", "windows_wsl2", "local", "LOCAL_MODEL_URL"),
            ("picoclaw", "android", "google", "GOOGLE_API_KEY"),
        ],
    )
    def test_env_template_has_correct_provider_key(self, stack, os_name, provider, expected_key):
        state = OnboardingState(stack=stack, os=os_name, provider=provider, goal="install")
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        assert expected_key in files[".env.template"]

    def test_no_tailscale_when_not_requested(self):
        state = OnboardingState(
            stack="hermes",
            os="linux",
            provider="openai",
            goal="install",
            networking="local",
        )
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        assert "tailscale-setup.sh" not in files

    def test_no_tailscale_when_networking_is_none(self):
        state = OnboardingState(
            stack="hermes",
            os="linux",
            provider="openai",
            goal="install",
        )
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        assert "tailscale-setup.sh" not in files

    def test_tailscale_included_when_requested(self):
        state = OnboardingState(
            stack="openclaw",
            os="linux",
            provider="openai",
            goal="install",
            networking="tailscale",
        )
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)
        assert "tailscale-setup.sh" in files

    def test_filename_reflects_stack(self):
        for stack in ("hermes", "openclaw", "nanoclaw", "picoclaw"):
            state = OnboardingState(stack=stack, os="linux", provider="openai", goal="install")
            _, filename = build_onboarding_package(state)
            assert filename == f"{stack}-setup.zip"

    @pytest.mark.parametrize(
        "stack,expected_doc",
        [
            ("hermes", "HERMES.md"),
            ("openclaw", "OPENCLAW.md"),
            ("nanoclaw", "NANOCLAW.md"),
            ("picoclaw", "PICOCLAW.md"),
        ],
    )
    def test_zip_contains_current_stack_specific_kb_doc(self, stack, expected_doc):
        state = OnboardingState(stack=stack, os="linux", provider="openai", goal="install")
        zip_bytes, _ = build_onboarding_package(state)
        files = _extract_zip(zip_bytes)

        assert files["kb/INSTALL_FLOW.md"] == _read_knowledge_doc("INSTALL_FLOW.md")
        assert files["kb/UPDATE_NOTES.md"] == _read_knowledge_doc("UPDATE_NOTES.md")
        assert files[f"kb/{expected_doc}"] == _read_knowledge_doc(expected_doc)
        assert "Runtime configuration is not generated by MUTX" in files["kb/INSTALL_FLOW.md"]
        assert "`channels/`" not in files["kb/INSTALL_FLOW.md"]
