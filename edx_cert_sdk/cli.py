#!/usr/bin/python3
import click
from mako.template import Template
from mako.lookup import TemplateLookup
from .settings import Settings
import json
import os
from serde.toml import from_toml, to_toml
import importlib.resources as pkg_resources
from . import mako_util
from click import FileError
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import HTMLResponse
from starlette.requests import Request
from sse_starlette.sse import EventSourceResponse
from .static_files import MultiDirStaticFiles
import uvicorn
import asyncio
import watchgod
import lxml.html
from typing import Set, Optional

PROJECT_NAME = "edx-cert-sdk"

class StubUser:
    id = 0
    def __init__(self, id: Optional[int] = None):
        if id:
            self.id = id

    def is_authenticated(self):
        return True
        


@click.group()
@click.option(
    "--config",
    default=os.path.realpath(Settings.DEFAULT_CONFIG_PATH),
    type=click.Path(),
)
@click.option("--create-config/--no-create-config", default=False)
@click.pass_context
def cli(ctx, config, create_config):
    """Command to test out edx certs easily without having to put them on the platform"""
    try:
        with open(config, "r") as config_file:
            settings = from_toml(Settings, config_file.read())
    except IOError as e:
        if create_config:
            settings = Settings()
            with open(config, "w") as config_file:
                config_file.write(to_toml(settings))
        else:
            raise FileError(config, e.strerror)
    project_dir = os.path.dirname(config)
    os.chdir(project_dir)
    ctx.obj = settings


@cli.command()
@click.option(
    "--watch/--no-watch", default=False, help="Watch for changes and reload web page"
)
@click.option(
    "--build-assets/--no-build-assets",
    default=True,
    help="Build assets with every page load",
)
@click.pass_obj
def dev(settings: Settings, watch, build_assets):

    context = {}
    with open(settings.cert_data_file, "r") as cf:
        context.update(json.load(cf))
    context["_"] = lambda x: x
    context["user"] = StubUser() 

    routes = [
        Mount("/static", app=MultiDirStaticFiles(directories=[settings.dist_dir, settings.img_dir]), name="static"),
        Mount("/", app=main_template),
    ]

    if watch:
        routes.insert(0, Route("/push", endpoint=watch_app))

    app = Starlette(routes=routes)
    app.state.settings = settings
    app.state.context = context
    app.state.build_assets = build_assets
    app.state.watch = watch

    uvicorn.run(app)


class MyDirWatcher(watchgod.DefaultDirWatcher):
    ignored_dirs = {".git", "__pycache__", "site-packages", ".idea", "node_modules"}

    def __init__(self, root_path: str, additional_ignored_dirs: Set[str]) -> None:
        self.ignored_dirs = self.ignored_dirs.union(additional_ignored_dirs)
        super().__init__(root_path)


async def watch_files(settings):
    async for changes in watchgod.awatch(
        "./",
        watcher_cls=MyDirWatcher,
        watcher_kwargs=dict(additional_ignored_dirs={str(settings.dist_dir)}),
    ):

        print(f"File {changes} changed, sending push...")
        yield changes


async def watch_app(request):
    msg = watch_files(request.app.state.settings)
    return EventSourceResponse(msg)


async def build_assets(settings: Settings):
    click.echo("Rebuilding assets...")
    await asyncio.create_subprocess_shell(
        f"npm run build"
    )


async def main_template(scope, receive, send):
    app = Request(scope, receive).app
    if app.state.build_assets:
        await build_assets(app.state.settings)
    assert scope["type"] == "http"
    response = HTMLResponse(
        render_template(app.state.settings, app.state.context, app.state.watch)
    )
    await response(scope, receive, send)


def render_template(settings, context, watch):
    # Inject a static_content.html namespace into the template so
    # that loading of static resources works exactly as when in production
    # TODO: Currently, only the following methods are provided:
    # * css(group, raw)
    # * js(group)
    # * certificate_asset_url(slug)
    # TODO: include js for watch functionality
    with pkg_resources.path(mako_util, "static_content.html") as mako_util_path:

        lookup = TemplateLookup(
            directories=[
                str(settings.template_root_file.parent),
                str(mako_util_path.parent),
            ]
        )
        main_html = Template(
            filename=str(settings.template_root_file),
            lookup=lookup,
            output_encoding="utf-8",
            input_encoding="utf-8",
            default_filters=["decode.utf8"],
            encoding_errors="replace",
        ).render(
            get_url_for_slug=lambda slug: "static/" + str(settings.slugs[slug]),
            **context,
        )
    # Inject script to reload page on push
    if watch:
        to_inject = lxml.html.fragment_fromstring(
            pkg_resources.read_text(mako_util, "watch_for_changes.html")
        )
        doc = lxml.html.document_fromstring(main_html)
        doc.find("body").insert(0, to_inject)
        main_html = lxml.html.tostring(doc)

    return main_html


def main():
    cli(auto_envvar_prefix="EDX_CERT_SDK")


if __name__ == "__main__":
    main()
