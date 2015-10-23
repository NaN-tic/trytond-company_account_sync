#!/usr/bin/env python
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_view, test_depends
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction


class CompanyAccountSyncTestCase(unittest.TestCase):
    'Test company_account_sync module'

    def setUp(self):
        trytond.tests.test_tryton.install_module('company_account_sync')
        self.account = POOL.get('account.account')
        self.account_create_chart = POOL.get('account.create_chart',
            type='wizard')
        self.syncronize_wizard = POOL.get('account.chart.syncronize',
            type='wizard')
        self.account_template = POOL.get('account.account.template')
        self.company = POOL.get('company.company')
        self.config = POOL.get('account.configuration')
        self.currency = POOL.get('currency.currency')
        self.party = POOL.get('party.party')
        self.user = POOL.get('res.user')

    def test0005views(self):
        'Test views'
        test_view('company_account_sync')

    def test0006depends(self):
        'Test depends'
        test_depends()

    def create_chart(self, company):
        user = self.user(USER)
        previous_company = user.company
        previous_main_company = user.main_company
        self.user.write([user], {
                'main_company': company.id,
                'company': company.id,
                })
        CONTEXT.update(self.user.get_preferences(context_only=True))
        account_template, = self.account_template.search([
                ('parent', '=', None),
                ])
        session_id, _, _ = self.account_create_chart.create()
        create_chart = self.account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()
        receivable, = self.account.search([
                ('kind', '=', 'receivable'),
                ('company', '=', company.id),
                ], limit=1)
        payable, = self.account.search([
                ('kind', '=', 'payable'),
                ('company', '=', company.id),
                ], limit=1)
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()
        self.user.write([user], {
                'main_company': (previous_main_company.id
                    if previous_main_company else None),
                'company': previous_company.id if previous_company else None,
                })
        CONTEXT.update(self.user.get_preferences(context_only=True))

    def syncronize(self):
        session_id, _, _ = self.syncronize_wizard.create()
        syncronize = self.syncronize_wizard(session_id)
        account_template, = self.account_template.search([
                ('parent', '=', None),
                ])
        syncronize.start.account_template = account_template
        syncronize.start.companies = self.company.search([])
        syncronize.transition_syncronize()

    def test0010_sync(self):
        '''
        Test user company
        '''
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            currency1, = self.currency.search([], limit=1)

            main_company, = self.company.search([
                    ('rec_name', '=', 'Dunder Mifflin'),
                    ], limit=1)
            self.create_chart(main_company)

            party1, = self.party.create([{
                        'name': 'Dunder Mifflin First Branch',
                        }])
            company1, = self.company.create([{
                        'party': party1.id,
                        'parent': main_company.id,
                        'currency': currency1.id,
                        }])
            self.create_chart(company1)

            party2, = self.party.create([{
                        'name': 'Dunder Mifflin Second Branch',
                        }])
            company2, = self.company.create([{
                        'party': party2.id,
                        'parent': main_company.id,
                        'currency': currency1.id,
                        }])
            self.create_chart(company2)

            companies = self.company.search([])
            user = self.user(USER)
            self.user.write([user], {
                    'main_company': main_company.id,
                    'company': main_company.id,
                    })
            CONTEXT.update(self.user.get_preferences(context_only=True))
            self.syncronize()
            #All accounts must have the link defined.
            accounts = self.account.search([])
            company_accounts = {}
            links = {}
            for account in accounts:
                self.assertIsNotNone(account.template)
                if not account.company in company_accounts:
                    company_accounts[account.company] = []
                if not account.template in links:
                    links[account.template] = 0
                company_accounts[account.company].append(account)
                links[account.template] += 1
            for _, link_count in links.iteritems():
                self.assertEqual(link_count, len(companies))
            #Ensure codes are synced
            first, second = self.account.search([
                    ('name', '=', 'Minimal Account Chart'),
                    ('company', 'in', [company1, company2]),
                    ])
            #Modify first account and test it gets modified on other company
            template = first.template
            template.code = '0'
            template.save()
            self.syncronize()
            first = self.account(first.id)
            second = self.account(second.id)
            self.assertEqual(first.code, '0')
            self.assertEqual(first.code, second.code)

            revenue,  = self.account.search([
                    ('company', '=', company1.id),
                    ('kind', '=', 'revenue'),
                    ])
            new_revenue, = self.account_template.copy([revenue.template], {
                    'code': '40',
                    'name': 'New revenue',
                    })
            self.syncronize()
            for company in companies:
                account, = self.account.search([
                        ('code', '=', '40'),
                        ('company', '=', company.id),
                        ])
                self.assertEqual(new_revenue.name, account.name)
                self.assertEqual(new_revenue.code, account.code)
                self.assertEqual(account.template.id, new_revenue.id)


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.company.tests import test_company
    for test in test_company.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            CompanyAccountSyncTestCase))
    return suite
