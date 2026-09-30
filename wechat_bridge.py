"""Independent implementation of the documented Wechatsync request protocol.

Only localhost; capability URL and token are never logged. No unauthenticated
HTTP proxy is exposed. An extension connection isn't a verified social login.
"""
import asyncio
import concurrent.futures
import json
import os
import secrets
import threading
import uuid
from pathlib import Path

class Bridge:
    def __init__(self, data, port=9537):
        self.port=port
        self.config_path=Path(data)/'bridge-secret.json'
        if not self.config_path.exists():
            fd=os.open(self.config_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:json.dump({'token':secrets.token_urlsafe(32),'path':secrets.token_urlsafe(24)},f)
        self.secret=json.loads(self.config_path.read_text())
        self.loop=None;self.client=None;self.pending={};self.error=None;self.started=False

    def start(self):
        if self.started:return
        self.started=True
        def thread():
            import websockets
            self.loop=asyncio.new_event_loop();asyncio.set_event_loop(self.loop)
            async def run():
                try:
                    async with websockets.serve(self.handle,'127.0.0.1',self.port,max_size=12*1024*1024,ping_interval=20):
                        await asyncio.Future()
                except Exception as e:self.error='连接服务无法启动，请检查端口或重新启动分发台'
            self.loop.run_until_complete(run())
        threading.Thread(target=thread,daemon=True,name='wechat-local-bridge').start()

    async def handle(self, ws, path):
        origin=ws.request_headers.get('Origin','')
        if path!='/'+self.secret['path'] or (origin and not origin.startswith('chrome-extension://')) or self.client:
            await ws.close(code=1008,reason='Connection not allowed');return
        self.client=ws
        try:
            async for raw in ws:
                try:msg=json.loads(raw)
                except (ValueError,TypeError):continue
                fut=self.pending.pop(msg.get('id'),None)
                if not fut or fut.done():continue
                if msg.get('error'):fut.set_exception(RuntimeError('扩展拒绝请求：请检查扩展版本、连接口令和平台登录状态'))
                else:fut.set_result(msg.get('result'))
        finally:
            if self.client is ws:self.client=None
            for fut in list(self.pending.values()):
                if not fut.done():fut.set_exception(ConnectionError('浏览器扩展已断开；如已提交内容，请先核对平台'))
            self.pending.clear()

    def status(self):
        return {'connected':bool(self.client and not self.client.closed),'started':self.started,'error':self.error}

    def settings(self):
        return dict(self.status(),url=f"ws://127.0.0.1:{self.port}/{self.secret['path']}",token_configured=bool(self.secret.get('configured')))

    def configure_token(self,token):
        self.secret['token']=token;self.secret['configured']=True
        with self.config_path.open('w') as f:json.dump(self.secret,f)
        os.chmod(self.config_path,0o600)

    def request(self,method,params,timeout=90):
        if not self.status()['connected']:raise ConnectionError('请先连接 Wechatsync 浏览器扩展')
        async def send():
            id=uuid.uuid4().hex;f=self.loop.create_future();self.pending[id]=f
            try:
                await self.client.send(json.dumps({'id':id,'method':method,'token':self.secret['token'],'params':params},ensure_ascii=False))
                return await asyncio.wait_for(f,timeout)
            finally:self.pending.pop(id,None)
        future=asyncio.run_coroutine_threadsafe(send(),self.loop)
        try:return future.result(timeout+2)
        except concurrent.futures.TimeoutError:
            future.cancel();raise TimeoutError('扩展未返回确认结果，请核对平台后处理')
