"""New Huddle safety and collaboration regression checks."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import create_app


def register(client,handle):
    result=client.post('/api/auth/register',json={
        'handle':handle,'name':handle.title(),'password':'StrongPassword123!'})
    assert result.status_code==201,result.text
    return result.json()['user']


def test_preferences_blocking_and_poll_events(tmp_path):
    app=create_app(str(tmp_path/'db.sqlite'))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as outsider:
        a=register(alice,'alice');b=register(bob,'bobby');c=register(outsider,'carol')
        dm=alice.post('/api/conversations/direct',json={'user_id':b['id']})
        assert dm.status_code==200,dm.text
        cid=dm.json()['conversation']['id']
        pref={'pinned':True,'archived':True,'muted':True}
        saved=alice.patch(f'/api/conversations/{cid}/preferences',json=pref)
        assert saved.status_code==200,saved.text
        def current(client):
            return next(x for x in client.get('/api/conversations').json()['conversations'] if x['id']==cid)
        assert current(alice)['preferences']=={'pinned':1,'archived':1,'muted':1}
        assert current(bob)['preferences']=={'pinned':0,'archived':0,'muted':0}
        poll=alice.post(f'/api/conversations/{cid}/polls',json={
            'question':'Where to meet tomorrow?','options':['Library','Cafe']})
        assert poll.status_code==201,poll.text
        p=poll.json()['poll']
        assert outsider.get(f'/api/conversations/{cid}/polls').status_code==404
        assert outsider.put('/api/polls/'+p['id']+'/vote',
                          json={'option_id':p['options'][0]['id']}).status_code==404
        invalid=alice.put('/api/polls/'+p['id']+'/vote',json={'option_id':'a'*32})
        assert invalid.status_code==422
        vote=bob.put('/api/polls/'+p['id']+'/vote',json={'option_id':p['options'][0]['id']})
        assert vote.status_code==200,vote.text
        assert vote.json()['poll']['options'][0]['count']==1
        change=bob.put('/api/polls/'+p['id']+'/vote',json={'option_id':p['options'][1]['id']})
        assert change.status_code==200
        assert change.json()['poll']['options'][0]['count']==0
        assert change.json()['poll']['options'][1]['count']==1
        assert alice.post(f'/api/conversations/{cid}/polls',json={
            'question':'What is best?','options':['Same','same']}).status_code==422
        start=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        event=alice.post(f'/api/conversations/{cid}/events',json={
            'title':'Library coding session','starts_at':start,'details':'Bring laptops'})
        assert event.status_code==201,event.text
        eid=event.json()['event']['id']
        assert outsider.get(f'/api/conversations/{cid}/events').status_code==404
        assert bob.put(f'/api/events/{eid}/rsvp',json={'answer':'going'}).status_code==200
        assert outsider.put(f'/api/events/{eid}/rsvp',json={'answer':'going'}).status_code==404
        assert alice.post(f'/api/conversations/{cid}/events',json={
            'title':'Old event','starts_at':'2020-01-01T00:00:00+00:00'}).status_code==422
        blocked=alice.put(f'/api/users/{b["id"]}/block')
        assert blocked.status_code==200,blocked.text
        assert b['id'] in [u['id'] for u in alice.get('/api/me/blocked').json()['users']]
        assert alice.post(f'/api/conversations/{cid}/messages',json={'body':'Blocked!'}).status_code==403
        assert bob.post(f'/api/conversations/{cid}/messages',json={'body':'Blocked!'}).status_code==403
        assert bob.post('/api/conversations/direct',json={'user_id':a['id']}).status_code==403
        assert b['id'] not in [u['id'] for u in alice.get('/api/users').json()['users']]
        assert alice.delete(f'/api/users/{b["id"]}/block').status_code==200
        assert alice.post(f'/api/conversations/{cid}/messages',json={'body':'We can talk now'}).status_code==201
        assert alice.put(f'/api/users/{a["id"]}/block').status_code==422


def test_recovery_disabled_without_sender_and_pwa_manifest(tmp_path):
    app=create_app(str(tmp_path/'db.sqlite'))
    with TestClient(app) as client:
        response=client.get('/manifest.webmanifest')
        assert response.status_code==200
        assert response.json()['display']=='standalone'
        sw=client.get('/sw.js')
        assert sw.status_code==200 and "CacheStorage" in sw.text
        assert 'no-store' in sw.headers['cache-control']
        recovery=client.post('/api/auth/recover',json={'email':'test@example.com'})
        assert recovery.status_code==503
