import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
import json
import logging
from pathlib import Path
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import Settings
from .db import Database, utcnow
from .geo import Geo
from .queries import Queries, RANGES, TOPS
from .tailer import Tailer

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent/'static'
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.basemaps.cartocdn.com; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


class Guard:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.clients = {}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        async def headers(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers',[]).extend([
                    (b'content-security-policy',CSP.encode()),(b'x-content-type-options',b'nosniff'),
                    (b'referrer-policy',b'no-referrer'),(b'permissions-policy',b'camera=(), microphone=(), geolocation=()'),
                    (b'x-frame-options',b'DENY')])
            await send(message)
        if scope['method'] != 'GET':
            return await JSONResponse({'detail':'Method not allowed'},405,headers={'Allow':'GET'})(scope,receive,headers)
        if scope['path'].startswith('/api/'):
            now = time.monotonic()
            ip = (scope.get('client') or ('unknown',0))[0]
            if ip not in self.clients:
                self.clients = {key:q for key,q in self.clients.items() if q and now-q[-1]<60}
                if len(self.clients)>=4096:
                    return await JSONResponse({'detail':'Busy'},503)(scope,receive,headers)
                self.clients[ip] = deque()
            queue = self.clients[ip]
            while queue and now-queue[0]>=60:
                queue.popleft()
            if len(queue)>=self.settings.rate_per_minute:
                return await JSONResponse({'detail':'Too many requests'},429,headers={'Retry-After':'60'})(scope,receive,headers)
            queue.append(now)
        await self.app(scope,receive,headers)


def create_app(settings=None, background=True):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        settings.data.mkdir(parents=True,exist_ok=True)
        db = Database(settings.data/'banmap.sqlite',settings)
        app.state.db = db
        # Apply newly configured exclusions to previously collected raw events too.
        with db.transaction() as c:
            for row in c.execute('SELECT ip FROM ip_info').fetchall():
                if settings.hidden_ip(row['ip']):
                    c.execute('DELETE FROM events WHERE ip=?',(row['ip'],))
                    c.execute('DELETE FROM ip_info WHERE ip=?',(row['ip'],))
        app.state.queries = Queries(db,settings)
        app.state.geo = Geo(db,settings)
        db.geo_lookup = app.state.geo.lookup
        app.state.tailer = Tailer(db,settings)
        app.state.started = time.monotonic()
        app.state.last_ingest = None
        app.state.worker_ok = True
        app.state.cache = {}
        app.state.cache_lock = asyncio.Lock()
        app.state.streams = defaultdict(int)
        async def worker():
            last_retention = 0
            while True:
                try:
                    await asyncio.to_thread(app.state.tailer.poll)
                    app.state.last_ingest = utcnow().isoformat()
                    if time.monotonic()-last_retention>3600:
                        await asyncio.to_thread(db.retain)
                        last_retention = time.monotonic()
                    app.state.worker_ok = True
                except Exception:
                    app.state.worker_ok = False
                    logger.error('Ingestion cycle failed; check local service logs and permissions')
                await asyncio.sleep(0.25)
        async def enrich_worker():
            while True:
                try:
                    await app.state.geo.refresh_tor()
                    await app.state.geo.enrich()
                except Exception:
                    logger.error('Enrichment unavailable; ingestion continues')
                await asyncio.sleep(1)
        db.retain()
        task = asyncio.create_task(worker()) if background else None
        enrichment = asyncio.create_task(enrich_worker()) if background else None
        try:
            yield
        finally:
            for running in (task,enrichment):
                if running:
                    running.cancel()
                    with suppress(asyncio.CancelledError):
                        await running
            app.state.geo.close()
            db.close()

    app = FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(Guard,settings=settings)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return JSONResponse({'detail':'Invalid request'},422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request,exc):
        return JSONResponse({'detail':str(exc.detail) if exc.status_code<500 else 'Service unavailable'},exc.status_code)

    @app.exception_handler(Exception)
    async def error(request,exc):
        logger.error('Request failed')
        return JSONResponse({'detail':'Service unavailable'},500)

    async def cached(key,operation):
        async with app.state.cache_lock:
            found = app.state.cache.get(key)
            if found and found[0]>time.monotonic():
                return found[1]
            result = await asyncio.to_thread(operation)
            app.state.cache[key] = (time.monotonic()+(0.5 if key[0] in {'map','events'} else 5),result)
            return result

    def range_check(value):
        if value not in RANGES:
            raise HTTPException(422,'Invalid range')
        return value

    @app.get('/healthz')
    async def health():
        app.state.db.query('SELECT 1')
        if not app.state.worker_ok or app.state.tailer.last_error:
            raise HTTPException(503,'Service unavailable')
        return {'status':'ok','geo_city':bool(app.state.geo.city),'geo_asn':bool(app.state.geo.asn),
                'last_ingest':app.state.last_ingest,'log_read_errors':app.state.tailer.errors}

    @app.get('/api/config')
    async def config():
        return {'password_min_ips':settings.threshold,'mask_ips':settings.mask_ips,'retention_days':settings.retention_days,'geo_city':bool(app.state.geo.city),'geo_asn':bool(app.state.geo.asn)}

    @app.get('/api/map')
    async def map(range: str='24h'):
        range_check(range)
        return await cached(('map',range),lambda:app.state.queries.map(range))

    @app.get('/api/stats')
    async def stats(range: str='24h'):
        range_check(range)
        result = dict(await cached(('stats',range),lambda:app.state.queries.stats(range)))
        result['uptime_seconds'] = round(time.monotonic()-app.state.started)
        first = result['first_event']
        origin = app.state.db.query("SELECT value FROM metadata WHERE key='sensor_started'")
        from datetime import datetime
        result['seconds_to_first_event'] = max(0,round((datetime.fromisoformat(first)-datetime.fromisoformat(origin[0]['value'])).total_seconds())) if first else None
        return result

    @app.get('/api/top/{kind}')
    async def top(kind: str,range: str='24h'):
        range_check(range)
        if kind not in TOPS:
            raise HTTPException(404,'Not found')
        return await cached(('top',kind,range),lambda:app.state.queries.top(kind,range))

    @app.get('/api/events')
    async def events(limit: int=50):
        if limit<1 or limit>100:
            raise HTTPException(422,'Invalid limit')
        return await cached(('events',limit),lambda:app.state.queries.events(limit))

    @app.get('/api/stream')
    async def stream(request: Request):
        raw_id = request.headers.get('last-event-id')
        if raw_id is not None and (len(raw_id)>18 or not raw_id.isdecimal()):
            raise HTTPException(422,'Invalid event cursor')
        ip = request.client.host if request.client else 'unknown'
        streams = app.state.streams
        if sum(streams.values())>=settings.sse_total or streams[ip]>=settings.sse_per_ip:
            raise HTTPException(429,'Too many streams')
        streams[ip] += 1
        latest = app.state.db.query('SELECT COALESCE(max(id),0) id FROM events')[0]['id']
        cursor = min(int(raw_id),latest) if raw_id else latest
        async def generate():
            nonlocal cursor
            started = time.monotonic()
            try:
                yield 'retry: 2000\n: connected\n\n'
                while time.monotonic()-started<25:
                    if await request.is_disconnected():
                        break
                    rows = await asyncio.to_thread(app.state.queries.events,50,cursor)
                    for row in rows:
                        cursor = row['id']
                        yield f'id: {cursor}\nevent: attack\ndata: {json.dumps(row,ensure_ascii=True)}\n\n'
                    if not rows:
                        yield ': heartbeat\n\n'
                    await asyncio.sleep(0.5)
            finally:
                streams[ip] -= 1
                if not streams[ip]:
                    del streams[ip]
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.get('/')
    async def index():
        return FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-cache'})

    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    return app


app = create_app()
