import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as manager

qt = manager.QApplication.instance() or manager.QApplication([])


class PresentationTests(unittest.TestCase):
    def bounds(self, width, height):
        image = manager.QImage(width, height, manager.QImage.Format.Format_RGB32)
        image.fill(manager.QColor('#ff0000'))
        canvas = manager.fitted_thumbnail(image, manager.QSize(238, 176)).toImage()
        pixels = [(x, y) for y in range(canvas.height()) for x in range(canvas.width())
                  if canvas.pixelColor(x, y).red() > 240]
        return (max(x for x, y in pixels) - min(x for x, y in pixels) + 1,
                max(y for x, y in pixels) - min(y for x, y in pixels) + 1)

    def test_portrait_thumbnail_keeps_ratio_and_side_padding(self):
        self.assertEqual(self.bounds(200, 400), (88, 176))

    def test_landscape_thumbnail_keeps_ratio_and_letterboxing(self):
        width, height = self.bounds(400, 100)
        self.assertEqual(width, 238)
        self.assertLessEqual(abs(width / height - 4), .08)

    def test_video_badge_uses_fixed_canvas(self):
        image = manager.QImage(100, 200, manager.QImage.Format.Format_RGB32)
        image.fill(manager.QColor('#cccccc'))
        icon = manager.QIcon(manager.fitted_thumbnail(image, manager.QSize(238, 176), True, 28000))
        self.assertEqual(icon.pixmap(238, 176).size(), manager.QSize(238, 176))

    def test_time_picker_disables_empty_months_and_selects_whole_year(self):
        picker = manager.TimePicker({'2024-06': 5, '2026-10': 12}, '2024-06')
        self.assertEqual(picker.year.currentData(), '2024')
        self.assertTrue(picker.months[5].isEnabled())
        self.assertFalse(picker.months[0].isEnabled())
        self.assertTrue(picker.months[5].isChecked())
        chosen = []
        picker.chosen.connect(chosen.append)
        picker.choose_year()
        self.assertEqual(chosen, ['2024'])

    def test_time_picker_empty_library(self):
        picker = manager.TimePicker({})
        self.assertFalse(picker.whole_year.isEnabled())
        self.assertTrue(all(not b.isEnabled() for b in picker.months))


if __name__ == '__main__':
    unittest.main()
