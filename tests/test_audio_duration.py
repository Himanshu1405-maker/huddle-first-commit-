"""Regression for voice metadata: new recordings, legacy WAV, bad duration input
and forwarded voice messages keep their accurate duration and secure attachment.
"""
from io import BytesIO
import wave
from fastapi.testclient import TestClient
from app.main import create_app

def new_user(client,handle):
    r=client.post('/api/auth/register',json={
        'name':handle.title(),'handle':handle,'password':'StrongTestingPassword123!'})
    assert r.status_code==201,r.text
    return r.json()['user']

def wav_note(ms=1800):
    out=BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        w.writeframes(b'\0\0'*round(16000*ms/1000))
    return out.getvalue()

def test_duration_derived_saved_and_forwarded(tmp_path):
    app=create_app(str(tmp_path/'notes.sqlite'))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as carol:
        new_user(alice,'alice');b=new_user(bob,'bobby');c=new_user(carol,'carol')
        room=alice.post('/api/conversations/direct',json={'user_id':b['id']}).json()['conversation']['id']
        dest=alice.post('/api/conversations/direct',json={'user_id':c['id']}).json()['conversation']['id']
        audio=wav_note(1800)
        response=alice.post(f'/api/conversations/{room}/attachments',content=audio,
            headers={'content-type':'audio/wav','x-huddle-filename':'note.wav','x-huddle-duration-ms':'1'})
        assert response.status_code==201,response.text
        original=response.json()['message']
        assert 1799<=original['attachments'][0]['duration_ms']<=1801,original
        assert bob.get(f'/api/conversations/{room}/messages').json()['messages'][-1]['attachments'][0]['duration_ms']==1800
        copy=alice.post(f'/api/conversations/{dest}/messages/context',json={
            'action':'forward','source_message_id':original['id']})
        assert copy.status_code==201,copy.text
        attachment=copy.json()['message']['attachments'][0]
        assert attachment['duration_ms']==1800
        assert carol.get('/api/media/'+attachment['id']).content==audio

def test_preexisting_media_migration_preserves_messages(tmp_path):
    location=str(tmp_path/'migrate.sqlite')
    app=create_app(location)
    with TestClient(app) as alice,TestClient(app) as bob:
        new_user(alice,'alice');b=new_user(bob,'bobby')
        room=alice.post('/api/conversations/direct',json={'user_id':b['id']}).json()['conversation']['id']
        sent=alice.post(f'/api/conversations/{room}/attachments',content=wav_note(510),
            headers={'content-type':'audio/wav','x-huddle-filename':'legacy.wav'})
        assert sent.status_code==201,sent.text
        assert sent.json()['message']['attachments'][0]['duration_ms']==510
    # New instance uses the same installation. Optional duration column remains.
    app2=create_app(location)
    with TestClient(app2) as alice:
        r=alice.post('/api/auth/login',json={'handle':'alice','password':'StrongTestingPassword123!'})
        assert r.status_code==200,r.text
        result=alice.get(f'/api/conversations/{room}/messages')
        assert result.status_code==200,result.text
        assert result.json()['messages'][-1]['attachments'][0]['duration_ms']==510
