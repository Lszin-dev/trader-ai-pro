import unittest
from dataset_export import prepare_rows
class DatasetTests(unittest.TestCase):
    def test_chronological_split_excludes_overlap_and_unusable_outcomes(self):
        def row(observed,target,status="ACERTO"):
            return {"observed_at":observed,"target_at":target,"status":status,"features":{"metrics":{"rsi_1m":55}},"score":85}
        rows=[
          row("2026-11-30T09:50Z","2026-11-30T09:55Z"),
          row("2026-11-30T09:58Z","2026-11-30T10:03Z"),
          row("2026-11-30T10:01Z","2026-11-30T10:07Z","ERRO"),
          row("2026-11-30T10:02Z","2026-11-30T10:08Z","SEM_DADOS")
        ]
        data=prepare_rows(rows,"2026-11-30T10:00Z")
        self.assertEqual([(r["split"],r["label"]) for r in data],[("train",1),("test",0)])
        self.assertEqual(data[0]["rsi_1m"],55)
        self.assertNotIn("final_price",data[0])
