import shutil

import click

from cli.commands.tui import launch_tui
from cli.config import LOCAL_API_URL, current_config, get_client, resolve_hosted_api_url
from cli.faramesh_runtime import (
    ensure_faramesh_installed,
    is_faramesh_available,
    start_faramesh_daemon,
    FAREMESH_SOCKET_PATH,
)
from cli.local_control_plane import ensure_local_container_runtime, ensure_local_control_plane
from cli.openclaw_runtime import find_openclaw_bin
from cli.services import AssistantService, AuthService, CLIServiceError, RuntimeStateService
from cli.services.assistant import TemplatesService
from cli.setup_wizard import mark_auth_completed, run_openclaw_setup_wizard


@click.group(name="setup")
def setup_group():
    """Guided assistant-first onboarding."""
    pass


def _auth_service() -> AuthService:
    return AuthService(config=current_config(), client_factory=get_client)


def _templates_service() -> TemplatesService:
    return TemplatesService(config=current_config(), client_factory=get_client)


def _assistant_service() -> AssistantService:
    return AssistantService(config=current_config(), client_factory=get_client)


def _runtime_service() -> RuntimeStateService:
    return RuntimeStateService(config=current_config(), client_factory=get_client)


def _require_value(label: str, value: str | None, no_input: bool, *, secret: bool = False) -> str:
    if value:
        return value
    if no_input:
        raise click.ClickException(f"{label} is required in --no-input mode.")
    return click.prompt(label, hide_input=secret)


def _choose_openclaw_action(
    *, no_input: bool, import_openclaw: bool, install_openclaw: bool
) -> str:
    existing_binary = find_openclaw_bin()
    if import_openclaw:
        if not existing_binary:
            raise click.ClickException(
                "OpenClaw is not installed, so it cannot be imported yet. "
                "Install it first or rerun without `--import-openclaw`."
            )
        return "import"
    if not existing_binary:
        return "install"
    if no_input:
        return "import"

    click.echo("")
    click.echo("OpenClaw detected locally. Choose how MUTX should proceed:")
    click.echo(f"  1. Import Existing OpenClaw 🦞  [{existing_binary}]")
    click.echo("  2. Install / Repair OpenClaw")
    click.echo("  3. Open OpenClaw TUI 🦞")
    click.echo("  4. Cancel")
    selection = click.prompt("Select an action", type=click.IntRange(1, 4), default=1)
    mapping = {
        1: "import",
        2: "install",
        3: "tui",
        4: "cancel",
    }
    return mapping[selection]


def _echo_first_agent_hint() -> None:
    click.echo("")
    click.echo("Immediate payoff:")
    click.echo("  mutx onboard --help")
    if shutil.which("hermes"):
        click.echo(
            "Use onboard to pick your next guided flow, then run mutx runtime inspect to verify your local runtime."
        )
    else:
        click.echo(
            "Use onboard to pick your next guided flow, then run mutx runtime inspect after your runtime is configured."
        )


def _finish_setup(
    *,
    mode: str,
    provider: str,
    assistant_name: str,
    description: str | None,
    replicas: int,
    model: str | None,
    workspace: str | None,
    install_openclaw: bool,
    import_openclaw: bool,
    openclaw_install_method: str,
    no_input: bool,
    open_tui: bool,
) -> None:
    if provider != "openclaw":
        raise click.ClickException(
            f"Unsupported provider '{provider}'. Only openclaw is enabled in this sprint."
        )

    action_type = _choose_openclaw_action(
        no_input=no_input,
        import_openclaw=import_openclaw,
        install_openclaw=install_openclaw,
    )
    if action_type == "cancel":
        click.echo("Setup cancelled before OpenClaw import/install.")
        return

    default_model = str(current_config().assistant_defaults.get("model") or model or "")
    effective_install_openclaw = install_openclaw or (
        action_type == "install" and find_openclaw_bin() is not None
    )

    def _report(event: dict[str, object]) -> None:
        state = str(event.get("state") or "running")
        message = str(event.get("message") or "").strip()
        prefix = {"running": "…", "completed": "✓", "failed": "x"}.get(state, "•")
        click.echo(f"{prefix} {message}")

    result = run_openclaw_setup_wizard(
        mode=mode,
        assistant_name=assistant_name,
        description=description,
        replicas=replicas,
        model=model or default_model,
        workspace=workspace,
        install_openclaw=effective_install_openclaw,
        openclaw_install_method=openclaw_install_method,
        no_input=no_input,
        requested_action=action_type,
        templates_service=_templates_service(),
        assistant_service=_assistant_service(),
        runtime_service=_runtime_service(),
        prompt_install=lambda: click.confirm(
            "OpenClaw is required for the Personal Assistant and is not installed. Install it now?",
            default=True,
        ),
        progress=_report,
    )
    if result.deployment is not None:
        click.echo(f"Assistant deployed: {result.deployment['agent']['id']}")
        click.echo(f"Deployment: {result.deployment['deployment']['id']}")
    else:
        click.echo(f"Assistant already present: {result.assistant_id}")
    click.echo(f"OpenClaw assistant_id: {result.binding.agent_id}")
    click.echo(f"OpenClaw binary: {result.runtime_snapshot.get('binary_path') or 'n/a'}")
    click.echo(f"OpenClaw home: {result.runtime_snapshot.get('home_path') or 'n/a'}")
    click.echo(f"OpenClaw config: {result.runtime_snapshot.get('config_path') or 'n/a'}")
    click.echo(f"Workspace: {result.binding.workspace}")
    click.echo(f"Gateway: {result.health.gateway_url or 'n/a'} ({result.health.status})")
    click.echo("Tracking: imported into ~/.mutx/providers/openclaw")
    if result.action_type in {"import", "tui", "configure"}:
        click.echo(
            "Adoption: existing OpenClaw runtime added to MUTX tracking without moving the upstream home."
        )
    click.echo(
        f"Privacy: {result.runtime_snapshot.get('privacy_summary') or 'Local-only runtime tracking.'}"
    )

    _echo_first_agent_hint()
    _install_faramesh_governance()

    if open_tui:
        launch_tui()


def _install_faramesh_governance() -> None:
    """Auto-install and start Faramesh governance daemon as part of MUTX setup."""
    import os
    import shutil

    click.echo("")
    click.echo("… Installing Faramesh governance engine")

    installed, bin_path = ensure_faramesh_installed(install_if_missing=False, non_interactive=True)
    if not installed:
        click.echo("  ⚠ Faramesh is not installed; skipping automatic install for security")
        click.echo("    Install manually via trusted channel, then run: mutx governance start")
        return

    click.echo(f"  ✓ Faramesh installed: {bin_path}")

    if is_faramesh_available():
        click.echo("  ✓ Faramesh governance daemon already running")
        return

    bundled_policy = os.path.join(os.path.dirname(__file__), "..", "policies", "starter.fpl")
    bundled_policy = os.path.abspath(bundled_policy)
    policy_dir = os.path.expanduser("~/.mutx/policies")
    policy_path = os.path.join(policy_dir, "starter.fpl")

    os.makedirs(policy_dir, exist_ok=True)
    if not os.path.exists(policy_path):
        shutil.copy(bundled_policy, policy_path)
        click.echo(f"  ✓ Bundled policy installed to {policy_path}")

    proc = start_faramesh_daemon(policy_path=policy_path, socket_path=FAREMESH_SOCKET_PATH)  # noqa: F821
    if proc is None:
        click.echo("  ⚠ Faramesh daemon could not be started automatically")
        click.echo("    Run manually: faramesh serve --policy <policy.yaml>")
        return

    import time

    time.sleep(0.3)
    if proc.poll() is not None:
        click.echo("  ⚠ Faramesh daemon exited immediately - may need a policy file")
        click.echo("    Run manually: faramesh serve --policy <policy.yaml>")
        return

    click.echo(f"  ✓ Faramesh governance daemon started on {FAREMESH_SOCKET_PATH}")
    click.echo("    Governance is now active for all agent tool calls.")


@setup_group.command(name="hosted")
@click.option(
    "--api-url",
    default=None,
    help="Hosted API base URL (defaults to the configured remote or https://api.mutx.dev)",
)
@click.option("--email", default=None, help="Account email")
@click.option("--password", default=None, help="Account password")
@click.option("--assistant-name", default="Personal Assistant", help="Assistant display name")
@click.option("--description", default=None, help="Assistant description")
@click.option("--replicas", default=1, type=int, help="Replica count")
@click.option("--model", default=None, help="Assistant model override")
@click.option("--workspace", default=None, help="Assistant workspace override")
@click.option(
    "--provider",
    type=click.Choice(["openclaw"]),
    default="openclaw",
    show_default=True,
    help="Runtime provider for the starter assistant",
)
@click.option(
    "--install-openclaw", is_flag=True, help="Install OpenClaw automatically if it is missing"
)
@click.option(
    "--import-openclaw",
    is_flag=True,
    help="Import and track an existing OpenClaw runtime without reinstalling it",
)
@click.option(
    "--openclaw-install-method",
    type=click.Choice(["npm", "git"]),
    default="npm",
    show_default=True,
    help="OpenClaw install method when installation is required",
)
@click.option("--open-tui", is_flag=True, help="Launch the TUI after setup")
@click.option("--no-input", is_flag=True, help="Disable prompts")
@click.option(
    "--register/--login-existing",
    default=False,
    help="Register a new account (default: login to existing)",
)
@click.option(
    "--name",
    "display_name",
    default=None,
    help="Display name for new account (used with --register)",
)
def setup_hosted(
    api_url: str | None,
    email: str | None,
    password: str | None,
    register: bool,
    display_name: str | None,
    assistant_name: str,
    description: str | None,
    replicas: int,
    model: str | None,
    workspace: str | None,
    provider: str,
    install_openclaw: bool,
    import_openclaw: bool,
    openclaw_install_method: str,
    open_tui: bool,
    no_input: bool,
):
    config = current_config()
    target_api_url = resolve_hosted_api_url(config, api_url)
    config.api_url = target_api_url

    try:
        if register:
            registration = _auth_service().register(
                name=_require_value("Name", display_name or "MUTX User", no_input),
                email=_require_value("Email", email, no_input),
                password=_require_value("Password", password, no_input, secret=True),
                api_url=target_api_url,
            )
            if registration is not None and not registration.authenticated:
                click.echo("Registered. Verify your email, then rerun 'mutx setup hosted'.")
                return
        else:
            _auth_service().login(
                email=_require_value("Email", email, no_input),
                password=_require_value("Password", password, no_input, secret=True),
                api_url=target_api_url,
            )
        mark_auth_completed(
            mode="hosted",
            provider=provider,
            assistant_name=assistant_name,
            runtime_service=_runtime_service(),
            reset=True,
        )
        _finish_setup(
            mode="hosted",
            provider=provider,
            assistant_name=assistant_name,
            description=description,
            replicas=replicas,
            model=model,
            workspace=workspace,
            install_openclaw=install_openclaw,
            import_openclaw=import_openclaw,
            openclaw_install_method=openclaw_install_method,
            no_input=no_input,
            open_tui=open_tui,
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc


@setup_group.command(name="local")
@click.option("--email", default=None, help="Existing local account email (advanced)")
@click.option("--password", default=None, help="Existing local account password (advanced)")
@click.option(
    "--name", "display_name", default="Local Operator", help="Local operator display name"
)
@click.option(
    "--register/--login-existing",
    default=True,
    help="Legacy credential flow when email and password are supplied",
)
@click.option("--assistant-name", default="Personal Assistant", help="Assistant display name")
@click.option("--description", default=None, help="Assistant description")
@click.option("--replicas", default=1, type=int, help="Replica count")
@click.option("--model", default=None, help="Assistant model override")
@click.option("--workspace", default=None, help="Assistant workspace override")
@click.option(
    "--provider",
    type=click.Choice(["openclaw"]),
    default="openclaw",
    show_default=True,
    help="Runtime provider for the starter assistant",
)
@click.option(
    "--install-openclaw", is_flag=True, help="Install OpenClaw automatically if it is missing"
)
@click.option(
    "--import-openclaw",
    is_flag=True,
    help="Import and track an existing OpenClaw runtime without reinstalling it",
)
@click.option(
    "--openclaw-install-method",
    type=click.Choice(["npm", "git"]),
    default="npm",
    show_default=True,
    help="OpenClaw install method when installation is required",
)
@click.option("--open-tui", is_flag=True, help="Launch the TUI after setup")
@click.option("--no-input", is_flag=True, help="Disable prompts")
def setup_local(
    email: str | None,
    password: str | None,
    display_name: str,
    register: bool,
    assistant_name: str,
    description: str | None,
    replicas: int,
    model: str | None,
    workspace: str | None,
    provider: str,
    install_openclaw: bool,
    import_openclaw: bool,
    openclaw_install_method: str,
    open_tui: bool,
    no_input: bool,
):
    current_config().api_url = LOCAL_API_URL

    try:
        local_state = ensure_local_control_plane(
            api_url=LOCAL_API_URL,
            progress=lambda message: click.echo(f"… {message}"),
            container_runtime_ensurer=lambda progress: ensure_local_container_runtime(
                progress=progress,
                prompt_install=(
                    None if no_input else lambda prompt: click.confirm(prompt, default=True)
                ),
            ),
        )
        if local_state.bootstrapped_now:
            click.echo(f"✓ Local control plane ready at {LOCAL_API_URL}")
            if local_state.source_kind == "managed_checkout":
                click.echo(
                    "Tracking: managed localhost stack lives under ~/.mutx/runtime/local-control"
                )
        if email or password:
            email_value = _require_value("Email", email, no_input)
            password_value = _require_value("Password", password, no_input, secret=True)
            if register:
                registration = _auth_service().register(
                    name=display_name,
                    email=email_value,
                    password=password_value,
                )
                if registration is not None and not registration.authenticated:
                    click.echo("Registered. Verify your email, then rerun 'mutx setup local'.")
                    return
            else:
                _auth_service().login(email=email_value, password=password_value)
        else:
            _auth_service().local_bootstrap(name=display_name)
        mark_auth_completed(
            mode="local",
            provider=provider,
            assistant_name=assistant_name,
            runtime_service=_runtime_service(),
            reset=True,
        )
        _finish_setup(
            mode="local",
            provider=provider,
            assistant_name=assistant_name,
            description=description,
            replicas=replicas,
            model=model,
            workspace=workspace,
            install_openclaw=install_openclaw,
            import_openclaw=import_openclaw,
            openclaw_install_method=openclaw_install_method,
            no_input=no_input,
            open_tui=open_tui,
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
