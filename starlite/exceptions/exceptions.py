from http import HTTPStatus
from typing import Any, Dict, List, Optional, Union

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)


class StarLiteException(Exception):
    def __init__(self, *args: Any, detail: str = ""):
        """Base `starlite` exception.

        Args:
            *args (Any): args are cast to `str` before passing to `Exception.__init__()`
            detail (str, optional): detail of the exception.
        """
        self.detail = detail
        super().__init__(*(str(arg) for arg in args if arg), detail)

    def __repr__(self) -> str:
        if self.detail:
            return f"{self.__class__.__name__} - {self.detail}"
        return self.__class__.__name__

    def __str__(self) -> str:
        return " ".join(self.args).strip()


class MissingDependencyException(StarLiteException, ImportError):
    """Missing optional dependency."""


class HTTPException(StarletteHTTPException, StarLiteException):
    status_code = HTTP_500_INTERNAL_SERVER_ERROR
    """Default status code for the exception type"""

    def __init__(
        self,
        *args: Any,
        detail: Optional[str] = None,
        status_code: Optional[int] = None,
        extra: Optional[Union[Dict[str, Any], List[Any]]] = None,
    ):
        """Base exception for HTTP error responses.

        These exceptions carry information to construct an HTTP response.

        Args:
            *args (Any): if `detail` kwarg not provided, first arg should be error detail.
            detail (str | None, optional): explicit detail kwarg should be specified if first `arg` is not the detail `str`.
            status_code (int | None, optional): override the exception type default status code.
            extra (dict[str, Any], list[Any] | None, optional): extra info for HTTP response.
        """
        if not detail:
            detail = args[0] if len(args) > 0 else HTTPStatus(status_code or self.status_code).phrase
        self.extra = extra
        super().__init__(status_code or self.status_code, *args)
        self.detail = detail
        self.args = (f"{self.status_code}: {self.detail}", *args)

    def __repr__(self) -> str:
        return f"{self.status_code} - {self.__class__.__name__} - {self.detail}"


class ImproperlyConfiguredException(HTTPException, ValueError):
    """Application has improper configuration."""


class ValidationException(HTTPException, ValueError):
    """Client error."""

    status_code = HTTP_400_BAD_REQUEST


class NotAuthorizedException(HTTPException):
    """Request lacks valid authentication credentials for the requested
    resource."""

    status_code = HTTP_401_UNAUTHORIZED


class PermissionDeniedException(HTTPException):
    """Request understood, but not authorized."""

    status_code = HTTP_403_FORBIDDEN


class NotFoundException(HTTPException, ValueError):
    """Cannot find the requested resource."""

    status_code = HTTP_404_NOT_FOUND


class MethodNotAllowedException(HTTPException):
    """Server knows the request method, but the target resource doesn't support
    this method."""

    status_code = HTTP_405_METHOD_NOT_ALLOWED


class InternalServerException(HTTPException):
    """Server encountered an unexpected condition that prevented it from
    fulfilling the request."""

    status_code = HTTP_500_INTERNAL_SERVER_ERROR


class ServiceUnavailableException(HTTPException):
    """Server is not ready to handle the request."""

    status_code = HTTP_503_SERVICE_UNAVAILABLE


class TemplateNotFoundException(InternalServerException):
    def __init__(self, *args: Any, template_name: str):
        """Referenced template could not be found.

        Args:
            *args (Any): Passed through to `super().__init__()` - should not include `detail`.
            template_name (str): Name of template that could not be found.
        """
        super().__init__(*args, detail=f"Template {template_name} not found.")
