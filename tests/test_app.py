import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def pair(tmp_path):
    app = create_app(str(tmp_path / 'test.db'))
    with TestClient(app) as a, TestClient(app) as b, TestClient(app) as outsider:
        yield a, b, outsider


def register(client, handle, name=None):
    result = client.post('/api/auth/register', json={'name': name or handle.title(), 'handle': handle, 'password': 'SecurePass123!'})
    assert result.status_code == 201, result.text
    return result.json()['user']


def direct(a, b):
    result = a.post('/api/conversations/direct', json={'user_id': b['id']})
    assert result.status_code == 200, result.text
    return result.json()['conversation']['id']


def test_health_auth_and_sessions(pair):
    a, b, _ = pair
    assert a.get('/health').json()['ok']
    assert a.get('/api/conversations').status_code == 401
    alice = register(a, 'alice')
    assert alice['handle'] == 'alice'
    assert a.get('/api/me').json()['user']['id'] == alice['id']
    assert a.post('/api/auth/register', json={'name': 'Dup','handle': 'alice','password': 'abcdefgh'}).status_code == 409
    assert a.patch('/api/me', json={'name': 'Alice Updated','bio':'Building in Mandi'}).json()['user']['bio'] == 'Building in Mandi'
    assert a.post('/api/auth/logout').status_code == 200
    assert a.get('/api/me').status_code == 401
    assert a.post('/api/auth/login',json={'handle':'alice','password':'wrong-password'}).status_code == 401
    assert a.post('/api/auth/login',json={'handle':'alice','password':'SecurePass123!'}).status_code == 200
    assert a.get('/api/me').status_code == 200


def test_dm_realtime_persistence_and_isolation(pair):
    a, b, stranger = pair
    alice, bob, eve = register(a,'alice'),register(b,'bob'),register(stranger,'eve')
    cid = direct(a,bob)
    # Stable 1:1 conversation regardless of starter.
    assert direct(b,alice) == cid
    assert stranger.get(f'/api/conversations/{cid}/messages').status_code == 404
    assert stranger.post(f'/api/conversations/{cid}/messages',json={'body':'intrude'}).status_code == 404
    with a.websocket_connect('/ws') as wa, b.websocket_connect('/ws') as wb:
        assert wa.receive_json()['type'] == 'hello'
        assert wb.receive_json()['type'] == 'hello'
        # The presence event is emitted on the second connection.
        assert wa.receive_json()['type'] == 'presence:update'  # own connection
        assert wa.receive_json()['type'] == 'presence:update'  # Bob connected
        assert wb.receive_json()['type'] == 'presence:update'  # own connection
        wa.send_json({'type':'message:send','conversation_id':cid,'body':'Hello Bob 👋','nonce':'idemp-1'})
        delivered_to_a = wa.receive_json()
        delivered_to_b = wb.receive_json()
        assert delivered_to_a['type'] == 'message:new'
        assert delivered_to_b['type'] == 'message:new'
        assert delivered_to_b['message']['body'] == 'Hello Bob 👋'
        assert wa.receive_json() == {'type':'message:ack','nonce':'idemp-1','message_id':delivered_to_a['message']['id']}
        msg_id = delivered_to_a['message']['id']
        assert a.get(f'/api/conversations/{cid}/messages').json()['messages'][0]['id'] == msg_id
        assert stranger.patch(f'/api/messages/{msg_id}',json={'body':'hack'}).status_code == 404
        assert stranger.post(f'/api/messages/{msg_id}/reactions',json={'emoji':'👍'}).status_code == 404
        result = a.post(f'/api/conversations/{cid}/messages',json={'body':'Hello Bob 👋','client_nonce':'idemp-1'})
        assert not result.json()['created']
        assert len(b.get(f'/api/conversations/{cid}/messages').json()['messages']) == 1
    # Messages remain available after clients disconnect.
    assert b.get(f'/api/conversations/{cid}/messages').json()['messages'][0]['body'] == 'Hello Bob 👋'


def test_group_reaction_edit_delete_search_and_reads(pair):
    a, b, outsider = pair
    alice,bob,eve=register(a,'alice'),register(b,'bob'),register(outsider,'eve')
    group=a.post('/api/conversations/group',json={'name':'First Commit Builders','description':'Ship it','member_ids':[bob['id']]})
    assert group.status_code==201,group.text
    cid=group.json()['conversation']['id']
    assert group.json()['conversation']['kind']=='group'
    assert outsider.get(f'/api/conversations/{cid}/messages').status_code==404
    msg=a.post(f'/api/conversations/{cid}/messages',json={'body':'The prototype is ready 🚀'}).json()['message']
    mid=msg['id']
    assert b.get('/api/conversations').json()['conversations'][0]['unread']==1
    assert b.post(f'/api/conversations/{cid}/read').status_code==200
    assert b.get('/api/conversations').json()['conversations'][0]['unread']==0
    assert bob['id'] in a.get(f'/api/conversations/{cid}/messages').json()['messages'][0]['seen_by']
    assert b.post(f'/api/messages/{mid}/reactions',json={'emoji':'🔥'}).json()['message']['reactions'][0]['count']==1
    assert b.post(f'/api/messages/{mid}/reactions',json={'emoji':'🔥'}).json()['message']['reactions']==[]
    assert b.post(f'/api/messages/{mid}/reactions',json={'emoji':'🧨'}).status_code==422
    assert b.patch(f'/api/messages/{mid}',json={'body':'not mine'}).status_code==404
    assert a.patch(f'/api/messages/{mid}',json={'body':'Prototype shipped'}).status_code==200
    assert len(a.get('/api/search/messages?q=shipped').json()['results'])==1
    assert outsider.get('/api/search/messages?q=shipped').json()['results']==[]
    assert a.delete(f'/api/messages/{mid}').status_code==200
    assert a.get('/api/search/messages?q=shipped').json()['results']==[]
    assert a.get(f'/api/conversations/{cid}/messages').json()['messages'][0]['deleted_at'] is not None


def test_input_security(pair):
    a,b,c=pair
    register(a,'alice')
    assert b.post('/api/auth/login',json={'handle':'alice','password':'SecurePass123!'},headers={'Origin':'https://evil.example'}).status_code==403
    assert a.post('/api/conversations/direct',json={'user_id':'nope'}).status_code==404
    assert a.post('/api/conversations/group',json={'name':'ABC','member_ids':['nope']}).status_code==422
    assert a.get('/api/search/messages?q=a').json()['results']==[]
    bad_handle = a.post('/api/auth/register',json={'name':'Valid Name','handle':'bad handle','password':'12345678'})
    assert bad_handle.status_code == 422 and 'Username' in bad_handle.json()['detail']
    bad_name = a.post('/api/auth/register',json={'name':'A ','handle':'valid_name','password':'12345678'})
    assert bad_name.status_code == 422 and 'Display name' in bad_name.json()['detail']
    assert a.post('/api/auth/register',json={'name':'bad','handle':'bad-handle!','password':'12345678'}).status_code==422


def test_group_admin_can_invite_and_non_admin_cannot(pair):
    owner, member, third = pair
    a = register(owner, 'owner')
    b = register(member, 'member')
    c = register(third, 'third')
    cid = owner.post('/api/conversations/group', json={'name':'Study Circle', 'member_ids':[b['id']]}).json()['conversation']['id']
    assert member.post(f'/api/conversations/{cid}/members',json={'member_ids':[c['id']]}).status_code == 403
    assert third.get(f'/api/conversations/{cid}/messages').status_code == 404
    res=owner.post(f'/api/conversations/{cid}/members',json={'member_ids':[c['id']]})
    assert res.status_code == 200 and res.json()['added'] == 1
    assert third.get(f'/api/conversations/{cid}/messages').status_code == 200
    assert owner.post(f'/api/conversations/{cid}/members',json={'member_ids':[c['id']]}).json()['added'] == 0


def test_public_preview_safety_headers_and_message_rate_limit(pair):
    a, b, _ = pair
    register(a, 'alice')
    bob = register(b, 'bob')
    room = direct(a, bob)
    headers = a.get('/').headers
    assert 'frame-ancestors' in headers['content-security-policy']
    assert headers['x-frame-options'] == 'DENY'
    assert 'camera=()' in headers['permissions-policy']
    for i in range(30):
        result = a.post(f'/api/conversations/{room}/messages', json={'body':f'message {i}'})
        assert result.status_code == 201
    assert a.post(f'/api/conversations/{room}/messages', json={'body':'spam'}).status_code == 429
    assert len(b.get(f'/api/conversations/{room}/messages').json()['messages']) == 30


def test_history_pagination_boundary_and_timestamp_ties(pair):
    a, b, _ = pair
    register(a, 'alice')
    bob = register(b, 'bobby')
    room = direct(a, bob)
    # Forty-nine old entries plus eleven entries with identical timestamps.
    # Pagination must not skip any or imply older messages at exactly 60.
    with a.app.state.db.connection() as cx:
        for i in range(60):
            cx.execute("""INSERT INTO messages(id,conversation_id,sender_id,body,created_at)
                          VALUES(?,?,?,?,?)""", (f'{i:032d}',room,a.get('/api/me').json()['user']['id'],
                                     f'Message {i}', '2026-01-01T00:00:00.000000+00:00' if i>=49 else f'2025-01-01T00:00:{i:02d}+00:00'))
    one = a.get(f'/api/conversations/{room}/messages').json()
    assert len(one['messages']) == 60 and one['has_more'] is False
    with a.app.state.db.connection() as cx:
        cx.execute("""INSERT INTO messages(id,conversation_id,sender_id,body,created_at)
                      VALUES(?,?,?,?,?)""", ('a'*32,room,a.get('/api/me').json()['user']['id'],
                                 'Newest', '2027-01-01T00:00:00+00:00'))
    newer = a.get(f'/api/conversations/{room}/messages').json()
    assert newer['has_more'] is True and len(newer['messages']) == 60
    before_id = newer["messages"][0]["id"]
    older = a.get(f'/api/conversations/{room}/messages?before={before_id}').json()
    ids = [m['id'] for m in older['messages']] + [m['id'] for m in newer['messages']]
    assert len(ids) == 61 and len(set(ids)) == 61 and older['has_more'] is False


def test_validation_and_access_security(pair):
    alice, bob, other = pair
    register(alice, 'alice')
    b = register(bob, 'bobby')
    outsider = register(other, 'outsider')
    room = direct(alice, b)
    assert alice.post('/api/auth/register',json={'handle':'alice','name':'Alice','password':'abcdefgh'}).status_code == 409
    assert alice.post('/api/auth/register',json={'handle':'a@b','name':'Alice','password':'abcdefgh'}).status_code == 422
    assert alice.post('/api/auth/register',json={'handle':'valid_1','name':'Alice','password':'short'}).status_code == 422
    assert other.get(f'/api/conversations/{room}/messages').status_code == 404
    assert other.post(f'/api/conversations/{room}/messages',json={'body':'Intrusion'}).status_code == 404
    assert other.get(f'/api/conversations/{room}/messages?before=invalid').status_code == 404
    assert alice.get(f'/api/conversations/{room}/messages?before=invalid').status_code == 404
    assert alice.post('/api/conversations/direct',json={'user_id':outsider['id']}).status_code == 200
    assert alice.post('/api/conversations/direct',json={'user_id':outsider['id']}).status_code == 200


def test_literal_search_and_user_lookup(pair):
    alice, bob, _ = pair
    register(alice, 'alice')
    b = register(bob, 'user_01', 'User Zero One')
    room = direct(alice, b)
    first = alice.post(f'/api/conversations/{room}/messages', json={'body':'plain hello'})
    second = alice.post(f'/api/conversations/{room}/messages', json={'body':'code__check 100% reliable'})
    assert first.status_code == 201 and second.status_code == 201
    assert alice.get('/api/search/messages?q=__').json()['results'][0]['body'] == 'code__check 100% reliable'
    assert len(alice.get('/api/search/messages?q=__').json()['results']) == 1
    assert len(alice.get('/api/search/messages?q=100%25').json()['results']) == 1
    assert len(alice.get('/api/users?search=_').json()['users']) == 1
    assert len(alice.get('/api/users?search=%25').json()['users']) == 0



def test_email_otp_registration_resend_and_lockout(tmp_path, monkeypatch):
    """New users get no session until a real provider has sent and they enter the OTP."""
    monkeypatch.setenv('BREVO_API_KEY', 'unit-test-not-a-real-key')
    monkeypatch.setenv('MAIL_FROM', 'sender@example.com')
    sent=[]
    async def fake_email(email,code):
        sent.append((email,code))
    monkeypatch.setattr('app.main.send_verification_email',fake_email)
    app=create_app(str(tmp_path/'otp.db'))
    with TestClient(app) as client:
        assert client.get('/api/config').json()['email_otp'] is True
        request={'name':'Alice Test','handle':'alice_otp','password':'StrongPassword123!','email':'alice@example.com'}
        resp=client.post('/api/auth/register',json=request)
        assert resp.status_code==202,resp.text
        ticket=resp.json()['ticket']
        assert client.get('/api/me').status_code==401
        assert len(sent)==1 and len(sent[0][1])==6
        assert client.post('/api/auth/verify',json={'ticket':ticket,'code':'99999'}).status_code==422
        wrong='000000' if sent[0][1]!='000000' else '111111'
        assert client.post('/api/auth/verify',json={'ticket':ticket,'code':wrong}).status_code==422
        assert client.post('/api/auth/verify',json={'ticket':ticket,'code':sent[0][1]}).status_code==200
        assert client.get('/api/me').json()['user']['handle']=='alice_otp'
        assert client.post('/api/auth/register',json=request).status_code==409
        assert client.post('/api/auth/verify',json={'ticket':ticket,'code':sent[0][1]}).status_code==410


def test_email_otp_failed_delivery_prevents_account(tmp_path,monkeypatch):
    monkeypatch.setenv('BREVO_API_KEY','fake')
    monkeypatch.setenv('MAIL_FROM','sender@example.com')
    async def fail_email(email,code): raise RuntimeError('provider down')
    monkeypatch.setattr('app.main.send_verification_email',fail_email)
    app=create_app(str(tmp_path/'down.db'))
    with TestClient(app) as client:
        payload={'name':'Alice Name','handle':'my_handle','password':'abcdefgh123!','email':'alice@example.com'}
        assert client.post('/api/auth/register',json=payload).status_code==503
        assert client.get('/api/me').status_code==401


def test_ai_permissions_history_and_rate_limit(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','fake-test-key')
    monkeypatch.delenv('HF_TOKEN',raising=False)
    async def fake_ai(messages):
        return 'Think of a derivative as the instant slope.'
    monkeypatch.setattr('app.main.ask_ai',fake_ai)
    app=create_app(str(tmp_path/'ai.db'))
    with TestClient(app) as a,TestClient(app) as b:
        assert a.get('/api/config').json()=={'email_otp':False,'ai_chat':True,'ai_image':False,'google_login':False,'google_client_id':''}
        assert a.post('/api/ai/chat',json={'prompt':'Teach derivatives'}).status_code==401
        register(a,'learner')
        register(b,'another')
        resp=a.post('/api/ai/chat',json={'prompt':'Teach derivatives'})
        assert resp.status_code==200,resp.text
        assert resp.json()['reply']['role']=='assistant'
        assert len(a.get('/api/ai/history').json()['messages'])==2
        assert b.get('/api/ai/history').json()['messages']==[]
        assert a.post('/api/ai/image',json={'prompt':'Blue mountains'}).status_code==503
        for i in range(19):
            assert a.post('/api/ai/chat',json={'prompt':f'Question number {i}'}).status_code==200
        assert a.post('/api/ai/chat',json={'prompt':'An extra question'}).status_code==429


# Google account verification is mocked here; real ID-token signatures and the
# Google OAuth consent screen require a configured real Google OAuth web client.
def test_google_disabled_rejects_fake_credentials_and_hides_button(tmp_path, monkeypatch):
    monkeypatch.delenv('GOOGLE_CLIENT_ID', raising=False)
    app = create_app(str(tmp_path / 'g-off.db'))
    with TestClient(app) as visitor:
        config = visitor.get('/api/config').json()
        assert config['google_login'] is False
        assert config['google_client_id'] == ''
        assert visitor.post('/api/auth/google',json={'credential':'x'*90},headers={'X-Huddle-Client':'web'}).status_code == 503


def test_google_new_account_signin_and_random_password(tmp_path, monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','1234567890-test-application.apps.googleusercontent.com')
    identity={'sub':'subject-123','email':'test.person@gmail.com','name':'Test Person'}
    monkeypatch.setattr('app.main.verify_google_credential', lambda token: identity if token == 'credential-valid-'*5 else (_ for _ in ()).throw(ValueError('Invalid token')))
    app=create_app(str(tmp_path/'g-on.db'))
    with TestClient(app) as visitor:
        c=visitor.get('/api/config').json()
        assert c['google_login'] and c['google_client_id'].startswith('1234567890-')
        assert visitor.post('/api/auth/google',json={'credential':'credential-valid-'*5}).status_code == 403
        assert visitor.post('/api/auth/google',json={'credential':'bad-token-'*5},headers={'X-Huddle-Client':'web'}).status_code == 401
        created=visitor.post('/api/auth/google',json={'credential':'credential-valid-'*5},headers={'X-Huddle-Client':'web'})
        assert created.status_code == 200, created.text
        u=created.json()['user']
        assert u['handle']=='test_person'
        assert visitor.get('/api/me').json()['user']['id']==u['id']
        assert visitor.post('/api/auth/logout').status_code == 200
        again=visitor.post('/api/auth/google',json={'credential':'credential-valid-'*5},headers={'X-Huddle-Client':'web'})
        assert again.json()['user']['id']==u['id']
        assert visitor.post('/api/auth/login',json={'handle':u['handle'],'password':'credential-valid-'*5}).status_code == 401
        with app.state.db.connection() as cx:
            assert cx.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1
            assert cx.execute('SELECT email FROM verified_emails WHERE user_id=?',(u['id'],)).fetchone()[0]=='test.person@gmail.com'


def test_google_avoids_existing_verified_email_takeover(tmp_path,monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','1234567890-test-application.apps.googleusercontent.com')
    monkeypatch.setattr('app.main.verify_google_credential', lambda credential:{'sub':'sub-ABC','email':'alice@example.com','name':'Alice Google'})
    app=create_app(str(tmp_path/'g-link.db'))
    with TestClient(app) as alice,TestClient(app) as stranger:
        original=register(alice,'alice')
        with app.state.db.connection() as cx:
            cx.execute('INSERT INTO verified_emails(user_id,email,verified_at) VALUES(?,?,?)',(original['id'],'alice@example.com','2026-10-01T01:01:01Z'))
        rejected=stranger.post('/api/auth/google',json={'credential':'fake-google-credential-valid-length'},headers={'X-Huddle-Client':'web'})
        assert rejected.status_code==409
        assert stranger.get('/api/me').status_code==401
        linked=alice.post('/api/auth/google/link',json={'credential':'fake-google-credential-valid-length'},headers={'X-Huddle-Client':'web'})
        assert linked.status_code==200,linked.text
        assert linked.json()['already_linked']==False
        assert alice.post('/api/auth/google/link',json={'credential':'fake-google-credential-valid-length'},headers={'X-Huddle-Client':'web'}).json()['already_linked']
        assert alice.post('/api/auth/logout').status_code==200
        relogin=stranger.post('/api/auth/google',json={'credential':'fake-google-credential-valid-length'},headers={'X-Huddle-Client':'web'})
        assert relogin.status_code==200
        assert relogin.json()['user']['id']==original['id']


def test_google_link_requires_session_and_unique_subject(tmp_path,monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','1234567890-test-application.apps.googleusercontent.com')
    monkeypatch.setattr('app.main.verify_google_credential', lambda credential:{'sub':'google-person','email':'google@example.com','name':'Google Person'})
    app=create_app(str(tmp_path/'g-unique.db'))
    with TestClient(app) as a,TestClient(app) as b:
        x=register(a,'sam')
        y=register(b,'jane')
        assert b.post('/api/auth/logout').status_code==200
        assert b.post('/api/auth/google/link',json={'credential':'long-google-credential-test-with-minimum-length'},headers={'X-Huddle-Client':'web'}).status_code==401
        assert a.post('/api/auth/google/link',json={'credential':'long-google-credential-test-with-minimum-length'},headers={'X-Huddle-Client':'web'}).status_code==200
        assert b.post('/api/auth/login',json={'handle':'jane','password':'SecurePass123!'}).status_code==200
        assert b.post('/api/auth/google/link',json={'credential':'long-google-credential-test-with-minimum-length'},headers={'X-Huddle-Client':'web'}).status_code==409
