#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button

__all__ = ['SyncronizeChartStart', 'SyncronizeChartSucceed', 'SyncronizeChart']
__metaclass__ = PoolMeta


class SyncronizeChartStart(ModelView):
    'Syncornize Account Chart'
    __name__ = 'account.chart.syncronize.start'
    account_template = fields.Many2One('account.account.template',
        'Account Template', required=True,
        domain=[
            ('parent', '=', None),
            ])
    companies = fields.Many2Many('company.company', None, None, 'Companies',
        required=True)

    @classmethod
    def default_account_template(cls):
        pool = Pool()
        Template = pool.get('account.account.template')
        templates = Template.search(cls.account_template.domain)
        if len(templates) == 1:
            return templates[0].id

    @staticmethod
    def default_companies():
        pool = Pool()
        Company = pool.get('company.company')
        return [x.id for x in Company.search([])]


class SyncronizeChartSucceed(ModelView):
    'Syncronize Account Chart Succeed'
    __name__ = 'account.chart.syncronize.succeed'


class SyncronizeChart(Wizard):
    'Syncronize Chart'
    __name__ = 'account.chart.syncronize'
    start = StateView('account.chart.syncronize.start',
        'company_account_sync.syncronize_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'syncronize', 'tryton-ok', default=True),
            ])
    syncronize = StateTransition()
    succeed = StateView('account.chart.syncronize.succeed',
        'company_account_sync.syncronize_succeed_view_form', [
            Button('Ok', 'end', 'tryton-ok', default=True),
            ])

    def transition_syncronize(self):
        pool = Pool()
        Account = pool.get('account.account')
        CreateChart = pool.get('account.create_chart', type='wizard')
        UpdateChart = pool.get('account.update_chart', type='wizard')
        template = self.start.account_template
        for company in self.start.companies:
            def set_defaults(form):
                field_names = set(form.__class__._fields)
                for key, value in form.default_get(field_names).iteritems():
                    setattr(form, key, value)
            transaction = Transaction()
            with transaction.set_context(company=company.id,
                    _check_access=False):
                roots = Account.search([
                        ('company', '=', company.id),
                        ('template', '=', template.id),
                        ])
                if roots:
                    root, = roots
                    session_id, _, _ = UpdateChart.create()
                    update = UpdateChart(session_id)
                    set_defaults(update.start)
                    update.start.account = root
                    with transaction.set_user(0):
                        update.transition_update()
                    update.delete(session_id)
                else:
                    session_id, _, _ = CreateChart.create()
                    create = CreateChart(session_id)
                    create.account.company = company
                    create.account.account_template = template
                    set_defaults(create.account)
                    with transaction.set_user(0):
                        create.transition_create_account()
                    receivables = Account.search([
                            ('kind', '=', 'receivable'),
                            ('company', '=', company.id),
                            ], limit=1)
                    payables = Account.search([
                            ('kind', '=', 'payable'),
                            ('company', '=', company.id),
                            ], limit=1)
                    if receivables and payables:
                        receivable, = receivables
                        payable, = payables
                        create.properties.company = company
                        create.properties.account_receivable = receivable
                        create.properties.account_payable = payable
                        with transaction.set_user(0):
                            create.transition_create_properties()
                    create.delete(session_id)
        return 'succeed'