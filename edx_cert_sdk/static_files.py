import typing
import stat
import anyio
from typing import List
import os
import importlib.util
from starlette.staticfiles import StaticFiles

PathLike = typing.Union[str, os.PathLike[str]]

class MultiDirStaticFiles(StaticFiles):
    def __init__(
        self,
        *,
        directories: List[PathLike] = None,
        packages: typing.List[str] = None,
        html: bool = False,
    ) -> None:
        self.packages = packages
        self.directories = directories
        self.all_directories = self.get_directories(directories or [], packages)
        self.html = html
        self.config_checked = False

    def get_directories(
        self, directories: List[PathLike], packages: typing.List[str] = None
    ) -> typing.List[PathLike]:
        """
        Given `directory` and `packages` arguments, return a list of all the
        directories that should be used for serving static files from.
        """

        for package in packages or []:
            spec = importlib.util.find_spec(package)
            assert spec is not None, f"Package {package!r} could not be found."
            assert (
                spec.origin is not None
            ), f"Directory 'statics' in package {package!r} could not be found."
            package_directory = os.path.normpath(
                os.path.join(spec.origin, "..", "statics")
            )
            assert os.path.isdir(
                package_directory
            ), f"Directory 'statics' in package {package!r} could not be found."
            directories.append(package_directory)

        return directories

    async def check_config(self) -> None:
        """
        Perform a one-off configuration check that StaticFiles is actually
        pointed at a directory, so that we can raise loud errors rather than
        just returning 404 responses.
        """
        if self.directories is None:
            return

        for dir in self.directories:
            try:
                stat_result = await anyio.to_thread.run_sync(os.stat, dir)
            except FileNotFoundError:
                raise RuntimeError(
                    f"StaticFiles directory '{dir}' does not exist."
                )
            if not (stat.S_ISDIR(stat_result.st_mode) or stat.S_ISLNK(stat_result.st_mode)):
                raise RuntimeError(
                    f"StaticFiles path '{dir}' is not a directory."
                )
