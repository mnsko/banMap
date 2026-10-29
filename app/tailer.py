"""Bounded JSONL ingestion; event inserts and cursor advances share a transaction."""
from pathlib import Path
import logging
from . import cowrie_parser, f2b_parser

logger = logging.getLogger(__name__)
MAX_LINE = 65536


class Tailer:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.errors = 0
        self.last_error = None

    def read_file(self, path, parser):
        added = []
        try:
            with path.open('rb') as stream:
                stat = path.stat()
                identity = f'{stat.st_dev}:{stat.st_ino}'
                rows = self.db.query('SELECT * FROM cursors WHERE identity=?', (identity,))
                offset, anchor = (rows[0]['offset'], rows[0]['anchor']) if rows else (0,b'')
                head = stream.read(256)
                if stat.st_size < offset or head[:len(anchor)] != anchor:
                    offset = 0
                stream.seek(offset)
                # Bound time spent in one scan, so API/SSE remain responsive during history import.
                with self.db.transaction() as c:
                    for _ in range(1000):
                        start = stream.tell()
                        line = stream.readline(MAX_LINE + 1)
                        if not line:
                            break
                        too_long = len(line) > MAX_LINE
                        while too_long and line and not line.endswith(b'\n'):
                            line = stream.readline(MAX_LINE + 1)
                        if not line.endswith(b'\n'):
                            stream.seek(start)
                            break
                        if not too_long:
                            event = parser(line.decode('utf-8', errors='replace'))
                            if event is not None and (event_id := self.db.insert(event, c)):
                                added.append(event_id)
                    c.execute('INSERT OR REPLACE INTO cursors VALUES (?,?,?,?)', (identity,str(path),stream.tell(),head))
            return added
        except FileNotFoundError:
            return added
        except OSError:
            self.errors += 1
            self.last_error = 'Log file unavailable; check read permissions'
            logger.warning('Cannot read configured log source')
            return added

    def poll(self):
        added = []
        for base, parser in [(self.settings.cowrie_log, cowrie_parser.parse), (self.settings.f2b_log, f2b_parser.parse)]:
            # Replay dated rotations too: inode identities avoid losing late writes to a renamed log.
            paths = sorted(p for p in base.parent.glob(base.name + '*') if p.is_file() and p.suffix not in {'.gz','.zip'})
            for path in paths:
                added.extend(self.read_file(path, parser))
        return added
