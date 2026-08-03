"""Load DataHub's official showcase pack, including on Windows drive paths."""

import os
import sys


def _patch_windows_file_paths() -> None:
    if os.name != "nt":
        return

    from datahub.ingestion.source import file as file_source

    original = file_source.get_path_schema

    def windows_aware_path_schema(path: str) -> str:
        path = str(path)
        if len(path) >= 2 and path[0].isalpha() and path[1] == ":":
            return "file"
        return original(path)

    file_source.get_path_schema = windows_aware_path_schema
    file_source.GenericFileSource.get_filenames.__globals__["get_path_schema"] = (
        windows_aware_path_schema
    )
    file_source.GenericFileSource._iterate_file.__globals__["get_path_schema"] = (
        windows_aware_path_schema
    )


def main() -> None:
    _patch_windows_file_paths()
    from datahub.entrypoints import main as datahub_main

    sys.argv = ["datahub", "datapack", "load", "showcase-ecommerce", *sys.argv[1:]]
    datahub_main()


if __name__ == "__main__":
    main()