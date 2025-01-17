from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, Union, cast

from pydantic import validate_arguments
from pydantic.fields import FieldInfo
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from starlite.asgi import StarliteASGIRouter
from starlite.config import (
    CacheConfig,
    CompressionConfig,
    CORSConfig,
    CSRFConfig,
    OpenAPIConfig,
    StaticFilesConfig,
    TemplateConfig,
)
from starlite.datastructures import Cookie, ResponseHeader, State
from starlite.exceptions import ImproperlyConfiguredException
from starlite.handlers.asgi import ASGIRouteHandler, asgi
from starlite.handlers.http import HTTPRouteHandler
from starlite.middleware import CSRFMiddleware, ExceptionHandlerMiddleware
from starlite.middleware.compression.base import CompressionMiddleware
from starlite.plugins.base import PluginProtocol
from starlite.provide import Provide
from starlite.response import Response
from starlite.router import Router
from starlite.routes import ASGIRoute, BaseRoute, HTTPRoute, WebSocketRoute
from starlite.signature import SignatureModelFactory
from starlite.types import (
    AfterRequestHandler,
    AfterResponseHandler,
    BeforeRequestHandler,
    ControllerRouterHandler,
    ExceptionHandler,
    Guard,
    LifeCycleHandler,
    Middleware,
)
from starlite.utils.templates import create_template_engine

if TYPE_CHECKING:
    from pydantic.typing import AnyCallable
    from pydantic_openapi_schema.v3_1_0.open_api import OpenAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

    from starlite.handlers.base import BaseRouteHandler
    from starlite.handlers.websocket import WebsocketRouteHandler

DEFAULT_OPENAPI_CONFIG = OpenAPIConfig(title="Starlite API", version="1.0.0")
"""
    The default OpenAPI config used if not configuration is explicitly passed
    to the [Starlite][starlite.app.Starlite] instance constructor.
"""
DEFAULT_CACHE_CONFIG = CacheConfig()
"""
    The default cache config used if not configuration is explicitly passed
    to the [Starlite][starlite.app.Starlite] instance constructor.
"""


class Starlite(Router):
    __slots__ = (
        "_registered_routes",
        "_static_paths",
        "allowed_hosts",
        "asgi_handler",
        "asgi_router",
        "cache_config",
        "compression_config",
        "cors_config",
        "csrf_config",
        "debug",
        "openapi_schema",
        "plain_routes",
        "plugins",
        "route_map",
        "state",
        "template_engine",
    )

    @validate_arguments(config={"arbitrary_types_allowed": True})
    def __init__(
        self,
        *,
        after_request: Optional[AfterRequestHandler] = None,
        after_response: Optional[AfterResponseHandler] = None,
        allowed_hosts: Optional[List[str]] = None,
        before_request: Optional[BeforeRequestHandler] = None,
        cache_config: CacheConfig = DEFAULT_CACHE_CONFIG,
        compression_config: Optional[CompressionConfig] = None,
        cors_config: Optional[CORSConfig] = None,
        csrf_config: Optional[CSRFConfig] = None,
        debug: bool = False,
        dependencies: Optional[Dict[str, Provide]] = None,
        exception_handlers: Optional[Dict[Union[int, Type[Exception]], ExceptionHandler]] = None,
        guards: Optional[List[Guard]] = None,
        middleware: Optional[List[Middleware]] = None,
        on_shutdown: Optional[List[LifeCycleHandler]] = None,
        on_startup: Optional[List[LifeCycleHandler]] = None,
        openapi_config: Optional[OpenAPIConfig] = DEFAULT_OPENAPI_CONFIG,
        parameters: Optional[Dict[str, FieldInfo]] = None,
        plugins: Optional[List[PluginProtocol]] = None,
        response_class: Optional[Type[Response]] = None,
        response_cookies: Optional[List[Cookie]] = None,
        response_headers: Optional[Dict[str, ResponseHeader]] = None,
        route_handlers: List[ControllerRouterHandler],
        static_files_config: Optional[Union[StaticFilesConfig, List[StaticFilesConfig]]] = None,
        template_config: Optional[TemplateConfig] = None,
        tags: Optional[List[str]] = None,
    ):
        """The Starlite application.

        `Starlite` is the root level of the app - it has the base path of "/" and all root level
        Controllers, Routers and Route Handlers should be registered on it.

        It inherits from the [Router][starlite.router.Router] class.

        Args:
            after_request: A sync or async function executed before a [Request][starlite.connection.Request] is passed
                to any route handler. If this function returns a value, the request will not reach the route handler,
                and instead this value will be used.
            after_response: A sync or async function called after the response has been awaited. It receives the
                [Request][starlite.connection.Request] object and should not return any values.
            allowed_hosts: A list of allowed hosts - enables `AllowedHostsMiddleware`.
            before_request: A sync or async function called immediately before calling the route handler. Receives
                the `starlite.connection.Request` instance and any non-`None` return value is used for the response,
                bypassing the route handler.
            cache_config: Configures caching behavior of the application.
            compression_config: Configures compression behaviour of the application.
            cors_config: If set this enables the `starlette.middleware.cores.CORSMiddleware`.
            csrf_config: If set this enables the CSRF middleware.
            debug: If `True`, app errors rendered as HTML with a stack trace.
            dependencies: A string/[Provider][starlite.provide.Provide] dictionary that maps dependency providers.
            exception_handlers: A dictionary that maps handler functions to status codes and/or exception types.
            guards: A list of [Guard][starlite.types.Guard] callables.
            middleware: A list of [Middleware][starlite.types.Middleware].
            on_shutdown: A list of [LifeCycleHandler][starlite.types.LifeCycleHandler] called during application
                shutdown.
            on_startup: A list of [LifeCycleHandler][starlite.types.LifeCycleHandler] called during application startup.
            openapi_config: Defaults to [DEFAULT_OPENAPI_CONFIG][starlite.app.DEFAULT_OPENAPI_CONFIG]
            parameters: A mapping of [Parameter][starlite.params.Parameter] definitions available to all
                application paths.
            plugins: List of plugins.
            response_class: A custom subclass of [starlite.response.Response] to be used as the app's default response.
            response_cookies: A list of [Cookie](starlite.datastructures.Cookie] instances.
            response_headers: A string keyed dictionary mapping [ResponseHeader][starlite.datastructures.ResponseHeader]
                instances.
            route_handlers: A required list of route handlers, which can include instances of
                [Router][starlite.router.Router], subclasses of [Controller][starlite.controller.Controller] or any
                function decorated by the route handler decorators.
            static_files_config: An instance or list of [StaticFilesConfig][starlite.config.StaticFilesConfig]
            template_config: An instance of [TemplateConfig][starlite.config.TemplateConfig]
            tags: A list of string tags that will be appended to the schema of all route handlers under the application.
        """
        self._registered_routes: Set[BaseRoute] = set()
        self._static_paths: Set[str] = set()
        self.allowed_hosts = allowed_hosts
        self.cache_config = cache_config
        self.cors_config = cors_config
        self.csrf_config = csrf_config
        self.debug = debug
        self.compression_config = compression_config
        self.plain_routes: Set[str] = set()
        self.plugins = plugins or []
        self.route_map: Dict[str, Any] = {}
        self.routes: List[BaseRoute] = []
        self.state = State()

        super().__init__(
            after_request=after_request,
            after_response=after_response,
            before_request=before_request,
            dependencies=dependencies,
            exception_handlers=exception_handlers,
            guards=guards,
            middleware=middleware,
            parameters=parameters,
            path="",
            response_class=response_class,
            response_cookies=response_cookies,
            response_headers=response_headers,
            route_handlers=route_handlers,
            tags=tags,
        )

        self.asgi_router = StarliteASGIRouter(on_shutdown=on_shutdown or [], on_startup=on_startup or [], app=self)
        self.asgi_handler = self._create_asgi_handler()
        self.openapi_schema: Optional["OpenAPI"] = None
        if openapi_config:
            self.openapi_schema = openapi_config.create_openapi_schema_model(self)
            self.register(openapi_config.openapi_controller)
        if static_files_config:
            for config in static_files_config if isinstance(static_files_config, list) else [static_files_config]:
                self._static_paths.add(config.path)
                self.register(asgi(path=config.path)(config.to_static_files_app()))
        self.template_engine = create_template_engine(template_config)

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        """The application entry point.

        Lifespan events (startup / shutdown) are sent to the lifespan
        handler, otherwise the ASGI handler is used
        """
        scope["app"] = self
        if scope["type"] == "lifespan":
            await self.asgi_router.lifespan(scope, receive, send)
            return
        scope["state"] = {}
        await self.asgi_handler(scope, receive, send)

    def register(self, value: ControllerRouterHandler) -> None:  # type: ignore[override]
        """Registers a route handler on the app. This method can be used to
        dynamically add endpoints to an application.

        Args:
            value: an instance of [Router][starlite.router.Router], a subclasses of
        [Controller][starlite.controller.Controller] or any function decorated by the route handler decorators.

        Returns:
            None
        """
        routes = super().register(value=value)
        for route in routes:
            if isinstance(route, HTTPRoute):
                route_handlers = route.route_handlers
            else:
                route_handlers = [cast("Union[WebSocketRoute, ASGIRoute]", route).route_handler]  # type: ignore
            for route_handler in route_handlers:
                self._create_handler_signature_model(route_handler=route_handler)
                route_handler.resolve_guards()
                route_handler.resolve_middleware()
                if isinstance(route_handler, HTTPRouteHandler):
                    route_handler.resolve_before_request()
                    route_handler.resolve_after_response()
                    route_handler.resolve_response_handler()
            if isinstance(route, HTTPRoute):
                route.create_handler_map()
            elif isinstance(route, WebSocketRoute):
                route.handler_parameter_model = route.create_handler_kwargs_model(route.route_handler)
        self._construct_route_map()

    def _create_asgi_handler(self) -> "ASGIApp":
        """Creates an ASGIApp that wraps the ASGI router inside an exception
        handler.

        If CORS or TrustedHost configs are provided to the constructor,
        they will wrap the router as well.
        """
        asgi_handler: "ASGIApp" = self.asgi_router
        if self.compression_config:
            asgi_handler = CompressionMiddleware(app=asgi_handler, config=self.compression_config)
        if self.allowed_hosts:
            asgi_handler = TrustedHostMiddleware(app=asgi_handler, allowed_hosts=self.allowed_hosts)
        if self.cors_config:
            asgi_handler = CORSMiddleware(app=asgi_handler, **self.cors_config.dict())
        if self.csrf_config:
            asgi_handler = CSRFMiddleware(app=asgi_handler, config=self.csrf_config)
        return self._wrap_in_exception_handler(asgi_handler, exception_handlers=self.exception_handlers or {})

    def _wrap_in_exception_handler(
        self, app: "ASGIApp", exception_handlers: Dict[Union[int, Type[Exception]], ExceptionHandler]
    ) -> "ASGIApp":
        """Wraps the given ASGIApp in an instance of
        ExceptionHandlerMiddleware."""

        return ExceptionHandlerMiddleware(app=app, exception_handlers=exception_handlers, debug=self.debug)

    def _add_node_to_route_map(self, route: BaseRoute) -> Dict[str, Any]:
        """Adds a new route path (e.g. '/foo/bar/{param:int}') into the
        route_map tree.

        Inserts non-parameter paths ('plain routes') off the tree's root
        node. For paths containing parameters, splits the path on '/'
        and nests each path segment under the previous segment's node
        (see prefix tree / trie).
        """
        current_node = self.route_map
        path = route.path
        if route.path_parameters or path in self._static_paths:
            for param_definition in route.path_parameters:
                path = path.replace(param_definition["full"], "")
            path = path.replace("{}", "*")
            components = ["/", *[component for component in path.split("/") if component]]
            for component in components:
                components_set = cast("Set[str]", current_node["_components"])
                components_set.add(component)
                if component not in current_node:
                    current_node[component] = {"_components": set()}
                current_node = cast("Dict[str, Any]", current_node[component])
                if "_static_path" in current_node:
                    raise ImproperlyConfiguredException("Cannot have configured routes below a static path")
        else:
            if path not in self.route_map:
                self.route_map[path] = {"_components": set()}
            self.plain_routes.add(path)
            current_node = self.route_map[path]
        self._configure_route_map_node(route, current_node)
        return current_node

    def _configure_route_map_node(self, route: BaseRoute, node: Dict[str, Any]) -> None:
        """Set required attributes and route handlers on route_map tree
        node."""
        if "_path_parameters" not in node:
            node["_path_parameters"] = route.path_parameters
        if "_asgi_handlers" not in node:
            node["_asgi_handlers"] = {}
        if "_is_asgi" not in node:
            node["_is_asgi"] = False
        if route.path in self._static_paths:
            if node["_components"]:
                raise ImproperlyConfiguredException("Cannot have configured routes below a static path")
            node["_static_path"] = route.path
            node["_is_asgi"] = True
        asgi_handlers = cast("Dict[str, ASGIApp]", node["_asgi_handlers"])
        if isinstance(route, HTTPRoute):
            for method, handler_mapping in route.route_handler_map.items():
                handler, _ = handler_mapping
                asgi_handlers[method] = self._build_route_middleware_stack(route, handler)
        elif isinstance(route, WebSocketRoute):
            asgi_handlers["websocket"] = self._build_route_middleware_stack(route, route.route_handler)
        elif isinstance(route, ASGIRoute):
            asgi_handlers["asgi"] = self._build_route_middleware_stack(route, route.route_handler)
            node["_is_asgi"] = True

    def _construct_route_map(self) -> None:
        """Create a map of the app's routes.

        This map is used in the asgi router to route requests.
        """
        if "_components" not in self.route_map:
            self.route_map["_components"] = set()
        new_routes = [route for route in self.routes if route not in self._registered_routes]
        for route in new_routes:
            node = self._add_node_to_route_map(route)
            if node["_path_parameters"] != route.path_parameters:
                raise ImproperlyConfiguredException("Should not use routes with conflicting path parameters")
            self._registered_routes.add(route)

    def _build_route_middleware_stack(
        self,
        route: Union[HTTPRoute, WebSocketRoute, ASGIRoute],
        route_handler: Union[HTTPRouteHandler, "WebsocketRouteHandler", ASGIRouteHandler],
    ) -> "ASGIApp":
        """Constructs a middleware stack that serves as the point of entry for
        each route."""

        # we wrap the route.handle method in the ExceptionHandlerMiddleware
        asgi_handler = self._wrap_in_exception_handler(
            app=route.handle, exception_handlers=route_handler.resolve_exception_handlers()
        )

        for middleware in route_handler.resolve_middleware():
            if isinstance(middleware, StarletteMiddleware):
                asgi_handler = middleware.cls(app=asgi_handler, **middleware.options)
            else:
                asgi_handler = middleware(app=asgi_handler)

        # we wrap the entire stack again in ExceptionHandlerMiddleware
        return self._wrap_in_exception_handler(
            app=asgi_handler, exception_handlers=route_handler.resolve_exception_handlers()
        )

    def _create_handler_signature_model(self, route_handler: "BaseRouteHandler") -> None:
        """Creates function signature models for all route handler functions
        and provider dependencies."""
        if not route_handler.signature_model:
            route_handler.signature_model = SignatureModelFactory(
                fn=cast("AnyCallable", route_handler.fn),
                plugins=self.plugins,
                dependency_names=route_handler.dependency_name_set,
            ).create_signature_model()
        for provider in list(route_handler.resolve_dependencies().values()):
            if not provider.signature_model:
                provider.signature_model = SignatureModelFactory(
                    fn=provider.dependency,
                    plugins=self.plugins,
                    dependency_names=route_handler.dependency_name_set,
                ).create_signature_model()
