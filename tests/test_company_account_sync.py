#!/usr/bin/env python
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
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
        self.account_template = POOL.get('account.account.template')
        self.company = POOL.get('company.company')
        self.config = POOL.get('account.configuration')
        self.currency = POOL.get('currency.currency')
        self.employee = POOL.get('company.employee')
        self.lang = POOL.get('ir.lang')
        self.party = POOL.get('party.party')
        self.tax = POOL.get('account.tax')
        self.tax_code = POOL.get('account.tax.code')
        self.user = POOL.get('res.user')

    def test0005views(self):
        'Test views'
        test_view('company_account_sync')

    def test0006depends(self):
        'Test depends'
        test_depends()

    def create_chart(self, company):
        user = self.user(USER)
        self.user.write([user], {
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
                ])
        payable, = self.account.search([
                ('kind', '=', 'payable'),
                ('company', '=', company.id),
                ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def test0010_sync(self):
        '''
        Test user company
        '''
        with Transaction().start(DB_NAME, USER,
                context=CONTEXT) as transaction:
            currency1, = self.currency.search([], limit=1)

            main_company, = self.company.search([
                    ('rec_name', '=', 'Dunder Mifflin'),
                    ], limit=1)

            party1, = self.party.create([{
                        'name': 'Dunder Mifflin First Branch',
                        }])
            company1, = self.company.create([{
                        'party': party1.id,
                        'parent': main_company.id,
                        'currency': currency1.id,
                        }])

            party2, = self.party.create([{
                        'name': 'Dunder Mifflin Second Branch',
                        }])
            company2, = self.company.create([{
                        'party': party2.id,
                        'parent': main_company.id,
                        'currency': currency1.id,
                        }])
            user = self.user(USER)
            self.user.write([user], {
                    'main_company': main_company.id,
                    'company': main_company.id,
                    })
            CONTEXT.update(self.user.get_preferences(context_only=True))

            self.create_chart(company1)
            original_accounts = self.account.search([])
            #Create chart for other company
            self.create_chart(company2)
            accounts = self.account.search([])
            self.assertEqual(len(accounts), len(original_accounts))
            #Enable syncronization
            config = self.config(1)
            config.sync_companies = True
            config.save()
            self.user.write([user], {
                    'main_company': main_company.id,
                    'company': main_company.id,
                    })
            CONTEXT.update(self.user.get_preferences(context_only=True))
            #All accounts must have the link defined.
            accounts = self.account.search([])
            company_accounts = {}
            links = {}
            for account in accounts:
                self.assertIsNotNone(account.sync_link)
                if not account.company in company_accounts:
                    company_accounts[account.company] = []
                if not account.sync_link in links:
                    links[account.sync_link] = 0
                company_accounts[account.company].append(account)
                links[account.sync_link] += 1
            for _, link_count in links.iteritems():
                self.assertEqual(link_count, 3)
            #Ensure codes are synced
            first, second = self.account.search([
                    ('name', '=', 'Minimal Account Chart'),
                    ('company', 'in', [company1, company2]),
                    ])
            #Modify first account and test it gets modified on other company
            first.note = 'Modified'
            first.save()
            second = self.account(second.id)
            self.assertEqual(first.note, second.note)

            revenue,  = self.account.search([
                    ('company', '=', company1.id),
                    ('kind', '=', 'revenue'),
                    ])
            new_revenue, = self.account.copy([revenue], {
                    'code': '40',
                    'name': 'New revenue',
                    })
            self.assertIsNotNone(new_revenue.sync_link)
            self.assertNotEqual(new_revenue.sync_link, revenue.sync_link)
            account, = self.account.search([
                    ('code', '=', '40'),
                    ('company', '=', company2.id),
                    ])
            self.assertEqual(new_revenue.name, account.name)
            #Check correct types and parents
            self.assertEqual(new_revenue.sync_link, account.sync_link)
            #Modifiy it and check it has changed in the other company
            account.note = 'Modified on company2'
            account.save()

            new_revenue = self.account(new_revenue.id)
            self.assertEqual(new_revenue.note, account.note)
            #Activate transslations and change the name for one account
            #in on language
            lang_es, = self.lang.search([
                    ('code', '=', 'es_ES'),
                    ])
            lang_es.translatable = True
            lang_es.save()
            with transaction.set_context(language=lang_es.code):
                new_revenue = self.account(new_revenue.id)
                new_revenue.name = 'Nombre en castellano'
                new_revenue.save()

            with transaction.set_context(language='en_US'):
                new_revenue = self.account(new_revenue.id)
                account = self.account(account.id)
                self.assertEqual(new_revenue.name, 'New revenue')
                self.assertEqual(account.name, 'New revenue')
            with transaction.set_context(language=lang_es.code):
                new_revenue = self.account(new_revenue.id)
                account = self.account(account.id)
                self.assertEqual(new_revenue.name, 'Nombre en castellano')
                self.assertEqual(account.name, 'Nombre en castellano')

            #Delete new revenue account and check deleted in all companies
            self.account.delete([new_revenue])
            self.assertEqual(self.account.search([
                        ('code', '=', '40'),
                        ]), [])
            #TODO: Create a tax and link it to an account. Check it gets sync
            with transaction.set_context(company=company1.id):
                account_tax, = self.account.search([
                        ('kind', '=', 'other'),
                        ('name', '=', 'Main Tax'),
                        ])
                (invoice_base, invoice_tax, credit_note_base,
                    credit_note_tax) = self.tax_code.create([{
                                'name': 'invoice base',
                                },
                            {
                                'name': 'invoice tax',
                                },
                            {
                                'name': 'credit note base',
                                },
                            {
                                'name': 'credit note tax',
                            }])
                tax1, = self.tax.create([{
                            'name': 'Tax 1',
                            'description': 'Tax 1',
                            'type': 'percentage',
                            'rate': Decimal('.10'),
                            'invoice_account': account_tax.id,
                            'credit_note_account': account_tax.id,
                            'invoice_base_code': invoice_base.id,
                            'invoice_tax_code': invoice_tax.id,
                            'credit_note_base_code': credit_note_base.id,
                            'credit_note_tax_code': credit_note_tax.id,
                            }])
                account_tax.taxes = [tax1]
                account_tax.save()
            with transaction.set_user(0):
                self.assertEqual(len(self.tax_code.search([])), 12)
                self.assertEqual(len(self.tax.search([])), 3)
                tax_accounts = self.account.search([
                            ('kind', '=', 'other'),
                            ('name', '=', 'Main Tax'),
                            ])
                self.assertEqual(len(tax_accounts), 3)
                for account in tax_accounts:
                    tax, = account.taxes
                    self.assertEqual(tax.name, tax1.name)


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.company.tests import test_company
    for test in test_company.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            CompanyAccountSyncTestCase))
    return suite
