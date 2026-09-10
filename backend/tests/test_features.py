import math
import tempfile
import unittest
from pathlib import Path
import ezdxf
from backend.drawing import parse_dxf
from backend.features import build_features
from backend.app import FeaturesRequest

class FeatureTests(unittest.TestCase):
    def test_different_views_side_hole_and_added_boss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            doc=ezdxf.new()
            m=doc.modelspace()
            m.add_lwpolyline([(100,200),(120,200),(120,210),(100,210)],close=True)
            m.add_circle((300,400),2)
            doc.saveas(root/'arbitrary.dxf')
            drawing=parse_dxf(root/'arbitrary.dxf','arbitrary.dxf')
            layout=drawing['layouts'][0]
            rectangle=next(p for p in layout['profiles'] if p['outer']['type']=='polygon')
            circle=next(p for p in layout['profiles'] if p['outer']['type']=='circle')
            base={'layout':layout['name'],'profileId':rectangle['id'],'originU':100,'originV':200,'depthMm':10}
            side={'layout':layout['name'],'profileId':circle['id'],'originU':300,'originV':400,'plane':'XZ','positionX':10,'positionY':10,'positionZ':5,'depthMm':10,'combine':'cut'}
            boss={**side,'plane':'XY','positionY':5,'positionZ':10,'depthMm':3,'combine':'add'}
            params=FeaturesRequest(mmPerUnit=1,features=[base,side,boss],confirmed=True).model_dump()
            stats=build_features(drawing,params,root)
            self.assertEqual(stats['solids'],1)
            self.assertAlmostEqual(stats['volumeMm3'],2000-math.pi*4*10+math.pi*4*3,places=5)
            self.assertTrue(stats['stepRoundTripVerified'])
            params['features'][1]['positionX']=1000
            with self.assertRaisesRegex(ValueError,'未切到'):
                build_features(drawing,params,root)
            params['features']=[params['features'][0],{**params['features'][2],'positionX':1000}]
            with self.assertRaisesRegex(ValueError,'单实体'):
                build_features(drawing,params,root)
