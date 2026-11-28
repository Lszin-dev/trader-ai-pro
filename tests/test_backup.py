import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from cryptography.fernet import Fernet, InvalidToken
from backup import FORMAT, collect, seal, verify, write_encrypted, upload_verified

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key()
        self.payload = {"format":FORMAT, "completed_at":"2026-11-28T15:00:00Z",
                        "tables":{"historico_sinais":[{"id":1}], "monitoramento_estado":[]},
                        "counts":{"historico_sinais":1,"monitoramento_estado":0}}
    def test_round_trip_and_wrong_key(self):
        token=seal(self.payload,self.key)
        self.assertEqual(verify(token,self.key)["counts"],self.payload["counts"])
        with self.assertRaises(InvalidToken):
            verify(token,Fernet.generate_key())
    def test_tamper_detected(self):
        token=bytearray(seal(self.payload,self.key))
        token[30]=65 if token[30]!=65 else 66
        with self.assertRaises(InvalidToken): verify(bytes(token),self.key)
    def test_duplicate_rejected(self):
        self.payload["tables"]["historico_sinais"].append({"id":1})
        self.payload["counts"]["historico_sinais"]=2
        with self.assertRaises(ValueError): seal(self.payload,self.key)
    def test_file_is_encrypted_and_verifiable(self):
        with tempfile.TemporaryDirectory() as folder:
            token=seal(self.payload,self.key)
            path=write_encrypted(token,folder)
            self.assertEqual(Path(path).read_bytes(),token)
            self.assertEqual(verify(path.read_bytes(),self.key)["counts"],self.payload["counts"])
    def test_cloud_readback(self):
        token=seal(self.payload,self.key)
        s3=Mock()
        body=Mock()
        body.iter_chunks.return_value=[token]
        s3.get_object.return_value={"Body":body}
        self.assertEqual(len(upload_verified(s3,"private","backup",token)),64)
        self.assertEqual(s3.put_object.call_args.kwargs["Body"],token)
        body.iter_chunks.return_value=[b"corrupted"]
        with self.assertRaises(RuntimeError): upload_verified(s3,"private","backup",token)
    def test_collect_read_only(self):
        db=Mock()
        q=db.table.return_value.select.return_value
        q.order.return_value=q
        q.range.return_value=q
        q.execute.return_value.count=0
        payload=collect(db,include_research=False)
        self.assertEqual(payload["counts"],{"historico_sinais":0,"monitoramento_estado":0})
        self.assertNotIn("delete",str(db.mock_calls))
        self.assertNotIn("insert",str(db.mock_calls))
