import unittest
from unittest.mock import Mock
import pandas as pd
from research import create_trials, evaluate_trial, record_trials, settle_pending, summarize_research

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.observed=pd.Timestamp("2026-11-30T12:00:15Z")
        self.rows=create_trials("twelvedata","FOREX:EURUSD","2026-11-30T11:59Z",self.observed,"CALL",85,{"rsi":55})
        idx=pd.date_range("2026-11-30T12:01Z",periods=7,freq="min")
        p=[1+i*.0001 for i in range(7)]
        self.frame=pd.DataFrame({"open":p,"close":p,"high":p,"low":p},index=idx)
    def test_future_entry_and_two_expiries(self):
        self.assertEqual([r["expiration_minutes"] for r in self.rows],[1,5])
        self.assertGreater(pd.Timestamp(self.rows[0]["entry_at"]),self.observed)
    def test_no_lookahead_even_if_future_data_present(self):
        self.assertIsNone(evaluate_trial(self.rows[0],self.frame,"2026-11-30T12:02:59Z"))
        self.assertEqual(evaluate_trial(self.rows[0],self.frame,"2026-11-30T12:03Z")["status"],"ACERTO")
        self.assertIsNone(evaluate_trial(self.rows[1],self.frame,"2026-11-30T12:03Z"))
    def test_missing_exact_bar_never_substituted(self):
        f=self.frame.drop(self.frame.index[1])
        self.assertIsNone(evaluate_trial(self.rows[0],f,"2026-11-30T12:05Z"))
        self.assertEqual(evaluate_trial(self.rows[0],f,"2026-11-30T12:20Z")["status"],"SEM_DADOS")
    def test_bearish_result(self):
        row=dict(self.rows[0],direction="PUT")
        self.assertEqual(evaluate_trial(row,self.frame,"2026-11-30T12:05Z")["status"],"ERRO")
    def test_duplicate_insert_ignores_conflict(self):
        db=Mock()
        record_trials(self.rows,db)
        db.table.assert_called_once_with("pesquisa_sinais")
        self.assertTrue(db.table.return_value.upsert.call_args.kwargs["ignore_duplicates"])
    def test_settlement_queries_same_source_and_asset(self):
        db=Mock()
        q=db.table.return_value.select.return_value
        q.eq.return_value=q
        q.lte.return_value=q
        q.order.return_value=q
        q.limit.return_value=q
        q.execute.return_value.data=[]
        self.assertEqual(settle_pending("twelvedata","FOREX:EURUSD",self.frame,self.observed,db),0)
        q.eq.assert_any_call("provider","twelvedata")
        q.eq.assert_any_call("ativo","FOREX:EURUSD")
    def test_no_rate_without_decisive_samples(self):
        db=Mock()
        q=db.table.return_value.select.return_value
        q.eq.return_value=q
        q.execute.return_value.count=0
        self.assertIsNone(summarize_research("twelvedata","FOREX:EURUSD",client=db)[1]["taxa"])
