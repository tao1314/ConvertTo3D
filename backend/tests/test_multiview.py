import json
import math
from pathlib import Path
import tempfile
import unittest

from OCP.STEPControl import STEPControl_Reader
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.gp import gp_Pnt
from backend.drawing import parse_dxf, ROOT
from backend.modeling import build_multiview
from backend.tests.fixtures import endcap_drawing


class MultiViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_pair_views_form_one_stepped_part_with_eight_holes(self):
        drawing = parse_dxf(endcap_drawing(self.path/'fixture.dxf', shift=72), 'fixture.dxf')
        self.assertEqual(len(drawing['partCandidates']), 1)
        part = drawing['partCandidates'][0]
        self.assertEqual(part['totalLength'], 30)
        self.assertEqual(len(part['holes']), 8)
        stats = build_multiview(part, {'mmPerUnit': 1, 'threadMode': 'nominal-through'}, self.path)
        expected = math.pi*(55**2*10 + 37.5**2*20 - 27.5**2*5 - 30**2*25 - 4*6.25**2*10 - 4*2.5**2*30)
        self.assertAlmostEqual(stats['volumeMm3'], expected, places=4)
        self.assertEqual(stats['solids'], 1)
        self.assertEqual(stats['featureCount'], 12)
        reader = STEPControl_Reader()
        reader.ReadFile(str(self.path/'model.step'))
        reader.TransferRoots()
        solid = reader.OneShape()
        # Independent spatial checks: flange, hub, stepped bore, both hole sets.
        def state(x,y,z):
            return BRepClass3d_SolidClassifier(solid, gp_Pnt(x,y,z), 1e-6).State()
        self.assertEqual(state(40,10,5), TopAbs_IN)
        self.assertEqual(state(40,10,20), TopAbs_OUT)
        self.assertEqual(state(33,0,20), TopAbs_IN)
        self.assertEqual(state(29,0,2), TopAbs_IN)
        self.assertEqual(state(29,0,8), TopAbs_OUT)
        self.assertEqual(state(0,45,5), TopAbs_OUT)
        self.assertEqual(state(24,24,20), TopAbs_OUT)

    def test_single_view_is_not_treated_as_complete_part(self):
        drawing = parse_dxf(endcap_drawing(self.path/'front.dxf', missing_side=True), 'front.dxf')
        self.assertEqual(drawing['partCandidates'], [])

    def test_omitting_threads_is_explicit_and_changes_volume(self):
        drawing = parse_dxf(endcap_drawing(self.path/'fixture.dxf'), 'fixture.dxf')
        stats = build_multiview(drawing['partCandidates'][0], {'mmPerUnit': 1, 'threadMode': 'omit'}, self.path)
        expected = math.pi*(55**2*10 + 37.5**2*20 - 27.5**2*5 - 30**2*25 - 4*6.25**2*10)
        self.assertAlmostEqual(stats['volumeMm3'], expected, places=4)
        self.assertEqual(stats['featureCount'], 8)

    @unittest.skipUnless((ROOT/'runtime/endcap/converted.dxf').exists(), 'User sample is local only')
    def test_real_endcap_and_dimension_override(self):
        drawing = parse_dxf(ROOT/'runtime/endcap/converted.dxf', 'Drawing1.dwg')
        part = drawing['partCandidates'][0]
        self.assertEqual(len(drawing['partCandidates']), 1)
        self.assertEqual(len(part['holes']), 8)
        self.assertTrue(part['dimensionNotes'])
        self.assertEqual({h['y'] for h in part['holes'] if h['thread']}, {-24,24})
        x_values = [h['x'] for h in part['holes'] if h['thread']]
        self.assertAlmostEqual(max(x_values)-min(x_values), math.sqrt(67.5**2-48**2), places=5)
        aligned = next(a for a in drawing['layouts'][0]['annotations'] if a.get('dimensionType') == 1)
        self.assertAlmostEqual(aligned['measurement'], 67.5, places=5)
        self.assertEqual([s['radius'] for s in part['innerStages']], [27.5,30])
