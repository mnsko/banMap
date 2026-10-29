from datetime import timedelta
from .db import utcnow
from .sanitize import credential, defang, public_ip

RANGES = {'1h':3600, '24h':86400, '7d':604800, 'all':None}
TOPS = {'passwords','usernames','credentials','countries','asns','ips','clients','hassh','commands','download-domains','tcp-targets'}
ATTEMPTS = "('login_failed','login_success','f2b_found')"


class Queries:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    def since(self, range):
        seconds = RANGES[range]
        return (utcnow()-timedelta(seconds=seconds)).isoformat(timespec='microseconds') if seconds else ''

    def events(self, limit=50, after=None):
        where, params = ('e.id>?',[after]) if after is not None else ('1=1',[])
        rows = self.db.query(f'''SELECT e.id,e.ts,e.type,e.ip,e.username,i.country,i.country_code,i.lat,i.lon
            FROM events e LEFT JOIN ip_info i ON e.ip=i.ip WHERE {where}
            ORDER BY {'e.id ASC' if after is not None else 'e.ts DESC,e.id DESC'} LIMIT ?''', (*params,limit))
        # An explicit allowlist: passwords, commands, raw URLs and session IDs never enter this projection.
        for row in rows:
            username = row['username']
            row['username'] = None
            if username and username != '[masked]':
                distinct = self.db.query('SELECT count(DISTINCT ip) n FROM events WHERE username=?', (username,))[0]['n']
                if distinct >= self.settings.threshold:
                    row['username'] = credential(username)
            row['ip'] = public_ip(row['ip'], self.settings.mask_ips)
        return rows

    def map(self, range):
        rows = self.db.query(f'''SELECT e.ip, count(*) events,
            sum(e.type IN {ATTEMPTS}) attempts,min(e.ts) first_seen,max(e.ts) last_seen,
            i.country_code,i.country,i.city,i.lat,i.lon,i.asn,i.asn_org,i.rdns,i.is_tor
            FROM events e LEFT JOIN ip_info i ON e.ip=i.ip WHERE e.ts>=?
            GROUP BY e.ip ORDER BY events DESC LIMIT 1000''', (self.since(range),))
        for row in rows:
            bans = self.db.query("SELECT type FROM events WHERE ip=? AND type IN ('f2b_ban','f2b_unban') ORDER BY ts DESC,id DESC LIMIT 1",(row['ip'],))
            row['banned'] = bool(bans and bans[0]['type']=='f2b_ban')
            row['ip'] = public_ip(row['ip'],self.settings.mask_ips)
        return rows

    def top(self, kind, range):
        since = self.since(range)
        columns = {'passwords':'e.password','usernames':'e.username','countries':"COALESCE(i.country,'Unknown')",
                   'asns':"CAST(i.asn AS TEXT) || ' · ' || COALESCE(i.asn_org,'')",'ips':'e.ip',
                   'clients':'e.client_version','hassh':'e.hassh','commands':'e.command','tcp-targets':'e.tcp_dst',
                   'download-domains':'d.domain'}
        params = [since]
        if kind == 'credentials':
            select = 'e.username username,e.password password'
            group = 'e.username,e.password'
            where = "e.username IS NOT NULL AND e.password IS NOT NULL"
        else:
            column = columns[kind]
            select, group = column+' value', column
            where = f'{column} IS NOT NULL AND {column} != \'\''
        sensitive = kind in {'passwords','usernames','credentials'}
        having = 'HAVING count(DISTINCT e.ip)>=?' if sensitive else ''
        if sensitive:
            params.append(self.settings.threshold)
        rows = self.db.query(f'''SELECT {select}, count(*) count, count(DISTINCT e.ip) distinct_ips
            FROM events e LEFT JOIN ip_info i ON i.ip=e.ip
            {'JOIN event_domains d ON d.event_id=e.id' if kind=='download-domains' else ''}
            WHERE e.ts>=? AND {where} GROUP BY {group} {having} ORDER BY count DESC LIMIT 20''', params)
        for row in rows:
            if kind == 'credentials':
                row['username'], row['password'] = credential(row['username']),credential(row['password'])
            elif sensitive:
                row['value'] = credential(row['value'])
            elif kind == 'ips':
                row['value'] = public_ip(row['value'],self.settings.mask_ips)
            elif kind in {'commands','download-domains','tcp-targets'}:
                row['value'] = defang(row['value'])
        return rows

    def stats(self, range):
        since = self.since(range)
        counts = self.db.query('SELECT type,count(*) count FROM events WHERE ts>=? GROUP BY type', (since,))
        count_by_type = {r['type']:r['count'] for r in counts}
        summary = self.db.query(f'''SELECT count(DISTINCT ip) unique_ips,count(DISTINCT password) passwords,
            min(ts) first_event,sum(type IN {ATTEMPTS}) attempts FROM events WHERE ts>=?''',(since,))[0]
        repeat = self.db.query(f'''SELECT count(*) n FROM (SELECT ip FROM events WHERE ts>=? AND type IN {ATTEMPTS} GROUP BY ip HAVING count(*)>1)''',(since,))[0]['n']
        lifetime = self.db.query('SELECT COALESCE(sum(count),0) n FROM daily_counts')[0]['n']
        lifetime_attempts = self.db.query(f'SELECT COALESCE(sum(count),0) n FROM daily_counts WHERE type IN {ATTEMPTS}')[0]['n']
        today = self.db.query(f'SELECT COALESCE(sum(count),0) n FROM daily_counts WHERE day=? AND type IN {ATTEMPTS}', (utcnow().date().isoformat(),))[0]['n']
        # Graph is always the last 24 hours; the range controls totals and the weekly heatmap.
        graph_since = (utcnow()-timedelta(hours=24)).isoformat(timespec='microseconds')
        series = self.db.query(f"SELECT strftime('%Y-%m-%dT%H:00:00Z',ts) hour,count(*) count FROM events WHERE ts>=? AND type IN {ATTEMPTS} GROUP BY hour ORDER BY hour", (graph_since,))
        heatmap = self.db.query(f"SELECT CAST(strftime('%w',ts) AS INTEGER) day,CAST(strftime('%H',ts) AS INTEGER) hour,count(*) count FROM events WHERE ts>=? AND type IN {ATTEMPTS} GROUP BY day,hour", (since,))
        summary.update(lifetime_attempts=lifetime_attempts, attempts=summary['attempts'] or 0, attempts_today=today, lifetime_events=lifetime, repeat_attackers=repeat,
                       repeat_ratio=repeat/summary['unique_ips'] if summary['unique_ips'] else 0,
                       types=count_by_type, series=series, heatmap=heatmap,
                       lifetime_unique_ips=self.db.query('SELECT count(DISTINCT ip_hash) n FROM daily_ips')[0]['n'])
        return summary
