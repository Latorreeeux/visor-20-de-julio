"""Prueba de integración con los archivos oficiales incluidos, sin red."""

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def test_offline_start_filters_and_nearby(self):
        with patch("visor.datos.urlopen", side_effect=AssertionError("Arranque debe ser local")):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            initial = int(app.metric[0].value)
            self.assertGreater(initial, 0)
            self.assertGreater(int(app.metric[2].value), 0)
            places = app.dataframe[0].value
            pharmacies = places.loc[places["categoría"] == "Droguerías"]
            self.assertFalse(pharmacies["nombre"].isin(["4444", "8888"]).any())
            unnamed = pharmacies.loc[pharmacies["nombre"] == "Sin nombre informado"]
            self.assertIn("CL 27 SUR 8 06", unnamed["dirección"].tolist())
            app.sidebar.checkbox[0].uncheck().run()
            self.assertEqual(len(app.exception), 0)
            self.assertLess(int(app.metric[0].value), initial)
            self.assertEqual(int(app.metric[2].value), 0)
            app.text_input[0].set_value("CAI").run()
            self.assertEqual(len(app.exception), 0)
            self.assertGreater(int(app.metric[0].value), 0)


if __name__ == "__main__":
    unittest.main()
