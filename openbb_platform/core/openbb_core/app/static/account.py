"""Account."""

# pylint: disable=W0212:protected-access
import json
from functools import wraps
from pathlib import Path
from sys import exc_info
from typing import TYPE_CHECKING, Optional

from openbb_core.app.logs.logging_service import LoggingService
from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.app.model.hub.hub_session import HubSession
from openbb_core.app.model.user_settings import UserSettings
from openbb_core.app.service.hub_service import HubService
from openbb_core.app.service.user_service import UserService

if TYPE_CHECKING:
    from openbb_core.app.static.app_factory import BaseApp


class Account:
    """/account
    login
    logout
    save
    refresh
    """

    SESSION_FILE = ".hub_session.json"

    def __init__(self, base_app: "BaseApp"):
        """Initialize account service."""
        self._base_app = base_app
        self._openbb_directory = (
            base_app._command_runner.system_settings.openbb_directory
        )

    def __repr__(self) -> str:
        """Human readable representation of the object."""
        return self.__doc__ or ""

    def _log_account_command(func):  # pylint: disable=E0213
        """Log account command."""

        @wraps(func)
        def wrapped(self, *args, **kwargs):
            try:
                result = func(self, *args, **kwargs)  # pylint: disable=E1102
            except Exception as e:
                raise OpenBBError(e) from e
            finally:
                user_settings = self._base_app._command_runner.user_settings
                system_settings = self._base_app._command_runner.system_settings
                ls = LoggingService(
                    user_settings=user_settings, system_settings=system_settings
                )
                ls.log(
                    user_settings=user_settings,
                    system_settings=system_settings,
                    route=f"/account/{func.__name__}",  # pylint: disable=E1101
                    func=func,
                    kwargs={},  # don't want any credentials being logged by accident
                    exec_info=exc_info(),
                )

            return result

        return wrapped

    def _create_hub_service(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        pat: Optional[str] = None,
    ) -> HubService:
        """Create hub service to handle connection."""
        if email is None and password is None and pat is None:
            session_file = Path(self._openbb_directory, self.SESSION_FILE)
            if not session_file.exists():
                raise OpenBBError("Session not found.")

            with open(session_file) as f:
                session_dict = json.load(f)

            hub_session = HubSession(**session_dict)
            hs = HubService(hub_session)
        else:
            hs = HubService()
            hs.connect(email, password, pat)
        return hs

    @_log_account_command  # type: ignore
    def login(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        pat: Optional[str] = None,
        remember_me: bool = False,
        return_settings: bool = False,
    ) -> Optional[UserSettings]:
        """Login to hub.

        Parameters
        ----------
        email : Optional[str], optional
            Email address, by default None
        password : Optional[str], optional
            Password, by default None
        pat : Optional[str], optional
            Personal access token, by default None
        remember_me : bool, optional
            Remember me, by default False
        return_settings : bool, optional
            Return user settings, by default False

        Returns
        -------
        Optional[UserSettings]
            User settings: profile, credentials, preferences
        """
        hs = self._create_hub_service(email, password, pat)
        incoming = hs.pull()
        updated: UserSettings = UserService.update_default(incoming)
        self._base_app._command_runner.user_settings = updated
        if remember_me:
            Path(self._openbb_directory).mkdir(parents=False, exist_ok=True)
            session_file = Path(self._openbb_directory, self.SESSION_FILE)
            with open(session_file, "w") as f:
                if not hs.session:
                    raise OpenBBError("Not connected to hub.")

                json.dump(hs.session.model_dump(mode="json"), f, indent=4)

        if return_settings:
            return self._base_app._command_runner.user_settings
        return None

    @_log_account_command  # type: ignore
    def save(self, return_settings: bool = False) -> Optional[UserSettings]:
        """Save user settings.

        Parameters
        ----------
        return_settings : bool, optional
            Return user settings, by default False

        Returns
        -------
        Optional[UserSettings]
            User settings: profile, credentials, preferences
        """
        hub_session = self._base_app._command_runner.user_settings.profile.hub_session
        if not hub_session:
            UserService.write_default_user_settings(
                self._base_app._command_runner.user_settings
            )
        else:
            hs = HubService(hub_session)
            hs.push(self._base_app._command_runner.user_settings)

        if return_settings:
            return self._base_app._command_runner.user_settings
        return None

    @_log_account_command  # type: ignore
    def refresh(self, return_settings: bool = False) -> Optional[UserSettings]:
        """Refresh user settings.

        Parameters
        ----------
        return_settings : bool, optional
            Return user settings, by default False

        Returns
        -------
        Optional[UserSettings]
            User settings: profile, credentials, preferences
        """
        hub_session = self._base_app._command_runner.user_settings.profile.hub_session
        if not hub_session:
            self._base_app._command_runner.user_settings = (
                UserService.read_default_user_settings()
            )
        else:
            hs = HubService(hub_session)
            incoming = hs.pull()
            updated: UserSettings = UserService.update_default(incoming)
            updated.id = self._base_app._command_runner.user_settings.id
            self._base_app._command_runner.user_settings = updated

        if return_settings:
            return self._base_app._command_runner.user_settings
        return None

    @_log_account_command  # type: ignore
    def logout(self, return_settings: bool = False) -> Optional[UserSettings]:
        """Logout from hub.

        Parameters
        ----------
        return_settings : bool, optional
            Return user settings, by default False

        Returns
        -------
        Optional[UserSettings]
            User settings: profile, credentials, preferences
        """
        hub_session = self._base_app._command_runner.user_settings.profile.hub_session
        if not hub_session:
            raise OpenBBError("Not connected to hub.")

        hs = HubService(hub_session)
        hs.disconnect()

        session_file = Path(self._openbb_directory, self.SESSION_FILE)
        if session_file.exists():
            session_file.unlink()

        self._base_app._command_runner.user_settings = (
            UserService.read_default_user_settings()
        )

        if return_settings:
            return self._base_app._command_runner.user_settings
        return None
