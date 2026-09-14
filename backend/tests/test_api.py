"""Exercise the real HTTP boundary against an isolated temporary job directory."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn
import ezdxf
import backend.app as service
from backend.tests.fixtures import endcap_drawing
from backend.tests.test_axial import axial_drawing
from backend.inventor import inventor_available


class ApiTests(unittest.TestCase):
    # Check generation, PDF retrieval and identifier validation against the real HTTP API.
    def test_engineering_pdf_endpoint_and_download(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from backend.modeling import export_solid
        directory = service.DATA / ('a' * 32)
        output = directory / ('b' * 32)
        output.mkdir(parents=True, exist_ok=True)
        (directory / 'drawing.json').write_text('{}', encoding='utf-8')
        export_solid(BRepPrimAPI_MakeCylinder(10, 30).Shape(), output)
        endpoint = f'/api/drawings/{directory.name}/outputs/{output.name}/engineering-pdf'
        code, payload = self.call(endpoint, json.dumps({'title': 'PDF test'}).encode())
        self.assertEqual(code, 200, payload)
        report = json.loads(payload)
        code, pdf = self.call(report['pdfUrl'])
        self.assertEqual(code, 200)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertEqual(self.call(report['pdfUrl'] + '?download=true')[0], 200)
        self.assertEqual(self.call(endpoint, b'{"sectionPercent":100}')[0], 422)
        self.assertEqual(self.call(endpoint, b'{"scale":10}')[0], 422)
        self.assertEqual(self.call(endpoint + '/not-a-revision')[0], 404)

    # Exercise actual uploaded IPT samples through conversion and downloadable STEP output.
    @unittest.skipUnless(os.getenv('IPT_SAMPLE_DIR') and inventor_available(), 'Optional real IPT samples/runtime unavailable')
    def test_real_ipt_uploads_preserve_complete_geometry(self):
        samples = [('下接头.ipt', 1, 21), ('中部连接头.ipt', 1, 54), ('下接头 -2.ipt', 2, 42)]
        for filename, solids, faces in samples:
            with self.subTest(filename=filename):
                source = Path(os.environ['IPT_SAMPLE_DIR']) / filename
                code, payload = self.upload(filename, source.read_bytes())
                self.assertEqual(code, 200, payload.decode('utf-8'))
                drawing = json.loads(payload)
                result = drawing['result']
                self.assertEqual(drawing['layouts'], [])
                self.assertTrue(result['stats']['valid'])
                self.assertTrue(result['stats']['stepRoundTripVerified'])
                self.assertEqual(result['stats']['solids'], solids)
                report = json.loads((service.DATA / drawing['id'] / 'converter.log').read_text(encoding='utf-8'))
                self.assertEqual(report['sourceFaces'], faces)
                self.assertEqual(report['outputFaces'], faces)
                self.assertTrue(report['faceCountVerified'])
                status, step = self.call(result['stepUrl'])
                self.assertEqual(status, 200)
                self.assertTrue(step.startswith(b'ISO-10303-21;'))
                self.assertEqual(self.call(result['previewUrl'])[0], 200)

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

    # Send an explicit output choice when testing format routing; retain legacy uploads.
    def upload(self, filename, content, output_format=None):
        boundary = 'test-cad-boundary'
        fields = (f'--{boundary}\r\nContent-Disposition: form-data; name="outputFormat"\r\n\r\n'
                  f'{output_format}\r\n').encode() if output_format is not None else b''
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        return self.call('/api/drawings', fields + body, f'multipart/form-data; boundary={boundary}')

    # Reject unsupported parametric output before conversion or creating a misleading job.
    def test_ipt_output_selection_does_not_fall_back_to_step(self):
        previous_jobs = set(service.DATA.iterdir())
        with patch('backend.app.convert_ipt') as converter:
            code, payload = self.upload('part.ipt', b'ipt', 'sldprt')
            self.assertEqual(code, 503)
            self.assertIn('尚未实现', json.loads(payload)['detail'])
            self.assertEqual(self.upload('drawing.dxf', b'dxf', 'sldprt')[0], 422)
            self.assertEqual(self.upload('part.ipt', b'ipt', 'unknown')[0], 422)
            converter.assert_not_called()
        self.assertEqual(set(service.DATA.iterdir()), previous_jobs)
        code, payload = self.call('/api/health')
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(payload)['iptParametric']['available'])

    def test_rejects_unsupported_empty_and_invalid_dwg(self):
        self.assertEqual(self.upload('test.txt', b'test')[0], 415)
        code, body = self.upload('test.idw', b'test')
        self.assertEqual(code, 415)
        self.assertIn('IDW', json.loads(body)['detail'])
        with patch('backend.app.convert_ipt', side_effect=ValueError('IPT 文件头无效')):
            self.assertEqual(self.upload('test.ipt', b'test')[0], 422)
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

    # Native IPT files bypass all drawing profiles and return one ready model.
    def test_ipt_upload_returns_complete_native_part(self):
        def fake_convert(_source, target):
            Path(target).write_bytes(b'translated-step')
            return 'Inventor test translator'

        def fake_import(_source, output):
            (Path(output) / 'model.step').write_bytes(b'ISO-10303-21; test')
            (Path(output) / 'preview.stl').write_bytes(b'solid test\nendsolid test')
            return {'valid': True, 'solids': 1, 'volumeMm3': 125.5,
                    'stepRoundTripVerified': True}

        with patch('backend.app.convert_ipt', side_effect=fake_convert), \
                patch('backend.modeling.import_step', side_effect=fake_import):
            code, payload = self.upload('part.ipt', bytes.fromhex('D0CF11E0A1B11AE1') + b'part', 'step')
        self.assertEqual(code, 200, payload)
        part = json.loads(payload)
        self.assertEqual(part['sourceType'], 'inventor-part')
        self.assertEqual(part['layouts'], [])
        self.assertEqual(part['result']['mode'], 'inventor-native-part')
        self.assertEqual(part['result']['stats']['solids'], 1)
        self.assertTrue(self.call(part['result']['stepUrl'])[1].startswith(b'ISO-10303-21;'))

    # Exercise the same upload/generate/download route used by the whole-part UI.
    def test_axial_section_endpoint_returns_one_complete_solid(self):
        source = axial_drawing(Path(self.temp.name) / 'axial.dxf')
        code, payload = self.upload('axial.dxf', source.read_bytes())
        self.assertEqual(code, 200, payload)
        drawing = json.loads(payload)
        self.assertEqual(drawing['partCandidates'][0]['kind'], 'axial-section')
        params = {'partId': drawing['partCandidates'][0]['id'], 'mmPerUnit': 1, 'confirmed': True}
        code, payload = self.call(f"/api/drawings/{drawing['id']}/generate-part", json.dumps(params).encode())
        self.assertEqual(code, 200, payload)
        result = json.loads(payload)
        self.assertEqual(result['stats']['solids'], 1)
        self.assertEqual(result['stats']['featureCount'], 3)
        self.assertTrue(result['stats']['stepRoundTripVerified'])
        self.assertEqual(self.call(result['previewUrl'])[0], 200)
        self.assertTrue(self.call(result['stepUrl'])[1].startswith(b'ISO-10303-21;'))

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
