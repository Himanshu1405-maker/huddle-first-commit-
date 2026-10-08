"""True WebSocket integration test through an actual local Uvicorn TCP server.
Run as `python tests/socket_network_smoke.py`; Python packages `requests` and `websockets` required.
"""
import asyncio
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from websockets.asyncio.client import connect

ROOT=Path(__file__).resolve().parents[1]

async def receive_type(ws, event_type):
    for _ in range(10):
        data=json.loads(await asyncio.wait_for(ws.recv(), timeout=4))
        if data['type']==event_type:return data
    raise AssertionError('Did not receive '+event_type)

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        p=subprocess.Popen(['uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env={**os.environ,'HUDDLE_DB':tmp+'/smoke.db','SEED_DEMO':'0'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for _ in range(60):
                try:
                    if requests.get(base+'/health',timeout=.2).status_code==200:break
                except requests.ConnectionError:pass
                await asyncio.sleep(.1)
            else:raise RuntimeError('Could not boot Uvicorn')
            a,b=requests.Session(),requests.Session()
            ua=a.post(base+'/api/auth/register',json={'handle':'alpha','name':'Alpha Tester','password':'ValidPass123!'}).json()['user']
            ub=b.post(base+'/api/auth/register',json={'handle':'bravo','name':'Bravo Tester','password':'ValidPass123!'}).json()['user']
            cid=a.post(base+'/api/conversations/direct',json={'user_id':ub['id']}).json()['conversation']['id']
            def hdr(client):return {'Cookie':'huddle_session='+client.cookies['huddle_session']}
            async with connect(f'ws://127.0.0.1:{port}/ws',additional_headers=hdr(a),origin=base) as wa:
                await receive_type(wa,'hello')
                async with connect(f'ws://127.0.0.1:{port}/ws',additional_headers=hdr(b),origin=base) as wb:
                    await receive_type(wb,'hello')
                    await wb.send(json.dumps({'type':'typing','conversation_id':cid,'typing':True}))
                    typing=await receive_type(wa,'typing:update')
                    assert typing['user_id']==ub['id']
                    await wa.send(json.dumps({'type':'message:send','conversation_id':cid,'body':'Actual network WebSocket success!','nonce':'actual-1'}))
                    message=await receive_type(wb,'message:new')
                    assert message['message']['body']=='Actual network WebSocket success!'
                    ack=await receive_type(wa,'message:ack')
                    assert ack['message_id']==message['message']['id']
                    assert b.get(base+f'/api/conversations/{cid}/messages').json()['messages'][0]['body']=='Actual network WebSocket success!'
                    b.post(base+f'/api/conversations/{cid}/read',json={})
                    read=await receive_type(wa,'read:update')
                    assert read['user_id']==ub['id']
                    print('NETWORK_SMOKE_PASS: actual WS typing, instant delivery, ACK, DB persistence, read receipts')
        finally:
            p.terminate()
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:p.kill()

if __name__=='__main__':asyncio.run(main())
