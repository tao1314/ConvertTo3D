"""Verify section reconstruction with independent geometry and the local nozzle DWG."""

import math
from pathlib import Path
import tempfile
import unittest

import ezdxf
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT

from backend.drawing import convert_dwg, parse_dxf
from backend.modeling import build_multiview, solid_stats

SAMPLE = Path('C:/Users/86152/Desktop/测试转换三维文件/喷嘴-删除内容测试版.dwg')


# Draw a different-sized annular body with two explicitly sectioned blind holes.
def axial_drawing(target, shift=0, missing_hole=False, asymmetric=False):
    doc = ezdxf.new('R2010')
    doc.header['$INSUNITS'] = 4
    doc.layers.new('CENTER')
    model = doc.modelspace()
    outline = [(0, 3), (12, 3), (12, 20), (0, 20), (0, 12),
               (5, 12), (6, 10), (5, 8), (0, 8)]
    cavity = [(0, 8), (5, 8), (6, 10), (5, 12), (0, 12)]
    for sign in (1, -1):
        for points in (outline, cavity):
            model.add_lwpolyline([(x + shift, sign * y + shift
                                  - (1 if asymmetric and sign == -1 and y == 3 else 0))
                                 for x, y in points], close=True)
    model.add_line((shift - 1, shift), (shift + 13, shift), dxfattribs={'layer': 'CENTER'})
    model.add_circle((shift + 50, shift), 20)
    model.add_circle((shift + 50, shift), 3)
    model.add_circle((shift + 50, shift + 10), 2)
    if not missing_hole:
        model.add_circle((shift + 50, shift - 10), 2)
    model.add_linear_dim(base=(shift, shift - 25), p1=(shift, shift),
                         p2=(shift + 12, shift), angle=0).render()
    doc.saveas(target)
    return target


class AxialTests(unittest.TestCase):
    # Isolate generated CAD artifacts between tests.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    # Release only this test's temporary outputs.
    def tearDown(self):
        self.temp.cleanup()

    # Inspect the exported solid rather than only the in-memory result.
    def read_solid(self):
        reader = STEPControl_Reader()
        reader.ReadFile(str(self.path / 'model.step'))
        reader.TransferRoots()
        return reader.OneShape()

    # Prove the blind-hole floor and the material outside the hole meridian survive.
    def test_translated_section_volume_and_blind_hole_floor(self):
        source = axial_drawing(self.path / 'unrelated-name.dxf', shift=137)
        drawing = parse_dxf(source, 'unrelated-name.dxf')
        self.assertEqual(len(drawing['partCandidates']), 1)
        part = drawing['partCandidates'][0]
        stats = build_multiview(part, {'mmPerUnit': 1}, self.path)
        self.assertEqual(stats['solids'], 1)
        self.assertTrue(stats['stepRoundTripVerified'])
        expected = math.pi * ((20**2 - 3**2) * 12 - 2 * 2**2 * (5 + 1 / 3))
        self.assertAlmostEqual(stats['volumeMm3'], expected, places=5)
        shape = self.read_solid()
        for coords, expected_state in [((2, 10, 0), TopAbs_OUT), ((7, 10, 0), TopAbs_IN),
                                       ((2, 0, 10), TopAbs_IN), ((2, 0, 0), TopAbs_OUT)]:
            self.assertEqual(BRepClass3d_SolidClassifier(shape, gp_Pnt(*coords), 1e-6).State(), expected_state)
        scaled = build_multiview(part, {'mmPerUnit': 2}, self.path)
        self.assertAlmostEqual(scaled['volumeMm3'], stats['volumeMm3'] * 8, places=4)

    # Reject unexplained section cavities instead of silently filling a missing hole.
    def test_missing_end_view_hole_is_rejected(self):
        drawing = parse_dxf(axial_drawing(self.path / 'missing.dxf', missing_hole=True), 'missing.dxf')
        self.assertEqual(drawing['partCandidates'], [])

    # Axis dimensions are necessary evidence for automatic reconstruction.
    def test_missing_dimension_is_rejected(self):
        source = axial_drawing(self.path / 'no-dim.dxf')
        doc = ezdxf.readfile(source)
        for entity in list(doc.modelspace().query('DIMENSION')):
            doc.modelspace().delete_entity(entity)
        doc.saveas(source)
        self.assertEqual(parse_dxf(source, 'no-dim.dxf')['partCandidates'], [])

    # An asymmetric bore must not be guessed from only its upper half.
    def test_asymmetric_section_is_rejected(self):
        source = axial_drawing(self.path / 'asymmetric.dxf', asymmetric=True)
        self.assertEqual(parse_dxf(source, 'asymmetric.dxf')['partCandidates'], [])

    # Use the actual DWG when present, including conversion and exported point classification.
    @unittest.skipUnless(SAMPLE.exists(), 'User DWG is local only')
    def test_actual_nozzle_is_one_solid_with_groove_bore_and_blind_holes(self):
        target = self.path / 'converted.dxf'
        convert_dwg(SAMPLE, target)
        drawing = parse_dxf(target, 'renamed.dwg')
        self.assertEqual(len(drawing['partCandidates']), 1)
        part = drawing['partCandidates'][0]
        self.assertEqual(part['kind'], 'axial-section')
        self.assertAlmostEqual(part['totalLength'], 15)
        self.assertEqual([h['diameter'] for h in part['holes']], [5.5, 5.5])
        stats = build_multiview(part, {'mmPerUnit': 1}, self.path)
        self.assertTrue(stats['stepRoundTripVerified'])
        shape = self.read_solid()
        self.assertEqual(solid_stats(shape)['solids'], 1)
        for coords, expected_state in [((2, 19, 0), TopAbs_OUT), ((9, 19, 0), TopAbs_IN),
                                       ((2, 0, 19), TopAbs_IN), ((10.5, 22, 0), TopAbs_OUT),
                                       ((13, 22, 0), TopAbs_IN), ((5, 0, 0), TopAbs_OUT),
                                       ((5, -19, 0), TopAbs_OUT), ((9, -19, 0), TopAbs_IN)]:
            self.assertEqual(BRepClass3d_SolidClassifier(shape, gp_Pnt(*coords), 1e-6).State(), expected_state)
