from datetime import timedelta
import json
from app.db import utcnow
from app.tailer import Tailer


def line(event):
    return json.dumps({'timestamp':event['ts'],'eventid':'cowrie.login.failed','src_ip':event['ip'],'username':event['username'],'password':event['password'],'session':event['session']})+'\n'


def test_null_safe_deduplication(db,event):
    e=event(eventid='cowrie.session.connect')
    assert db.insert(e)
    assert db.insert(e) is None
    assert db.query('SELECT sum(count) n FROM daily_counts')[0]['n']==1


def test_partial_restart_rotation_truncation(db,settings,event):
    log=settings.cowrie_log; log.parent.mkdir()
    text=line(event())
    log.write_text(text[:-2])
    tail=Tailer(db,settings)
    assert tail.poll()==[]
    with log.open('a') as f: f.write(text[-2:])
    assert len(tail.poll())==1
    # A new instance must resume the persisted offset.
    assert Tailer(db,settings).poll()==[]
    log.rename(log.with_name('cowrie.json.1'))
    log.write_text(line(event(ip='203.0.113.2')))
    assert len(tail.poll())==1
    # Late append to the renamed file must not be lost.
    with log.with_name('cowrie.json.1').open('a') as f: f.write(line(event(ip='203.0.113.3')))
    assert len(tail.poll())==1
    log.write_text(line(event(ip='203.0.113.4')))
    assert len(tail.poll())==1
    assert db.query('SELECT count(*) n FROM events')[0]['n']==4


def test_copytruncate_replay_deduplicates(db,settings,event):
    log=settings.cowrie_log; log.parent.mkdir()
    text=line(event())
    log.write_text(text)
    tail=Tailer(db,settings); assert len(tail.poll())==1
    log.with_name('cowrie.json.1').write_text(text)
    assert tail.poll()==[]
    log.write_text('')
    assert tail.poll()==[]
    log.write_text(text)
    assert tail.poll()==[]


def test_oversize_and_invalid_lines(db,settings,event):
    log=settings.cowrie_log; log.parent.mkdir()
    log.write_text('x'*100000+'\n{\n'+line(event()))
    assert len(Tailer(db,settings).poll())==1


def test_retention_keeps_only_anonymous_totals(db,event):
    e=event(); event_id=db.insert(e)
    past=(utcnow()-timedelta(days=100)).isoformat()
    with db.transaction() as c:
        c.execute('UPDATE events SET ts=? WHERE id=?',(past,event_id))
        c.execute('UPDATE ip_info SET last_seen=?',(past,))
    db.retain()
    assert not db.query('SELECT * FROM events')
    assert not db.query('SELECT * FROM ip_info')
    assert db.query('SELECT sum(count) n FROM daily_counts')[0]['n']==1
    assert '203.0.113.1' not in str(db.query('SELECT * FROM daily_ips'))
    e['ts']=past
    assert db.insert(e) is None


def test_hidden_ip_never_stored(db,settings,event):
    import ipaddress
    settings.hidden=[ipaddress.ip_network('203.0.113.0/24')]
    assert db.insert(event()) is None
    assert not db.query('SELECT * FROM events')
