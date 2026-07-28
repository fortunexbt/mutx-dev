from __future__ import annotations

from cli.errors import InvalidCredentialsError
from cli.services.base import APIRequestError, APIService
from cli.services.models import CLIStatus, UserProfile


class AuthService(APIService):
    def _store_tokens(self, access_token: str | None, refresh_token: str | None) -> None:
        if hasattr(self.config, "access_token"):
            self.config.access_token = access_token
        else:
            self.config.api_key = access_token
        self.config.refresh_token = refresh_token

    def status(self) -> CLIStatus:
        access_token = getattr(self.config, "access_token", getattr(self.config, "api_key", None))
        refresh_token = getattr(self.config, "refresh_token", None)
        return CLIStatus(
            api_url=self.config.api_url,
            config_path=self.config.config_path,
            api_url_source=getattr(self.config, "api_url_source", "config"),
            authenticated=self.config.is_authenticated(),
            has_access_token=bool(access_token),
            has_refresh_token=bool(refresh_token),
        )

    def login(self, email: str, password: str, api_url: str | None = None) -> CLIStatus:
        if api_url:
            self.config.api_url = api_url
        elif not self.config.api_url:
            self.config.api_url = "http://localhost:8000"

        response = self._request(
            "post",
            "/v1/auth/login",
            require_auth=False,
            json={"email": email, "password": password},
        )

        if response.status_code == 200:
            tokens = self._decode_json(response, expected_type=dict)
            self._store_tokens(tokens.get("access_token"), tokens.get("refresh_token"))
            return self.status()

        if response.status_code == 401:
            raise InvalidCredentialsError("Invalid email or password")

        raise APIRequestError(
            self._extract_error_message(response, "Login failed."),
            status_code=response.status_code,
        )

    def local_bootstrap(
        self,
        *,
        name: str = "Local Operator",
        api_url: str | None = None,
    ) -> CLIStatus:
        if api_url:
            self.config.api_url = api_url
        elif not self.config.api_url:
            self.config.api_url = "http://localhost:8000"

        response = self._request(
            "post",
            "/v1/auth/local-bootstrap",
            require_auth=False,
            json={"name": name},
        )

        if response.status_code == 200:
            tokens = self._decode_json(response, expected_type=dict)
            self._store_tokens(tokens.get("access_token"), tokens.get("refresh_token"))
            return self.status()

        raise APIRequestError(
            self._extract_error_message(response, "Local bootstrap failed."),
            status_code=response.status_code,
        )

    def register(
        self, name: str, email: str, password: str, api_url: str | None = None
    ) -> CLIStatus:
        if api_url:
            self.config.set_runtime_api_url(api_url)

        response = self._request(
            "post",
            "/v1/auth/register",
            require_auth=False,
            json={"name": name, "email": email, "password": password},
        )

        if response.status_code == 201:
            tokens = self._decode_json(response, expected_type=dict)
            self._store_tokens(tokens.get("access_token"), tokens.get("refresh_token"))
            return self.status()

        raise APIRequestError(
            self._extract_error_message(response, "Registration failed."),
            status_code=response.status_code,
        )

    def logout(self) -> bool:
        if not self.config.is_authenticated():
            return False

        response = self._request(
            "post",
            "/v1/auth/logout",
            allow_refresh=False,
            json={"refresh_token": self.config.refresh_token},
        )
        self._expect_status(response, {200})
        self.config.clear_auth()
        return True

    def whoami(self) -> UserProfile:
        response = self._request("get", "/v1/auth/me")
        self._expect_status(response, {200})
        return UserProfile.from_payload(self._decode_json(response, expected_type=dict))
