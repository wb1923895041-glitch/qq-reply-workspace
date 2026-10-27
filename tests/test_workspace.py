import tempfile
import unittest
from workspace import Workspace

class WorkspaceTest(unittest.TestCase):
    def test_persona_binding_and_disable(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workspace(d)
            p=w.save_persona({'name':'友善','prompt':'简短回应'})
            w.save_chat({'id':'1234','name':'群一','persona_id':p['id'],'enabled':True})
            self.assertEqual(w.resolve('1234',{'persona':'默认'})['persona'],'简短回应')
            self.assertIsNone(w.resolve('1235',{'persona':'默认'}))
            with self.assertRaises(ValueError): w.delete_persona({'id':p['id']})
            w.save_chat({'id':'1234','name':'群一','persona_id':'','enabled':False})
            self.assertIsNone(w.resolve('1234',{'persona':'默认'}))
            w.delete_persona({'id':p['id']})
            self.assertEqual(w.read()['personas'],[])
    def test_rejects_invalid_and_unknown_persona(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workspace(d)
            with self.assertRaises(ValueError): w.save_chat({'id':'a','enabled':True})
            with self.assertRaises(ValueError): w.save_chat({'id':'123','enabled':True,'persona_id':'nope'})
            self.assertEqual(w.read()['chats'],[])

if __name__=='__main__': unittest.main()
