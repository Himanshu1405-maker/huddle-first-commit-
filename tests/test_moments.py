"""Private Huddle Moments: 24-hour expiration, contact visibility, media security,
view receipts, hearts, deletion and durable SQLite persistence.
"""
from datetime import datetime,timedelta,timezone
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app

def signup(client,handle):
    result=client.post('/api/auth/register',json={'name':handle.title(),
         'handle':handle,'password':'StrongPassword123!'})
    assert result.status_code==201,result.text
    return result.json()['user']

def new_photo():
    file=BytesIO()
    Image.new('RGB',(64,80),'#8465d9').save(file,'JPEG')
    return file.getvalue()

def test_private_text_media_views_and_expiry(tmp_path):
    location=str(tmp_path/'moments.sqlite')
    app=create_app(location)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as outsider:
        me=signup(alice,'alice');friend=signup(bob,'bobby');signup(outsider,'carlx')
        assert alice.get('/api/moments').status_code==200
        created=alice.post('/api/moments',json={'text':'Our first shared Moment!','palette':'sunrise'})
        assert created.status_code==201,created.text
        id=created.json()['id']
        # No conversation link: no discovery or access to a stranger's Moments.
        assert bob.get('/api/moments').json()['moments']==[]
        assert bob.post(f'/api/moments/{id}/view').status_code==404
        assert bob.put(f'/api/moments/{id}/heart').status_code==404
        assert outsider.get(f'/api/moments/{id}/media').status_code==404
        room=alice.post('/api/conversations/direct',json={'user_id':friend['id']})
        assert room.status_code==200,room.text
        mefeed=alice.get('/api/moments').json()['moments']
        assert len(mefeed)==1 and mefeed[0]['mine'] and mefeed[0]['views']==0
        friendfeed=bob.get('/api/moments').json()['moments']
        assert friendfeed[0]['text']=='Our first shared Moment!'
        assert not friendfeed[0]['mine'] and friendfeed[0]['views'] is None
        assert bob.post(f'/api/moments/{id}/view').status_code==200
        assert bob.post(f'/api/moments/{id}/view').status_code==200
        assert alice.get('/api/moments').json()['moments'][0]['views']==1
        assert bob.put(f'/api/moments/{id}/heart').json()['hearted']
        assert bob.put(f'/api/moments/{id}/heart').status_code==200
        assert alice.get('/api/moments').json()['moments'][0]['hearts']==1
        assert bob.delete(f'/api/moments/{id}/heart').json()['hearted'] is False
        assert bob.delete(f'/api/moments/{id}/heart').status_code==200
        assert bob.delete(f'/api/moments/{id}').status_code==404

        image=new_photo()
        upload=alice.post('/api/moments/media',content=image,headers={'content-type':'image/jpeg'})
        assert upload.status_code==201,upload.text
        photoid=upload.json()['id']
        read=bob.get(f'/api/moments/{photoid}/media')
        assert read.status_code==200 and read.content==image
        assert 'no-store' in read.headers['cache-control']
        assert outsider.get(f'/api/moments/{photoid}/media').status_code==404
        assert alice.post('/api/moments/media',content=b'badtype'*4,
            headers={'content-type':'image/jpeg'}).status_code==422
        assert alice.post('/api/moments/media',content=b'x'*(24*1024*1024+1),
            headers={'content-type':'image/jpeg'}).status_code==413
        assert alice.post('/api/moments',json={'text':'Hi','palette':'evil'}).status_code==422
        assert alice.delete(f'/api/moments/{photoid}').status_code==200
        assert bob.get(f'/api/moments/{photoid}/media').status_code==404
        # Simulate expiry without sleeping and verify feed/media/view secrecy.
        with app.state.db.connection() as cx:
            cx.execute("UPDATE moments SET expires_at=? WHERE id=?",
               ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),id))
        assert bob.get('/api/moments').json()['moments']==[]
        assert bob.post(f'/api/moments/{id}/view').status_code==404

def test_group_contact_access_and_restart(tmp_path):
    location=str(tmp_path/'moments-persist.sqlite')
    app=create_app(location)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as outsider:
        signup(alice,'alice');b=signup(bob,'bobby');signup(outsider,'carlx')
        created=alice.post('/api/conversations/group',json={
            'name':'Huddle Circle','member_ids':[b['id']]})
        assert created.status_code==201,created.text
        moment=alice.post('/api/moments',json={'text':'Study group vibe!'})
        assert moment.status_code==201,moment.text
        mid=moment.json()['id']
        assert bob.get('/api/moments').json()['moments'][0]['id']==mid
        assert outsider.get('/api/moments').json()['moments']==[]
    newer=create_app(location)
    with TestClient(newer) as alice:
        signed=alice.post('/api/auth/login',json={'handle':'alice','password':'StrongPassword123!'})
        assert signed.status_code==200,signed.text
        assert alice.get('/api/moments').json()['moments'][0]['text']=='Study group vibe!'
