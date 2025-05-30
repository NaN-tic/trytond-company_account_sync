
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction

from trytond.modules.company.tests import create_company, set_company, CompanyTestMixin
from trytond.modules.account.tests import create_chart


class CompanyAccountSyncTestCase(CompanyTestMixin, ModuleTestCase):
    'Test CompanyAccountSync module'
    module = 'company_account_sync'

    def syncronize(self):
        pool = Pool()
        SyncronizeWizard = pool.get('account.chart.syncronize', type='wizard')
        AccountTemplate = pool.get('account.account.template')
        Company = pool.get('company.company')
        companies = Company.search([])
        for company in companies:
            with set_company(company):
                session_id, _, _ = SyncronizeWizard.create()
                syncronize = SyncronizeWizard(session_id)
                account_template, = AccountTemplate.search([
                        ('parent', '=', None),
                        ('name', '=', 'Universal Chart of Accounts'),
                        ])
                syncronize.start.account_template = account_template
                syncronize.start.companies = [company]
                syncronize.transition_syncronize()

    @with_transaction()
    def test0010_sync(self):
        '''
        Test user company
        '''
        pool = Pool()
        Account = pool.get('account.account')
        AccountTemplate = pool.get('account.account.template')
        User = pool.get('res.user')

        # Create Company
        main_company = create_company()

        main_company_user = User()
        main_company_user.name = 'Main Company'
        main_company_user.login = 'main'
        main_company_user.companies = [main_company]
        main_company_user.company = main_company
        main_company_user.save()

        main_company.intercompany_user = main_company_user
        main_company.save()

        with set_company(main_company):
            create_chart(main_company)

        account0, = Account.search([
                ('parent', '=', None), # Universal Chart of Accounts
                ('company', '=', main_company),
                ])

        # Create Company1
        company1 = create_company(name='Dunder Mifflin First Branch')
        company1.save()

        company1_user = User()
        company1_user.name = 'Company 1'
        company1_user.login = 'company1'
        company1_user.companies = [company1]
        company1_user.company = company1
        company1_user.save()

        company1.intercompany_user = company1_user
        company1.save()

        with set_company(company1):
            create_chart(company1)

        account1, = Account.search([
                ('parent', '=', None), # Universal Chart of Accounts
                ('company', '=', company1),
                ])
        revenue1, = Account.search([
                ('company', '=', company1),
                ('type.revenue', '=', True),
                ('closed', '=', False),
                ], limit=1)

        # Create Company2
        company2 = create_company(name='Dunder Mifflin Second Branch')
        company2.save()

        company2_user = User()
        company2_user.name = 'Company 2'
        company2_user.login = 'company2'
        company2_user.companies = [company2]
        company2_user.company = company2
        company2_user.save()

        company2.intercompany_user = company2_user
        company2.save()

        with set_company(company2):
            create_chart(company2)

        account2, = Account.search([
                ('parent', '=', None), # Universal Chart of Accounts
                ('company', '=', company2),
                ])

        # Syncronize
        self.syncronize()

        with set_company(main_company):
            # All accounts must have the link defined.
            company_accounts = {}
            links = {}
            for account in [account0, account1, account2]:
                self.assertIsNotNone(account.template)
                if account.template not in links:
                    links[account.template] = 0
                company_accounts[account.company] = account
                links[account.template] += 1
            for _, link_count in links.items():
                self.assertEqual(link_count, 3)

        # Ensure codes are synced
        # Modify first account and test it gets modified on other company
        template, = AccountTemplate.search([
                ('name', '=', 'Universal Chart of Accounts'),
                ])
        template.code = '0'
        template.save()
        self.syncronize()

        with set_company(company1):
            account1 = Account(account1)
            code1 = account1.code
            self.assertEqual(code1, '0')
        with set_company(company2):
            account2 = Account(account2)
            code2 = account2.code
            self.assertEqual(code2, code1)

        # Ensure new accounts in template are synced
        revenue, = AccountTemplate.search([
                ('type.revenue', '=', True),
                ('closed', '=', False),
                ], limit=1)
        new_revenue, = AccountTemplate.copy([revenue], {
                'code': '40',
                'name': 'New revenue',
                })
        self.syncronize()

        for company in company_accounts:
            with set_company(company):
                account, = Account.search([
                        ('code', '=', '40'),
                        ('company', '=', company),
                        ])
                self.assertEqual(new_revenue.name, account.name)
                self.assertEqual(new_revenue.code, account.code)
                self.assertEqual(account.template.id, new_revenue.id)


del ModuleTestCase
