"""Exercise the real HTTP boundary against an isolated temporary job directory."""
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn
import ezdxf
import backend.app as service
from backend.tests.fixtures import endcap_drawing


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.previous_data = service.DATA
        service.DATA = Path(cls.temp.name)
        cls.sock = socket.socket()
        cls.sock.bind(('127.0.0.1', 0))
        cls.port = cls.sock.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(service.app, log_level='error'))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={'sockets': [cls.sock]}, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError('Test HTTP server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.sock.close()
        service.DATA = cls.previous_data
        cls.temp.cleanup()

    def call(self, endpoint, data=None, content_type='application/json'):
        req = Request(f'http://127.0.0.1:{self.port}{endpoint}', data=data,
                      headers={'Content-Type': content_type})
        try:
            with urlopen(req, timeout=30) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def upload(self, filename, content):
        boundary = 'test-cad-boundary'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        return self.call('/api/drawings', body, f'multipart/form-data; boundary={boundary}')

    def test_rejects_unsupported_empty_and_invalid_dwg(self):
        self.assertEqual(self.upload('test.txt', b'test')[0], 415)
        code, body = self.upload('test.idw', b'test')
        self.assertEqual(code, 415)
        self.assertIn('IDW', json.loads(body)['detail'])
        self.assertEqual(self.upload('test.ipt', b'test')[0], 415)
        self.assertEqual(self.upload('test.dxf', b'')[0], 422)
        self.assertEqual(self.upload('test.dwg', b'not a dwg')[0], 422)
        self.assertEqual(self.call('/api/drawings/not-a-job/outputs/bad/model.step')[0], 404)

    def test_full_pipeline_and_validation(self):
        doc = ezdxf.new('R2010')
        doc.header['$INSUNITS'] = 4
        doc.modelspace().add_circle((0,0), 10)
        doc.modelspace().add_circle((0,0), 4)
        source = Path(self.temp.name) / 'fixture.dxf'
        doc.saveas(source)
        code, payload = self.upload('fixture.dxf', source.read_bytes())
        self.assertEqual(code, 200, payload)
        drawing = json.loads(payload)
        profile = next(p for p in drawing['layouts'][0]['profiles'] if p['holes'])
        endpoint = f"/api/drawings/{drawing['id']}/generate"
        params = {'layout': 'Model', 'profileId': profile['id'], 'mmPerUnit': 1, 'depthMm': 8}
        self.assertEqual(self.call(endpoint, json.dumps(params).encode())[0], 422)
        params['confirmed'] = True
        self.assertEqual(self.call(endpoint, json.dumps({**params, 'depthMm': -1}).encode())[0], 422)
        self.assertEqual(self.call(endpoint, json.dumps({**params, 'profileId': 'missing'}).encode())[0], 422)
        code, payload = self.call(endpoint, json.dumps(params).encode())
        self.assertEqual(code, 200, payload)
        generated = json.loads(payload)
        self.assertTrue(generated['stats']['stepRoundTripVerified'])
        code, step = self.call(generated['stepUrl'])
        self.assertEqual(code, 200)
        self.assertTrue(step.startswith(b'ISO-10303-21;'))
        self.assertEqual(self.call(generated['previewUrl'])[0], 200)
        self.assertEqual(self.call(generated['recipeUrl'])[0], 200)
        _, again = self.call(endpoint, json.dumps({**params, 'depthMm': 9}).encode())
        self.assertNotEqual(generated['generationId'], json.loads(again)['generationId'])
        self.assertEqual(self.call(generated['stepUrl'])[1], step)

    def test_multiview_endpoint_requires_confirmation_and_returns_one_solid(self):
        source = endcap_drawing(Path(self.temp.name)/'endcap.dxf')
        code, payload = self.upload('endcap.dxf', source.read_bytes())
        self.assertEqual(code, 200, payload)
        drawing = json.loads(payload)
        endpoint = f"/api/drawings/{drawing['id']}/generate-part"
        params = {'partId': drawing['partCandidates'][0]['id'], 'mmPerUnit': 1, 'threadMode': 'nominal-through'}
        self.assertEqual(self.call(endpoint, json.dumps(params).encode())[0], 422)
        params['confirmed'] = True
        self.assertEqual(self.call(endpoint, json.dumps({**params,'partId':'missing'}).encode())[0], 422)
        self.assertEqual(self.call(endpoint, json.dumps({**params,'threadMode':'guess'}).encode())[0], 422)
        code, payload = self.call(endpoint, json.dumps(params).encode())
        self.assertEqual(code, 200, payload)
        result = json.loads(payload)
        self.assertEqual(result['stats']['solids'], 1)
        self.assertEqual(result['mode'], 'multiview-single-part')
        self.assertEqual(result['stats']['featureCount'], 12)
        self.assertTrue(self.call(result['stepUrl'])[1].startswith(b'ISO-10303-21;'))


if __name__ == '__main__':
    unittest.main()
