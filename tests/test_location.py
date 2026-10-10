"""Location privacy, authorization, expiry and updates in Huddle chats."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import create_app


def signup(client, name):
    response = client.post('/api/auth/register',json={
        'name':name.title(),'handle':name,'password':'SecurePass123!'
    })
    assert response.status_code==201, response.text
    return response.json()['user']


def test_location_pin_and_live_privacy(tmp_path):
    app=create_app(str(tmp_path/'location.db'))
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as eve:
        a=signup(alice,'alice')
        b=signup(bob,'bob')
        signup(eve,'eve')
        cid=alice.post('/api/conversations/direct',json={'user_id':b['id']}).json()['conversation']['id']
        route=f'/api/conversations/{cid}/locations'
        assert eve.post(route,json={'mode':'pin','latitude':0,'longitude':0}).status_code==404
        assert alice.post(route,json={'mode':'pin','latitude':100,'longitude':0}).status_code==422
        pin=alice.post(route,json={'mode':'pin','latitude':31.77,'longitude':76.98})
        assert pin.status_code==201,pin.text
        pinned=pin.json()['message']
        assert pinned['location']['mode']=='pin'
        assert pinned['location']['latitude']==31.77
        assert bob.get(f'/api/conversations/{cid}/messages').json()['messages'][0]['location']['longitude']==76.98
        assert eve.get(f'/api/conversations/{cid}/messages').status_code==404

        live=alice.post(route,json={'mode':'live','latitude':31.77,'longitude':76.98,'duration_minutes':15})
        assert live.status_code==201,live.text
        msg=live.json()['message']
        mid=msg['id']
        assert msg['location']['active']
        assert alice.post(route,json={'mode':'live','latitude':31.8,'longitude':76.9}).status_code==409
        assert bob.patch(f'/api/locations/{mid}',json={'latitude':31.79,'longitude':76.98}).status_code==404
        assert eve.post(f'/api/locations/{mid}/stop').status_code==404
        with app.state.db.connection() as cx:
            cx.execute("UPDATE location_shares SET updated_at=? WHERE message_id=?",
                       ((datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat(timespec='microseconds'),mid))
        updated=alice.patch(f'/api/locations/{mid}',json={'latitude':31.79001,'longitude':76.99999})
        assert updated.status_code==200,updated.text
        assert updated.json()['message']['location']['latitude']==31.79001
        assert bob.get(f'/api/conversations/{cid}/messages').json()['messages'][-1]['location']['longitude']==76.99999
        stopped=alice.post(f'/api/locations/{mid}/stop')
        assert stopped.status_code==200,stopped.text
        assert stopped.json()['message']['location']['active'] is False
        assert stopped.json()['message']['location']['latitude'] is None
        assert alice.patch(f'/api/locations/{mid}',json={'latitude':31.7,'longitude':76.9}).status_code==404
        with app.state.db.connection() as cx:
            row=cx.execute('SELECT coordinates FROM location_shares WHERE message_id=?',(mid,)).fetchone()
            assert row['coordinates'] is None


def test_live_expiry_and_delete_clears_coordinates(tmp_path):
    app=create_app(str(tmp_path/'location-expiry.db'))
    with TestClient(app) as alice,TestClient(app) as bob:
        signup(alice,'alice'); user=signup(bob,'bob')
        cid=alice.post('/api/conversations/direct',json={'user_id':user['id']}).json()['conversation']['id']
        route=f'/api/conversations/{cid}/locations'
        mid=alice.post(route,json={'mode':'live','latitude':23.1,'longitude':75.4}).json()['message']['id']
        with app.state.db.connection() as cx:
            cx.execute('UPDATE location_shares SET expires_at=? WHERE message_id=?',(
                (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(timespec='microseconds'),mid))
        message=bob.get(f'/api/conversations/{cid}/messages').json()['messages'][0]
        assert not message['location']['active']
        assert message['location']['latitude'] is None
        with app.state.db.connection() as cx:
            assert cx.execute('SELECT coordinates FROM location_shares WHERE message_id=?',(mid,)).fetchone()['coordinates'] is None
        other=alice.post(route,json={'mode':'live','latitude':23.1,'longitude':75.4}).json()['message']['id']
        deleted=alice.delete(f'/api/messages/{other}')
        assert deleted.status_code==200,deleted.text
        with app.state.db.connection() as cx:
            assert cx.execute('SELECT coordinates FROM location_shares WHERE message_id=?',(other,)).fetchone()['coordinates'] is None
