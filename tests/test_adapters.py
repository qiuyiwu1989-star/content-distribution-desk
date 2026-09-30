import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import websockets
from wechat_bridge import Bridge
import adapters

class AdapterTests(unittest.TestCase):
    def test_bridge_protocol_roundtrip_and_rejects_wrong_path(self):
        async def scenario(root):
            b=Bridge(root);b.loop=asyncio.get_running_loop();b.configure_token('test-token-not-a-real-credential')
            async with websockets.serve(b.handle,'127.0.0.1',0) as server:
                port=server.sockets[0].getsockname()[1]
                async with websockets.connect(f'ws://127.0.0.1:{port}/wrong') as bad:
                    with self.assertRaises(websockets.ConnectionClosed):await bad.recv()
                async with websockets.connect(f'ws://127.0.0.1:{port}/'+b.secret['path']) as ws:
                    async def fake_extension():
                        message=json.loads(await ws.recv())
                        self.assertEqual(message['method'],'checkAuth');self.assertEqual(message['params'],{'platform':'weixin'})
                        self.assertEqual(message['token'],'test-token-not-a-real-credential')
                        await ws.send(json.dumps({'id':message['id'],'result':{'isAuthenticated':True,'uid':'test'}}))
                    reply, result=await asyncio.gather(fake_extension(),asyncio.to_thread(b.request,'checkAuth',{'platform':'weixin'},2))
                    self.assertEqual(result['uid'],'test')
            self.assertNotIn('token',b.settings())
        with tempfile.TemporaryDirectory() as root:asyncio.run(scenario(root))
    def test_changed_asset_prevents_submission(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'asset').write_bytes(b'changed')
            s={'account':{},'connection':{'adapter':'wechatsync'},'task':{},'options':{},'files_root':root,'assets':[{'id':'asset','metadata':{'sha256':'approved-old-hash'}}]}
            bridge=Mock();r=adapters.execute(s,bridge,Path(root));self.assertEqual(r['status'],'blocked');bridge.request.assert_not_called()
    def test_uploader_arguments_preserve_order_and_title(self):
        with tempfile.TemporaryDirectory() as root:
            for a in ['a','b']:Path(root,a).write_bytes(b'fixture')
            out=Path(root,'out');out.mkdir()
            s={'account':{'platform':'rednote'},'connection':{'reference':'test_only'},'task':{'format':'gallery','asset_ids':['b','a'],'title':'标题 $(literal)','body':'图文简介','tags':'#AI，#教育'},'options':{'mode':'publish'},'assets':[{'id':'a','name':'a.png'},{'id':'b','name':'b.png'}],'files_root':root}
            cmd=adapters.sau_command(s,out)
            self.assertEqual(cmd[cmd.index('--images')+1:cmd.index('--note')],[str(out/'02-b.png'),str(out/'01-a.png')])
            self.assertEqual(cmd[cmd.index('--title')+1],'标题 $(literal)');self.assertNotIn('--draft',cmd)
