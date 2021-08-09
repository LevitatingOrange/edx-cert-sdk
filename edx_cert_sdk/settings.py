from typing import Dict
from pathlib import Path, PurePath
from dataclasses import dataclass, field
import dataclasses
from serde import serialize, deserialize


@serialize
@deserialize
@dataclass
class Settings:
    DEFAULT_CONFIG_PATH = "./certconf.toml"

    template_root_file: Path = Path("index.html")
    img_dir: Path = Path("img/")
    dist_dir: Path = Path("dist/")
    cert_data_file: Path = Path("certdata.json")
    slugs: Dict[str, Path] = field(
        default_factory=lambda: (
            {"cert-css": Path("index.css"), "cert-js": Path("index.js")}
        )
    )


# def dict_path_factory(data):
#    """ Encode pathlibs paths manually and inefficiently because the toml library's way via `encoder=toml.TomlPathLibEncoder` is bugged """
#    return dict((x[0], str(x[1])) if isinstance(x[1], PurePath) else (x[0], dict_path_factory(x[1].items())) if isinstance(x[1], Dict) else x for x in data)
#
