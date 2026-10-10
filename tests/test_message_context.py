"""Reply/forward server-side chat integrity, authorization and media isolation."""
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def signup(client, handle):
    res=client.post('/api/auth/register',json={
        'name':handle.title(),'handle':handle,'password':'SecurePass123!'})
    assert res.status_code==201,res.text
    return res.json()['user']


def test_reply_forward_and_cross_chat_privacy(tmp_path):
    app=create_app(str(tmp_path/'messages.sqlite'))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as carl,TestClient(app) as stranger:
        a=signup(alice,'alice'); b=signup(bob,'bobby')
        c=signup(carl,'carlx');signup(stranger,'zorro')
        source=alice.post('/api/conversations/direct',json={'user_id':b['id']}).json()['conversation']['id']
        target=alice.post('/api/conversations/direct',json={'user_id':c['id']}).json()['conversation']['id']
        message=alice.post(f'/api/conversations/{source}/messages',json={'body':'Planning our group trip'}).json()['message']
        uri=f'/api/conversations/{source}/messages/context'
        reply=alice.post(uri,json={'action':'reply','source_message_id':message['id'],'body':'Sounds good'})
        assert reply.status_code==201,reply.text
        output=reply.json()['message']
        assert output['reply_to']['id']==message['id']
        assert output['reply_to']['preview']=='Planning our group trip'
        assert output['forwarded'] is False
        assert bob.get(f'/api/conversations/{source}/messages').json()['messages'][-1]['reply_to']['name']=='Alice'
        assert carl.post(f'/api/conversations/{target}/messages/context',json={
            'action':'reply','source_message_id':message['id'],'body':'Not my chat'}).status_code==404
        assert stranger.post(uri,json={'action':'reply','source_message_id':message['id'],'body':'Nope'}).status_code==404
        assert alice.post(f'/api/conversations/{target}/messages/context',json={
            'action':'reply','source_message_id':message['id'],'body':'Wrong destination'}).status_code==422
        forward=alice.post(f'/api/conversations/{target}/messages/context',json={
            'action':'forward','source_message_id':message['id'],'body':'Tampered body deliberately'})
        assert forward.status_code==201,forward.text
        dest=forward.json()['message']
        assert dest['body']=='Planning our group trip'
        assert dest['forwarded'] is True and dest['reply_to'] is None
        assert carl.get(f'/api/conversations/{target}/messages').json()['messages'][-1]['forwarded']
        assert carl.get(f'/api/conversations/{source}/messages').status_code==404
        # Later deleting a replied-to message invalidates the preview, not the reply.
        assert alice.delete('/api/messages/'+message['id']).status_code==200
        reply_after=bob.get(f'/api/conversations/{source}/messages').json()['messages'][-1]
        assert reply_after['reply_to']['preview']=='This message was deleted'
        # But forwarded copy is independent of the source text.
        assert carl.get(f'/api/conversations/{target}/messages').json()['messages'][-1]['body']=='Planning our group trip'


def test_forward_media_and_restrict_location(tmp_path):
    app=create_app(str(tmp_path/'forward.sqlite'))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as carl:
        signup(alice,'alice');b=signup(bob,'bobby');c=signup(carl,'carlx')
        source=alice.post('/api/conversations/direct',json={'user_id':b['id']}).json()['conversation']['id']
        dest=alice.post('/api/conversations/direct',json={'user_id':c['id']}).json()['conversation']['id']
        img=Image.new('RGB',(15,15),'blue')
        bio=BytesIO();img.save(bio,format='PNG')
        blob=bio.getvalue()
        upload=alice.post(f'/api/conversations/{source}/attachments',content=blob,
                          headers={'content-type':'image/png','x-huddle-filename':'sea.png',
                                   'x-huddle-caption':'Shared image'})
        assert upload.status_code==201,upload.text
        origin=upload.json()['message']
        fwd=alice.post(f'/api/conversations/{dest}/messages/context',json={
            'action':'forward','source_message_id':origin['id']})
        assert fwd.status_code==201,fwd.text
        new=fwd.json()['message']
        assert new['forwarded'] and new['attachments'][0]['id']!=origin['attachments'][0]['id']
        new_file=new['attachments'][0]['id']
        assert carl.get('/api/media/'+new_file).content==blob
        assert carl.get('/api/media/'+origin['attachments'][0]['id']).status_code==404
        loc=alice.post(f'/api/conversations/{source}/locations',json={
            'mode':'pin','latitude':31.72,'longitude':76.93})
        assert loc.status_code==201,loc.text
        refuse=alice.post(f'/api/conversations/{dest}/messages/context',json={
            'action':'forward','source_message_id':loc.json()['message']['id']})
        assert refuse.status_code==422
        assert carl.get(f'/api/conversations/{dest}/messages').json()['messages'][-1]['location'] is None
