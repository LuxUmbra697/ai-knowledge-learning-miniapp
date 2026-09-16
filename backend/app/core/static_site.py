"""History fallback only for the app's route namespaces, never an API fallback."""
from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class H5StaticFiles(StaticFiles):
    async def index_response(self, scope):
        # Release archives normalize mtimes; equal-sized HTML must not reuse an old ETag.
        fresh = {**scope, 'headers': [(name, value) for name, value in scope['headers']
                                     if name.lower() not in (b'if-none-match', b'if-modified-since')]}
        return await super().get_response('index.html', fresh)

    async def get_response(self, path, scope):
        path = path.replace('\\', '/')
        parts = PurePosixPath(path).parts
        if any(part.startswith('.') for part in parts) or (parts and parts[0] in ('api', 'docs', 'redoc')):
            raise HTTPException(404)
        try:
            if path in ('', '.', 'index.html'):
                return await self.index_response(scope)
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or PurePosixPath(path).suffix or not parts or parts[0] not in ('pages', 'learning'):
                raise
            return await self.index_response(scope)
