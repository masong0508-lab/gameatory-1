"""ROM-free classification guards for near-neutral PS1 city scenes."""
from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from payback import view_state, measures


class ViewStateTests(unittest.TestCase):
    def test_black_and_fade_stay_distinct(self):
        self.assertEqual(view_state(Image.new('RGB', (320, 224), (0, 0, 0))), 'black')
        self.assertEqual(view_state(Image.new('RGB', (320, 224), (255, 255, 255))), 'white')

    def test_flat_gray_menu_is_not_a_city(self):
        im = Image.new('RGB', (320, 224), (105, 105, 105))
        self.assertEqual(view_state(im), 'menu')

    def test_pale_world_with_few_colored_patches_is_a_city(self):
        im = Image.new('RGB', (320, 224), (120, 121, 123))
        im.paste((75, 135, 180), (8, 50, 27, 194))
        lit, white, chroma = measures(im)
        self.assertGreater(lit, 0.9)
        self.assertLess(chroma, 0.105)
        self.assertGreater(chroma, 0.02)
        self.assertEqual(view_state(im), 'city')

    def test_shaded_world_with_mild_chroma_is_a_city(self):
        im = Image.new('RGB', (320, 224), (57, 65, 60))
        im.paste((100, 140, 165), (4, 4, 36, 180))
        self.assertEqual(view_state(im), 'city')

    def test_saturated_original_city_rule_still_works(self):
        im = Image.new('RGB', (320, 224), (80, 135, 90))
        im.paste((0, 0, 0), (0, 0, 320, 22))
        self.assertEqual(view_state(im), 'city')

    def test_dark_menu_with_colored_accent_stays_dark(self):
        im = Image.new('RGB', (320, 224), (10, 10, 10))
        im.paste((90, 140, 160), (0, 0, 40, 224))
        self.assertEqual(view_state(im), 'dark')


if __name__ == '__main__':
    unittest.main()
