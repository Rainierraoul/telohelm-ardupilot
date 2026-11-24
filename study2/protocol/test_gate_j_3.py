"""Build J (ruling 58): the two findings of the review of build G.

J1  a provider row with no spending row and no list cost makes the spend a known subtotal and a count of calls of unknown cost
J2  provider rows and spending rows pair one to one by request id

They use the gate's real fixture and the helpers of test_gate_e1_3 and test_gate_g_3. No model, simulator or network is used.
"""
import json
import unittest

from protocol import test_protocol3 as T
from protocol import test_gate_e1_3 as E
from protocol import test_gate_g_3 as G
from protocol import test_split3 as S
from protocol import contract3 as C
from protocol import validate3 as V
from protocol.set_aside3 import set_aside_dir


def setUpModule():
    T.setUpModule()


def tearDownModule():
    T.tearDownModule()


def gateway_run(case):
    root, gate = E.fresh(case)
    E.provider_log(root, via='gem')
    E.name_gateway(root)
    return root, gate


def register(root, message_id, block):
    with open(root / 'message-ids.jsonl', 'a') as f:
        f.write(json.dumps({'message_id': message_id, 'block': block}) + '\n')


def aside_block_with_one_spending_row(root, provider_rows):
    """A set-aside folder with one spending row (call id 'x1', copied from a real row) and the given provider rows."""
    learn = E.learn_folders(root)[0]
    folder = set_aside_dir(root) / f'{learn.name}-attempt1' / learn.name
    folder.mkdir(parents=True)
    spending = json.loads((learn / 'usage.jsonl').read_text().splitlines()[0])
    spending['call_id'] = 'x1'
    (folder / 'usage.jsonl').write_text(json.dumps(spending) + '\n')
    (folder / 'claude-usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in provider_rows))
    for r in provider_rows:
        if r.get('message_id'):
            register(root, r['message_id'], learn.name)
    return folder


def aside_provider_rows(case, root, rows):
    """Provider rows only, in a set-aside block; the ids they carry are in the run's file of ids."""
    folder = G.LedgerPairing.aside_provider_rows(case, root, rows)
    for r in rows:
        if r.get('message_id'):
            register(root, r['message_id'], folder.name)
    return folder


def provider_row(request_id, message_id, **more):
    return {'request_id': request_id, 'via': 'gem', 'gateway_cache': E.CACHE, 'model': 'synthetic-fixture', 'status': 'end_turn',
            'cost_usd': 0.004, 'message_id': message_id, 'charged_usd': None, **more}


class UnpricedUnpairedRow(unittest.TestCase):
    """J1."""

    def timed_out(self, n=1):
        """The reviewer's row: cut off before usage arrived, so no price, no message id and no charge."""
        row = provider_row(f'cut-{n}', None, status='timeout', cost_usd=None)
        row.pop('cost_usd')
        return row

    def test_the_gate_reports_one_call_of_unknown_cost_and_a_known_subtotal(self):
        root, gate = gateway_run(self)
        aside_provider_rows(self, root, [self.timed_out(), provider_row('cut-2', 'msg_cut_2')])
        report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['provider_rows_with_no_spending_row'],
                         {'count': 2, 'list_cost_usd': 0.004, 'charged_usd': 0.0, 'rows_with_charge': 0, 'rows_without_list_cost': 1})
        self.assertEqual(snap['gate']['provider_rows_with_no_spending_row']['rows_without_list_cost'], 1)

    def test_the_analysis_does_not_add_the_unknown_as_zero(self):
        from protocol import analysis3 as A
        root, gate = gateway_run(self)
        aside_provider_rows(self, root, [self.timed_out()])
        report, snap = V.load_run(root, **gate)
        for tasks in snap['learning'].values():
            for learn in tasks.values():
                for usage_row in learn['usage']:
                    usage_row['list_cost_usd'] = 0.001
        result = A.analyse_snapshot(snap, n_boot=30)
        spend = result['secondary']['spend']
        self.assertIsNone(spend['unique_plus_set_aside_list_cost_usd'])
        self.assertAlmostEqual(spend['unique_plus_set_aside_known_subtotal_usd'], spend['unique']['list_cost_usd'])
        self.assertGreater(spend['unique_plus_set_aside_known_subtotal_usd'], 0)
        self.assertEqual(spend['unique_plus_set_aside_calls_of_unknown_cost'], 1)
        text = '\n'.join(A.report_lines(result))
        self.assertIn('Known subtotal US$0.0', text)
        self.assertIn('; 1 calls of unknown cost (a call with no price', text)
        self.assertIn('Together, with the list cost of the provider rows that have no spending row: not known.', text)
        json.dumps(result)

    def test_calls_of_unknown_cost_also_count_the_calls_of_the_spending_ledger_with_no_price(self):
        from protocol import analysis3 as A
        root, gate = gateway_run(self)
        aside_provider_rows(self, root, [self.timed_out()])
        report, snap = V.load_run(root, **gate)
        first = next(iter(next(iter(snap['learning'].values())).values()))['usage'][0]
        first['list_cost_usd'] = None                                              # one spending row with no price
        spend = A.analyse_snapshot(snap, n_boot=30)['secondary']['spend']
        ledger = spend['unique']['calls'] - spend['unique']['list_cost_usd_calls_known']
        self.assertEqual(ledger, 1)
        self.assertEqual(spend['unique_plus_set_aside_calls_of_unknown_cost'], ledger + 1)

    def test_known_cases_are_unchanged(self):
        from protocol import analysis3 as A
        root, gate = gateway_run(self)
        aside_provider_rows(self, root, [provider_row('cut-1', 'msg_cut_1'), provider_row('cut-2', 'msg_cut_2')])
        report, snap = V.load_run(root, **gate)
        self.assertEqual(report['provider_rows_with_no_spending_row']['rows_without_list_cost'], 0)
        for tasks in snap['learning'].values():
            for learn in tasks.values():
                for usage_row in learn['usage']:
                    usage_row['list_cost_usd'] = 0.001
        spend = A.analyse_snapshot(snap, n_boot=30)['secondary']['spend']
        self.assertAlmostEqual(spend['unique_plus_set_aside_list_cost_usd'], spend['unique']['list_cost_usd'] + 0.008, places=9)
        self.assertEqual(spend['unique_plus_set_aside_calls_of_unknown_cost'], 0)


class KnownSubtotalKeepsEveryKnownPrice(unittest.TestCase):
    """L1 (review of part J, finding 1)."""

    def test_five_priced_calls_one_unpriced_call_and_an_unpriced_unpaired_row(self):
        from protocol import analysis3 as A
        root, gate = gateway_run(self)
        row = {'request_id': 'cut-1', 'via': 'gem', 'gateway_cache': E.CACHE, 'model': 'synthetic-fixture', 'status': 'timeout',
               'message_id': None, 'charged_usd': None}
        aside_provider_rows(self, root, [row])
        report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        rows = [r for tasks in snap['learning'].values() for learn in tasks.values() for r in learn['usage']]
        self.assertEqual(len(rows), 6)
        for r in rows[:5]:
            r['list_cost_usd'] = 0.001
        rows[5]['list_cost_usd'] = None
        spend = A.analyse_snapshot(snap, n_boot=30)['secondary']['spend']
        self.assertIsNone(spend['unique']['list_cost_usd'])
        self.assertAlmostEqual(spend['unique']['list_cost_usd_known_subtotal'], 0.005, places=9)
        self.assertAlmostEqual(spend['unique_plus_set_aside_known_subtotal_usd'], 0.005, places=9)
        self.assertEqual(spend['unique_plus_set_aside_calls_of_unknown_cost'], 2)
        self.assertIsNone(spend['unique_plus_set_aside_list_cost_usd'])


class OneToOnePairing(unittest.TestCase):
    """J2."""

    def test_a_second_provider_row_with_the_same_request_id_in_a_kept_block_is_refused(self):
        root, gate = gateway_run(self)
        learn = E.learn_folders(root)[0]
        E.rewrite_rows(learn, lambda rows: rows.append({**rows[0], 'message_id': 'msg_second', 'cost_usd': 0.004}))
        register(root, 'msg_second', learn.name)
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'], 'the gate accepted two provider rows for one spending row')
        self.assertIn('in a kept block have no spending row', report['errors'][0])
        self.assertIn('1 provider rows', report['errors'][0])

    def test_the_same_in_a_set_aside_block_is_counted_and_costed_once(self):
        root, gate = gateway_run(self)
        aside_block_with_one_spending_row(root, [provider_row('x1', 'msg_x1_a'), provider_row('x1', 'msg_x1_b', cost_usd=0.005)])
        report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['provider_rows_with_no_spending_row'],
                         {'count': 1, 'list_cost_usd': 0.005, 'charged_usd': 0.0, 'rows_with_charge': 0, 'rows_without_list_cost': 0})

    def test_one_provider_row_and_one_spending_row_pair_as_before(self):
        root, gate = gateway_run(self)
        aside_block_with_one_spending_row(root, [provider_row('x1', 'msg_x1_a')])
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['provider_rows_with_no_spending_row']['count'], 0)

    def test_two_spending_rows_with_one_id_cover_two_provider_rows(self):
        root, gate = gateway_run(self)
        learn = E.learn_folders(root)[0]
        folder = aside_block_with_one_spending_row(root, [provider_row('x1', 'msg_x1_a'), provider_row('x1', 'msg_x1_b')])
        row = (folder / 'usage.jsonl').read_text()
        (folder / 'usage.jsonl').write_text(row + row)
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['provider_rows_with_no_spending_row']['count'], 0)


class SurplusSpendingRow(unittest.TestCase):
    """L2 (review of part J, finding 2): the pairing is one to one in both directions."""

    def two_spending_rows_one_provider_row(self, root):
        folder = aside_block_with_one_spending_row(root, [provider_row('x1', 'msg_x1_a')])
        row = json.loads((folder / 'usage.jsonl').read_text())
        row['list_cost_usd'] = 0.004
        row[C.SETTINGS_FIELD] = {'model': 'synthetic-fixture', 'via': 'gem'}      # the ladder's spending row names the route it asked for
        (folder / 'usage.jsonl').write_text(json.dumps(row) + '\n' + json.dumps(row) + '\n')
        return folder

    def test_in_a_set_aside_block_the_extra_spending_row_is_counted_and_costed(self):
        from protocol import analysis3 as A
        root, gate = gateway_run(self)
        self.two_spending_rows_one_provider_row(root)
        report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['spending_rows_with_no_provider_row'], {'count': 1, 'list_cost_usd': 0.004, 'rows_without_list_cost': 0})
        self.assertEqual(report['provider_rows_with_no_spending_row']['count'], 0)
        result = A.analyse_snapshot(snap, n_boot=30)
        self.assertEqual(result['secondary']['spend']['learning_blocks_set_aside']['spending_rows_with_no_provider_row']['count'], 1)
        self.assertIn('with no provider row of their own', '\n'.join(A.report_lines(result)))

    def test_in_a_kept_block_it_refuses(self):
        root, gate = gateway_run(self)
        learn = E.learn_folders(root)[0]
        rows = [json.loads(l) for l in (learn / 'usage.jsonl').read_text().splitlines()]
        rows[0][C.SETTINGS_FIELD] = {'model': 'synthetic-fixture', 'via': 'gem'}
        (learn / 'usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows + [rows[0]]))
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'], 'the gate accepted two spending rows for one provider row')
        # The gate's older check of duplicate spending rows in a kept block names it first; the pairing check refuses it too.
        self.assertTrue(any('duplicate usage call' in e or 'in a kept block have no provider row of their own' in e
                            for e in report['errors']), report['errors'])

    def test_an_unpriced_extra_row_is_counted_without_a_price(self):
        root, gate = gateway_run(self)
        folder = self.two_spending_rows_one_provider_row(root)
        a, b = (json.loads(l) for l in (folder / 'usage.jsonl').read_text().splitlines())
        b['list_cost_usd'] = None
        (folder / 'usage.jsonl').write_text(json.dumps(a) + '\n' + json.dumps(b) + '\n')
        report = V.validate(root, **gate)
        self.assertEqual(report['spending_rows_with_no_provider_row'], {'count': 1, 'list_cost_usd': 0.0, 'rows_without_list_cost': 1})

    def test_ordinary_runs_and_j2_are_unchanged(self):
        root, gate = gateway_run(self)
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['spending_rows_with_no_provider_row'], {'count': 0, 'list_cost_usd': 0.0, 'rows_without_list_cost': 0})


class SplitRoots(S.Split):
    """The scored path always goes through combine_roots: the count of unpriced unpaired rows adds up across the three roots."""

    def test_the_rows_without_a_list_cost_add_up_across_roots(self):
        for task, n in (('reach', 1), ('land', 2)):
            rows = [{'request_id': f'cut-{task}-{i}', 'via': 'anthropic', 'model': 'synthetic-fixture', 'status': 'timeout',
                     'message_id': None, 'charged_usd': None} for i in range(n)]
            rows.append({**rows[0], 'request_id': f'priced-{task}', 'status': 'end_turn', 'cost_usd': 0.002, 'message_id': None})
            G.LedgerPairing.aside_provider_rows(self, self.roots[task], rows)
        report, snap = self.load()
        self.assertTrue(report['ok'], report['errors'])
        merged = snap['gate']['provider_rows_with_no_spending_row']
        self.assertEqual(merged['rows_without_list_cost'], 3)
        self.assertEqual(merged['count'], 5)
        self.assertAlmostEqual(merged['list_cost_usd'], 0.004)


for _name in [n for n in dir(S.Split) if n.startswith('test_')]:
    setattr(SplitRoots, _name, None)


if __name__ == '__main__':
    unittest.main()
