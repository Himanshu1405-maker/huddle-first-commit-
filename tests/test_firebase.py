"""Firebase Google sign-in regression tests (mocked provider response, no real account required)."""
import base64
import json

from fastapi.testclient import TestClient
from app import extras
from app.main import create_app

ENV={'FIREBASE_API_KEY':'public-web-key-test','FIREBASE_PROJECT_ID':'huddle-test',
     'FIREBASE_APP_ID':'1:1:web:abcd','FIREBASE_AUTH_DOMAIN':'huddle-test.firebaseapp.com'}

def make_token(provider='google.com', uid='UID123', aud='huddle-test'):
    claims={'iss':'https://securetoken.google.com/huddle-test','sub':uid,'aud':aud,
            'firebase':{'sign_in_provider':provider}}
    payload=base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return 'eyJhbGciOiJSUzI1NiJ9.'+payload+'.'+'x'*200

def test_verified_firebase_google_account(tmp_path,monkeypatch):
    for k,v in ENV.items():monkeypatch.setenv(k,v)
    monkeypatch.delenv('GOOGLE_CLIENT_ID',raising=False)
    def lookup(url,payload,headers,timeout=20):
        assert url.startswith('https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=')
        assert payload['idToken']
        return {'users':[{'localId':'UID123','email':'person@example.com','displayName':'Test Person',
                          'emailVerified':True,'providerUserInfo':[{'providerId':'google.com'}]}]}
    monkeypatch.setattr(extras,'_post_json',lookup)
    with TestClient(create_app(str(tmp_path/'fb.db'))) as client:
        conf=client.get('/api/config').json()
        assert conf['google_login'] and conf['firebase_config']['projectId']=='huddle-test'
        headers={'X-Huddle-Client':'web'}
        token=make_token()
        first=client.post('/api/auth/google',json={'credential':token},headers=headers)
        assert first.status_code==200,first.text
        first_id=first.json()['user']['id']
        assert client.get('/api/me').json()['user']['id']==first_id
        repeat=client.post('/api/auth/google',json={'credential':token},headers=headers)
        assert repeat.status_code==200 and repeat.json()['user']['id']==first_id
        assert client.post('/api/auth/google',json={'credential':token}).status_code==403

def test_reject_invalid_project_and_unverified_email(tmp_path,monkeypatch):
    for k,v in ENV.items():monkeypatch.setenv(k,v)
    monkeypatch.delenv('GOOGLE_CLIENT_ID',raising=False)
    monkeypatch.setattr(extras,'_post_json',lambda *_args,**kwargs:
        {'users':[{'localId':'UID123','email':'person@example.com','displayName':'Test Person',
                   'emailVerified':True,'providerUserInfo':[{'providerId':'google.com'}]}]})
    with TestClient(create_app(str(tmp_path/'fb.db'))) as client:
        headers={'X-Huddle-Client':'web'}
        for token in ['not-a-token-'*7,make_token(provider='password'),
                      make_token(aud='wrong-project'),make_token(uid='wrong-uid')]:
            assert client.post('/api/auth/google',json={'credential':token},headers=headers).status_code==401
        monkeypatch.setattr(extras,'_post_json',lambda *_args,**kwargs:
            {'users':[{'localId':'UID123','email':'person@example.com',
                       'emailVerified':False,'providerUserInfo':[{'providerId':'google.com'}]}]})
        assert client.post('/api/auth/google',json={'credential':make_token()},headers=headers).status_code==401


def test_browser_diagnostics_are_safe_and_rate_limited(tmp_path,monkeypatch,caplog):
    for key in FB: monkeypatch.delenv(key,raising=False)
    with TestClient(create_app(str(tmp_path/'diagnostics.db'))) as client:
        assert client.post('/api/diagnostics/google',json={'stage':'popup','code':'auth/popup-closed-by-user'}).status_code==200
        assert 'error_code=auth/popup-closed-by-user' in caplog.text
        assert client.post('/api/diagnostics/google',json={'stage':'popup','code':'token=secret'}).status_code==422
        assert client.post('/api/diagnostics/google',json={'stage':'popup','code':'auth/unknown','email':'private@example.com'}).status_code==200
        assert 'private@example.com' not in caplog.text
