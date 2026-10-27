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

    def test_same_number_private_and_group_are_separate(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workspace(d)
            w.save_chat({'id':'1234','kind':'group','name':'群','enabled':True})
            w.save_chat({'id':'1234','kind':'private','name':'好友','enabled':True})
            self.assertEqual(len(w.read()['chats']),2)
            w.delete_chat({'id':'1234','kind':'private'})
            self.assertEqual(w.read()['chats'][0]['kind'],'group')
            with self.assertRaises(ValueError): w.save_chat({'id':'0001','kind':'private','enabled':True})
            with self.assertRaises(ValueError): w.save_chat({'id':'9007199254740992','kind':'group','enabled':True})

if __name__=='__main__': unittest.main()
