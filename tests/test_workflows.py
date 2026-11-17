from pathlib import Path
import tempfile
import unittest
from app.journal import Journal
from app.storage import DataError,Store

DATA=Path(__file__).parents[1]/'data'


class BusinessChainTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(DATA)
        self.journal=Journal()

    def tearDown(self):
        self.journal.close()

    def test_business_chain(self):
        self.exercise(self.store,self.journal)

    def test_rollback_on_failure(self):
        with self.assertRaises(DataError):
            with self.journal.transaction():
                self.journal.put('test','a',{'value':1})
                raise DataError('aborted')
        self.assertEqual(self.journal.all('test'),[])

    def test_restart_retains_business_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'workflow.sqlite3'
            journal=Journal(path)
            try:
                self.exercise(self.store,journal)
                before={kind[0] for kind in journal.connection.execute('SELECT DISTINCT kind FROM documents')}
                snapshot={kind:journal.all(kind) for kind in before}
            finally:
                journal.close()
            reopened=Journal(path)
            try:
                self.assertEqual(snapshot,{kind:reopened.all(kind) for kind in before})
            finally:
                reopened.close()

    def exercise(self,store,journal):
        from app import targets,followups,deliveries
        assessment=targets.evaluate(store,journal,dict(assessment='e1',view='weekly-east'))
        self.assertTrue(assessment['below_target'])
        case=followups.assign(store,journal,dict(assessment='e1'))
        delivery=deliveries.prepare(store,journal,dict(assessment='e1',delivery='d1'))
        self.assertEqual(delivery['followups'][0]['case'],case['case'])
        followups.close(store,journal,dict(case='C1',owner='east'))
        self.assertEqual(followups.assign(store,journal,dict(assessment='e1'))['status'],'closed')
