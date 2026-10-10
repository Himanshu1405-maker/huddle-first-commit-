"""Personal message stars must persist and never cross account or chat boundaries."""
from fastapi.testclient import TestClient
from app.main import create_app

def reg(client,handle):
    result=client.post('/api/auth/register',json={
        'name':handle.title(),'handle':handle,'password':'SecurePassword123!'})
    assert result.status_code==201,result.text
    return result.json()['user']

def test_private_star_toggle_list_authorization_and_restart(tmp_path):
    location=str(tmp_path/'stars.sqlite')
    app=create_app(location)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as outsider:
        a=reg(alice,'alice');b=reg(bob,'bobby');c=reg(outsider,'carlx')
        chat=alice.post('/api/conversations/direct',json={'user_id':b['id']}).json()['conversation']['id']
        first=alice.post(f'/api/conversations/{chat}/messages',json={'body':'Important private checklist'}).json()['message']
        mid=first['id'];route=f'/api/messages/{mid}/star'
        assert outsider.put(route).status_code==404
        assert outsider.delete(route).status_code==404
        assert alice.get('/api/messages/starred').json()['items']==[]
        assert alice.put(route).json()['starred'] is True
        assert alice.put(route).json()['starred'] is True
        saved=alice.get('/api/messages/starred').json()['items']
        assert len(saved)==1 and saved[0]['message']['id']==mid
        assert saved[0]['message']['body']=='Important private checklist'
        assert saved[0]['conversation_name']
        assert bob.get('/api/messages/starred').json()['items']==[]
        assert outsider.get('/api/messages/starred').json()['items']==[]
        assert bob.put(route).status_code==200
        assert len(bob.get('/api/messages/starred').json()['items'])==1
        assert alice.delete(route).json()['starred'] is False
        assert alice.delete(route).json()['starred'] is False
        assert alice.get('/api/messages/starred').json()['items']==[]
        assert len(bob.get('/api/messages/starred').json()['items'])==1
        # Both recipients can star independently and deleting removes results.
        assert alice.put(route).status_code==200
        assert alice.delete(f'/api/messages/{mid}').status_code==200
        assert alice.get('/api/messages/starred').json()['items']==[]
        assert bob.get('/api/messages/starred').json()['items']==[]
        assert alice.put(route).status_code==404
        assert bob.delete(route).status_code==404

        second=alice.post(f'/api/conversations/{chat}/messages',json={'body':'Saved for later'}).json()['message']
        assert alice.put(f"/api/messages/{second['id']}/star").status_code==200
        assert outsider.put(f"/api/messages/{second['id']}/star").status_code==404

    new_app=create_app(location)
    with TestClient(new_app) as alice:
        r=alice.post('/api/auth/login',json={'handle':'alice','password':'SecurePassword123!'})
        assert r.status_code==200,r.text
        items=alice.get('/api/messages/starred').json()['items']
        assert [entry['message']['body'] for entry in items]==['Saved for later']
