import unittest
from unittest.mock import patch
import app

class RulesTest(unittest.TestCase):
    def test_mentions(self):
        self.assertTrue(app.mentioned('@小明 你好', '小明'))
        self.assertTrue(app.mentioned('＠ 小明！', '小明'))
        self.assertFalse(app.mentioned('@小明123', '小明'))
        self.assertFalse(app.mentioned('你好', '小明'))
        self.assertFalse(app.mentioned('@小明', ''))
    def test_validation_rejects_invalid_environment_name(self):
        with self.assertRaises(ValueError): app.save_config({'model':'deepseek-v4-pro','key_env':'BAD KEY'})
    def test_config_defaults(self):
        with patch.object(app, 'CONFIG') as path:
            path.exists.return_value = False
            self.assertEqual(app.load_config()['mention'], '')

if __name__ == '__main__': unittest.main()
