"""History fallback only for the app's route namespaces, never an API fallback."""
from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class H5StaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        path = path.replace('\\', '/')
        parts = PurePosixPath(path).parts
        if any(part.startswith('.') for part in parts) or (parts and parts[0] in ('api', 'docs', 'redoc')):
            raise HTTPException(404)
        try:
            return await super().get_response('index.html' if path in ('', '.') else path, scope)
        except HTTPException as error:
            if error.status_code != 404 or PurePosixPath(path).suffix or not parts or parts[0] not in ('pages', 'learning'):
                raise
            return await super().get_response('index.html', scope)
