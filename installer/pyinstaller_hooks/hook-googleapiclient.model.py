"""Bundle only the Gmail API discovery document.

`google-api-python-client` ships a static discovery document for every
Google API - roughly 600 files and about 100 MB. PyInstaller's bundled
hook for `googleapiclient.model` collects the whole
`googleapiclient.discovery_cache` package as data, because that is where
`discovery.build()` reads them from. Unified calls exactly one API, so
99% of that is dead weight in the download.

A hook of the same name in `--additional-hooks-dir` takes precedence over
PyInstaller's own, so this replaces that collection rather than adding to
it. It keeps everything the upstream hook keeps except the unused
documents:

* the package metadata, which `googleapiclient.model` reads at import to
  report the library version, and
* `gmail.v1.json`, at its original relative path - which is where
  `discovery.build()` looks it up, so static discovery keeps working and
  the app never has to fetch the document over the network.
"""

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

_KEEP = ("gmail.v1.json",)


def _wanted(source: str) -> bool:
    normalized = source.replace("\\", "/")
    if "/discovery_cache/documents/" not in normalized:
        return True
    return normalized.endswith(_KEEP)


datas = copy_metadata("google_api_python_client")
datas += [
    entry
    for entry in collect_data_files(
        "googleapiclient.discovery_cache", excludes=["*.txt", "**/__pycache__"]
    )
    if _wanted(entry[0])
]
