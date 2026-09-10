import math
from pathlib import Path
import tempfile
import unittest

import ezdxf

from backend.drawing import parse_dxf, convert_dwg, ROOT
from backend.modeling import build_model


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self, create):
        doc = ezdxf.new('R2010')
        doc.header['$INSUNITS'] = 4
        create(doc.modelspace())
        filename = self.directory / 'test.dxf'
        doc.saveas(filename)
        return parse_dxf(filename, 'test.dxf')['layouts'][0]

    def params(self, **changes):
        return {'operation': 'extrude', 'depthMm': 5, 'mmPerUnit': 1,
                'axis': 'y', 'axisOffset': 0, 'angleDeg': 360, **changes}

    def test_annular_extrusion_preserves_exact_circles_and_hole(self):
        layout = self.parse(lambda m: (m.add_circle((0, 0), 10), m.add_circle((0, 0), 4)))
        ring = next(p for p in layout['profiles'] if p['holes'])
        self.assertEqual(ring['outer']['type'], 'circle')
        self.assertEqual(ring['holes'][0]['type'], 'circle')
        stats = build_model(ring, self.params(), self.directory)
        self.assertAlmostEqual(stats['volumeMm3'], math.pi*(100-16)*5, places=5)
        self.assertTrue(stats['stepRoundTripVerified'])

    def test_rectangle_revolution_volume_and_axis_rejection(self):
        layout = self.parse(lambda m: m.add_lwpolyline([(2, 0), (5, 0), (5, 10), (2, 10)], close=True))
        profile = layout['profiles'][0]
        stats = build_model(profile, self.params(operation='revolve'), self.directory)
        self.assertAlmostEqual(stats['volumeMm3'], math.pi*(25-4)*10, places=5)
        with self.assertRaisesRegex(ValueError, '旋转轴'):
            build_model(profile, self.params(operation='revolve', axisOffset=3), self.directory)

    def test_open_lines_do_not_become_fake_closed_profile(self):
        layout = self.parse(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((10, 0), (10, 10))))
        self.assertEqual(layout['profiles'], [])

    def test_nonplanar_excluded_and_dimensions_separate(self):
        def create(m):
            m.add_lwpolyline([(0,0),(10,0),(10,10),(0,10)], close=True, dxfattribs={'elevation': 5})
            m.add_text('10 mm')
        layout = self.parse(create)
        self.assertEqual(layout['profiles'], [])
        self.assertEqual(layout['nonPlanarCount'], 1)
        self.assertEqual(layout['annotations'][0]['text'], '10 mm')

    def test_units_change_volume_cubically(self):
        layout = self.parse(lambda m: m.add_lwpolyline([(0,0),(2,0),(2,3),(0,3)], close=True))
        stats = build_model(layout['profiles'][0], self.params(mmPerUnit=10, depthMm=40), self.directory)
        self.assertAlmostEqual(stats['volumeMm3'], 20*30*40, places=5)

    def test_nested_block_geometry_is_transformed(self):
        doc = ezdxf.new('R2010')
        block = doc.blocks.new('outline')
        block.add_lwpolyline([(0,0),(2,0),(2,3),(0,3)], close=True)
        doc.modelspace().add_blockref('outline', (10,20))
        filename = self.directory / 'block.dxf'
        doc.saveas(filename)
        result = parse_dxf(filename, 'block.dxf')
        self.assertEqual(result['layouts'][0]['profiles'][0]['bounds'], [10,20,12,23])

    @unittest.skipUnless((ROOT/'runtime/sample/source.dwg').is_file(), 'Local user sample is not checked into git')
    def test_real_user_dwg(self):
        target = self.directory / 'sample.dxf'
        convert_dwg(ROOT/'runtime/sample/source.dwg', target)
        drawing = parse_dxf(target, 'sample.dwg', 'AC1015')
        layout = drawing['layouts'][0]
        self.assertEqual(layout['entityCounts'], {'LWPOLYLINE': 3, 'SPLINE': 14, 'LINE': 4})
        self.assertEqual(drawing['insunits'], 4)
        self.assertEqual(layout['annotations'], [])
        self.assertGreater(len(layout['profiles']), 0)


if __name__ == '__main__':
    unittest.main()
