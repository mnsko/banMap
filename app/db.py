from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading

SCHEMA = '''
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL UNIQUE,
 ts TEXT NOT NULL, source TEXT NOT NULL, type TEXT NOT NULL, ip TEXT NOT NULL,
 session TEXT, src_port INTEGER, dst_port INTEGER, username TEXT, password TEXT,
 command TEXT, client_version TEXT, hassh TEXT, url TEXT, shasum TEXT,
 tcp_dst TEXT, duration REAL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_ip ON events(ip);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE TABLE IF NOT EXISTS event_domains (event_id INTEGER REFERENCES events(id) ON DELETE CASCADE, domain TEXT, PRIMARY KEY(event_id, domain));
CREATE TABLE IF NOT EXISTS ip_info (
 ip TEXT PRIMARY KEY, country_code TEXT, country TEXT, city TEXT,
 lat REAL, lon REAL, asn INTEGER, asn_org TEXT, rdns TEXT,
 is_tor INTEGER DEFAULT 0, first_seen TEXT, last_seen TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS cursors (identity TEXT PRIMARY KEY, path TEXT, offset INTEGER NOT NULL, anchor BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS daily_counts (day TEXT, type TEXT, count INTEGER NOT NULL, PRIMARY KEY(day,type));
CREATE TABLE IF NOT EXISTS daily_ips (day TEXT, ip_hash TEXT, count INTEGER NOT NULL, PRIMARY KEY(day,ip_hash));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''
COLUMNS = ['ts','source','type','ip','session','src_port','dst_port','username','password','command','client_version','hassh','url','shasum','tcp_dst','duration']


def utcnow():
    return datetime.now(timezone.utc)


class Database:
    def __init__(self, path, settings):
        self.settings = settings
        self.geo_lookup = None
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA secure_delete=ON')
        self.conn.execute('PRAGMA busy_timeout=5000')
        self.conn.executescript(SCHEMA)
        self.conn.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('salt', secrets.token_hex(32)))
        self.conn.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('sensor_started', utcnow().isoformat()))
        self.salt = self.conn.execute("SELECT value FROM metadata WHERE key='salt'").fetchone()[0].encode()
        self.conn.commit()

    @contextmanager
    def transaction(self):
        with self.lock, self.conn:
            yield self.conn

    def query(self, sql, params=()):
        with self.lock:
            return [dict(row) for row in self.conn.execute(sql, params)]

    def insert(self, event, conn=None):
        if self.settings.hidden_ip(event['ip']):
            return None
        now = utcnow()
        dt = datetime.fromisoformat(event['ts'])
        if dt < now - timedelta(days=self.settings.retention_days) or dt > now + timedelta(minutes=5):
            return None
        fingerprint = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(',',':')).encode()).hexdigest()
        def write(c):
            result = c.execute(f'INSERT OR IGNORE INTO events (fingerprint,{",".join(COLUMNS)}) VALUES ({",".join("?" for _ in range(len(COLUMNS)+1))})', [fingerprint] + [event.get(k) for k in COLUMNS])
            if not result.rowcount:
                return None
            event_id = result.lastrowid
            c.executemany('INSERT OR IGNORE INTO event_domains VALUES (?,?)', [(event_id, d) for d in event.get('domains', [])])
            day = event['ts'][:10]
            c.execute('INSERT INTO daily_counts VALUES (?,?,1) ON CONFLICT(day,type) DO UPDATE SET count=count+1', (day,event['type']))
            digest = hmac.new(self.salt, event['ip'].encode(), hashlib.sha256).hexdigest()
            c.execute('INSERT INTO daily_ips VALUES (?,?,1) ON CONFLICT(day,ip_hash) DO UPDATE SET count=count+1', (day,digest))
            new_ip = c.execute('INSERT OR IGNORE INTO ip_info (ip,first_seen,last_seen) VALUES (?,?,?)', (event['ip'],event['ts'],event['ts'])).rowcount
            c.execute('UPDATE ip_info SET first_seen=min(first_seen,?),last_seen=max(last_seen,?) WHERE ip=?', (event['ts'],event['ts'],event['ip']))
            if new_ip and self.geo_lookup:
                info = self.geo_lookup(event['ip'])
                c.execute('UPDATE ip_info SET country_code=?,country=?,city=?,lat=?,lon=?,asn=?,asn_org=? WHERE ip=?', (*info.values(),event['ip']))
            return event_id
        if conn is not None:
            return write(conn)
        with self.transaction() as c:
            return write(c)

    def retain(self):
        cutoff = (utcnow() - timedelta(days=self.settings.retention_days)).isoformat(timespec='microseconds')
        with self.transaction() as c:
            c.execute('DELETE FROM events WHERE ts < ?', (cutoff,))
            c.execute('DELETE FROM ip_info WHERE last_seen < ?', (cutoff,))
        with self.lock:
            self.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    def close(self):
        with self.lock:
            self.conn.close()
