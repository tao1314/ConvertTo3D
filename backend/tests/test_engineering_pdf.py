"""Verify actual section material and dimension accuracy in engineering PDFs."""

import math
from pathlib import Path
import tempfile
import unittest

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from pypdf import PdfReader
from shapely.geometry import Point

from backend.engineering_pdf import generate_pdf, read_model, section
from backend.modeling import export_solid
from backend.pdf_routes import PdfSettings


class EngineeringPdfTests(unittest.TestCase):
    # Construct a known hollow part whose section area can be checked independently.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        part = BRepAlgoAPI_Cut(BRepPrimAPI_MakeCylinder(10, 30).Shape(),
                              BRepPrimAPI_MakeCylinder(4, 30).Shape()).Shape()
        export_solid(part, self.directory)
        self.source = self.directory / 'model.step'

    # Remove only the temporary artifacts created by this test.
    def tearDown(self):
        self.temp.cleanup()

    # Ensure a cavity stays unhatched and the cross section matches the known ring area.
    def test_sections_preserve_hole_and_material_area(self):
        shape, axis = read_model(self.source, 'auto', 0)
        self.assertEqual(axis, 'z')
        cross = section(shape, 'x', 0)
        self.assertAlmostEqual(sum(p.area for p in cross['polygons']), math.pi * (100 - 16), delta=1.0)
        self.assertFalse(any(p.contains(Point(0, 0)) for p in cross['polygons']))
        longitudinal = section(shape, 'z', 0)
        self.assertEqual(len(longitudinal['polygons']), 2)
        self.assertAlmostEqual(sum(p.area for p in longitudinal['polygons']), 360, places=4)

    # Check real PDF output, title metadata and dimensions measured from geometry.
    def test_vector_pdf_contains_measurements_and_user_fields(self):
        target = self.directory / 'drawing.pdf'
        report = generate_pdf(self.source, target, PdfSettings(title='测试套筒', material='用户材料').model_dump())
        pdf = PdfReader(target)
        self.assertEqual(len(pdf.pages), 1)
        text = pdf.pages[0].extract_text()
        for expected in ('测试套筒', '用户材料', '30.00', '20.00', 'Ø8.00', 'A-A', 'B-B'):
            self.assertIn(expected, text)
        self.assertEqual(len(pdf.pages[0].images), 0)
        self.assertEqual(report['views'], 4)
        self.assertAlmostEqual(report['dimensionsMm'][0], 30, places=5)

    # Do not silently shrink a requested scale or fabricate sections outside the model.
    def test_unusable_scale_and_section_are_rejected(self):
        for settings in (PdfSettings(scale=10), PdfSettings(sectionOffset=100)):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                generate_pdf(self.source, self.directory / 'invalid.pdf', settings.model_dump())
